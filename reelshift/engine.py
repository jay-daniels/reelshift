"""FFprobe inspection and FFmpeg command/progress helpers (no Qt dependency)."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .naming import EpisodeName, parse_name, output_name


@dataclass
class VideoItem:
    source: Path
    target_name: str
    codec: str
    duration: float
    parsed: EpisodeName
    pix_fmt: str = ""
    profile: str = ""
    hdr: bool = False
    note: str = ""
    status: str = "Bereit"
    progress: float = 0.0


def executable(tool: str, ffmpeg_override: str = "") -> str:
    if ffmpeg_override:
        exe = Path(ffmpeg_override).expanduser()
        if exe.is_file():
            candidate = exe if tool == "ffmpeg" else exe.with_name("ffprobe.exe" if os.name == "nt" else "ffprobe")
            if candidate.is_file():
                return str(candidate)
    if getattr(sys, "frozen", False):
        bundled = Path(sys.executable).parent / (tool + (".exe" if os.name == "nt" else ""))
        if bundled.is_file():
            return str(bundled)
    found = shutil.which(tool)
    if not found:
        raise FileNotFoundError(f"{tool} fehlt. FFmpeg installieren und zum PATH hinzufügen oder die ffmpeg.exe auswählen.")
    return found


def popen_flags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def inspect_video(path: Path, ffprobe: str) -> VideoItem:
    run = subprocess.run([ffprobe, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
                         capture_output=True, text=True, errors="replace", timeout=40,
                         creationflags=popen_flags())
    if run.returncode:
        raise ValueError(run.stderr.strip()[:250] or "ffprobe konnte die Datei nicht lesen")
    data = json.loads(run.stdout)
    videos = [stream for stream in data.get("streams", []) if stream.get("codec_type") == "video"
              and not stream.get("disposition", {}).get("attached_pic")]
    if not videos:
        raise ValueError("Keine Videospur gefunden")
    stream = videos[0]
    duration = float(data.get("format", {}).get("duration") or stream.get("duration") or 0)
    hdr = stream.get("color_transfer") in ("smpte2084", "arib-std-b67")
    note = "HDR: kein Tonemapping in v0.1!" if hdr else ""
    parsed = parse_name(path)
    return VideoItem(path, output_name(parsed), stream.get("codec_name", "unbekannt"),
                     duration, parsed, stream.get("pix_fmt", ""), stream.get("profile", ""), hdr, note)


def needs_video_encode(item: VideoItem) -> bool:
    return item.codec != "h264" or item.pix_fmt != "yuv420p" or item.profile.lower() not in {
        "baseline", "constrained baseline", "main", "high"}


def ffmpeg_command(ffmpeg: str, item: VideoItem, temp: Path, use_gpu: bool, quality: int,
                   aac_stereo: bool, force: bool = False) -> list[str]:
    command = [ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error", "-nostats",
               "-progress", "pipe:1", "-i", str(item.source),
               "-map", "0:v:0", "-map", "0:a?", "-map", "0:s?", "-map", "0:t?",
               "-map_metadata", "0", "-map_chapters", "0", "-c", "copy"]
    if force or needs_video_encode(item):
        if use_gpu:
            command += ["-c:v:0", "h264_nvenc", "-preset", "p5", "-rc", "vbr",
                        "-cq", str(quality), "-b:v", "0", "-pix_fmt", "yuv420p"]
        else:
            command += ["-c:v:0", "libx264", "-preset", "medium", "-crf", str(quality),
                        "-pix_fmt", "yuv420p"]
    if aac_stereo:
        command += ["-c:a", "aac", "-b:a", "192k", "-ac", "2"]
    command += ["-f", "matroska", str(temp)]
    return command


def ffmpeg_seconds(fields: dict[str, str]) -> float:
    # Both out_time_us and legacy out_time_ms are microseconds, not milliseconds.
    for name in ("out_time_us", "out_time_ms"):
        if fields.get(name) and fields[name].lstrip("-").isdigit():
            return max(0, int(fields[name]) / 1_000_000)
    value = fields.get("out_time", "")
    found = re.match(r"(\d+):(\d+):(\d+(?:\.\d+)?)", value)
    return int(found[1]) * 3600 + int(found[2]) * 60 + float(found[3]) if found else 0.0


def scan_paths(source: Path, pattern: str, recursive: bool, output_dir: Path) -> list[Path]:
    import fnmatch
    filters = [s.strip().casefold() for s in pattern.split(";") if s.strip()] or ["*.mkv"]
    source = source.resolve()
    output_dir = output_dir.resolve()
    matches = source.rglob("*") if recursive else source.iterdir()
    return sorted((path for path in matches if path.is_file() and path.suffix.casefold() == ".mkv"
                   and not path.resolve().is_relative_to(output_dir)
                   and any(fnmatch.fnmatch(path.name.casefold(), glob) for glob in filters)),
                  key=lambda p: p.name.casefold())
