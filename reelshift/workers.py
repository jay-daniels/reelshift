"""Qt background workers. All disk, subprocess and network work runs outside the UI thread."""
from __future__ import annotations

import os
import subprocess
import threading
import time
import uuid
from pathlib import Path

import psutil
from PySide6.QtCore import QObject, Signal, Slot

from .engine import VideoItem, executable, ffmpeg_command, ffmpeg_seconds, inspect_video, popen_flags, scan_paths
from .metadata import EpisodeLookup
from .naming import output_name


class ScanWorker(QObject):
    progress = Signal(int, int, str)
    complete = Signal(object)
    error = Signal(str)
    finished = Signal()

    def __init__(self, folder: Path, destination: Path, pattern: str, recursive: bool,
                 online: bool, tmdb_token: str, ffmpeg_override: str) -> None:
        super().__init__()
        self.folder, self.destination = folder, destination
        self.pattern, self.recursive = pattern, recursive
        self.online, self.tmdb_token, self.ffmpeg_override = online, tmdb_token, ffmpeg_override

    @Slot()
    def run(self) -> None:
        try:
            if not self.folder.is_dir():
                raise ValueError("Quellordner nicht gefunden")
            if self.folder.resolve().is_relative_to(self.destination.resolve()):
                raise ValueError("Zielordner darf nicht die Quelle selbst oder deren übergeordneter Ordner sein")
            ffprobe = executable("ffprobe", self.ffmpeg_override)
            files = scan_paths(self.folder, self.pattern, self.recursive, self.destination)
            resolver = EpisodeLookup(self.tmdb_token)
            items: list[VideoItem] = []
            for i, path in enumerate(files, 1):
                self.progress.emit(i, len(files), path.name)
                try:
                    item = inspect_video(path, ffprobe)
                    if self.online and item.parsed.season is not None and not item.parsed.title:
                        found = resolver.find(item.parsed.series, item.parsed.season, item.parsed.episode)
                        if found:
                            item.target_name = output_name(item.parsed, found[0])
                            item.note = (item.note + " | " if item.note else "") + found[1]
                    items.append(item)
                except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
                    items.append(VideoItem(path, path.name, "?", 0, None, status="Fehler: " + str(exc)[:140]))  # type: ignore[arg-type]
            self.complete.emit(items)
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.finished.emit()


class EncodeWorker(QObject):
    file_state = Signal(int, str)
    file_progress = Signal(int, float, str, str)
    log = Signal(str)
    complete = Signal(int, int, int)
    finished = Signal()

    def __init__(self, items: list[VideoItem], destination: Path, ffmpeg_override: str,
                 gpu: bool, quality: int, aac_stereo: bool, force_encode: bool) -> None:
        super().__init__()
        self.items, self.destination = items, destination
        self.ffmpeg_override, self.gpu, self.quality = ffmpeg_override, gpu, quality
        self.aac_stereo, self.force_encode = aac_stereo, force_encode
        self.cancelled = threading.Event()
        self.running = threading.Event()
        self.running.set()
        self.process: subprocess.Popen | None = None
        self._lock = threading.RLock()

    def pause(self) -> None:
        with self._lock:
            self.running.clear()
            if self.process and self.process.poll() is None:
                try:
                    psutil.Process(self.process.pid).suspend()
                except psutil.Error:
                    pass

    def resume(self) -> None:
        with self._lock:
            if self.process and self.process.poll() is None:
                try:
                    psutil.Process(self.process.pid).resume()
                except psutil.Error:
                    pass
            self.running.set()

    def cancel(self) -> None:
        self.cancelled.set()
        self.resume()
        with self._lock:
            if self.process and self.process.poll() is None:
                self.process.terminate()

    @Slot()
    def run(self) -> None:
        done = failed = skipped = 0
        try:
            ffmpeg = executable("ffmpeg", self.ffmpeg_override)
            self.destination.mkdir(parents=True, exist_ok=True)
            for index, item in enumerate(self.items):
                if self.cancelled.is_set():
                    break
                if item.status.startswith("Fehler"):
                    skipped += 1
                    continue
                self.running.wait()
                if self.cancelled.is_set():
                    break
                target = self.destination / item.target_name
                if target.exists() or target.resolve() == item.source.resolve():
                    skipped += 1
                    self.file_state.emit(index, "Übersprungen: Ziel existiert")
                    continue
                self.file_state.emit(index, "Konvertierung läuft")
                self.log.emit(f"START {item.source.name} -> {item.target_name}")
                temp = self.destination / ("." + uuid.uuid4().hex + ".reelshift.part.mkv")
                try:
                    command = ffmpeg_command(ffmpeg, item, temp, self.gpu, self.quality,
                                             self.aac_stereo, self.force_encode)
                    last_fields: dict[str, str] = {}
                    errors: list[str] = []
                    with self._lock:
                        self.process = subprocess.Popen(command, stdout=subprocess.PIPE,
                                                        stderr=subprocess.STDOUT, text=True,
                                                        encoding="utf-8", errors="replace",
                                                        bufsize=1, creationflags=popen_flags())
                        if not self.running.is_set():
                            psutil.Process(self.process.pid).suspend()
                    assert self.process.stdout is not None
                    for raw in self.process.stdout:
                        line = raw.strip()
                        if "=" in line and line.split("=", 1)[0] in {
                            "frame", "fps", "bitrate", "total_size", "out_time_us", "out_time_ms",
                            "out_time", "dup_frames", "drop_frames", "speed", "progress"}:
                            key, value = line.split("=", 1)
                            last_fields[key] = value
                            if key == "progress":
                                seconds = ffmpeg_seconds(last_fields)
                                percent = min(100., 100. * seconds / item.duration) if item.duration > 0 else 0.
                                speed = last_fields.get("speed", "–")
                                try:
                                    multiplier = float(speed.rstrip("x"))
                                    eta = max(0, (item.duration - seconds) / multiplier) if multiplier > 0 else -1
                                    remaining = f"{int(eta // 60):02d}:{int(eta % 60):02d}" if eta >= 0 else "–"
                                except ValueError:
                                    remaining = "–"
                                self.file_progress.emit(index, percent, speed, remaining)
                                last_fields.clear()
                        elif line:
                            errors.append(line)
                            errors = errors[-12:]
                    exit_code = self.process.wait()
                    with self._lock:
                        self.process = None
                    if self.cancelled.is_set():
                        self.file_state.emit(index, "Abgebrochen")
                        break
                    if exit_code or not temp.exists() or temp.stat().st_size == 0:
                        raise RuntimeError(" | ".join(errors[-3:]) or f"FFmpeg Exit-Code {exit_code}")
                    # Windows rename never replaces an existing destination; guard again.
                    if target.exists():
                        raise FileExistsError("Zieldatei wurde während der Konvertierung erstellt")
                    os.rename(temp, target)
                    done += 1
                    self.file_progress.emit(index, 100., "–", "00:00")
                    self.file_state.emit(index, "Fertig")
                    self.log.emit(f"OK    {target.name}")
                except Exception as exc:
                    failed += 1
                    self.file_state.emit(index, "Fehler")
                    self.log.emit(f"FEHLER {item.source.name}: {exc}")
                finally:
                    with self._lock:
                        self.process = None
                    temp.unlink(missing_ok=True)
        except Exception as exc:
            self.log.emit("FATAL: " + str(exc))
            failed += 1
        finally:
            self.complete.emit(done, failed, skipped)
            self.finished.emit()
