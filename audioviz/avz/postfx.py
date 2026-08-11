"""Post-processing shared by every style: bloom, aberration, vignette, grain.

This is what makes procedural output look like it was graded rather than
plotted. Styles render clean colour; the glow happens here.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import gaussian_filter


@dataclass
class PostConfig:
    bloom_threshold: float = 0.55
    bloom_intensity: float = 0.85
    bloom_sigma: float = 6.0
    aberration: float = 1.5     # pixels of R/B separation at full energy
    vignette: float = 0.35
    grain: float = 0.02
    saturation: float = 1.06
    gamma: float = 0.95
    exposure: float = 1.15      # tone-map strength; highlights roll off, never clip flat


def upscale(img: np.ndarray, factor: int) -> np.ndarray:
    """Nearest-neighbour upscale followed by a light blur.

    Styles render at a fraction of the output size (their content is smooth, so
    the difference is invisible) and this brings them back up cheaply.
    """
    if factor <= 1:
        return img
    big = img.repeat(factor, axis=0).repeat(factor, axis=1)
    return gaussian_filter(big, sigma=(factor * 0.4, factor * 0.4, 0), mode="nearest")


def _half(a: np.ndarray) -> np.ndarray:
    """2x box downsample — four-tap average, no interpolation machinery."""
    h, w = (a.shape[0] // 2) * 2, (a.shape[1] // 2) * 2
    a = a[:h, :w]
    return (a[0::2, 0::2] + a[1::2, 0::2] + a[0::2, 1::2] + a[1::2, 1::2]) * 0.25


def _double(a: np.ndarray, sigma: float) -> np.ndarray:
    """2x upsample, smoothed just enough to erase the block edges."""
    big = a.repeat(2, axis=0).repeat(2, axis=1)
    return gaussian_filter(big, sigma=(sigma, sigma, 0), mode="nearest")


def bloom(img: np.ndarray, cfg: PostConfig, amount: float = 1.0) -> np.ndarray:
    """Two-scale glow around the brightest parts of the frame.

    The blur runs at quarter resolution. A gaussian wide enough to bloom is a
    low-pass filter by definition, so nothing survives downsampling that the
    blur wouldn't have destroyed anyway — and it costs about a sixth as much,
    which matters because this is the most expensive step in the pipeline.
    """
    if cfg.bloom_intensity <= 0 or amount <= 0:
        return img
    # Channel-wise maximum written out: `img.max(axis=2)` reduces along the
    # short, strided axis and is an order of magnitude slower.
    lum = np.maximum(np.maximum(img[..., 0], img[..., 1]), img[..., 2])
    mask = np.clip((lum - cfg.bloom_threshold) / max(1.0 - cfg.bloom_threshold, 1e-6), 0.0, 1.0)
    bright = img * mask[..., None]

    quarter = _half(_half(bright))
    s = cfg.bloom_sigma / 4.0
    glow = gaussian_filter(quarter, sigma=(s, s, 0), mode="nearest")
    glow += 0.6 * gaussian_filter(quarter, sigma=(s * 2.6, s * 2.6, 0), mode="nearest")

    # Smooth on the way up, then a plain pixel-doubling for the last step: the
    # glow is already blurred well past a two-pixel block by that point.
    glow = _double(glow, 1.4).repeat(2, axis=0).repeat(2, axis=1)
    # Guard against the odd-size crop in _half leaving the glow a pixel short.
    gh, gw = glow.shape[:2]
    if (gh, gw) != img.shape[:2]:
        pad = ((0, max(0, img.shape[0] - gh)), (0, max(0, img.shape[1] - gw)), (0, 0))
        glow = np.pad(glow[:img.shape[0], :img.shape[1]], pad, mode="edge")
    return img + glow * (cfg.bloom_intensity * amount)


def aberration(img: np.ndarray, pixels: float) -> np.ndarray:
    """Split red and blue horizontally — cheap lens-fringe / VHS cue."""
    shift = int(round(pixels))
    if shift <= 0:
        return img
    out = img.copy()
    out[..., 0] = np.roll(img[..., 0], shift, axis=1)
    out[..., 2] = np.roll(img[..., 2], -shift, axis=1)
    return out


def make_vignette(h: int, w: int, amount: float) -> np.ndarray:
    if amount <= 0:
        return np.ones((h, w, 1), np.float32)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    xx = (xx / max(w - 1, 1)) * 2.0 - 1.0
    yy = (yy / max(h - 1, 1)) * 2.0 - 1.0
    r = np.sqrt(xx * xx + yy * yy) / np.sqrt(2.0)
    return (1.0 - amount * np.clip(r, 0.0, 1.0) ** 2.2).astype(np.float32)[..., None]


def tonemap(img: np.ndarray, exposure: float) -> np.ndarray:
    """Exponential roll-off.

    Bloom happily pushes values well above 1.0; clipping there turns every glow
    into a flat white blob. This compresses instead, so bright areas keep their
    hue and only the very hottest cores reach white.
    """
    return 1.0 - np.exp(-np.clip(img, 0.0, None) * exposure)


def saturate(img: np.ndarray, amount: float) -> np.ndarray:
    if abs(amount - 1.0) < 1e-3:
        return img
    lum = (img[..., 0] * 0.2126 + img[..., 1] * 0.7152 + img[..., 2] * 0.0722)[..., None]
    return lum + (img - lum) * amount


class PostChain:
    """Reusable post pipeline — caches the vignette mask across frames."""

    def __init__(self, width: int, height: int, cfg: PostConfig, seed: int = 0):
        self.cfg = cfg
        self._vignette = make_vignette(height, width, cfg.vignette)
        self._rng = np.random.default_rng(seed)
        self._shape = (height, width)

    def apply(self, img: np.ndarray, energy: float = 0.0, onset: float = 0.0) -> np.ndarray:
        cfg = self.cfg
        img = bloom(img, cfg, 1.0 + 0.5 * energy)
        if cfg.aberration > 0:
            img = aberration(img, cfg.aberration * (0.35 + 0.65 * onset))
        img = img * self._vignette
        img = tonemap(img, cfg.exposure)
        img = saturate(img, cfg.saturation)
        if cfg.gamma != 1.0:
            img = np.power(np.clip(img, 0.0, None), cfg.gamma)
        if cfg.grain > 0:
            noise = self._rng.standard_normal(self._shape).astype(np.float32)
            img = img + noise[..., None] * cfg.grain
        return img


def to_uint8(img: np.ndarray) -> np.ndarray:
    return (np.clip(img, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
