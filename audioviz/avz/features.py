"""The feature containers styles read from.

Deliberately free of librosa (and of any heavy import): render workers unpickle
a :class:`Timeline` and need this module, but never the analysis code itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

#: Frequency bands (Hz) exposed to styles as `bass`, `low_mid`, ... .
BANDS: dict[str, tuple[float, float]] = {
    "bass": (20.0, 160.0),
    "low_mid": (160.0, 500.0),
    "mid": (500.0, 2000.0),
    "high": (2000.0, 6000.0),
    "air": (6000.0, 11000.0),
}

N_SPECTRUM_BANDS = 48


@dataclass
class Frame:
    """One video frame's worth of audio-derived control values.

    All scalar fields are normalised to 0..1 unless noted.
    """

    index: int
    t: float                 # seconds into the render
    energy: float            # smoothed overall loudness
    bass: float
    low_mid: float
    mid: float
    high: float
    air: float
    onset: float             # decayed onset strength — "something just hit"
    beat: float              # 1.0 on a beat, decaying exponentially after it
    beat_phase: float        # 0..1 position between the surrounding beats
    bar_phase: float         # 0..1 position within a 4-beat bar
    beat_index: int          # how many beats have elapsed
    brightness: float        # spectral centroid, normalised
    section: int             # index of the current structural section
    section_phase: float     # 0..1 position within that section
    spectrum: np.ndarray     # (N_SPECTRUM_BANDS,) normalised mel spectrum


@dataclass
class Timeline:
    """Per-frame feature arrays plus the metadata styles like to know about."""

    fps: float
    n_frames: int
    duration: float
    tempo: float
    beat_times: np.ndarray
    section_times: np.ndarray
    scalars: dict[str, np.ndarray] = field(default_factory=dict)
    spectrum: np.ndarray = field(default_factory=lambda: np.zeros((0, 0), np.float32))

    def frame(self, i: int) -> Frame:
        s = self.scalars
        return Frame(
            index=i,
            t=i / self.fps,
            energy=float(s["energy"][i]),
            bass=float(s["bass"][i]),
            low_mid=float(s["low_mid"][i]),
            mid=float(s["mid"][i]),
            high=float(s["high"][i]),
            air=float(s["air"][i]),
            onset=float(s["onset"][i]),
            beat=float(s["beat"][i]),
            beat_phase=float(s["beat_phase"][i]),
            bar_phase=float(s["bar_phase"][i]),
            beat_index=int(s["beat_index"][i]),
            brightness=float(s["brightness"][i]),
            section=int(s["section"][i]),
            section_phase=float(s["section_phase"][i]),
            spectrum=self.spectrum[i],
        )
