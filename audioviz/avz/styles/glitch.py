"""Glitch: spectrum bars torn apart by slice displacement and channel splits."""

from __future__ import annotations

import numpy as np

from ..features import Frame
from ..palettes import ramp
from ..postfx import PostConfig
from .base import Style, fract, sample_spectrum, smoothstep

N_BARS = 56


class Glitch(Style):
    name = "glitch"
    render_scale = 1.0       # tearing wants crisp pixels, so render at full size
    stateful = False
    default_palette = "sunset"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Quantise columns into bars once; every frame just looks up heights.
        self.bar_index = np.floor(self.u * N_BARS).astype(np.int32)
        self.bar_pos = np.clip(self.bar_index / (N_BARS - 1.0), 0.0, 1.0).astype(np.float32)
        # Mirror the spectrum so low frequencies sit in the middle.
        self.bar_freq = np.abs(self.bar_pos - 0.5) * 2.0
        self.bar_gap = (fract(self.u * N_BARS) > 0.32).astype(np.float32)
        self.scanline = (0.82 + 0.18 * np.cos(self.v * self.h * 3.1416)).astype(np.float32)

    def post_config(self) -> PostConfig:
        return PostConfig(bloom_threshold=0.6, bloom_intensity=0.6, bloom_sigma=4.0,
                          aberration=0.0,       # this style does its own, harder
                          vignette=0.32, grain=0.020, saturation=1.15)

    def _base(self, f: Frame) -> np.ndarray:
        # A power curve exaggerates the differences between bands: mel levels
        # within one moment sit in a narrow range, which would otherwise draw
        # as a solid block rather than a spectrum.
        heights = sample_spectrum(f.spectrum, self.bar_freq) ** 2.4
        heights = 0.04 + 0.80 * heights
        half = heights * 0.5
        inside = (np.abs(self.v - 0.5) < half).astype(np.float32) * self.bar_gap

        # Colour by height and by position across the bar field.
        col = ramp(self.pal, np.clip(0.22 + 0.42 * heights + 0.10 * f.brightness, 0.0, 0.84))
        img = col * (inside * (0.60 + 0.45 * f.energy))[..., None]

        # Hot caps on the tips of the bars.
        cap = smoothstep(0.03, 0.0, np.abs(np.abs(self.v - 0.5) - half))
        img += ramp(self.pal, np.float32(0.92)) * (cap * inside * (0.5 + 0.9 * f.onset))[..., None]

        # Background wash so the frame isn't half empty on quiet passages.
        wash = 0.05 + 0.10 * fract(self.v * 3.0 - f.t * 0.25) + 0.10 * f.low_mid
        img += ramp(self.pal, np.clip(wash, 0.0, 1.0)) * 0.40

        # Rolling bright band, one sweep per bar of music.
        band = np.exp(-((self.v - fract(f.bar_phase)) ** 2) * 260.0)
        img += ramp(self.pal, np.float32(0.8)) * (band * (0.15 + 0.5 * f.high))[..., None]
        return img

    def _tear(self, img: np.ndarray, f: Frame, rng: np.random.Generator) -> np.ndarray:
        """Displace horizontal slices — the core of the look."""
        n = int(2 + 16 * f.onset)
        max_shift = int(self.w * (0.02 + 0.22 * f.onset))
        if max_shift < 1:
            return img
        for _ in range(n):
            y0 = int(rng.integers(0, self.h))
            height = int(rng.integers(4, max(6, self.h // 8)))
            y1 = min(self.h, y0 + height)
            shift = int(rng.integers(-max_shift, max_shift + 1))
            img[y0:y1] = np.roll(img[y0:y1], shift, axis=1)
        return img

    def _blocks(self, img: np.ndarray, f: Frame, rng: np.random.Generator) -> np.ndarray:
        """Solid/noise rectangles punched into the frame on strong hits."""
        n = int(6 * f.onset * f.energy)
        for _ in range(n):
            bw = int(rng.integers(self.w // 20, self.w // 4))
            bh = int(rng.integers(self.h // 60, self.h // 12))
            x0 = int(rng.integers(0, max(1, self.w - bw)))
            y0 = int(rng.integers(0, max(1, self.h - bh)))
            if rng.random() < 0.5:
                # Copy a block from elsewhere: datamosh-style smearing.
                sy = int(rng.integers(0, max(1, self.h - bh)))
                img[y0:y0 + bh, x0:x0 + bw] = img[sy:sy + bh, x0:x0 + bw]
            else:
                tint = ramp(self.pal, np.float32(rng.random()))
                noise = rng.random((bh, bw)).astype(np.float32)
                img[y0:y0 + bh, x0:x0 + bw] = tint * (0.4 + 0.9 * noise)[..., None]
        return img

    def render(self, f: Frame) -> np.ndarray:
        # Hold each tear pattern for two frames. Real datamosh artifacts
        # persist rather than re-rolling every frame, and re-randomising all
        # 30 times a second leaves the encoder nothing to predict — it was
        # costing three times the bitrate of any other style.
        rng = np.random.default_rng(self.seed * 7919 + f.index // 2)
        img = self._base(f)
        img = self._tear(img, f, rng)
        img = self._blocks(img, f, rng)

        # Hard RGB separation, scaled by the transient.
        split = int(self.w * 0.02 * f.onset) + int(2 * f.beat)
        if split > 0:
            img[..., 0] = np.roll(img[..., 0], split, axis=1)
            img[..., 2] = np.roll(img[..., 2], -split, axis=1)

        img *= self.scanline[..., None]

        # Full-frame inversion flash on the hardest hits only.
        if f.onset > 0.86 and f.beat > 0.8:
            img = np.clip(img, 0.0, 1.0)
            img = 1.0 - img
        return img.astype(np.float32)
