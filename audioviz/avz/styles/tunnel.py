"""Tunnel: infinite ring corridor, spectrum wrapped around the angle."""

from __future__ import annotations

import numpy as np

from ..features import Frame
from ..palettes import ramp
from ..postfx import PostConfig
from .base import Style, fract, line_glow, sample_spectrum

TWO_PI = 6.2831853


class Tunnel(Style):
    name = "tunnel"
    render_scale = 0.5
    stateful = False
    default_palette = "ice"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.r_safe = np.maximum(self.radius, 0.06).astype(np.float32)
        self.depth = (0.65 / self.r_safe).astype(np.float32)
        self.ang01 = ((self.angle / TWO_PI) + 0.5).astype(np.float32)
        self.center = np.exp(-(self.radius ** 2) * 22.0).astype(np.float32)

    def post_config(self) -> PostConfig:
        return PostConfig(bloom_threshold=0.5, bloom_intensity=1.05, bloom_sigma=6.0,
                          aberration=1.6, vignette=0.3, grain=0.016)

    def render(self, f: Frame) -> np.ndarray:
        # Travel speed follows energy; each beat shoves us a little further in.
        z = self.depth * 3.2 - (f.t * (1.4 + 2.4 * f.energy) + 0.30 * f.beat)
        # Twist the corridor with depth so it corkscrews rather than sliding.
        twist = self.ang01 + z * 0.035 + f.t * 0.02
        seg = fract(twist * 16.0)

        zf = fract(z)
        rings = line_glow(np.minimum(zf, 1.0 - zf), 0.05 + 0.05 * f.low_mid)
        ribs = line_glow(np.minimum(seg, 1.0 - seg), 0.035 + 0.05 * f.high)

        # Each angular slice is driven by its own band of the spectrum.
        spec = sample_spectrum(f.spectrum, fract(twist))
        spec = 0.35 + 1.25 * spec

        falloff = np.clip(self.r_safe * 1.5, 0.0, 1.0) ** 1.4
        struct = (rings * (0.75 + 0.9 * f.mid) + ribs * 0.55 * spec) * falloff

        col = ramp(self.pal, np.clip(0.35 + 0.45 * fract(z * 0.25) + 0.2 * f.brightness,
                                     0.0, 1.0))
        img = col * struct[..., None]

        # Light at the end of the tunnel, pumped by the kick.
        img += ramp(self.pal, np.float32(0.9)) * (self.center * (0.30 + 1.1 * f.bass))[..., None]
        # Dark walls so the rings read against something.
        img += ramp(self.pal, np.float32(0.08)) * (falloff * 0.5)[..., None]
        return img.astype(np.float32)
