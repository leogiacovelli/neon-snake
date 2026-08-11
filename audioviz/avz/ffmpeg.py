"""Locating and driving the ffmpeg binary."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


class FFmpegNotFound(RuntimeError):
    pass


def find_ffmpeg(explicit: str | None = None) -> str:
    """Resolve an ffmpeg binary.

    Order: --ffmpeg flag, $FFMPEG_BIN, PATH, then the npm ffmpeg-static package
    if it happens to be installed in this repo (handy, never required).
    """
    candidates = [explicit, os.environ.get("FFMPEG_BIN")]
    for cand in candidates:
        if cand and Path(cand).exists():
            return str(cand)

    on_path = shutil.which("ffmpeg")
    if on_path:
        return on_path

    vendored = _REPO_ROOT / "node_modules" / "ffmpeg-static" / "ffmpeg"
    if vendored.exists():
        return str(vendored)

    raise FFmpegNotFound(
        "ffmpeg not found. Install it (apt install ffmpeg / brew install ffmpeg), "
        "or run `npm i -D ffmpeg-static` in this repo, or pass --ffmpeg /path/to/ffmpeg."
    )


def decode_mono(ffmpeg: str, path: str, sr: int, start: float = 0.0,
                duration: float | None = None) -> bytes:
    """Decode any audio file to raw mono float32 PCM at `sr`.

    Going through ffmpeg rather than librosa's own loaders means mp3/m4a/ogg/flac
    all work identically without extra Python codec dependencies.
    """
    cmd = [ffmpeg, "-v", "error", "-nostdin"]
    if start > 0:
        cmd += ["-ss", f"{start:.6f}"]
    cmd += ["-i", path]
    if duration is not None:
        cmd += ["-t", f"{duration:.6f}"]
    cmd += ["-f", "f32le", "-ac", "1", "-ar", str(sr), "pipe:1"]

    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed to decode {path}:\n{proc.stderr.decode('utf-8', 'replace')}"
        )
    return proc.stdout


def probe_duration(ffmpeg: str, path: str) -> float | None:
    """Best-effort container duration in seconds, via ffmpeg's own stderr banner."""
    proc = subprocess.run(
        [ffmpeg, "-v", "info", "-nostdin", "-i", path, "-f", "null", "-"],
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
    )
    for line in proc.stderr.decode("utf-8", "replace").splitlines():
        line = line.strip()
        if line.startswith("Duration:"):
            stamp = line.split("Duration:", 1)[1].split(",", 1)[0].strip()
            try:
                h, m, s = stamp.split(":")
                return int(h) * 3600 + int(m) * 60 + float(s)
            except ValueError:
                return None
    return None
