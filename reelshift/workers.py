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

from .engine import VideoItem, executable, ffmpeg_command, ffmpeg_seconds, inspect_video, popen_flags, scan_paths, probe_av_sync, av_sync_report, probe_decode_start, validate_decode_start, probe_video_codec, decode_video_sample
from .metadata import EpisodeLookup
from .naming import output_name


class ScanWorker(QObject):
    progress = Signal(int, int, str)
    notice = Signal(str)
    complete = Signal(object)
    error = Signal(str)
    finished = Signal()

    def __init__(self, folder: Path, destination: Path, pattern: str, recursive: bool,
                 online: bool, tmdb_token: str, ffmpeg_override: str, rename_only: bool = False) -> None:
        super().__init__()
        self.folder, self.destination = folder, destination
        self.pattern, self.recursive = pattern, recursive
        self.online, self.tmdb_token, self.ffmpeg_override = online, tmdb_token, ffmpeg_override
        self.rename_only = rename_only

    @Slot()
    def run(self) -> None:
        try:
            if not self.folder.is_dir():
                raise ValueError("Quellordner nicht gefunden")
            if not self.rename_only and self.folder.resolve().is_relative_to(self.destination.resolve()):
                raise ValueError("Zielordner darf nicht die Quelle selbst oder deren übergeordneter Ordner sein")
            ffprobe = executable("ffprobe", self.ffmpeg_override) if not self.rename_only else ""
            files = scan_paths(self.folder, self.pattern, self.recursive,
                               None if self.rename_only else self.destination)
            resolver = EpisodeLookup(self.tmdb_token)
            items: list[VideoItem] = []
            for i, path in enumerate(files, 1):
                self.progress.emit(i, len(files), path.name)
                try:
                    if self.rename_only:
                        from .naming import parse_name
                        parsed = parse_name(path)
                        item = VideoItem(path, output_name(parsed), "–", 0, parsed)
                    else:
                        item = inspect_video(path, ffprobe)
                    if self.online and item.parsed.season is not None and not item.parsed.title:
                        found = resolver.find(item.parsed.series, item.parsed.season, item.parsed.episode)
                        if found:
                            item.target_name = output_name(item.parsed, found[0])
                            item.note = (item.note + " | " if item.note else "") + found[1]
                        elif resolver.last_diagnostic:
                            detail = "Episodensuche: " + resolver.last_diagnostic
                            item.note = (item.note + " | " if item.note else "") + detail
                            if not any(existing.note == item.note for existing in items):
                                self.notice.emit(f"ONLINE {item.parsed.series}: {resolver.last_diagnostic}")
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
            ffprobe = executable("ffprobe", self.ffmpeg_override)
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
                    # Detect changed A/V starts before publishing the output.
                    original_sync = probe_av_sync(item.source, ffprobe)
                    result_sync = probe_av_sync(temp, ffprobe)
                    sync_ok, sync_details = av_sync_report(original_sync, result_sync)
                    self.log.emit("SYNC  " + item.source.name + ": " + sync_details)
                    if not sync_ok:
                        raise RuntimeError("A/V-Syncprüfung fehlgeschlagen: " + sync_details)
                    if any(v is not None and abs(v) > 0.25 for v in original_sync.audio_video_deltas):
                        self.log.emit("HINWEIS: Die Quelle hat bereits einen Audio/Video-Startversatz. "
                                      "ReelShift korrigiert den Ton nicht blind.")
                    # Metadata start_time alone is insufficient. The first
                    # actual decoded video frame might be a minute late.
                    source_start = probe_decode_start(item.source, ffprobe)
                    output_start = probe_decode_start(temp, ffprobe)
                    startup_ok, startup_details = validate_decode_start(source_start, output_start)
                    self.log.emit("STARTUP " + item.source.name + ": " + startup_details)
                    if not startup_ok:
                        raise RuntimeError("Videostart-Prüfung fehlgeschlagen: " + startup_details)
                    # Reject streams that report H.264 but omit essential profile,
                    # pixel format or dimensions (common when codec initialization fails).
                    codec_details = probe_video_codec(temp, ffprobe)
                    if not codec_details.usable_h264:
                        raise RuntimeError(
                            "Ausgabe-H.264 nicht vollständig erkennbar: "
                            f"Profil={codec_details.profile or '?'}, "
                            f"Pixel={codec_details.pixel_format or '?'}, "
                            f"Auflösung={codec_details.width}x{codec_details.height}. "
                            f"FFprobe: {codec_details.probe_warnings[:240]}"
                        )
                    decoded = decode_video_sample(temp, ffmpeg)
                    self.log.emit(
                        f"DECODE {item.source.name}: erste 12s, "
                        f"{decoded.frames} Frames, FFmpeg-Exit {decoded.returncode}"
                    )
                    if not decoded.passed:
                        raise RuntimeError(
                            "Software-Decodierung der ersten 12s fehlgeschlagen: "
                            + (decoded.errors[-600:] or f"{decoded.frames} Frames")
                        )
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


class RenameWorker(QObject):
    """Rename files in-place without decoding, remuxing or rewriting contents."""
    file_state = Signal(int, str)
    file_progress = Signal(int, float, str, str)
    log = Signal(str)
    complete = Signal(int, int, int)
    finished = Signal()

    def __init__(self, items: list[VideoItem]) -> None:
        super().__init__()
        self.items = items
        self.cancelled = threading.Event()
        self.running = threading.Event()
        self.running.set()

    def pause(self) -> None:
        self.running.clear()

    def resume(self) -> None:
        self.running.set()

    def cancel(self) -> None:
        self.cancelled.set()
        self.running.set()

    @Slot()
    def run(self) -> None:
        done = failed = skipped = 0
        try:
            from .engine import rename_conflicts
            errors = rename_conflicts(self.items)
            if errors:
                self.log.emit("UMBENENNEN ABGEBROCHEN: " + " | ".join(errors[:10]))
                failed = len(errors)
                return
            for index, item in enumerate(self.items):
                self.running.wait()
                if self.cancelled.is_set():
                    break
                if item.status.startswith("Fehler"):
                    skipped += 1
                    continue
                source = item.source
                target = source.with_name(item.target_name)
                if source == target:
                    skipped += 1
                    self.file_state.emit(index, "Unverändert")
                    self.file_progress.emit(index, 100., "–", "00:00")
                    continue
                try:
                    if not source.is_file() or (target.exists() and not source.samefile(target)):
                        raise FileExistsError("Quelldatei fehlt oder Zieldatei existiert")
                    source.rename(target)
                    done += 1
                    self.file_state.emit(index, "Umbenannt")
                    self.file_progress.emit(index, 100., "–", "00:00")
                    self.log.emit(f"RENAME {source.name} -> {target.name}")
                except OSError as exc:
                    failed += 1
                    self.file_state.emit(index, "Fehler")
                    self.log.emit(f"RENAME FEHLER {source.name}: {exc}")
        except Exception as exc:
            failed += 1
            self.log.emit("UMBENENNEN FEHLGESCHLAGEN: " + str(exc))
        finally:
            self.complete.emit(done, failed, skipped)
            self.finished.emit()
