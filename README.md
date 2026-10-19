# ReelShift

**Transcode. Rename. Organize.** Desktop batch tool for MKV files on Windows 10/11.

ReelShift turns HEVC/H.265 videos into H.264/AVC for older playback devices, cleans TV episode release filenames, and can look up missing titles online. It is intended for media you own or are authorized to process.

## Features

- Two modes: encode to new H.264 MKVs **or rename source MKVs in place without FFmpeg**, both with filename preview. Dark-mode PySide6 GUI with wildcard patterns (`Vikings*;*S01E*.mkv`), recursive search, queue and log.
- NVIDIA NVENC H.264 hardware encoding (great for RTX cards); libx264 CPU alternative; adjustable CQ/CRF quality.
- FFprobe inspects codecs/duration. Already compatible 8-bit H.264 can be remuxed without video quality loss; all runs produce separate MKV files.
- FFmpeg `-progress`-based per-file and overall progress, speed and approximate remaining time; pause, resume and cancel.
- Optional AAC stereo transcoding; otherwise original audio, subtitles, chapters and container attachments are kept when supported by FFmpeg.
- Detects `S01E01` and `1x01`; cleans release tags and fills **German episode names without any key** using Wikipedia, with an offline 89-episode Vikings (2013) catalog. English names use free TVmaze; TMDb is only an optional German fallback.
- Originals are never deleted; existing target files are skipped, and output is first written to a temporary file.
- Resizable/reorderable queue columns with persistent widths, an adjustable queue/log divider and a custom icon in the GUI and local Windows EXE.

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

Im Feld **Arbeitsmodus** „Nur umbenennen (direkt im Quellordner)“ wählen, Quellordner und Wildcards einstellen und **Dateien scannen & Namen prüfen**. Die Vorschau lässt sich manuell anpassen; fehlende Episodentitel kommen auf Deutsch aus Wikipedia (ohne Key, für Vikings auch offline) und auf Englisch aus TVmaze. Anschließend **Dateien umbenennen** klicken und die Rückfrage bestätigen.

- Es wird **keine** Mediendatei decodiert, konvertiert, remuxt, kopiert oder gelöscht: Nur der Dateiname **am Originalspeicherort** wird geändert.
- Zielordner, Encoder und FFmpeg werden nicht gebraucht; sie sind in diesem Modus deaktiviert.
- Vorher werden Namenskollisionen und bereits vorhandene Dateien einschließlich Windows-typischer Groß-/Kleinschreibungsüberschneidungen geprüft. Bestehende andere Dateien werden nicht überschrieben.
- Ursprüngliche Dateinamen werden dabei geändert, es gibt noch keine automatische Undo-Funktion. Bei wichtigen Namen zuerst eine Kopie der Dateiliste sichern.
- Moduswechsel verwirft die alte Vorschau: nach dem Wechsel erneut scannen.

## Episodentitel ohne Registrierung

Bei **Titelsprache** stehen zwei kostenlose Optionen zur Verfügung:

- **Deutsch (Wikipedia, ohne Key)** — Voreinstellung. ReelShift nutzt die öffentlichen deutschen Wikipedia-Episodenlisten. Für die Originalserie **Vikings (2013)** ist ein überprüfter **Offline-Katalog aller 89 deutschen Episodentitel** enthalten. Für andere Serien sucht die Software zunächst deren Wikipedia-Episodenliste über die öffentliche MediaWiki-Schnittstelle. Das funktioniert nur, wenn es eine passend strukturierte deutsche Episodenliste gibt; es werden keine Übersetzungen erfunden.
- **Englisch (TVmaze, ohne Key)** — TVmaze als kostenlose englische Episodenquelle. Gleichnamige Serien werden nicht mehr anhand der höchsten numerischen ID ausgewählt: Vikings (2013, ID 29) war zuvor mit einer gleichnamigen BBC-Dokumentation (ID 1335) verwechselt worden.

Als **optionale Ersatzquelle** kann ein persönlicher TMDb-v3-Key/Read-Access-Token eingegeben werden. **Er ist für keine der Standardfunktionen nötig** und wird weder protokolliert noch in den Einstellungen gespeichert. Englisch benötigt nie einen TMDb-Key; im deutschen Modus wird TMDb nur probiert, wenn Wikipedia keinen Titel liefert.

Beispiel:

`Vikings.S02E01.German.AC3.DL.1080p.BluRay.x265-FuN.mkv`
wird mit Deutsch als
`Vikings - S02E01 - Bruderkrieg.mkv`
vorgeschlagen, ohne Netzwerkanfrage oder Anmeldung.

