"""ReelShift dark-mode desktop application."""
from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QThread
from PySide6.QtGui import QCloseEvent, QFont
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout, QGridLayout,
    QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QSpinBox,
    QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .engine import VideoItem, executable
from .naming import safe_filename
from .workers import EncodeWorker, ScanWorker

STYLE = """
QWidget { background: #10151f; color: #e7edf7; font-family: 'Segoe UI'; font-size: 10pt; }
QGroupBox { border: 1px solid #283446; border-radius: 10px; margin-top: 13px;
            padding: 17px 10px 10px; font-weight: 600; background: #171f2d; }
QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 6px; color: #9cb9e9; }
QLineEdit, QSpinBox, QComboBox, QPlainTextEdit, QTableWidget {
    border: 1px solid #35455b; border-radius: 6px; padding: 7px;
    background: #0c121b; selection-background-color: #2855ad; }
QLineEdit:focus, QSpinBox:focus { border-color: #5c92ea; }
QPushButton { background: #273954; padding: 9px 15px; border: 1px solid #3c5270;
              border-radius: 7px; font-weight: 600; }
QPushButton:hover { background: #345077; }
QPushButton:disabled { color: #6b798c; background: #1a2533; border-color: #273343; }
QPushButton#primary { background: #2864dc; border-color: #4481ef; color: white; }
QPushButton#primary:hover { background: #3f7be7; }
QPushButton#danger { background: #5d303c; border-color: #9a4654; }
QProgressBar { border: 1px solid #35455b; border-radius: 5px; text-align: center;
               background: #0c121b; min-height: 17px; }
QProgressBar::chunk { background: #397de8; border-radius: 4px; }
QHeaderView::section { background: #213044; padding: 7px; color: #cbd8f2; border: 0; }
QTableWidget { gridline-color: #233044; alternate-background-color: #171e29; }
QTableWidget::item { padding: 3px; }
QCheckBox { spacing: 8px; }
QSplitter::handle { background: #26384b; height: 5px; }
"""


class ReelShiftWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ReelShift — Transcode · Rename · Organize")
        self.resize(1220, 840)
        self.items: list[VideoItem] = []
        self.progresses: list[float] = []
        self.scan_thread: QThread | None = None
        self.scan_worker: ScanWorker | None = None
        self.encode_thread: QThread | None = None
        self.encode_worker: EncodeWorker | None = None
        self.encoding = False
        self.scanning = False
        self.paused = False
        self.settings = QSettings("ReelShift", "ReelShift")
        self._setup()
        self._restore()
        self._set_busy()

    def _setup(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)
        brand = QLabel("REELSHIFT")
        brand.setStyleSheet("font-size: 23pt; font-weight: 800; color: #73a8ff; letter-spacing: 3px;")
        tagline = QLabel("Deine MKV-Mediathek. Neu codiert, sauber benannt, bereit für den Fernseher.")
        tagline.setStyleSheet("color: #9bacc5; padding-bottom: 4px;")
        layout.addWidget(brand)
        layout.addWidget(tagline)

        sources = QGroupBox("01  QUELLE UND ZIEL")
        grid = QGridLayout(sources)
        grid.addWidget(QLabel("Quellordner"), 0, 0)
        self.source = QLineEdit()
        self.source.setPlaceholderText("Ordner mit deinen MKV-Dateien")
        grid.addWidget(self.source, 0, 1)
        src_browse = QPushButton("Durchsuchen …")
        src_browse.clicked.connect(self._choose_source)
        grid.addWidget(src_browse, 0, 2)
        grid.addWidget(QLabel("Zielordner"), 1, 0)
        self.target = QLineEdit()
        self.target.setPlaceholderText("Separater Ausgabeordner (Originale bleiben erhalten)")
        grid.addWidget(self.target, 1, 1)
        target_browse = QPushButton("Durchsuchen …")
        target_browse.clicked.connect(self._choose_target)
        grid.addWidget(target_browse, 1, 2)
        grid.addWidget(QLabel("Wildcards"), 2, 0)
        self.pattern = QLineEdit("*.mkv")
        self.pattern.setToolTip("Mehrere Muster mit ; trennen, z. B. Vikings*;*S01E*.mkv")
        grid.addWidget(self.pattern, 2, 1)
        self.recursive = QCheckBox("Unterordner")
        grid.addWidget(self.recursive, 2, 2)
        layout.addWidget(sources)

        options = QGroupBox("02  KONVERTIERUNG UND EPISODENTITEL")
        opts = QGridLayout(options)
        self.encoder = QComboBox()
        self.encoder.addItems(["NVIDIA NVENC (GPU)", "libx264 (CPU)"])
        self.quality = QSpinBox()
        self.quality.setRange(16, 32)
        self.quality.setValue(22)
        self.quality.setToolTip("Kleiner = bessere Qualität und größere Datei. 20–23 als Startwert.")
        opts.addWidget(QLabel("Encoder"), 0, 0)
        opts.addWidget(self.encoder, 0, 1)
        opts.addWidget(QLabel("Qualität (CQ/CRF)"), 0, 2)
        opts.addWidget(self.quality, 0, 3)
        self.aac = QCheckBox("Tonspuren in AAC-Stereo umwandeln (sonst Originalton behalten)")
        self.force = QCheckBox("Auch kompatibles H.264 neu codieren")
        opts.addWidget(self.aac, 1, 0, 1, 2)
        opts.addWidget(self.force, 1, 2, 1, 2)
        self.lookup = QCheckBox("Fehlende Episodentitel online ergänzen")
        self.lookup.setChecked(True)
        opts.addWidget(self.lookup, 2, 0, 1, 2)
        self.token = QLineEdit(os.environ.get("TMDB_READ_ACCESS_TOKEN") or os.environ.get("TMDB_API_KEY", ""))
        self.token.setEchoMode(QLineEdit.EchoMode.Password)
        self.token.setPlaceholderText("Optional: TMDb API-Key / Read Access Token für deutsche Titel")
        self.token.setToolTip("Nicht gespeichert. Ohne Schlüssel: TVmaze (meist englische Titel).")
        opts.addWidget(self.token, 2, 2, 1, 2)
        opts.addWidget(QLabel("FFmpeg (optional)"), 3, 0)
        self.ffmpeg_path = QLineEdit()
        self.ffmpeg_path.setPlaceholderText("Leer = PATH; alternativ ffmpeg.exe wählen (ffprobe.exe daneben)")
        opts.addWidget(self.ffmpeg_path, 3, 1, 1, 2)
        ff_browse = QPushButton("ffmpeg.exe …")
        ff_browse.clicked.connect(self._choose_ffmpeg)
        opts.addWidget(ff_browse, 3, 3)
        layout.addWidget(options)

        actions = QHBoxLayout()
        self.scan_btn = QPushButton("Dateien scannen & Namen prüfen")
        self.scan_btn.clicked.connect(self.start_scan)
        self.start_btn = QPushButton("▶  Batch starten")
        self.start_btn.setObjectName("primary")
        self.start_btn.clicked.connect(self.start_encode)
        self.pause_btn = QPushButton("⏸  Pause")
        self.pause_btn.clicked.connect(self.toggle_pause)
        self.cancel_btn = QPushButton("■  Abbrechen")
        self.cancel_btn.setObjectName("danger")
        self.cancel_btn.clicked.connect(self.cancel_encode)
        actions.addWidget(self.scan_btn)
        actions.addStretch()
        actions.addWidget(self.start_btn)
        actions.addWidget(self.pause_btn)
        actions.addWidget(self.cancel_btn)
        layout.addLayout(actions)

        splitter = QSplitter(Qt.Orientation.Vertical)
        queue = QWidget()
        queue_layout = QVBoxLayout(queue)
        queue_layout.setContentsMargins(0, 0, 0, 0)
        self.queue_label = QLabel("03  WARTESCHLANGE — Erst scannen, dann Ausgabenamen bei Bedarf per Doppelklick ändern")
        self.queue_label.setStyleSheet("color: #adc7f0; font-weight: bold;")
        queue_layout.addWidget(self.queue_label)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Quelldatei", "Video", "Zieldatei (editierbar)", "Dauer", "Fortschritt", "Status / Metadaten"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        for col in (1, 3, 4):
            self.table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemChanged.connect(self._edited_name)
        queue_layout.addWidget(self.table)
        splitter.addWidget(queue)
        logs = QWidget()
        logs_layout = QVBoxLayout(logs)
        logs_layout.setContentsMargins(0, 0, 0, 0)
        logs_layout.addWidget(QLabel("PROTOKOLL"))
        self.log_box = QPlainTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.document().setMaximumBlockCount(1200)
        logs_layout.addWidget(self.log_box)
        splitter.addWidget(logs)
        splitter.setSizes([460, 125])
        layout.addWidget(splitter, 1)

        bottom = QHBoxLayout()
        self.summary = QLabel("Bereit. FFmpeg + FFprobe erforderlich.")
        bottom.addWidget(self.summary, 2)
        self.total = QProgressBar()
        self.total.setRange(0, 100)
        self.total.setValue(0)
        bottom.addWidget(self.total, 3)
        layout.addLayout(bottom)

    def _restore(self) -> None:
        for name, widget in (("source", self.source), ("target", self.target),
                             ("pattern", self.pattern), ("ffmpeg", self.ffmpeg_path)):
            old = self.settings.value(name, "")
            if old:
                widget.setText(str(old))
        for name, widget in (("recursive", self.recursive), ("lookup", self.lookup),
                             ("aac", self.aac), ("force", self.force)):
            val = self.settings.value(name)
            if val is not None:
                widget.setChecked(str(val).lower() in ("true", "1"))
        self.quality.setValue(int(self.settings.value("quality", 22)))
        self.encoder.setCurrentIndex(int(self.settings.value("encoder", 0)))

    def _save(self) -> None:
        for name, widget in (("source", self.source), ("target", self.target),
                             ("pattern", self.pattern), ("ffmpeg", self.ffmpeg_path)):
            self.settings.setValue(name, widget.text())
        for name, widget in (("recursive", self.recursive), ("lookup", self.lookup),
                             ("aac", self.aac), ("force", self.force)):
            self.settings.setValue(name, widget.isChecked())
        self.settings.setValue("quality", self.quality.value())
        self.settings.setValue("encoder", self.encoder.currentIndex())

    def _choose_source(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Quellordner auswählen", self.source.text())
        if path:
            self.source.setText(path)
            if not self.target.text() or not Path(self.target.text()).exists():
                folder = Path(path)
                self.target.setText(str(folder.parent / (folder.name + "_ReelShift")))

    def _choose_target(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Zielordner auswählen", self.target.text() or self.source.text())
        if path:
            self.target.setText(path)

    def _choose_ffmpeg(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "ffmpeg.exe auswählen", "", "FFmpeg (ffmpeg.exe);;Alle Dateien (*)")
        if path:
            self.ffmpeg_path.setText(path)

    def _paths(self) -> tuple[Path, Path]:
        src = Path(self.source.text().strip().strip('"')).expanduser()
        dst_text = self.target.text().strip().strip('"')
        if not self.source.text().strip() or not src.is_dir():
            raise ValueError("Bitte einen gültigen Quellordner wählen.")
        if not dst_text:
            dst = src.parent / (src.name + "_ReelShift")
            self.target.setText(str(dst))
        else:
            dst = Path(dst_text).expanduser()
        if src.resolve().is_relative_to(dst.resolve()):
            raise ValueError("Zielordner darf weder die Quelle noch deren übergeordneter Ordner sein.")
        return src, dst

    def _set_busy(self) -> None:
        self.scan_btn.setEnabled(not (self.scanning or self.encoding))
        self.start_btn.setEnabled(not (self.scanning or self.encoding) and bool(self.items))
        self.pause_btn.setEnabled(self.encoding)
        self.cancel_btn.setEnabled(self.encoding)
        if not self.encoding:
            self.pause_btn.setText("⏸  Pause")
        for widget in (self.source, self.target, self.pattern, self.recursive,
                       self.ffmpeg_path, self.encoder, self.quality, self.aac,
                       self.force, self.lookup, self.token):
            widget.setEnabled(not (self.scanning or self.encoding))
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers if self.encoding or self.scanning
                                   else QTableWidget.EditTrigger.DoubleClicked | QTableWidget.EditTrigger.EditKeyPressed)

    def start_scan(self) -> None:
        try:
            src, dst = self._paths()
            executable("ffmpeg", self.ffmpeg_path.text().strip())
            executable("ffprobe", self.ffmpeg_path.text().strip())
        except (ValueError, FileNotFoundError) as exc:
            QMessageBox.warning(self, "ReelShift", str(exc))
            return
        self.items.clear()
        self.progresses.clear()
        self.table.setRowCount(0)
        self.total.setValue(0)
        self.scanning = True
        self._set_busy()
        self.log_box.appendPlainText("Scan gestartet …")
        self.scan_thread = QThread(self)
        self.scan_worker = ScanWorker(src, dst, self.pattern.text(), self.recursive.isChecked(),
                                      self.lookup.isChecked(), self.token.text(), self.ffmpeg_path.text().strip())
        self.scan_worker.moveToThread(self.scan_thread)
        self.scan_thread.started.connect(self.scan_worker.run)
        self.scan_worker.progress.connect(self._scan_progress)
        self.scan_worker.complete.connect(self._scan_complete)
        self.scan_worker.error.connect(self._scan_error)
        self.scan_worker.finished.connect(self.scan_thread.quit)
        self.scan_worker.finished.connect(self.scan_worker.deleteLater)
        self.scan_thread.finished.connect(self.scan_thread.deleteLater)
        self.scan_thread.finished.connect(self._scan_cleanup)
        self.scan_thread.start()

    def _scan_progress(self, index: int, total: int, name: str) -> None:
        self.summary.setText(f"Analysiere {index}/{total}: {name[:65]}")

    def _scan_complete(self, items: list[VideoItem]) -> None:
        self.items = items
        self.progresses = [0.] * len(items)
        self.table.blockSignals(True)
        self.table.setRowCount(len(items))
        for row, item in enumerate(items):
            for col, value in ((0, item.source.name), (1, item.codec.upper()),
                               (2, item.target_name), (3, f"{int(item.duration // 60)}:{int(item.duration % 60):02d}"),
                               (5, item.status + (" • " + item.note if item.note else ""))):
                cell = QTableWidgetItem(value)
                if col != 2:
                    cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row, col, cell)
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(0)
            self.table.setCellWidget(row, 4, bar)
        self.table.blockSignals(False)
        valid = sum(not x.status.startswith("Fehler") for x in items)
        self.summary.setText(f"{len(items)} MKVs gefunden, {valid} bereit. Zieldateinamen prüfen!")
        self.log_box.appendPlainText(f"Scan beendet: {valid}/{len(items)} Dateien bereit.")
        self.scanning = False
        self._set_busy()

    def _scan_error(self, message: str) -> None:
        self.scanning = False
        self._set_busy()
        self.summary.setText("Scan fehlgeschlagen")
        QMessageBox.warning(self, "Scan fehlgeschlagen", message)

    def _scan_cleanup(self) -> None:
        self.scan_thread = None
        self.scan_worker = None

    def _edited_name(self, cell: QTableWidgetItem) -> None:
        if cell.column() != 2 or self.encoding:
            return
        candidate = safe_filename(Path(cell.text().strip()).stem) + ".mkv"
        if candidate != cell.text():
            self.table.blockSignals(True)
            cell.setText(candidate)
            self.table.blockSignals(False)
        self.items[cell.row()].target_name = candidate

    def start_encode(self) -> None:
        if not self.items:
            return
        try:
            _, dst = self._paths()
            executable("ffmpeg", self.ffmpeg_path.text().strip())
            if dst.exists() and not dst.is_dir():
                raise ValueError("Zielpfad ist kein Verzeichnis.")
        except (ValueError, FileNotFoundError) as exc:
            QMessageBox.warning(self, "ReelShift", str(exc))
            return
        targets = [item.target_name.casefold() for item in self.items if not item.status.startswith("Fehler")]
        if len(targets) != len(set(targets)):
            QMessageBox.warning(self, "Namenskonflikt", "Zwei oder mehr Dateien haben denselben Zielnamen. Bitte in der Tabelle korrigieren.")
            return
        exists = sum((dst / item.target_name).exists() for item in self.items)
        if exists and QMessageBox.question(self, "Bereits vorhanden", f"{exists} Zieldatei(en) existieren bereits und werden übersprungen. Trotzdem starten?") != QMessageBox.StandardButton.Yes:
            return
        if any(item.hdr for item in self.items):
            if QMessageBox.warning(self, "HDR-Video erkannt", "Mindestens eine Datei ist HDR (PQ/HLG). ReelShift 0.1 wandelt die HDR-Farben NICHT korrekt nach SDR um. Diese Dateien können ausgewaschen aussehen. Trotzdem starten?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
                return
        self.progresses = [0.] * len(self.items)
        for row, item in enumerate(self.items):
            item.progress = 0
            if not item.status.startswith("Fehler"):
                self._write_state(row, "Wartet")
            bar = self.table.cellWidget(row, 4)
            if isinstance(bar, QProgressBar):
                bar.setValue(0)
        self.encoding = True
        self.paused = False
        self._set_busy()
        self.encode_thread = QThread(self)
        self.encode_worker = EncodeWorker(self.items, dst, self.ffmpeg_path.text().strip(),
                                          self.encoder.currentIndex() == 0, self.quality.value(),
                                          self.aac.isChecked(), self.force.isChecked())
        self.encode_worker.moveToThread(self.encode_thread)
        self.encode_thread.started.connect(self.encode_worker.run)
        self.encode_worker.file_state.connect(self._write_state)
        self.encode_worker.file_progress.connect(self._file_progress)
        self.encode_worker.log.connect(self.log_box.appendPlainText)
        self.encode_worker.complete.connect(self._encode_complete)
        self.encode_worker.finished.connect(self.encode_thread.quit)
        self.encode_worker.finished.connect(self.encode_worker.deleteLater)
        self.encode_thread.finished.connect(self.encode_thread.deleteLater)
        self.encode_thread.finished.connect(self._encode_cleanup)
        self.encode_thread.start()

    def _write_state(self, row: int, state: str) -> None:
        if 0 <= row < len(self.items):
            old = self.items[row]
            self.table.item(row, 5).setText(state + (" • " + old.note if old.note else ""))
            if state in ("Fertig", "Fehler", "Abgebrochen") or state.startswith("Übersprungen"):
                self.progresses[row] = 100. if state == "Fertig" or state.startswith("Übersprungen") else self.progresses[row]
                self._update_total()

    def _file_progress(self, row: int, percent: float, speed: str, eta: str) -> None:
        self.progresses[row] = percent
        bar = self.table.cellWidget(row, 4)
        if isinstance(bar, QProgressBar):
            bar.setValue(int(percent))
        self.summary.setText(f"{row + 1}/{len(self.items)}  •  {self.items[row].source.name[:48]}  •  {speed}  •  ETA {eta}")
        self._update_total()

    def _update_total(self) -> None:
        durations = [max(1., item.duration) for item in self.items]
        value = (sum(w * x for w, x in zip(durations, self.progresses)) / sum(durations)) if durations else 0
        self.total.setValue(int(value))

    def toggle_pause(self) -> None:
        worker = self.encode_worker
        if not worker:
            return
        self.paused = not self.paused
        if self.paused:
            worker.pause()
            self.pause_btn.setText("▶  Fortsetzen")
            self.summary.setText("Pausiert")
        else:
            worker.resume()
            self.pause_btn.setText("⏸  Pause")

    def cancel_encode(self) -> None:
        if self.encode_worker:
            self.encode_worker.cancel()
            self.cancel_btn.setEnabled(False)
            self.summary.setText("Abbruch läuft …")

    def _encode_complete(self, done: int, failed: int, skipped: int) -> None:
        self.encoding = False
        self.paused = False
        self._set_busy()
        self.summary.setText(f"Fertig: {done} erfolgreich, {failed} Fehler, {skipped} übersprungen.")
        self.log_box.appendPlainText(f"BATCH: {done} OK, {failed} Fehler, {skipped} übersprungen.")

    def _encode_cleanup(self) -> None:
        self.encode_thread = None
        self.encode_worker = None

    def closeEvent(self, event: QCloseEvent) -> None:
        if (self.scan_thread and self.scan_thread.isRunning()) or (self.encode_thread and self.encode_thread.isRunning()):
            QMessageBox.information(self, "ReelShift", "Scan/Konvertierung läuft noch. Laufenden Batch zuerst abbrechen bzw. Scan beenden.")
            event.ignore()
            return
        self._save()
        event.accept()


def main() -> None:
    import sys
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    app.setFont(QFont("Segoe UI", 10))
    window = ReelShiftWindow()
    window.show()
    sys.exit(app.exec())
