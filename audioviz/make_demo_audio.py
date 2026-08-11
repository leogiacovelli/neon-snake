#!/usr/bin/env python3
"""Synthesise a short demo track so the renderer can be tried without assets.

    python3 make_demo_audio.py --out demo.mp3 --bars 12

Four-on-the-floor kick, offbeat bass, hats, a chord stab and a riser at the end
of each 4-bar phrase — enough transient and spectral variety to exercise every
feature the analyser extracts.
"""

from __future__ import annotations

import argparse
import struct
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from avz.ffmpeg import find_ffmpeg  # noqa: E402

SR = 44100


def _env(n: int, attack: float, decay: float) -> np.ndarray:
    t = np.arange(n) / SR
    a = np.clip(t / max(attack, 1e-6), 0.0, 1.0)
    d = np.exp(-t / max(decay, 1e-6))
    return (a * d).astype(np.float32)


def kick(dur: float = 0.42) -> np.ndarray:
    n = int(SR * dur)
    t = np.arange(n) / SR
    freq = 52.0 + 130.0 * np.exp(-t / 0.028)
    body = np.sin(2 * np.pi * np.cumsum(freq) / SR) * _env(n, 0.001, 0.16)
    click = np.random.default_rng(1).standard_normal(n) * _env(n, 0.0005, 0.006) * 0.35
    return (body * 1.0 + click).astype(np.float32)


def hat(dur: float = 0.09, bright: float = 1.0) -> np.ndarray:
    n = int(SR * dur)
    rng = np.random.default_rng(2)
    noise = rng.standard_normal(n).astype(np.float32)
    # Crude high-pass: subtract a running mean.
    k = 8
    smooth = np.convolve(noise, np.ones(k, np.float32) / k, mode="same")
    return ((noise - smooth) * _env(n, 0.0005, 0.02 * bright) * 0.5).astype(np.float32)


def bass(freq: float, dur: float) -> np.ndarray:
    n = int(SR * dur)
    t = np.arange(n) / SR
    saw = 2.0 * ((t * freq) % 1.0) - 1.0
    # One-pole lowpass with an envelope-following cutoff.
    env = _env(n, 0.004, dur * 0.45)
    out = np.zeros(n, np.float32)
    prev = 0.0
    cutoff = 0.06 + 0.10 * env
    for i in range(n):
        prev += cutoff[i] * (saw[i] - prev)
        out[i] = prev
    return (out * env * 0.75).astype(np.float32)


def stab(root: float, dur: float) -> np.ndarray:
    n = int(SR * dur)
    t = np.arange(n) / SR
    env = _env(n, 0.006, dur * 0.35)
    out = np.zeros(n, np.float32)
    for ratio, gain in ((1.0, 0.5), (1.19, 0.4), (1.5, 0.42), (2.0, 0.25), (3.0, 0.12)):
        detune = 1.0 + 0.004 * (ratio % 0.7)
        out += np.sin(2 * np.pi * root * ratio * t) * gain
        out += np.sin(2 * np.pi * root * ratio * detune * t) * gain * 0.6
    return (out * env * 0.12).astype(np.float32)


def riser(dur: float) -> np.ndarray:
    n = int(SR * dur)
    t = np.arange(n) / SR
    sweep = np.sin(2 * np.pi * np.cumsum(200 + 2600 * (t / dur) ** 2) / SR)
    noise = np.random.default_rng(3).standard_normal(n).astype(np.float32) * 0.35
    return ((sweep * 0.5 + noise) * (t / dur) ** 2.2 * 0.35).astype(np.float32)


def add(buf: np.ndarray, sample: np.ndarray, at: float, gain: float = 1.0) -> None:
    i = int(at * SR)
    j = min(len(buf), i + len(sample))
    if i < len(buf):
        buf[i:j] += sample[: j - i] * gain


def synth(bpm: float = 126.0, bars: int = 12) -> np.ndarray:
    beat = 60.0 / bpm
    bar = beat * 4
    total = bar * bars + 1.5
    buf = np.zeros(int(total * SR), np.float32)

    k, h, h_soft = kick(), hat(), hat(bright=2.2)
    # A minor-ish two-chord loop.
    roots = [110.0, 110.0, 146.83, 130.81]
    for b in range(bars):
        t0 = b * bar
        phrase = b % 4
        for beat_i in range(4):
            tb = t0 + beat_i * beat
            add(buf, k, tb, 1.0)
            add(buf, h, tb + beat * 0.5, 0.5 if phrase < 2 else 0.75)
            if b >= 2:
                add(buf, h_soft, tb + beat * 0.25, 0.25)
                add(buf, h_soft, tb + beat * 0.75, 0.3)
            if b >= 1:
                root = roots[b % len(roots)]
                add(buf, bass(root / 2, beat * 0.45), tb + beat * 0.5, 0.9)
                if beat_i % 2 == 0:
                    add(buf, bass(root / 2, beat * 0.3), tb + beat * 0.25, 0.5)
        if b >= 4 and phrase in (0, 2):
            add(buf, stab(roots[b % len(roots)], beat * 1.6), t0 + beat * 2, 1.0)
        if phrase == 3:
            add(buf, riser(bar), t0, 1.0)

    # Soft-clip and normalise.
    buf = np.tanh(buf * 1.25)
    peak = float(np.max(np.abs(buf))) or 1.0
    return (buf / peak * 0.92).astype(np.float32)


def write_wav(path: Path, audio: np.ndarray) -> None:
    pcm = (np.clip(audio, -1.0, 1.0) * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(struct.pack(f"<{len(pcm)}h", *pcm.tolist()))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Synthesise a demo track for the renderer.")
    ap.add_argument("--out", "-o", default="demo.mp3", help="output file (.mp3 or .wav)")
    ap.add_argument("--bpm", type=float, default=126.0)
    ap.add_argument("--bars", type=int, default=12)
    ap.add_argument("--ffmpeg", default=None)
    args = ap.parse_args(argv)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    audio = synth(args.bpm, args.bars)

    if out.suffix.lower() == ".wav":
        write_wav(out, audio)
    else:
        tmp = out.with_suffix(".tmp.wav")
        write_wav(tmp, audio)
        ffmpeg = find_ffmpeg(args.ffmpeg)
        subprocess.run([ffmpeg, "-y", "-v", "error", "-i", str(tmp),
                        "-c:a", "libmp3lame", "-b:a", "192k", str(out)], check=True)
        tmp.unlink()

    print(f"{out}  ({len(audio) / SR:.1f}s @ {args.bpm:g} BPM)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