**Quellennachweis:** Deutscher Vikings-Katalog nach
[Wikipedia – Vikings (Fernsehserie)/Episodenliste](https://de.wikipedia.org/wiki/Vikings_(Fernsehserie)/Episodenliste)
(Stand 19. Oktober 2026; Wikipedia-Inhalte unter [CC BY-SA](https://creativecommons.org/licenses/by-sa/4.0/deed.de), siehe Artikel-/Versionsgeschichte).
Das Programm kennzeichnet die vorgeschlagene Quelle in der Statusspalte.

## GUI: Spalten, Startlayout und Icon

- Jede Spaltengrenze in der Kopfzeile kann mit der Maus gezogen werden.
- Spalten lassen sich am Spaltenkopf in eine andere Reihenfolge ziehen.
- Die Spaltenbreiten und ihre Reihenfolge werden über QSettings gespeichert.
- Der Trenner zwischen Warteschlange und Protokoll ist vertikal verschiebbar; die Tabelle hat eine Mindesthöhe, damit beim Programmstart nicht nur eine Folge sichtbar bleibt.
- Die Fenstergröße wird gespeichert; eine sinnvolle Erststartgröße ist konfiguriert.
- `tools/make_icon.py` erzeugt mit Pillow die mehrstufige Windows-`.ico`-Datei `assets/reelshift.ico`. `build-local.cmd` übernimmt das automatisch und bündelt das Icon in der fertigen EXE. **Keine GitHub Actions.**

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

Built with Python, PySide6, FFmpeg/FFprobe, psutil, Pillow (build-only), and the Wikipedia/TVmaze APIs (TMDb optional).


## Diagnostik: H.264-Profil oder Pixelformat fehlen

Wenn der Ton in VLC sofort startet, das Bild aber erst viel später erscheint,
sind **normale Startzeitstempel allein kein Beweis für eine korrekte MKV**.
Ein konkreter Diagnosebericht kann bei H.264 zwar `start_time=0` und einen
Keyframe bei Sekunde 0 zeigen, aber trotzdem **leere Felder für `profile`
und `pix_fmt`** enthalten. Das ist verdächtig, aber noch keine eindeutige
Ursachendiagnose.

Die neuere, nur lesende Diagnose zeigt zusätzlich die erkannten H.264-Parameter
(Profil, Pixelformat, Bildgröße, Level, Codec-Extradata), FFprobe-Warnungen
und einen **Software-Decodiertest der ersten 12 Sekunden** mit FFmpeg.
Originale und Ausgabe werden nicht verändert.

```powershell
cd "C:\Users\danie\Documents\Code\Apps\reelshift"
git pull
.\.venv\Scripts\python.exe -m reelshift.diagnose `
  "C:\Users\danie\Desktop\Vikings\Season1\Vikings - S01E01 - Initiationsriten.mkv" `
  "C:\Users\danie\Desktop\Vikings\Season1_ReelShift\Vikings - S01E01 - Initiationsriten.mkv" `
  --save "reelshift-sync-report.txt"
```

Der Diagnosebefehl braucht keinen EXE-Neubau. Zum Aktualisieren der GUI
weiterhin `.\build-local.cmd` verwenden. Die Ausgabeprüfung des
Konvertierungsmodus verwirft neuerdings temporäre Ergebnisse, bei denen
FFprobe kein gültiges H.264-8-Bit-Format oder keine Bildgröße ermitteln kann
oder die Software-Decodierung der ersten 12 Sekunden fehlschlägt.

**Achtung:** Diese Prüfungen *finden* bestimmte Fehler, aber reparieren
nicht die Ursache eines fehlerhaften H.264-Streams. Nach dem nächsten
Diagnosebericht den konkreten Encoderfehler eingrenzen, bevor weitere
ganze Staffeln konvertiert werden. Prüfe außerdem die VLC-Hardwaredecodierung,
falls FFmpeg die Datei problemlos decodiert.

## Ton läuft, Video kommt erst deutlich später (VLC/Fire TV)

Eine MKV kann normale FFprobe-Stream-Startzeitstempel besitzen, obwohl der
erste tatsächlich decodierbare Videoframe erst 60 Sekunden nach dem ersten
Audiopaket erscheint. Die alte Prüfung übersah diese Fälle. ReelShift
vergleicht nun zusätzlich die **PTS des ersten decodierbaren Videobilds**
mit dem **PTS des ersten Audiopakets**, jeweils für Quelle und Ergebnis.
Ändert sich dieser Abstand um mehr als 350 ms, wird die temporäre Datei
nicht als erfolgreiches Endergebnis veröffentlicht.

Diese Prüfung **verhindert eine unerkannte Freigabe** auffälliger Dateien;
sie behebt nicht zwangsläufig die zugrundeliegende FFmpeg-/Encoder-Ursache,
garantiert keine lippensynchrone Wiedergabe und repariert keine alten Dateien.
Bewahre die Originale auf und teste erst eine Folge, bevor du einen Batch startest.

Bereits konvertierte Folge ohne Änderung der MKV-Dateien vergleichen
(im Repository-Ordner; die Pfade durch deine tatsächlichen Dateipfade ersetzen):

```powershell
.\.venv\Scripts\python.exe -m reelshift.diagnose "D:\Videos\Original.mkv" "D:\Videos\Konvertiert.mkv" --save "reelshift-sync-report.txt"
```

Falls FFprobe nicht über den PATH gefunden wird, ergänze
`--ffprobe "D:\Tools\ffmpeg\bin\ffprobe.exe"`.
Der Bericht zeigt Stream-Metadaten und tatsächlich decodierbaren Videostart
nebeneinander. Er enthält Dateipfade; diese gegebenenfalls vor dem Teilen entfernen.

