"""Audio analysis: turn a music file into a per-video-frame feature timeline.

Everything the visual styles react to is computed once, up front, and resampled
onto the video's frame grid. A style therefore never touches librosa — it just
reads a :class:`~avz.features.Frame` of already-normalised numbers.
"""

from __future__ import annotations

import librosa
import numpy as np

from .features import BANDS, N_SPECTRUM_BANDS, Frame, Timeline
from .ffmpeg import decode_mono

ANALYSIS_SR = 22050
N_FFT = 2048
HOP = 512


def _robust_norm(x: np.ndarray, lo_pct: float = 5.0, hi_pct: float = 97.0) -> np.ndarray:
    """Scale to roughly 0..1 using percentiles, so one loud transient can't
    flatten the whole track."""
    lo = float(np.percentile(x, lo_pct))
    hi = float(np.percentile(x, hi_pct))
    if hi - lo < 1e-9:
        return np.zeros_like(x, dtype=np.float32)
    return np.clip((x - lo) / (hi - lo), 0.0, 1.0).astype(np.float32)


def _envelope(x: np.ndarray, fps: float, attack: float = 0.02,
              release: float = 0.18) -> np.ndarray:
    """One-pole follower with separate attack/release.

    Fast attack keeps hits punchy; slow release stops the image from strobing.
    """
    a_att = float(np.exp(-1.0 / max(attack * fps, 1e-6)))
    a_rel = float(np.exp(-1.0 / max(release * fps, 1e-6)))
    out = np.empty_like(x, dtype=np.float32)
    prev = float(x[0]) if len(x) else 0.0
    for i, v in enumerate(x):
        coef = a_att if v > prev else a_rel
        prev = coef * prev + (1.0 - coef) * float(v)
        out[i] = prev
    return out


def _beat_signals(beat_times: np.ndarray, frame_times: np.ndarray,
                  tempo: float) -> dict[str, np.ndarray]:
    """Derive beat pulse / phase / count on the video frame grid."""
    n = len(frame_times)

    if len(beat_times) < 2:
        # No usable beat track: fall back to a steady grid at the reported tempo.
        period = 60.0 / max(tempo, 1e-6)
        beat_times = np.arange(0.0, frame_times[-1] + period, period) if n else np.zeros(0)

    if len(beat_times) >= 2:
        period = float(np.median(np.diff(beat_times)))
    else:
        period = 60.0 / max(tempo, 1e-6)
    period = max(period, 1e-3)

    # For each frame, the most recent beat at or before it.
    pos = np.searchsorted(beat_times, frame_times, side="right") - 1
    have = pos >= 0
    since = np.zeros(n, np.float32)
    since[have] = frame_times[have] - beat_times[pos[have]]
    since[~have] = period  # before the first beat: treat as fully decayed

    tau = min(0.13, period * 0.45)
    beat = np.exp(-since / tau).astype(np.float32)
    phase = np.clip(since / period, 0.0, 1.0).astype(np.float32)
    index = np.maximum(pos, 0).astype(np.int32)

    bar = ((index % 4).astype(np.float32) + phase) / 4.0
    return {"beat": beat, "beat_phase": phase, "beat_index": index,
            "bar_phase": bar.astype(np.float32)}


