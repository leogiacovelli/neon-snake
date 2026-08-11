"""Pipe raw frames into ffmpeg and mux the original audio in one pass."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import numpy as np


class VideoWriter:
    """Context manager writing rgb24 frames to ffmpeg's stdin.

    The audio file is a second input, so encoding and muxing happen together —
    no intermediate video file ever hits disk.
    """

    def __init__(self, ffmpeg: str, out_path: str, width: int, height: int, fps: float,
                 audio_path: str, audio_start: float = 0.0,
                 audio_duration: float | None = None, crf: int = 21,
                 preset: str = "medium", audio_bitrate: str = "192k"):
        self.out_path = out_path
        self._log = tempfile.NamedTemporaryFile(prefix="avz-ffmpeg-", suffix=".log", delete=False)

        cmd = [
            ffmpeg, "-y", "-nostdin", "-v", "warning",
            "-f", "rawvideo", "-pix_fmt", "rgb24",
            "-s", f"{width}x{height}", "-r", f"{fps}", "-i", "pipe:0",
        ]
        if audio_start > 0:
            cmd += ["-ss", f"{audio_start:.6f}"]
        cmd += ["-i", audio_path]
        if audio_duration is not None:
            cmd += ["-t", f"{audio_duration:.6f}"]
        cmd += [
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
            "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.1",
            "-c:a", "aac", "-b:a", audio_bitrate,
            "-movflags", "+faststart", "-shortest",
            str(out_path),
        ]
        self.cmd = cmd
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE,
                                     stdout=subprocess.DEVNULL, stderr=self._log)

    def write(self, frame: np.ndarray) -> None:
        assert self.proc.stdin is not None
        try:
            self.proc.stdin.write(frame.tobytes())
        except BrokenPipeError:
            raise RuntimeError(f"ffmpeg exited early:\n{self._read_log()}") from None

    def _read_log(self) -> str:
        try:
            return Path(self._log.name).read_text(errors="replace").strip()
        except OSError:
            return "(no ffmpeg log)"

    def close(self) -> None:
        if self.proc.stdin and not self.proc.stdin.closed:
            self.proc.stdin.close()
        code = self.proc.wait()
        log = self._read_log()
        self._log.close()
        Path(self._log.name).unlink(missing_ok=True)
        if code != 0:
            raise RuntimeError(f"ffmpeg failed (exit {code}):\n{log}")

    def __enter__(self) -> "VideoWriter":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is not None:
            # Let the original exception surface; just tear ffmpeg down.
            if self.proc.stdin and not self.proc.stdin.closed:
                self.proc.stdin.close()
            self.proc.kill()
            self.proc.wait()
            self._log.close()
            Path(self._log.name).unlink(missing_ok=True)
            return
        self.close()
