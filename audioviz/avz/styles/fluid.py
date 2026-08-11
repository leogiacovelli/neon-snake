"""Fluid: domain-warped plasma. Soft, organic, no hard edges."""

from __future__ import annotations

import numpy as np

from ..features import Frame
from ..palettes import ramp
from ..postfx import PostConfig
from .base import Style, wave_noise


class Fluid(Style):
    name = "fluid"
    render_scale = 0.5
    stateful = False
    default_palette = "toxic"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Fixed random offsets decorrelate the warp layers from each other.
        off = self.rng.random(8).astype(np.float32) * 40.0
        self.off = off

    def post_config(self) -> PostConfig:
        return PostConfig(bloom_threshold=0.62, bloom_intensity=0.7, bloom_sigma=8.0,
                          aberration=0.8, vignette=0.45, grain=0.02, saturation=1.12,
                          exposure=0.95)

    def render(self, f: Frame) -> np.ndarray:
        o = self.off
        # Time runs slightly faster when the track is busy.
        t = f.t * (0.55 + 0.7 * f.energy)
        zoom = 2.4 - 0.5 * f.bass
        x = self.xx * zoom
        y = self.yy * zoom

        # Two rounds of domain warping: noise displaces the lookup of more noise.
        warp = 0.9 + 1.5 * f.low_mid + 0.6 * f.beat
        qx = wave_noise(x + o[0], y + o[1], t)
        qy = wave_noise(x + o[2], y + o[3], t * 1.1)
        rx = wave_noise(x + warp * 3.0 * qx + o[4], y + warp * 3.0 * qy + o[5], t * 0.8)
        ry = wave_noise(x + warp * 3.0 * qy + o[6], y - warp * 3.0 * qx + o[7], t * 0.9)
        val = wave_noise(x + warp * 4.0 * rx, y + warp * 4.0 * ry, t * 0.6)

        # Filaments: where the second warp field is strongest.
        fil = np.sqrt(rx * rx + ry * ry)

        # Capped short of the palette's white top stop: unbounded, the plasma
        # bleaches out and stops reading as a dark neon piece.
        pos = np.clip(0.42 + val * 0.55 + 0.18 * f.brightness - 0.10 * f.bass, 0.04, 0.82)
        img = ramp(self.pal, pos)

        # Bright veins riding on top, tied to the mids.
        vein = np.clip((fil - 0.30) / 0.45, 0.0, 1.0) ** 2.0
        img += ramp(self.pal, np.float32(0.88)) * (vein * (0.20 + 0.55 * f.mid))[..., None]

        # Whole-frame lift on transients keeps it from feeling like a lava lamp.
        img *= (0.50 + 0.45 * f.energy + 0.25 * f.onset)
        return img.astype(np.float32)
