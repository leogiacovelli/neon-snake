"""Frame plan, rendering loop and encoding orchestration."""

from __future__ import annotations

import math
import sys
import time
from dataclasses import dataclass

import numpy as np

from . import palettes, styles
from .encoder import VideoWriter
from .features import Timeline
from .postfx import PostChain, to_uint8, upscale

CROSSFADE = 0.5  # seconds blended between styles in `mix` mode


@dataclass
class Segment:
    """A stretch of frames rendered by one style/palette pairing."""

    start: int          # first frame (inclusive)
    end: int            # last frame (exclusive)
    style: str
    palette: str


def build_plan(timeline: Timeline, style: str, palette: str | None,
               seed: int) -> list[Segment]:
    """Decide which style paints which frames."""
    rng = np.random.default_rng(seed)
    n = timeline.n_frames

    if style == "random":
        style = styles.pick(rng)

    if style != "mix":
        pal = palette or styles.get(style).default_palette
        return [Segment(0, n, style, pal)]

    # `mix`: one style per structural section, never repeating back to back.
    bounds = [int(round(t * timeline.fps)) for t in timeline.section_times]
    bounds = sorted({max(0, min(n, b)) for b in bounds} | {0})
    edges = bounds + [n]

    plan: list[Segment] = []
    prev_style: str | None = None
    prev_pal: str | None = None
    for i in range(len(edges) - 1):
        start, end = edges[i], edges[i + 1]
        if end - start < int(timeline.fps * 2):
            # Too short to register as its own look; fold it into the previous one.
            if plan:
                plan[-1] = Segment(plan[-1].start, end, plan[-1].style, plan[-1].palette)
                continue
        s = styles.pick(rng, exclude=prev_style)
        p = palette or palettes.pick(rng, exclude=prev_pal)
        plan.append(Segment(start, end, s, p))
        prev_style, prev_pal = s, p

    return plan or [Segment(0, n, "grid", palette or "neon")]


def _lcm(a: int, b: int) -> int:
    return a * b // math.gcd(a, b)


