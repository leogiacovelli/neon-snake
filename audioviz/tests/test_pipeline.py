"""Tests for the audio-reactive renderer.

Run with:  python3 -m pytest audioviz/tests -q

Tests that need ffmpeg are skipped when it isn't installed, so the suite still
runs on a bare checkout.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from avz import palettes, pipeline, styles                        # noqa: E402
from avz.features import N_SPECTRUM_BANDS, Frame, Timeline        # noqa: E402
from avz.ffmpeg import FFmpegNotFound, find_ffmpeg                # noqa: E402
from avz.postfx import PostChain, PostConfig, to_uint8, tonemap   # noqa: E402
from avz.styles.base import smoothstep                            # noqa: E402


def _ffmpeg_or_skip() -> str:
    try:
        return find_ffmpeg(None)
    except FFmpegNotFound:
        pytest.skip("ffmpeg not available")


def fake_timeline(n_frames: int = 90, fps: float = 30.0) -> Timeline:
    """A deterministic timeline, so style tests need no audio file."""
    rng = np.random.default_rng(0)
    t = np.arange(n_frames, dtype=np.float32) / fps
    scalars = {
        name: np.abs(np.sin(t * (1.0 + i))).astype(np.float32)
        for i, name in enumerate(
            ["energy", "bass", "low_mid", "mid", "high", "air", "onset", "beat",
             "beat_phase", "bar_phase", "brightness", "section_phase"]
        )
    }
    scalars["beat_index"] = (t * 2).astype(np.int32)
    scalars["section"] = np.zeros(n_frames, np.int32)
    return Timeline(
        fps=fps, n_frames=n_frames, duration=n_frames / fps, tempo=120.0,
        beat_times=np.arange(0, n_frames / fps, 0.5),
        section_times=np.array([0.0]),
        scalars=scalars,
        spectrum=rng.random((n_frames, N_SPECTRUM_BANDS)).astype(np.float32),
    )


# --------------------------------------------------------------------------
# palettes


def test_ramp_hits_the_end_stops():
    pal = palettes.stops("neon")
    assert np.allclose(palettes.ramp(pal, 0.0), pal[0])
    assert np.allclose(palettes.ramp(pal, 1.0), pal[-1])


def test_ramp_is_shaped_like_its_input():
    pal = palettes.stops("neon")
    assert palettes.ramp(pal, np.zeros((4, 5), np.float32)).shape == (4, 5, 3)
    assert palettes.ramp(pal, 0.5).shape == (3,)


def test_ramp_stays_in_gamut():
    pal = palettes.stops("ember")
    out = palettes.ramp(pal, np.linspace(-1.0, 2.0, 50))
    assert out.min() >= 0.0 and out.max() <= 1.0


def test_unknown_palette_is_rejected():
    with pytest.raises(KeyError):
        palettes.stops("chartreuse")


# --------------------------------------------------------------------------
# maths helpers


def test_smoothstep_handles_reversed_edges():
    """A reversed pair must invert the ramp, not collapse it.

    Clamping the denominator to a positive minimum silently turned every
    reversed-edge call into a step in the wrong direction.
    """
    x = np.array([0.0, 0.5, 1.0], np.float32)
    rising = smoothstep(0.0, 1.0, x)
    falling = smoothstep(1.0, 0.0, x)
    assert rising[0] == 0.0 and rising[-1] == 1.0
    assert falling[0] == 1.0 and falling[-1] == 0.0
    assert np.allclose(rising, 1.0 - falling)


def test_smoothstep_survives_equal_edges():
    out = smoothstep(0.5, 0.5, np.linspace(0.0, 1.0, 5))
    assert np.isfinite(out).all()


def test_tonemap_compresses_without_clipping_flat():
    """Bloom pushes values past 1.0; the roll-off must keep them apart.

    Only over the range bloom actually produces — far enough out, float32
    rounds the exponential to exactly 1.0, and that is fine.
    """
    x = np.array([0.5, 1.0, 2.0, 4.0], np.float32)
    out = tonemap(x, 1.15)
    assert (out <= 1.0).all()
    assert (np.diff(out) > 1e-3).all(), "highlights collapsed into one flat value"


def test_tonemap_never_exceeds_one():
    out = tonemap(np.array([0.0, 8.0, 64.0, 1e4], np.float32), 1.15)
    assert out.min() >= 0.0 and out.max() <= 1.0


# --------------------------------------------------------------------------
# styles


@pytest.mark.parametrize("name", styles.names())
def test_style_renders_sane_frames(name):
    cls = styles.get(name)
    factor = max(1, int(round(1.0 / cls.render_scale)))
    w = h = 128 // factor
    style = cls(w, h, palettes.stops(cls.default_palette), seed=1, tempo=120.0)
    tl = fake_timeline()

    for i in (0, 45, 89):
        img = style.render(tl.frame(i))
        assert img.shape == (h, w, 3), name
        assert img.dtype == np.float32, name
        assert np.isfinite(img).all(), f"{name} produced NaN/inf"
        assert img.min() >= -1e-3, name


@pytest.mark.parametrize("name", styles.names())
def test_style_output_is_not_blank(name):
    """Guards against a style that silently renders pure black."""
    cls = styles.get(name)
    factor = max(1, int(round(1.0 / cls.render_scale)))
    w = h = 128 // factor
    style = cls(w, h, palettes.stops(cls.default_palette), seed=1, tempo=120.0)
    tl = fake_timeline()

    # Stateful styles need a run-up before they have anything to show.
    for i in range(60):
        img = style.render(tl.frame(i))
    assert img.max() > 0.05, f"{name} rendered an effectively blank frame"


def test_stateless_styles_are_reproducible():
    """Parallel rendering depends on frame output being a pure function of index."""
    tl = fake_timeline()
    for name in styles.names():
        cls = styles.get(name)
        if cls.stateful:
            continue
        a = cls(64, 64, palettes.stops("neon"), seed=7, tempo=120.0).render(tl.frame(30))
        b = cls(64, 64, palettes.stops("neon"), seed=7, tempo=120.0).render(tl.frame(30))
        assert np.array_equal(a, b), f"{name} is not reproducible"


def test_particles_tolerates_a_time_jump():
    """Crossfades and stills can hand a stateful style a discontinuous t."""
    from avz.styles.particles import Particles

    tl = fake_timeline()
    style = Particles(64, 64, palettes.stops("vapor"), seed=2, tempo=120.0)
    style.render(tl.frame(0))
    img = style.render(tl.frame(89))          # 3 seconds later, no frames between
    assert np.isfinite(img).all()


# --------------------------------------------------------------------------
# post-processing


def test_post_chain_shape_and_range():
    chain = PostChain(64, 48, PostConfig(), seed=0)
    img = np.random.default_rng(0).random((48, 64, 3)).astype(np.float32) * 2.0
    out = chain.apply(img, energy=0.5, onset=0.5)
    assert out.shape == (48, 64, 3)
    assert np.isfinite(out).all()
    assert to_uint8(out).dtype == np.uint8


def test_bloom_only_adds_light():
    from avz.postfx import bloom

    img = np.zeros((64, 64, 3), np.float32)
    img[30:34, 30:34] = 1.0
    out = bloom(img, PostConfig(), 1.0)
    assert out.shape == img.shape
    assert (out >= img - 1e-5).all()
    # Light must have spread beyond the original square.
    assert out[20, 20].sum() > 0.0


# --------------------------------------------------------------------------
# planning


def test_single_style_plan_covers_every_frame():
    tl = fake_timeline()
    plan = pipeline.build_plan(tl, "grid", None, seed=1)
    assert len(plan) == 1
    assert plan[0].start == 0 and plan[0].end == tl.n_frames


def test_mix_plan_is_contiguous_and_complete():
    tl = fake_timeline(n_frames=900)
    tl.section_times = np.array([0.0, 8.0, 16.0, 24.0])
    plan = pipeline.build_plan(tl, "mix", None, seed=4)
    assert plan[0].start == 0
    assert plan[-1].end == tl.n_frames
    for a, b in zip(plan, plan[1:]):
        assert a.end == b.start, "plan has a gap or overlap"
        assert a.style != b.style, "mix repeated a style back to back"


def test_random_style_is_a_real_style():
    tl = fake_timeline()
    plan = pipeline.build_plan(tl, "random", None, seed=99)
    assert plan[0].style in styles.names()


def test_seed_determines_the_plan():
    tl = fake_timeline()
    a = pipeline.build_plan(tl, "random", None, seed=5)
    b = pipeline.build_plan(tl, "random", None, seed=5)
    assert [s.style for s in a] == [s.style for s in b]


def test_align_size_matches_each_styles_upscale_factor():
    tl = fake_timeline()
    for name in styles.names():
        plan = pipeline.build_plan(tl, name, None, seed=0)
        w, h = pipeline.align_size(1081, 1079, plan)
        factor = max(1, int(round(1.0 / styles.get(name).render_scale)))
        assert (w // factor) * factor == w and (h // factor) * factor == h
        assert w % 2 == 0 and h % 2 == 0, "yuv420p needs even dimensions"


def test_frame_renderer_returns_encodable_frames():
    tl = fake_timeline()
    plan = pipeline.build_plan(tl, "grid", "neon", seed=1)
    w, h = pipeline.align_size(128, 128, plan)
    renderer = pipeline.FrameRenderer(tl, plan, w, h, seed=1)
    frame = renderer.frame(10)
    assert frame.shape == (h, w, 3)
    assert frame.dtype == np.uint8


def test_crossfade_blends_between_segments():
    tl = fake_timeline(n_frames=300)
    plan = [pipeline.Segment(0, 150, "grid", "neon"),
            pipeline.Segment(150, 300, "fluid", "toxic")]
    renderer = pipeline.FrameRenderer(tl, plan, 64, 64, seed=1)
    solo = pipeline.FrameRenderer(tl, [pipeline.Segment(0, 300, "grid", "neon")],
                                  64, 64, seed=1)
    mid = renderer.frame(149)          # inside the crossfade window
    alone = solo.frame(149)
    assert not np.array_equal(mid, alone), "crossfade did not blend in the next style"


# --------------------------------------------------------------------------
# end to end


def test_render_produces_a_playable_mp4(tmp_path):
    ffmpeg = _ffmpeg_or_skip()
    audio = tmp_path / "demo.wav"
    subprocess.run(
        [sys.executable, str(ROOT / "make_demo_audio.py"), "--out", str(audio), "--bars", "2"],
        check=True, capture_output=True,
    )
    assert audio.exists()

    out = tmp_path / "out.mp4"
    result = subprocess.run(
        [sys.executable, str(ROOT / "render.py"), str(audio), "--style", "grid",
         "--size", "128x128", "--fps", "12", "--duration", "2", "--seed", "1",
         "--out", str(out), "--quiet"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert out.exists() and out.stat().st_size > 1000

    probe = subprocess.run([ffmpeg, "-v", "error", "-i", str(out), "-f", "null", "-"],
                           capture_output=True, text=True)
    assert probe.returncode == 0, probe.stderr
    assert probe.stderr.strip() == "", f"ffmpeg reported errors: {probe.stderr}"


def test_analysis_of_a_synthetic_track(tmp_path):
    """The analyser should find roughly the tempo it was given."""
    ffmpeg = _ffmpeg_or_skip()
    from avz.analysis import analyze

    audio = tmp_path / "demo.wav"
    subprocess.run(
        [sys.executable, str(ROOT / "make_demo_audio.py"), "--out", str(audio),
         "--bars", "8", "--bpm", "120"],
        check=True, capture_output=True,
    )

    tl = analyze(ffmpeg, str(audio), fps=30.0)
    assert tl.n_frames > 0
    assert tl.spectrum.shape == (tl.n_frames, N_SPECTRUM_BANDS)
    # Beat trackers commonly land on half or double time; accept those.
    assert min(abs(tl.tempo - m * 120.0) for m in (0.5, 1.0, 2.0)) < 12.0
    for name, values in tl.scalars.items():
        assert len(values) == tl.n_frames, name
        assert np.isfinite(values).all(), name

    frame = tl.frame(0)
    assert isinstance(frame, Frame)
    assert 0.0 <= frame.beat_phase <= 1.0
