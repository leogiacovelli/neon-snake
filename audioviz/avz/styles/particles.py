"""Particle swarm: curl-ish flow field, beat impulses, motion trails."""

from __future__ import annotations

import numpy as np
from scipy.ndimage import gaussian_filter

from ..features import Frame
from ..palettes import ramp
from ..postfx import PostConfig
from .base import Style, wave_noise

N_PARTICLES = 22000
#: Brightness of one particle splat. Trails accumulate over many frames, so this
#: is deliberately small — tuned so a busy frame's trail buffer peaks near 1.
SPLAT_GAIN = 0.30
#: The swarm covers most of the frame, so a linear mapping renders as flat haze.
#: Raising the trail to a power crushes the sparse tail and keeps the dense
#: filaments bright — contrast, rather than more light.
TRAIL_CONTRAST = 1.7
TRAIL_GAIN = 2.6


class Particles(Style):
    name = "particles"
    render_scale = 0.5
    stateful = True          # carries the simulation + trail buffer between frames
    default_palette = "vapor"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        rng = np.random.default_rng(self.seed + 5)
        self.aspect = self.w / self.h
        angle = rng.random(N_PARTICLES).astype(np.float32) * 6.2831853
        rad = np.sqrt(rng.random(N_PARTICLES).astype(np.float32)) * 0.9
        self.pos = np.stack([np.cos(angle) * rad * self.aspect,
                             np.sin(angle) * rad], axis=1).astype(np.float32)
        self.vel = (rng.standard_normal((N_PARTICLES, 2)) * 0.05).astype(np.float32)
        # A stable per-particle hue offset keeps the swarm from being one flat colour.
        self.hue = rng.random(N_PARTICLES).astype(np.float32)
        self.mass = (0.4 + 0.6 * rng.random(N_PARTICLES)).astype(np.float32)
        self.trail = np.zeros((self.h, self.w, 3), np.float32)
        self._prev_beat = 0.0
        self._last_t: float | None = None

    def post_config(self) -> PostConfig:
        return PostConfig(bloom_threshold=0.42, bloom_intensity=1.15, bloom_sigma=5.0,
                          aberration=1.0, vignette=0.45, grain=0.015)

    def _flow(self, x: np.ndarray, y: np.ndarray, f: Frame) -> tuple[np.ndarray, np.ndarray]:
        """Curl of a scalar noise field.

        A curl field is divergence-free, so particles never pile up into a blob;
        they stretch along filaments instead, which is what reads as motion.
        """
        scale = 1.9 + 1.1 * f.mid
        t = f.t * 0.35
        eps = np.float32(0.04)
        base = wave_noise(x * scale, y * scale, t)
        dx = wave_noise((x + eps) * scale, y * scale, t) - base
        dy = wave_noise(x * scale, (y + eps) * scale, t) - base
        return dy / eps, -dx / eps

    def _step(self, dt: float, f: Frame) -> None:
        x, y = self.pos[:, 0], self.pos[:, 1]
        r = np.sqrt(x * x + y * y) + 1e-5

        fx, fy = self._flow(x, y, f)
        speed = 0.35 + 0.85 * f.energy + 0.5 * f.high
        fx = fx * speed
        fy = fy * speed

        # Weak centring force so the swarm stays framed, plus a breathing term:
        # bass draws it in, air pushes it out.
        pull = -1.1 + 2.0 * f.bass - 1.1 * f.air
        fx += x / r * pull * 0.5
        fy += y / r * pull * 0.5

        # Advect towards the field rather than accumulating force, which keeps
        # the filaments crisp instead of letting particles overshoot.
        self.vel += (np.stack([fx, fy], axis=1) - self.vel) * min(1.0, dt * 6.0) \
            * self.mass[:, None]
        self.pos += self.vel * dt

        # Recycle anything that escapes the frame back into the core.
        out = (np.abs(self.pos[:, 0]) > self.aspect * 1.3) | (np.abs(self.pos[:, 1]) > 1.3)
        n_out = int(out.sum())
        if n_out:
            ang = self.rng.random(n_out).astype(np.float32) * 6.2831853
            rad = np.sqrt(self.rng.random(n_out).astype(np.float32)) * 0.7
            self.pos[out] = np.stack([np.cos(ang) * rad * self.aspect,
                                      np.sin(ang) * rad], axis=1)
            self.vel[out] *= 0.1

    def _burst(self, strength: float) -> None:
        """Radial kick on beat onsets."""
        x, y = self.pos[:, 0], self.pos[:, 1]
        r = np.sqrt(x * x + y * y) + 1e-5
        kick = strength * (2.4 / (1.0 + r * 2.0))
        self.vel[:, 0] += x / r * kick
        self.vel[:, 1] += y / r * kick

    def _splat(self, f: Frame) -> np.ndarray:
        speed = np.linalg.norm(self.vel, axis=1)
        # Colour by speed, nudged by each particle's own offset and the brightness.
        # Capped below 1.0: the top of a palette is white, and letting the fast
        # particles reach it turns every bright filament colourless.
        pos_in_ramp = np.clip(0.24 + speed * 0.12 + self.hue * 0.34 + 0.15 * f.brightness,
                              0.0, 0.86)
        colors = ramp(self.pal, pos_in_ramp)
        weight = (0.35 + 0.65 * self.mass) * (0.55 + 0.8 * f.energy)

        rng_y = [-1.0, 1.0]
        rng_x = [-self.aspect, self.aspect]
        frame = np.zeros((self.h, self.w, 3), np.float32)
        for c in range(3):
            hist, _, _ = np.histogram2d(
                self.pos[:, 1], self.pos[:, 0], bins=[self.h, self.w],
                range=[rng_y, rng_x], weights=colors[:, c] * weight,
            )
            frame[:, :, c] = hist.astype(np.float32)
        return gaussian_filter(frame, sigma=(1.3, 1.3, 0), mode="constant") * SPLAT_GAIN

    def render(self, f: Frame) -> np.ndarray:
        dt = 1.0 / 30.0 if self._last_t is None else f.t - self._last_t
        dt = float(np.clip(dt, 0.0, 0.1))     # survives seeks and style crossfades
        self._last_t = f.t

        if f.beat > 0.75 and self._prev_beat <= 0.75:
            self._burst(0.55 + 0.9 * f.energy)
        self._prev_beat = f.beat

        # Substep so fast particles don't tunnel through the flow field.
        for _ in range(2):
            self._step(dt * 0.5, f)

        # Slower decay leaves longer streaks; transients wipe them back.
        decay = float(np.exp(-dt * (1.5 + 3.0 * f.onset)))
        self.trail = self.trail * decay + self._splat(f)

        base = ramp(self.pal, np.float32(0.02 + 0.04 * f.energy)) * 0.5
        shaped = np.power(self.trail, TRAIL_CONTRAST) * TRAIL_GAIN
        return np.asarray(base, np.float32) + shaped
