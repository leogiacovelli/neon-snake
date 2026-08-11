"""Style base class plus the small bits of maths every style reaches for."""

from __future__ import annotations

import numpy as np

from ..features import Frame
from ..postfx import PostConfig


class Style:
    """A visual generator.

    Subclasses implement :meth:`render`, returning an ``(h, w, 3)`` float32
    image in 0..1 at the style's internal resolution. Everything after that —
    upscaling, bloom, grain — is handled by the pipeline.
    """

    name: str = "base"
    #: Fraction of the output resolution to render at. Smooth, low-frequency
    #: styles look identical at 0.5 and render four times faster.
    render_scale: float = 0.5
    #: Stateful styles carry a simulation between frames, so they must be
    #: rendered in order in a single process (no parallel workers).
    stateful: bool = False
    #: Palette used when the caller doesn't pick one.
    default_palette: str = "neon"

    def __init__(self, width: int, height: int, palette: np.ndarray,
                 seed: int = 0, tempo: float = 120.0):
        self.w = width
        self.h = height
        self.pal = palette
        self.rng = np.random.default_rng(seed)
        self.seed = seed
        self.tempo = tempo
        # Normalised coordinates: y in [-1, 1], x scaled by aspect ratio.
        aspect = width / height
        ys = np.linspace(-1.0, 1.0, height, dtype=np.float32)
        xs = np.linspace(-aspect, aspect, width, dtype=np.float32)
        self.yy, self.xx = np.meshgrid(ys, xs, indexing="ij")
        self.radius = np.sqrt(self.xx ** 2 + self.yy ** 2).astype(np.float32)
        self.angle = np.arctan2(self.yy, self.xx).astype(np.float32)
        # Screen-space 0..1 coordinates.
        self.u = ((self.xx / aspect) * 0.5 + 0.5).astype(np.float32)
        self.v = (self.yy * 0.5 + 0.5).astype(np.float32)

    def post_config(self) -> PostConfig:
        return PostConfig()

    def render(self, f: Frame) -> np.ndarray:  # pragma: no cover - abstract
        raise NotImplementedError


def smoothstep(edge0: float, edge1: float, x: np.ndarray) -> np.ndarray:
    """Hermite interpolation between the edges.

    `edge1 < edge0` is legal and inverts the ramp, so guard the denominator
    against zero without clamping away its sign.
    """
    den = edge1 - edge0
    if abs(den) < 1e-6:
        den = 1e-6 if den >= 0 else -1e-6
    t = np.clip((x - edge0) / den, 0.0, 1.0)
    return (t * t * (3.0 - 2.0 * t)).astype(np.float32)


def fract(x: np.ndarray) -> np.ndarray:
    return (x - np.floor(x)).astype(np.float32)


def line_glow(distance: np.ndarray, width: float) -> np.ndarray:
    """Soft falloff around a signed distance — a neon line rather than a hard edge."""
    return (width / (width + np.abs(distance) * 8.0 + 1e-6)).astype(np.float32)


def wave_noise(x: np.ndarray, y: np.ndarray, t: float) -> np.ndarray:
    """Cheap smooth pseudo-noise in -1..1, built from incommensurate sines.

    Not real Perlin noise, but it is fully vectorised, dependency-free and
    visually indistinguishable once it has been domain-warped a couple of times.
    """
    return (
        np.sin(x * 1.13 + t * 0.71)
        + np.sin(y * 1.47 - t * 0.53)
        + np.sin((x + y) * 0.79 + t * 0.37)
        + np.sin((x - y) * 1.31 - t * 0.61)
    ).astype(np.float32) * 0.25


def sample_spectrum(spectrum: np.ndarray, pos: np.ndarray) -> np.ndarray:
    """Interpolate a per-frame spectrum at fractional band positions in 0..1."""
    n = len(spectrum)
    idx = np.clip(np.asarray(pos, np.float32), 0.0, 1.0) * (n - 1)
    return np.interp(idx, np.arange(n, dtype=np.float32), spectrum).astype(np.float32)
