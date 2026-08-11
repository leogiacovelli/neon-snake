"""Colour ramps. Each palette is a list of hex stops, sampled with `ramp()`."""

from __future__ import annotations

import numpy as np

PALETTES: dict[str, list[str]] = {
    # Deep blue -> magenta -> cyan: the house look, matches Neon Snake.
    "neon":    ["#05010f", "#2a0a5e", "#b31cff", "#ff2fb0", "#22e7ff", "#eafcff"],
    "vapor":   ["#0b0221", "#4b1d8f", "#ff6ad5", "#ffa8e2", "#8be9fd", "#fdfdff"],
    "acid":    ["#040d04", "#0d4d1f", "#3fe33f", "#c8ff3f", "#f5ff9b", "#ffffff"],
    "ember":   ["#0a0300", "#4a1002", "#c8300a", "#ff7a18", "#ffcf5c", "#fff4d6"],
    "ice":     ["#01060f", "#0b2a52", "#1f7ac9", "#59d8ff", "#b9f2ff", "#ffffff"],
    "sunset":  ["#100320", "#5c1160", "#c02a6b", "#ff6b3d", "#ffc36b", "#fff0c9"],
    "mono":    ["#000000", "#1a1a1a", "#4d4d4d", "#9c9c9c", "#e0e0e0", "#ffffff"],
    "toxic":   ["#0c0016", "#3d0a52", "#7b12a8", "#12d9a0", "#a6ff4d", "#f2ffd6"],
}

DEFAULT_PALETTE = "neon"


def _hex_to_rgb(h: str) -> tuple[float, float, float]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))  # type: ignore[return-value]


def stops(name: str) -> np.ndarray:
    """(n, 3) float32 array of palette stops."""
    if name not in PALETTES:
        raise KeyError(f"unknown palette {name!r}; available: {', '.join(sorted(PALETTES))}")
    return np.array([_hex_to_rgb(c) for c in PALETTES[name]], dtype=np.float32)


def ramp(pal: np.ndarray, t: np.ndarray | float) -> np.ndarray:
    """Sample a palette at position(s) `t` in 0..1.

    Returns an array shaped like `t` with a trailing axis of 3.
    """
    t = np.clip(np.asarray(t, dtype=np.float32), 0.0, 1.0)
    xs = np.linspace(0.0, 1.0, len(pal), dtype=np.float32)
    out = np.empty(t.shape + (3,), dtype=np.float32)
    for c in range(3):
        out[..., c] = np.interp(t, xs, pal[:, c]).astype(np.float32)
    return out


def pick(rng: np.random.Generator, exclude: str | None = None) -> str:
    names = [n for n in PALETTES if n != exclude and n != "mono"]
    return str(rng.choice(names))
