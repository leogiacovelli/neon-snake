"""Style registry."""

from __future__ import annotations

import numpy as np

from .base import Style
from .fluid import Fluid
from .glitch import Glitch
from .neon_grid import NeonGrid
from .particles import Particles
from .tunnel import Tunnel

STYLES: dict[str, type[Style]] = {
    cls.name: cls for cls in (NeonGrid, Particles, Glitch, Fluid, Tunnel)
}

#: Meta-styles accepted on the command line but not present in STYLES.
META_STYLES = ("random", "mix")


def get(name: str) -> type[Style]:
    if name not in STYLES:
        raise KeyError(f"unknown style {name!r}; available: {', '.join(names())}")
    return STYLES[name]


def names() -> list[str]:
    return sorted(STYLES)


def pick(rng: np.random.Generator, exclude: str | None = None) -> str:
    options = [n for n in names() if n != exclude]
    return str(rng.choice(options))


__all__ = ["Style", "STYLES", "META_STYLES", "get", "names", "pick"]
