#!/usr/bin/env python3
"""Render an audio-reactive music video.

    python3 render.py track.mp3 --style grid --out video.mp4

Run with --list to see the available styles and palettes.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from avz import palettes, pipeline, styles          # noqa: E402
from avz.analysis import analyze                     # noqa: E402
from avz.ffmpeg import FFmpegNotFound, find_ffmpeg   # noqa: E402

SIZE_PRESETS = {
    "square": (1080, 1080),
    "story": (1080, 1920),
    "wide": (1920, 1080),
    "hd": (1280, 720),
    "reel": (1080, 1350),
}


def parse_size(value: str) -> tuple[int, int]:
    if value in SIZE_PRESETS:
        return SIZE_PRESETS[value]
    if "x" in value:
        w, h = value.lower().split("x", 1)
        return int(w), int(h)
    raise argparse.ArgumentTypeError(
        f"bad size {value!r}: use WxH or one of {', '.join(SIZE_PRESETS)}"
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="render.py",
        description="Render a music video that reacts to an audio file.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  python3 render.py track.mp3\n"
            "  python3 render.py track.mp3 --style glitch --size story --out clip.mp4\n"
            "  python3 render.py track.mp3 --style mix --start 30 --duration 20\n"
            "  python3 render.py track.mp3 --style random --palette ember --seed 7\n"
        ),
    )
    p.add_argument("audio", nargs="?", help="input audio file (mp3, wav, m4a, flac, ogg...)")
    p.add_argument("--out", "-o", help="output mp4 (default: <audio>-<style>.mp4)")
    p.add_argument("--style", "-s", default="random",
                   help="style name, or 'random' / 'mix' (default: random)")
    p.add_argument("--palette", "-p", default=None,
                   help="palette name; default is per-style, random in mix mode")
    p.add_argument("--size", type=parse_size, default=SIZE_PRESETS["square"],
                   help="WxH or preset: " + ", ".join(SIZE_PRESETS) + " (default: square)")
    p.add_argument("--fps", type=float, default=30.0, help="frame rate (default: 30)")
    p.add_argument("--start", type=float, default=0.0, help="skip this many seconds of audio")
    p.add_argument("--duration", "-d", type=float, default=None,
                   help="render only this many seconds")
    p.add_argument("--seed", type=int, default=None,
                   help="random seed; same seed + same audio = identical video")
    p.add_argument("--workers", "-j", type=int, default=0,
                   help="parallel render processes (0 = auto; stateless styles only)")
    p.add_argument("--crf", type=int, default=21,
                   help="x264 quality, lower is better; 23 roughly halves the file (default: 21)")
    p.add_argument("--preset", default="medium", help="x264 speed preset (default: medium)")
    p.add_argument("--ffmpeg", default=None, help="path to the ffmpeg binary")
    p.add_argument("--stills", metavar="SEC[,SEC...]",
                   help="write PNG stills at these timestamps instead of a video")
    p.add_argument("--analyze-only", action="store_true",
                   help="print the audio analysis summary and exit")
    p.add_argument("--list", action="store_true", help="list styles and palettes and exit")
    p.add_argument("--quiet", "-q", action="store_true", help="suppress progress output")
    return p


def write_stills(ffmpeg: str, renderer: pipeline.FrameRenderer, timeline, seconds: list[float],
                 out_base: Path, width: int, height: int) -> list[Path]:
    # Trails and particle positions only exist if the frames before them were
    # rendered, so a stateful style needs a run-up to look like it will in the video.
    warmup = int(round(2.0 * timeline.fps)) if renderer.stateful else 0

    written = []
    for sec in seconds:
        idx = int(round(sec * timeline.fps))
        if not 0 <= idx < timeline.n_frames:
            print(f"  skipping {sec}s: outside the rendered range", file=sys.stderr)
            continue
        for warm in range(max(0, idx - warmup), idx):
            renderer.frame(warm)
        frame = renderer.frame(idx)
        path = out_base.with_name(f"{out_base.stem}-{sec:g}s.png")
        proc = subprocess.run(
            [ffmpeg, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
             "-s", f"{width}x{height}", "-i", "pipe:0", "-frames:v", "1", str(path)],
            input=frame.tobytes(), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.decode("utf-8", "replace"))
        written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.list:
        print("styles:   " + ", ".join(styles.names() + list(styles.META_STYLES)))
        print("palettes: " + ", ".join(sorted(palettes.PALETTES)))
        print("sizes:    " + ", ".join(SIZE_PRESETS))
        return 0

    if not args.audio:
        build_parser().error("an audio file is required (or pass --list)")

    audio = Path(args.audio)
    if not audio.exists():
        print(f"error: no such file: {audio}", file=sys.stderr)
        return 1

    try:
        ffmpeg = find_ffmpeg(args.ffmpeg)
    except FFmpegNotFound as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    known = set(styles.names()) | set(styles.META_STYLES)
    if args.style not in known:
        print(f"error: unknown style {args.style!r}; available: {', '.join(sorted(known))}",
              file=sys.stderr)
        return 1
    if args.palette and args.palette not in palettes.PALETTES:
        print(f"error: unknown palette {args.palette!r}; available: "
              f"{', '.join(sorted(palettes.PALETTES))}", file=sys.stderr)
        return 1

    seed = args.seed if args.seed is not None else int(time.time()) & 0xFFFF

    if not args.quiet:
        print(f"analysing {audio.name} ...", file=sys.stderr)
    t0 = time.monotonic()
    timeline = analyze(ffmpeg, str(audio), args.fps, start=args.start, duration=args.duration)

    if not args.quiet or args.analyze_only:
        print(f"  duration {timeline.duration:.1f}s  tempo {timeline.tempo:.1f} BPM  "
              f"{len(timeline.beat_times)} beats  {len(timeline.section_times)} sections  "
              f"({time.monotonic() - t0:.1f}s)", file=sys.stderr)
    if args.analyze_only:
        return 0

    plan = pipeline.build_plan(timeline, args.style, args.palette, seed)
    width, height = pipeline.align_size(args.size[0], args.size[1], plan)

    if not args.quiet:
        print(f"  plan: {pipeline.describe_plan(plan, timeline.fps)}", file=sys.stderr)
        print(f"  output {width}x{height} @ {args.fps:g}fps, seed {seed}", file=sys.stderr)

    if args.stills:
        seconds = [float(s) for s in args.stills.split(",")]
        base = Path(args.out) if args.out else audio.with_suffix(".png")
        renderer = pipeline.FrameRenderer(timeline, plan, width, height, seed)
        written = write_stills(ffmpeg, renderer, timeline, seconds, base, width, height)
        for path in written:
            print(path)
        return 0

    style_tag = plan[0].style if len(plan) == 1 else "mix"
    out = Path(args.out) if args.out else audio.with_name(f"{audio.stem}-{style_tag}.mp4")
    out.parent.mkdir(parents=True, exist_ok=True)

    workers = args.workers
    if workers <= 0:
        import os
        workers = max(1, min(8, (os.cpu_count() or 2)))

    t1 = time.monotonic()
    pipeline.render_video(
        ffmpeg, str(audio), str(out), timeline, plan, width, height, seed,
        audio_start=args.start, audio_duration=args.duration,
        workers=workers, crf=args.crf, preset=args.preset, quiet=args.quiet,
    )

    if not args.quiet:
        size_mb = out.stat().st_size / 1e6
        print(f"done in {time.monotonic() - t1:.1f}s -> {out} ({size_mb:.1f} MB)",
              file=sys.stderr)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