def align_size(width: int, height: int, plan: list[Segment]) -> tuple[int, int]:
    """Snap output dimensions so every style's internal buffer upscales exactly.

    Also guarantees even dimensions, which yuv420p requires.
    """
    align = 2
    for seg in plan:
        factor = max(1, int(round(1.0 / styles.get(seg.style).render_scale)))
        align = _lcm(align, factor * 2)
    return (width // align) * align, (height // align) * align


class FrameRenderer:
    """Renders individual frames for a plan. Safe to construct inside a worker."""

    def __init__(self, timeline: Timeline, plan: list[Segment], width: int, height: int,
                 seed: int):
        self.timeline = timeline
        self.plan = plan
        self.width = width
        self.height = height
        self.seed = seed
        self._instances: dict[int, tuple[styles.Style, PostChain, int]] = {}
        self._xfade_frames = max(1, int(round(CROSSFADE * timeline.fps)))

    @property
    def stateful(self) -> bool:
        return any(styles.get(seg.style).stateful for seg in self.plan)

    def _instance(self, seg_idx: int) -> tuple[styles.Style, PostChain, int]:
        """Style, its post chain and its upscale factor — built once per segment."""
        if seg_idx not in self._instances:
            seg = self.plan[seg_idx]
            cls = styles.get(seg.style)
            factor = max(1, int(round(1.0 / cls.render_scale)))
            style = cls(self.width // factor, self.height // factor,
                        palettes.stops(seg.palette), seed=self.seed + seg_idx * 101,
                        tempo=self.timeline.tempo)
            post = PostChain(self.width, self.height, style.post_config(),
                             seed=self.seed + seg_idx)
            self._instances[seg_idx] = (style, post, factor)
        return self._instances[seg_idx]

    def _segment_at(self, index: int) -> int:
        for i, seg in enumerate(self.plan):
            if seg.start <= index < seg.end:
                return i
        return len(self.plan) - 1

    def _render_segment(self, seg_idx: int, frame) -> np.ndarray:
        style, post, factor = self._instance(seg_idx)
        img = style.render(frame)
        img = upscale(img, factor)
        return post.apply(img, energy=frame.energy, onset=frame.onset)

    def frame(self, index: int) -> np.ndarray:
        f = self.timeline.frame(index)
        seg_idx = self._segment_at(index)
        img = self._render_segment(seg_idx, f)

        # Crossfade into the next segment over the last CROSSFADE seconds.
        nxt = seg_idx + 1
        if nxt < len(self.plan):
            remaining = self.plan[seg_idx].end - index
            if 0 < remaining <= self._xfade_frames:
                alpha = 1.0 - remaining / self._xfade_frames
                alpha = alpha * alpha * (3.0 - 2.0 * alpha)   # smoothstep
                img = img * (1.0 - alpha) + self._render_segment(nxt, f) * alpha

        return to_uint8(img)


_WORKER: FrameRenderer | None = None


def _init_worker(timeline, plan, width, height, seed) -> None:
    global _WORKER
    _WORKER = FrameRenderer(timeline, plan, width, height, seed)


def _render_worker(index: int) -> np.ndarray:
    assert _WORKER is not None
    return _WORKER.frame(index)


def describe_plan(plan: list[Segment], fps: float) -> str:
    parts = [f"{seg.style}/{seg.palette} {seg.start / fps:.1f}-{seg.end / fps:.1f}s"
             for seg in plan]
    return "  |  ".join(parts)


def render_video(ffmpeg: str, audio_path: str, out_path: str, timeline: Timeline,
                 plan: list[Segment], width: int, height: int, seed: int,
                 audio_start: float = 0.0, audio_duration: float | None = None,
                 workers: int = 1, crf: int = 21, preset: str = "medium",
                 quiet: bool = False) -> None:
    n = timeline.n_frames
    renderer = FrameRenderer(timeline, plan, width, height, seed)
    use_pool = workers > 1 and not renderer.stateful

    started = time.monotonic()
    last_report = 0.0
    # Carriage-return redraws only make sense on a terminal; in a log they turn
    # into one enormous line, so fall back to sparse newline-terminated updates.
    interactive = sys.stderr.isatty()
    interval = 0.5 if interactive else 15.0

    def report(done: int, force: bool = False) -> None:
        nonlocal last_report
        now = time.monotonic()
        if quiet or (not force and now - last_report < interval):
            return
        if force and not interactive and last_report > 0.0 and done < n:
            return
        last_report = now
        elapsed = now - started
        rate = done / elapsed if elapsed > 0 else 0.0
        eta = (n - done) / rate if rate > 0 else 0.0
        if interactive:
            bar_len = 24
            filled = int(bar_len * done / max(n, 1))
            bar = "#" * filled + "-" * (bar_len - filled)
            sys.stderr.write(f"\r  [{bar}] {done}/{n} frames  {rate:5.1f} fps  eta {eta:5.1f}s")
        else:
            pct = 100.0 * done / max(n, 1)
            sys.stderr.write(f"  {pct:5.1f}%  {done}/{n} frames  {rate:.1f} fps  eta {eta:.0f}s\n")
        sys.stderr.flush()

    with VideoWriter(ffmpeg, out_path, width, height, timeline.fps, audio_path,
                     audio_start=audio_start, audio_duration=audio_duration,
                     crf=crf, preset=preset) as writer:
        if use_pool:
            import multiprocessing as mp

            ctx = mp.get_context("spawn")
            with ctx.Pool(workers, initializer=_init_worker,
                          initargs=(timeline, plan, width, height, seed)) as pool:
                for done, frame in enumerate(
                    pool.imap(_render_worker, range(n), chunksize=4), start=1
                ):
                    writer.write(frame)
                    report(done)
        else:
            for i in range(n):
                writer.write(renderer.frame(i))
                report(i + 1)
        report(n, force=True)

    if not quiet and interactive:
        sys.stderr.write("\n")
        sys.stderr.flush()