def _sections(mfcc: np.ndarray, duration: float,
              frame_times: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Segment the track structurally; used by `--style mix` to change look."""
    target = max(2, min(10, int(round(duration / 20.0))))
    try:
        bounds = librosa.segment.agglomerative(mfcc, target)
        bound_times = librosa.frames_to_time(bounds, sr=ANALYSIS_SR, hop_length=HOP)
    except Exception:
        bound_times = np.linspace(0.0, duration, target, endpoint=False)

    bound_times = np.unique(np.concatenate([[0.0], np.asarray(bound_times, np.float64)]))
    bound_times = bound_times[bound_times < duration - 1.0]
    if len(bound_times) == 0:
        bound_times = np.array([0.0])

    idx = np.clip(np.searchsorted(bound_times, frame_times, side="right") - 1, 0, None)
    edges = np.concatenate([bound_times, [duration]])
    starts = edges[idx]
    ends = edges[idx + 1]
    phase = np.clip((frame_times - starts) / np.maximum(ends - starts, 1e-6), 0.0, 1.0)
    return idx.astype(np.int32), phase.astype(np.float32), bound_times


def analyze(ffmpeg: str, path: str, fps: float, start: float = 0.0,
            duration: float | None = None) -> Timeline:
    """Decode `path` and build a per-frame :class:`Timeline`."""
    raw = decode_mono(ffmpeg, path, ANALYSIS_SR, start=start, duration=duration)
    y = np.frombuffer(raw, dtype=np.float32).copy()
    if y.size == 0:
        raise RuntimeError(f"No audio decoded from {path}")

    dur = len(y) / ANALYSIS_SR
    n_frames = max(1, int(np.floor(dur * fps)))
    frame_times = np.arange(n_frames, dtype=np.float64) / fps

    S = np.abs(librosa.stft(y, n_fft=N_FFT, hop_length=HOP)).astype(np.float32)
    feat_times = librosa.frames_to_time(np.arange(S.shape[1]), sr=ANALYSIS_SR, hop_length=HOP)
    freqs = librosa.fft_frequencies(sr=ANALYSIS_SR, n_fft=N_FFT)

    def resample(v: np.ndarray) -> np.ndarray:
        return np.interp(frame_times, feat_times, v).astype(np.float32)

    scalars: dict[str, np.ndarray] = {}

    rms = librosa.feature.rms(S=S, frame_length=N_FFT, hop_length=HOP)[0]
    scalars["energy"] = _envelope(resample(_robust_norm(np.sqrt(rms))), fps, 0.03, 0.25)

    power = S ** 2
    for name, (lo, hi) in BANDS.items():
        mask = (freqs >= lo) & (freqs < hi)
        band = np.sqrt(power[mask].mean(axis=0)) if mask.any() else np.zeros(S.shape[1])
        # Log scaling: bands otherwise sit near zero for most of a track.
        band = np.log1p(band * 40.0)
        scalars[name] = _envelope(resample(_robust_norm(band)), fps, 0.02, 0.16)

    onset_env = librosa.onset.onset_strength(S=librosa.power_to_db(power), sr=ANALYSIS_SR,
                                             hop_length=HOP)
    scalars["onset"] = _envelope(resample(_robust_norm(onset_env)), fps, 0.005, 0.10)

    centroid = librosa.feature.spectral_centroid(S=S, sr=ANALYSIS_SR)[0]
    scalars["brightness"] = _envelope(resample(_robust_norm(np.log1p(centroid))), fps, 0.05, 0.4)

    tempo_raw, beat_frames = librosa.beat.beat_track(onset_envelope=onset_env, sr=ANALYSIS_SR,
                                                    hop_length=HOP, trim=False)
    tempo = float(np.atleast_1d(tempo_raw)[0]) or 120.0
    beat_times = librosa.frames_to_time(beat_frames, sr=ANALYSIS_SR, hop_length=HOP)
    scalars.update(_beat_signals(np.asarray(beat_times, np.float64), frame_times, tempo))

    mel = librosa.feature.melspectrogram(S=power, sr=ANALYSIS_SR, n_mels=N_SPECTRUM_BANDS,
                                         fmax=11000)
    mel_db = librosa.power_to_db(mel, ref=np.max)
    absolute = np.clip((mel_db + 70.0) / 70.0, 0.0, 1.0)
    # Absolute levels alone leave every bar sitting near the same height, because
    # a mel band's dynamic range over a track is much narrower than the full
    # scale. Stretching each band across its own range makes the spectrum move;
    # keeping some of the absolute level means silence still reads as silence.
    per_band = np.stack([_robust_norm(absolute[b], 10.0, 95.0)
                         for b in range(absolute.shape[0])])
    mel_norm = 0.35 * absolute + 0.65 * per_band
    spectrum = np.stack([resample(mel_norm[b]) for b in range(mel_norm.shape[0])], axis=1)
    # Light temporal smoothing so bars glide instead of jittering.
    for i in range(1, len(spectrum)):
        spectrum[i] = 0.55 * spectrum[i] + 0.45 * spectrum[i - 1]

    mfcc = librosa.feature.mfcc(S=librosa.power_to_db(mel), n_mfcc=13)
    sec_idx, sec_phase, sec_times = _sections(mfcc, dur, frame_times)
    scalars["section"] = sec_idx
    scalars["section_phase"] = sec_phase

    return Timeline(
        fps=fps,
        n_frames=n_frames,
        duration=dur,
        tempo=tempo,
        beat_times=np.asarray(beat_times, np.float64),
        section_times=sec_times,
        scalars=scalars,
        spectrum=spectrum.astype(np.float32),
    )


__all__ = ["analyze", "Frame", "Timeline", "BANDS", "N_SPECTRUM_BANDS",
           "ANALYSIS_SR", "HOP", "N_FFT"]
