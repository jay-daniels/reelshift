# ReelShift

**Transcode. Rename. Organize.** Desktop batch tool for MKV files on Windows 10/11.

ReelShift turns HEVC/H.265 videos into H.264/AVC for older playback devices, cleans TV episode release filenames, and can look up missing titles online. It is intended for media you own or are authorized to process.

## Features

- Two modes: encode to new H.264 MKVs **or rename source MKVs in place without FFmpeg**, both with filename preview. Dark-mode PySide6 GUI with wildcard patterns (`Vikings*;*S01E*.mkv`), recursive search, queue and log.
- NVIDIA NVENC H.264 hardware encoding (great for RTX cards); libx264 CPU alternative; adjustable CQ/CRF quality.
- FFprobe inspects codecs/duration. Already compatible 8-bit H.264 can be remuxed without video quality loss; all runs produce separate MKV files.
- FFmpeg `-progress`-based per-file and overall progress, speed and approximate remaining time; pause, resume and cancel.
- Optional AAC stereo transcoding; otherwise original audio, subtitles, chapters and container attachments are kept when supported by FFmpeg.
- Detects `S01E01` and `1x01`; removes release tags from names and looks up **missing** episode titles from free TVmaze (mostly English), or TMDb with your own key/token (German requested).
- Originals are never deleted; existing target files are skipped, and output is first written to a temporary file.

### Example

`Vikings.-.S01E01.-.Initiationsriten.German.AC3.DL.1080p.BluRay.x265-FuN.mkv`

becomes

`Vikings - S01E01 - Initiationsriten.mkv`

## Install and run

