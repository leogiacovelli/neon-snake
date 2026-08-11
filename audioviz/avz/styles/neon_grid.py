"""Retrowave: perspective grid floor, slitted sun, star field."""

from __future__ import annotations

import numpy as np

from ..features import Frame
from ..palettes import ramp
from ..postfx import PostConfig
from .base import Style, fract, line_glow, smoothstep

HORIZON = 0.56
Z_DENSITY = 0.5     # grid lines per unit of depth
X_DENSITY = 1.6     # grid lines across, per unit of depth


def _dist_to_int(x: np.ndarray) -> np.ndarray:
    f = fract(x)
    return np.minimum(f, 1.0 - f)


class NeonGrid(Style):
    name = "grid"
    render_scale = 0.5
    stateful = False
    default_palette = "neon"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        rng = np.random.default_rng(self.seed + 17)
        # Static star field, only ever lit above the horizon.
        star = rng.random((self.h, self.w)).astype(np.float32)
        self.stars = np.clip((star - 0.9975) / 0.0025, 0.0, 1.0) ** 0.5
        self.star_phase = (rng.random((self.h, self.w)) * 6.283).astype(np.float32)
        self.sky_mask = (self.v < HORIZON).astype(np.float32)
        self.ground_mask = 1.0 - self.sky_mask
        # Depth of every ground pixel, clamped near the horizon where 1/d blows up.
        depth = 1.0 / np.maximum(self.v - HORIZON, 1e-3)
        self.depth = np.minimum(depth, 900.0).astype(np.float32)
        self.fade = np.exp(-self.depth * 0.05).astype(np.float32)
        # Screen-space size of one world unit, per axis. Dividing world distances
        # by these turns the grid into lines of constant on-screen thickness
        # instead of wedges that swell to fill the bottom of the frame.
        self.dz_du = (Z_DENSITY * self.depth ** 2).astype(np.float32)
        self.dx_du = (X_DENSITY * self.depth).astype(np.float32)
        # Lines converge past the pixel grid near the horizon; widening them with
        # depth trades a little softness for far less shimmer.
        self.line_w = (0.0035 * (1.0 + self.depth * 0.03)).astype(np.float32)

    def post_config(self) -> PostConfig:
        return PostConfig(bloom_threshold=0.5, bloom_intensity=1.0, bloom_sigma=5.0,
                          aberration=1.2, vignette=0.42, grain=0.018)

    def render(self, f: Frame) -> np.ndarray:
        t = f.t
        img = np.zeros((self.h, self.w, 3), np.float32)

        # --- sky -------------------------------------------------------
        sky_t = np.clip(self.v / HORIZON, 0.0, 1.0)
        sky = ramp(self.pal, 0.04 + 0.30 * sky_t ** 2 * (0.7 + 0.6 * f.energy))
        twinkle = 0.55 + 0.45 * np.sin(self.star_phase + t * 3.0)
        sky += (self.stars * twinkle * (0.5 + 0.9 * f.air))[..., None]
        img += sky * self.sky_mask[..., None]

        # --- sun -------------------------------------------------------
        sun_r = 0.24 + 0.035 * f.bass
        du = (self.u - 0.5) * (self.w / self.h)
        dv = self.v - (HORIZON - 0.20)
        sd = np.sqrt(du * du + dv * dv)
        disc = smoothstep(sun_r, sun_r - 0.015, sd)
        # Horizontal slits across the lower half of the disc.
        slit_pos = (dv + 0.18) * 22.0 - t * 0.8
        slit = smoothstep(0.20, 0.55, _dist_to_int(slit_pos) * 2.0)
        slit = np.where(dv > -0.10, slit, np.float32(1.0))
        sun_grad = ramp(self.pal, np.clip(0.88 - (dv + 0.22) * 1.35, 0.34, 0.95))
        img += sun_grad * (disc * slit * (0.85 + 0.4 * f.bass))[..., None] * self.sky_mask[..., None]

        # --- ground grid ----------------------------------------------
        # Constant scroll plus a forward kick on every beat.
        scroll = t * (1.1 + 1.7 * f.energy) + 0.22 * f.beat
        # World-space distance to the nearest line, converted to screen space.
        dz = _dist_to_int(self.depth * Z_DENSITY - scroll) / self.dz_du
        dx = _dist_to_int((self.u - 0.5) * self.depth * X_DENSITY) / self.dx_du
        lines_z = line_glow(dz, self.line_w)
        lines_x = line_glow(dx, self.line_w)
        grid = np.maximum(lines_z, lines_x * 0.9) * self.fade * self.ground_mask
        grid_col = ramp(self.pal, np.clip(0.60 + 0.30 * self.fade, 0.0, 1.0))
        img += grid_col * (grid * (0.9 + 1.3 * f.mid))[..., None]

        # Ground haze so the floor isn't pure black between the lines.
        haze = ramp(self.pal, 0.10 + 0.08 * self.fade)
        img += haze * (self.fade * self.ground_mask * (0.30 + 0.5 * f.low_mid))[..., None]

        # --- horizon bar ----------------------------------------------
        bar = line_glow(self.v - HORIZON, 0.010 + 0.012 * f.onset)
        img += ramp(self.pal, np.float32(0.92)) * (bar * (0.8 + 1.6 * f.onset))[..., None]

        return img
