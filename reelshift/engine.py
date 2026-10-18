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
        # Keep source frame timestamps and avoid H.264 B-frame startup reorder latency.
        command += ["-fps_mode:v:0", "passthrough", "-bf:v:0", "0", "-profile:v:0", "high"]
    if aac_stereo:
        command += ["-c:a", "aac", "-b:a", "192k", "-ac", "2"]
    # Apply the same timestamp shift to all mapped streams.
    command += ["-avoid_negative_ts", "make_zero", "-f", "matroska", str(temp)]
    return command


def ffmpeg_seconds(fields: dict[str, str]) -> float:
    # Both out_time_us and legacy out_time_ms are microseconds, not milliseconds.
    for name in ("out_time_us", "out_time_ms"):
        if fields.get(name) and fields[name].lstrip("-").isdigit():
            return max(0, int(fields[name]) / 1_000_000)
    value = fields.get("out_time", "")
    found = re.match(r"(\d+):(\d+):(\d+(?:\.\d+)?)", value)
    return int(found[1]) * 3600 + int(found[2]) * 60 + float(found[3]) if found else 0.0


def scan_paths(source: Path, pattern: str, recursive: bool, output_dir: Path | None = None) -> list[Path]:
    import fnmatch
    filters = [s.strip().casefold() for s in pattern.split(";") if s.strip()] or ["*.mkv"]
    source = source.resolve()
    output_dir = output_dir.resolve() if output_dir is not None else None
    matches = source.rglob("*") if recursive else source.iterdir()
    return sorted((path for path in matches if path.is_file() and path.suffix.casefold() == ".mkv"
                   and (output_dir is None or not path.resolve().is_relative_to(output_dir))
                   and any(fnmatch.fnmatch(path.name.casefold(), glob) for glob in filters)),
                  key=lambda p: p.name.casefold())


@dataclass(frozen=True)
class AVSyncInfo:
    """Container presentation start times, not a subjective lipsync check."""
    video_start: float | None
    audio_starts: tuple[float | None, ...]

    @property
    def audio_video_deltas(self) -> tuple[float | None, ...]:
        return tuple((self.video_start - start)
                     if self.video_start is not None and start is not None else None
                     for start in self.audio_starts)


def probe_av_sync(path: Path, ffprobe: str) -> AVSyncInfo:
    """Read A/V stream start offsets without full-file decoding."""
    run = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "stream=codec_type,start_time",
         "-of", "json", str(path)],
        capture_output=True, text=True, errors="replace", timeout=40,
        creationflags=popen_flags(),
    )
    if run.returncode:
        raise RuntimeError("FFprobe-Syncprüfung fehlgeschlagen: " + run.stderr.strip()[:260])
    streams = json.loads(run.stdout).get("streams", [])

    def start(stream: dict) -> float | None:
        try:
            value = float(stream["start_time"])
            return value if abs(value) < 1e12 else None
        except (TypeError, ValueError, KeyError):
            return None

    videos = [s for s in streams if s.get("codec_type") == "video"]
    audios = [s for s in streams if s.get("codec_type") == "audio"]
    return AVSyncInfo(start(videos[0]) if videos else None,
                      tuple(start(s) for s in audios))


def av_sync_report(before: AVSyncInfo, after: AVSyncInfo,
                   max_change_seconds: float = 0.15) -> tuple[bool, str]:
    """Check whether audio/video stream startup offsets changed by >150 ms.

    Cannot detect actual lip sync or playback-specific decoder stalls.
    """
    if len(before.audio_starts) != len(after.audio_starts):
        return False, "Anzahl der Tonspuren hat sich verändert"
    if before.video_start is None or after.video_start is None:
        return False, "Video-Startzeitstempel fehlen"
    checked = 0
    lines = []
    for index, (old, new) in enumerate(zip(before.audio_video_deltas,
                                            after.audio_video_deltas), start=1):
        if old is None or new is None:
            lines.append(f"Audio {index}: kein vergleichbarer Startzeitstempel")
            continue
        checked += 1
        change = (new - old) * 1000
        lines.append(f"Audio {index}: Video minus Audio vorher {old:+.3f}s, "
                     f"nachher {new:+.3f}s (Änderung {change:+.0f} ms)")
        if abs(change) > max_change_seconds * 1000:
            return False, "; ".join(lines) + " – Synchronitätsänderung zu groß"
    if before.audio_starts and checked == 0:
        return False, "Keine vergleichbaren A/V-Startzeitstempel vorhanden"
    return True, "; ".join(lines) if lines else "Keine Tonspur: nur Video validiert"


def rename_conflicts(items: list[VideoItem]) -> list[str]:
    """Reject in-place collisions without touching the input MKVs."""
    issues: list[str] = []
    planned: set[str] = set()
    for item in items:
        if item.status.startswith("Fehler"):
            continue
        source = item.source
        target = source.with_name(item.target_name)
        if not source.is_file():
            issues.append(f"Quelldatei fehlt: {source}")
            continue
        if target.suffix.casefold() != ".mkv" or target.name != item.target_name:
            issues.append(f"Ungültiger Dateiname: {item.target_name}")
            continue
        key = str(target.parent.resolve()).casefold() + "\0" + target.name.casefold()
        if key in planned:
            issues.append(f"Doppelter Zielname: {target}")
        planned.add(key)
        try:
            occupied = next((entry for entry in target.parent.iterdir()
                             if entry.name.casefold() == target.name.casefold()), None)
        except OSError as exc:
            issues.append(f"Zielordner nicht lesbar: {target.parent}: {exc}")
            continue
        if occupied is not None and occupied != source:
            issues.append(f"Ziel bereits belegt: {target}")
    return issues
