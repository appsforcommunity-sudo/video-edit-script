"""Thin wrappers around the ffmpeg / ffprobe command-line tools."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


class FFmpegError(RuntimeError):
    pass


def require_ffmpeg() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            raise FFmpegError(
                f"'{tool}' not found on PATH. Install FFmpeg: https://ffmpeg.org/download.html"
            )


def run(args: list[str], dry_run: bool = False) -> list[str]:
    """Run ffmpeg with the given arguments (without the leading 'ffmpeg')."""
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args]
    if dry_run:
        print(" ".join(cmd))
        return cmd
    require_ffmpeg()
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise FFmpegError(result.stderr.strip() or "ffmpeg failed")
    return cmd


def probe(path: str | Path) -> dict:
    """Return ffprobe JSON info (format + streams) for a media file."""
    require_ffmpeg()
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json",
         "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise FFmpegError(result.stderr.strip() or f"ffprobe failed on {path}")
    return json.loads(result.stdout)


def duration(path: str | Path) -> float:
    return float(probe(path)["format"]["duration"])


def has_audio(path: str | Path) -> bool:
    return any(s.get("codec_type") == "audio" for s in probe(path)["streams"])