1. Install [Python 3.10+](https://www.python.org/downloads/) and [FFmpeg](https://ffmpeg.org/download.html), including **ffprobe**.
   Windows example: `winget install Gyan.FFmpeg` (restart the terminal after installing), or place `ffmpeg.exe` and `ffprobe.exe` in the same folder and select `ffmpeg.exe` in the GUI.
2. From the repository directory:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -e .
   python -m reelshift
   ```

3. Choose input/output folders, optional semicolon-delimited wildcards, scan, **review/edit proposed names** by double-clicking the output filename, and click **Batch starten**.

### Windows .exe – lokal erstellen, ohne GitHub Actions

Es werden **keine GitHub-Actions-Runner** benötigt oder automatisch gestartet.

1. Repository auf deinen Windows-PC klonen oder als ZIP herunterladen und entpacken.
2. [Python 3.10+](https://www.python.org/downloads/) installieren (am einfachsten Python 3.10/3.12, falls noch nicht vorhanden). Internet wird beim ersten Build für PySide6 und PyInstaller benötigt.
3. Im Projektordner **`build-local.cmd` doppelklicken**. Das Skript legt `.venv` an, installiert die benötigten Pakete, führt die Unit-Tests aus und baut die EXE.
4. Nach erfolgreichem Build liegt **`dist\ReelShift.exe`** bereit. Du kannst sie durch Doppelklick starten.

Alternativ aus PowerShell:

```powershell
.\build-local.cmd
# Oder direkt, z. B. ohne Unit-Tests:
powershell -NoProfile -ExecutionPolicy Bypass -File .\build-local.ps1 -SkipTests -OpenOutput
```

Für den Betrieb werden **FFmpeg und FFprobe** separat benötigt (über den `PATH` oder per Auswahl in der GUI). Die EXE enthält die Python-/PySide6-Anwendung, **nicht** die FFmpeg-Binaries. Die EXE wird auf deinem eigenen Rechner erstellt; es wird kein GitHub-Kontingent verbraucht. **Die Originalvideos werden nicht gelöscht.**

Fehlersuche: Wenn Python nicht gefunden wird, `py -3.10 --version` im Terminal prüfen; bei fehlendem FFmpeg `winget install Gyan.FFmpeg` ausführen und die App neu starten.

## Arbeitsmodi

### Konvertieren – neues H.264-MKV

ReelShift schreibt in einen **separaten Zielordner**. Die Originaldateien bleiben erhalten. Der Encoder verwendet für neu encodiertes Video den Präsentationszeitablauf der Quelle, vermeidet H.264-B-Frames am Anfang und verschiebt bei Bedarf die Ausgabestreams gemeinsam auf nichtnegative Zeitstempel. **Nach jedem erfolgreichen FFmpeg-Lauf** vergleicht das Programm Audio- und Video-Startzeitstempel der Quelle und der temporären Ausgabe. Wenn sich ein A/V-Abstand um mehr als 150 ms ändert oder die Prüfwerte nicht verfügbar sind, wird die temporäre Datei verworfen statt als Erfolg veröffentlicht. Das kann keine Abspielprobleme, tatsächliche Lippen-Synchronität oder defekte Quellzeitstempel zuverlässig ausschließen.

**Wichtig:** Ein Fire TV kann auch an Bitrate, Audioformat oder Hardware-Decoding scheitern. Teste jede Änderung erst mit ein bis zwei Folgen. Alte Ausgaben werden nicht automatisch korrigiert; überprüfe und ersetze sie nach Bedarf separat. Überschrieben wird nichts.

### Nur umbenennen – ohne FFmpeg

Im Feld **Arbeitsmodus** „Nur umbenennen (direkt im Quellordner)“ wählen, Quellordner und Wildcards einstellen und **Dateien scannen & Namen prüfen**. Die Vorschau lässt sich manuell anpassen; fehlende Episodentitel können weiterhin über TVmaze/TMDb ergänzt werden. Anschließend **Dateien umbenennen** klicken und die Rückfrage bestätigen.

- Es wird **keine** Mediendatei decodiert, konvertiert, remuxt, kopiert oder gelöscht: Nur der Dateiname **am Originalspeicherort** wird geändert.
- Zielordner, Encoder und FFmpeg werden nicht gebraucht; sie sind in diesem Modus deaktiviert.
- Vorher werden Namenskollisionen und bereits vorhandene Dateien einschließlich Windows-typischer Groß-/Kleinschreibungsüberschneidungen geprüft. Bestehende andere Dateien werden nicht überschrieben.
- Ursprüngliche Dateinamen werden dabei geändert, es gibt noch keine automatische Undo-Funktion. Bei wichtigen Namen zuerst eine Kopie der Dateiliste sichern.
- Moduswechsel verwirft die alte Vorschau: nach dem Wechsel erneut scannen.

## Episode data

Online lookup sends only the recognized series name, season and episode to the enabled metadata provider. Disable the checkbox for fully offline renaming. TVmaze requires no key and generally has original/English titles. For possible German episode titles, enter your personal [TMDb](https://www.themoviedb.org/settings/api) API v3 key or API Read Access Token in the masked field. Alternatively set `TMDB_API_KEY` / `TMDB_READ_ACCESS_TOKEN` in your environment. The key/token is **not persisted** in settings or logged.

> Online matches are heuristic. Review them before starting, especially remakes, DVD-order episodes, specials and shows with duplicate names. TMDb may also return original-language titles if no German translation exists.

## Compatibility and limitations

- The **Fire TV Stick model and playback app** determine supported codecs, audio and subtitles. H.264 alone is no universal guarantee. MKV playback depends on the app, and some Fire TV players cannot decode DTS, TrueHD or PGS subtitles. Enable AAC stereo if your player cannot handle the source audio; this changes surround tracks to stereo. Subtitle streams are copied, not converted into text subtitles.
- **HDR-to-SDR tone mapping is not implemented in v0.1.** HDR sources trigger a warning before encoding; avoid converting HDR content until tone mapping is available.
- Encoding HEVC → AVC is lossy and usually increases file size at similar visual quality. Keep the originals until playback and quality are verified. NVENC may be faster but can yield larger files than slower CPU encoding.
- Only the first video stream is selected; audio/subtitle streams and attachments are mapped separately. No automatic disc navigation/BDMV ripping or DRM circumvention.
- A running scan can finish before the window closes; running encodes can be cancelled. Pausing suspends the FFmpeg process with `psutil`.
- Files with name conflicts are blocked at batch start; already-existing outputs are skipped rather than overwritten.

## Development

```powershell
python -m unittest discover -s tests -v
```

Built with Python, PySide6, FFmpeg/FFprobe, psutil, and TVmaze/TMDb web APIs.
