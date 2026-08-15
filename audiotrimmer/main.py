"""AudioTrimmer main window."""

from __future__ import annotations

import os
import threading
from pathlib import Path

from PySide6.QtCore import (
    QEasingCurve,
    QMetaObject,
    QObject,
    QPoint,
    QPropertyAnimation,
    QTimer,
    QUrl,
    Qt,
    Signal,
    Slot,
)
from PySide6.QtGui import QColor, QDragEnterEvent, QDropEvent, QFont, QKeySequence, QPainter, QPen, QShortcut
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .audio import AudioFile, compute_peaks, default_out_name, export_mp3, open_audio, SUPPORTED_EXT
from .config import load as load_config, save as save_config
from .widgets import WaveformWidget, fmt_ms

BG = "#101216"
PANEL = "#171a21"
PANEL_HOVER = "#1f2430"
PANEL_PRESSED = "#0d0f14"
ACCENT = "#ffb347"
SEL = "#5dd6b0"
TEXT = "#e6e8ee"
DIM = "#8a91a3"


STYLE = f"""
QMainWindow, QWidget {{ background: {BG}; color: {TEXT}; font: 10pt 'Segoe UI'; }}
QLabel#AppTitle {{ font: 700 15pt 'Segoe UI'; color: {ACCENT}; letter-spacing: 1px; }}
QLabel#FileLabel {{ color: {DIM}; font: 9pt 'Segoe UI'; }}
QLabel#Mono {{ font: 9pt 'Consolas'; color: {ACCENT}; }}
QLabel#Dim {{ color: {DIM}; font: 9pt 'Consolas'; }}
QPushButton {{ background: {PANEL}; color: {TEXT}; border: 1px solid #262c3a; border-radius: 8px; padding: 6px 14px; }}
QPushButton:hover {{ background: {PANEL_HOVER}; border-color: #333b4d; }}
QPushButton:pressed {{ background: {PANEL_PRESSED}; }}
QPushButton:disabled {{ color: #4a5060; }}
QPushButton#Export {{ background: {ACCENT}; color: #14161c; font-weight: 700; border: none; border-radius: 8px; padding: 7px 18px; }}
QPushButton#Export:hover {{ background: #ffc169; }}
QPushButton#Export:pressed {{ background: #e89b32; }}
QComboBox {{ background: {PANEL}; color: {TEXT}; border: 1px solid #262c3a; border-radius: 6px; padding: 4px 10px; }}
QComboBox:hover {{ border-color: #333b4d; }}
QComboBox QAbstractItemView {{ background: {PANEL}; color: {TEXT}; selection-background-color: #2c3a44; }}
QSlider::groove:horizontal {{ height: 4px; background: #262c3a; border-radius: 2px; }}
QSlider::handle:horizontal {{ width: 12px; height: 12px; margin: -4px 0; border-radius: 6px; background: {ACCENT}; }}
QWidget#TopBar {{ background: {PANEL}; border-bottom: 1px solid #1f2430; }}
"""


class TransportButton(QPushButton):
    """Flat circular-ish transport button with a painted icon."""

    def __init__(self, kind: str, parent=None):
        super().__init__(parent)
        self._kind = kind
        self._hover = False
        self.setFixedSize(42, 40)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setToolTip({"play": "Play", "pause": "Pause", "stop": "Stop", "jump": "Jump to selection start",
                            "selstart": "Set trim START at playhead", "selend": "Set trim END at playhead",
                            "tostart": "Skip to start of track", "toend": "Skip to end of track"}[kind])

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.rect().adjusted(1, 1, -1, -1)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(PANEL_HOVER if self._hover else PANEL))
        p.drawRoundedRect(r, 9, 9)
        p.setPen(QPen(QColor(SEL if self._kind in ("stop", "selstart", "jump") else ACCENT), 0))
        p.setBrush(QColor(SEL if self._kind in ("stop", "selstart", "jump") else ACCENT))
        cx = self.width() / 2
        cy = self.height() / 2
        if self._kind == "play":
            p.drawPolygon([QPoint(cx - 5, cy - 7), QPoint(cx - 5, cy + 7), QPoint(cx + 8, cy)])
        elif self._kind == "pause":
            p.drawRect(int(cx - 7), int(cy - 7), 4, 14)
            p.drawRect(int(cx + 3), int(cy - 7), 4, 14)
        elif self._kind == "stop":
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(int(cx - 7), int(cy - 7), 14, 14, 2, 2)
        elif self._kind == "jump":
            p.drawPolygon([QPoint(cx + 6, cy - 7), QPoint(cx - 4, cy), QPoint(cx + 6, cy + 7)])
            p.setPen(Qt.NoPen)
            p.drawRect(int(cx - 10), int(cy - 3), 2, 6)
        elif self._kind == "selstart":
            p.setPen(Qt.NoPen)
            p.drawRect(int(cx - 12), int(cy - 7), 2, 14)
            p.drawPolygon([QPoint(cx + 9, cy - 6), QPoint(cx - 3, cy), QPoint(cx + 9, cy + 6)])
        elif self._kind == "selend":
            p.setPen(Qt.NoPen)
            p.drawRect(int(cx + 10), int(cy - 7), 2, 14)
            p.drawPolygon([QPoint(cx - 9, cy - 6), QPoint(cx + 3, cy), QPoint(cx - 9, cy + 6)])
        elif self._kind == "tostart":
            p.setPen(Qt.NoPen)
            p.drawRect(int(cx - 13), int(cy - 7), 2, 14)
            p.drawRect(int(cx - 9), int(cy - 7), 2, 14)
            p.drawPolygon([QPoint(cx + 8, cy - 6), QPoint(cx - 3, cy), QPoint(cx + 8, cy + 6)])
        elif self._kind == "toend":
            p.setPen(Qt.NoPen)
            p.drawRect(int(cx + 7), int(cy - 7), 2, 14)
            p.drawRect(int(cx + 11), int(cy - 7), 2, 14)
            p.drawPolygon([QPoint(cx - 8, cy - 6), QPoint(cx + 3, cy), QPoint(cx - 8, cy + 6)])


class _Bridge(QObject):
    peak_done = Signal(int, int, int, object)  # gen, start_ms, end_ms, data
    export_done = Signal(bool, str)


class _Snackbar(QLabel):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)
        self.setWordWrap(True)
        self._effect.setOpacity(0.0)
        self.hide()
        self._anim = QPropertyAnimation(self._effect, b"opacity", self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.finished.connect(self._on_anim_done)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._fade_out)
        self._fading = False
        self._base = (
            "background:#1d2430;border:1px solid {c};border-radius:10px;"
            "padding:10px 16px;color:{t};font:10pt 'Segoe UI';"
        )

    def show_msg(self, text: str, kind: str = "") -> None:
        self._anim.stop()
        self._timer.stop()
        self._fading = False
        if kind == "ok":
            css = self._base.format(c="#3d9c6e", t="#7fe0ac")
        elif kind == "err":
            css = self._base.format(c="#e04444", t="#ff9a9a")
        else:
            css = self._base.format(c="#2c3340", t="#e6e8ee")
        self.setStyleSheet(css)
        self.setText(text.strip())
        self.adjustSize()
        self._place()
        if self.isHidden():
            self._effect.setOpacity(0.0)
            self.show()
        self._anim.setStartValue(self._effect.opacity())
        self._anim.setEndValue(1.0)
        self._anim.start()
        self._timer.start(3400)

    def _place(self) -> None:
        r = self.parent().rect()
        self.move(r.right() - self.width() - 16, 70)

    def _fade_out(self) -> None:
        self._fading = True
        self._anim.setStartValue(self._effect.opacity())
        self._anim.setEndValue(0.0)
        self._anim.start()

    def _on_anim_done(self) -> None:
        if self._fading:
            self.hide()
            self._effect.setOpacity(0.0)
            self._fading = False


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AudioTrimmer")
        self.resize(980, 580)
        self.setMinimumSize(820, 480)
        self.setAcceptDrops(True)
        self.setStyleSheet(STYLE)
        self.setWindowIcon(self._make_logo())

        self._audio: AudioFile | None = None
        self._cfg = load_config()
        self._peak_gen = 0
        self._peak_cache: dict[tuple[int, int, int], list] = {}
        self._bridge = _Bridge()
        self._bridge.peak_done.connect(self._on_peaks_done)
        self._bridge.export_done.connect(self._on_export_done)

        self._player = QMediaPlayer(self)
        self._out = QAudioOutput(self)
        self._out.setVolume(0.7)
        self._player.setAudioOutput(self._out)
        self._player.positionChanged.connect(self._on_position)

        self._build_ui()
        self._snack = _Snackbar(self)

        QShortcut(QKeySequence("Space"), self, activated=self._toggle_play)
        QShortcut(QKeySequence(Qt.Key_Left), self, activated=lambda: self._nudge(-1000))
        QShortcut(QKeySequence(Qt.Key_Right), self, activated=lambda: self._nudge(1000))
        QShortcut(QKeySequence("Ctrl+O"), self, activated=self._open)
        QShortcut(QKeySequence("Ctrl+E"), self, activated=self._export)
        for seq in ("Ctrl+0", "Ctrl+="):
            QShortcut(QKeySequence(seq), self, activated=self._waveview.zoom_fit)

        self._set_status("Open an audio file or drop it here (m4a, mp3, wav, flac, ogg, opus, aac)")

    # ---- UI ---------------------------------------------------------------------

    def _make_logo(self):
        from PySide6.QtGui import QIcon, QPixmap

        pix = QPixmap(64, 64)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(ACCENT))
        p.drawRoundedRect(6, 6, 52, 52, 12, 12)
        p.setBrush(QColor("#14161c"))
        p.drawPolygon([QPoint(24, 20), QPoint(24, 44), QPoint(43, 32)])
        p.end()
        return QIcon(pix)

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # top bar
        top = QWidget()
        top.setObjectName("TopBar")
        top.setFixedHeight(64)
        tv = QHBoxLayout(top)
        tv.setContentsMargins(16, 10, 16, 10)
        title = QLabel("AudioTrimmer")
        title.setObjectName("AppTitle")
        tv.addWidget(title)
        tv.addSpacing(16)
        self._file_label = QLabel("no file loaded")
        self._file_label.setObjectName("FileLabel")
        tv.addWidget(self._file_label, 1)
        open_btn = QPushButton("Open…")
        open_btn.setShortcut("Ctrl+O")
        open_btn.clicked.connect(self._open)
        tv.addWidget(open_btn)
        self._btn_sel_start = TransportButton("selstart")
        self._btn_sel_end = TransportButton("selend")
        self._btn_sel_start.clicked.connect(self._set_trim_start)
        self._btn_sel_end.clicked.connect(self._set_trim_end)
        tv.addWidget(self._btn_sel_start)
        tv.addWidget(self._btn_sel_end)
        self._btn_to_start = TransportButton("tostart")
        self._btn_to_end = TransportButton("toend")
        self._btn_to_start.clicked.connect(self._skip_to_start)
        self._btn_to_end.clicked.connect(self._skip_to_end)
        tv.addWidget(self._btn_to_start)
        tv.addWidget(self._btn_to_end)
        gear = QPushButton("⚙")
        gear.setFixedSize(34, 34)
        gear.setFocusPolicy(Qt.NoFocus)
        gear.setToolTip("Settings")
        gear.clicked.connect(self._open_settings)
        tv.addWidget(gear)
        v.addWidget(top)

        # waveform
        self._waveview = WaveformWidget()
        self._waveview.selection_changed.connect(self._on_selection)
        self._waveview.pos_changed.connect(self._seek_playhead)
        self._waveview.play_requested.connect(self._play_from)
        v.addWidget(self._waveview, 1)

        # transport row
        row1 = QWidget()
        h1 = QHBoxLayout(row1)
        h1.setContentsMargins(16, 10, 16, 4)
        for text, fn in (("−", self._waveview.zoom_out), ("＋", self._waveview.zoom_in)):
            b = QPushButton(text)
            b.setFixedSize(30, 30)
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(fn)
            h1.addWidget(b)
        fit = QPushButton("⤢")
        fit.setFixedSize(30, 30)
        fit.setFocusPolicy(Qt.NoFocus)
        fit.clicked.connect(self._waveview.zoom_fit)
        fit.setToolTip("Fit whole file")
        h1.addWidget(fit)
        h1.addSpacing(14)
        self._time_label = QLabel("0:00.0 / 0:00.0")
        self._time_label.setObjectName("Mono")
        h1.addWidget(self._time_label)
        h1.addSpacing(14)
        vol_lbl = QLabel("♥")
        vol_lbl.setObjectName("Mono")
        h1.addWidget(vol_lbl)
        self._volume = QSlider(Qt.Horizontal)
        self._volume.setRange(0, 100)
        self._volume.setValue(70)
        self._volume.setFixedWidth(110)
        self._volume.setToolTip("Volume")
        self._volume.valueChanged.connect(lambda v: self._out.setVolume(v / 100))
        h1.addWidget(self._volume)
        h1.addStretch(1)
        self._btn_play = TransportButton("play")
        self._btn_pause = TransportButton("pause")
        self._btn_stop = TransportButton("stop")
        self._btn_jump = TransportButton("jump")
        self._btn_play.clicked.connect(self._toggle_play)
        self._btn_pause.clicked.connect(self._player.pause)
        self._btn_stop.clicked.connect(self._stop)
        self._btn_jump.clicked.connect(self._jump_to_sel_start)
        for b in (self._btn_play, self._btn_pause, self._btn_stop, self._btn_jump):
            h1.addWidget(b)
        v.addWidget(row1)

        # selection / export row
        row2 = QWidget()
        h2 = QHBoxLayout(row2)
        h2.setContentsMargins(16, 4, 16, 12)
        self._sel_label = QLabel("Selection: 0:00.0 – 0:00.0  ·  0:00.0")
        self._sel_label.setObjectName("Mono")
        h2.addWidget(self._sel_label)
        h2.addStretch(1)
        self._bitrate = QComboBox()
        self._bitrate.addItems(["128 kbps", "192 kbps", "320 kbps"])
        self._bitrate.setCurrentIndex(1)
        self._bitrate.setToolTip("MP3 bitrate")
        h2.addWidget(self._bitrate)
        self._export_btn = QPushButton("Export MP3")
        self._export_btn.setObjectName("Export")
        self._export_btn.clicked.connect(self._export)
        h2.addWidget(self._export_btn)
        v.addWidget(row2)

        self._update_labels()

    def resizeEvent(self, ev) -> None:
        super().resizeEvent(ev)
        if hasattr(self, "_snack"):
            self._snack._place()

    # ---- state ------------------------------------------------------------------

    def _set_status(self, text: str, kind: str = "") -> None:
        self._snack.show_msg(text, kind)

    def _update_labels(self) -> None:
        if not self._audio:
            self._file_label.setText("no file loaded")
            self._time_label.setText("0:00.0 / 0:00.0")
            self._sel_label.setText("Selection: 0:00.0 – 0:00.0  ·  0:00.0")
            self._export_btn.setEnabled(False)
            return
        a, b = self._waveview.selection()
        self._sel_label.setText(
            f"Selection: {fmt_ms(a)} – {fmt_ms(b)}  ·  {fmt_ms(b - a)}"
        )
        pos = self._player.position()
        dur = self._audio.duration_ms
        self._time_label.setText(f"{fmt_ms(pos, False)} / {fmt_ms(dur, False)}")
        self._export_btn.setEnabled(True)

    # ---- file loading ------------------------------------------------------------

    def _open(self) -> None:
        start_dir = Path(self._cfg.get("source") or "")
        if not start_dir.is_dir():
            start_dir = Path.home()
        path, _ = QFileDialog.getOpenFileName(
            self, "Open audio", str(start_dir),
            "Audio files (*.m4a *.mp3 *.wav *.flac *.ogg *.opus *.aac *.wma *.aiff *.aif);;All files (*)",
        )
        if path:
            self._load(path)

    def _open_settings(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Settings")
        dlg.setFixedWidth(520)
        form = QFormLayout(dlg)
        form.setLabelAlignment(Qt.AlignRight)
        src = QLineEdit(self._cfg.get("source", ""))
        out = QLineEdit(self._cfg.get("output", ""))
        src.setPlaceholderText("Folder with audio tracks")
        out.setPlaceholderText("Folder for exported MP3 files")

        def browse(line: QLineEdit) -> None:
            cur = Path(line.text() or Path.home())
            d = QFileDialog.getExistingDirectory(dlg, "Choose folder", str(cur if cur.is_dir() else Path.home()))
            if d:
                line.setText(d)

        src_row = QWidget()
        src_h = QHBoxLayout(src_row)
        src_h.setContentsMargins(0, 0, 0, 0)
        src_h.addWidget(src, 1)
        sb = QPushButton("Browse…")
        sb.setFocusPolicy(Qt.NoFocus)
        sb.clicked.connect(lambda: browse(src))
        src_h.addWidget(sb)
        out_row = QWidget()
        out_h = QHBoxLayout(out_row)
        out_h.setContentsMargins(0, 0, 0, 0)
        out_h.addWidget(out, 1)
        ob = QPushButton("Browse…")
        ob.setFocusPolicy(Qt.NoFocus)
        ob.clicked.connect(lambda: browse(out))
        out_h.addWidget(ob)
        form.addRow("Source:", src_row)
        form.addRow("Output:", out_row)
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.button(QDialogButtonBox.Ok).setText("Save")
        box.button(QDialogButtonBox.Cancel).setText("Cancel")
        box.accepted.connect(dlg.accept)
        box.rejected.connect(dlg.reject)
        form.addRow(box)
        if dlg.exec() != QDialog.Accepted:
            return
        for name, line in (("source", src), ("output", out)):
            path = Path(line.text().strip())
            if not path.is_dir():
                try:
                    path.mkdir(parents=True, exist_ok=True)
                except OSError as exc:
                    QMessageBox.warning(self, "Settings", f"Could not create folder:\n{path}\n\n{exc}")
                    return
            self._cfg[name] = str(path)
        save_config(self._cfg)
        self._set_status("Settings saved", "ok")

    def dragEnterEvent(self, e: QDragEnterEvent) -> None:
        urls = e.mimeData().urls()
        if urls and any(Path(url.toLocalFile()).suffix.lower() in SUPPORTED_EXT for url in urls):
            e.acceptProposedAction()

    def dropEvent(self, e: QDropEvent) -> None:
        for url in e.mimeData().urls():
            p = url.toLocalFile()
            if p and os.path.splitext(p)[1].lower() in SUPPORTED_EXT:
                self._load(p)
                break

    def _load(self, path: str) -> None:
        try:
            af = open_audio(path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Open failed", f"Could not load file:\n{path}\n\n{exc}")
            self._set_status(str(exc), "err")
            return
        self._audio = af
        self._player.stop()
        self._player.setSource(QUrl.fromLocalFile(af.path))
        self._waveview.set_duration(af.duration_ms)
        self._peak_cache.clear()
        self._file_label.setText(
            f"{af.filename}   ·   {af.duration_ms / 1000:.1f}s   ·   {af.frame_rate} Hz   ·   {af.channels} ch"
        )
        self._set_status(f"Loaded {af.filename}", "ok")
        self._update_labels()
        self._request_peaks()

    # ---- peaks ------------------------------------------------------------------

    def _visible_range(self):
        return self._waveview.visible_range()

    def _request_peaks(self) -> None:
        if not self._audio:
            return
        start, end = self._waveview.visible_range()
        buckets = self._waveview.buckets_needed()
        key = (start, end, buckets)
        if key in self._peak_cache:
            self._waveview.set_peaks(start, end, self._peak_cache[key])
            return
        self._peak_gen += 1
        gen = self._peak_gen
        seg = self._audio.segment

        def work():
            try:
                data = compute_peaks(seg, start, end, buckets)
            except Exception as exc:  # noqa: BLE001
                data = [(0.0, 0.0)] * buckets
                print("peaks error:", exc)
            self._bridge.peak_done.emit(gen, start, end, data)

        threading.Thread(target=work, daemon=True).start()

    @Slot(int, int, int, object)
    def _on_peaks_done(self, gen: int, start: int, end: int, data) -> None:
        buckets = self._waveview.buckets_needed()
        self._peak_cache[(start, end, buckets)] = data
        if len(self._peak_cache) > 24:
            self._peak_cache.pop(next(iter(self._peak_cache)))
        if gen == self._peak_gen:
            self._waveview.set_peaks(start, end, data)

    # ---- playback ----------------------------------------------------------------

    def _seek_playhead(self, ms: int) -> None:
        if not self._audio:
            return
        ms = max(0, min(ms, self._audio.duration_ms))
        self._player.setPosition(ms)
        self._update_labels()

    def _play_from(self, ms: int) -> None:
        if not self._audio:
            return
        self._player.setPosition(max(0, min(ms, self._audio.duration_ms)))
        self._player.play()
        self._waveview.set_position(self._player.position())

    def _toggle_play(self) -> None:
        if not self._audio:
            return
        if self._player.playbackState() == QMediaPlayer.PlayingState:
            self._player.pause()
            return
        pos = max(0, min(self._waveview.position(), self._audio.duration_ms))
        self._player.setPosition(pos)
        self._player.play()

    def _stop(self) -> None:
        if not self._audio:
            return
        self._player.stop()
        pos = self._waveview.position()
        self._player.setPosition(pos)
        self._waveview.set_position(pos)
        self._update_labels()

    def _jump_to_sel_start(self) -> None:
        if not self._audio:
            return
        a, _ = self._waveview.selection()
        self._player.setPosition(a)
        self._waveview.set_position(a)
        self._update_labels()

    def _set_trim_start(self) -> None:
        if not self._audio:
            return
        pos = max(0, min(self._player.position(), self._audio.duration_ms))
        a, b = self._waveview.selection()
        if pos > b:
            b = pos  # start pressed after end -> end follows the start
        self._waveview.set_selection(pos, b)
        self._update_labels()

    def _set_trim_end(self) -> None:
        if not self._audio:
            return
        pos = max(0, min(self._player.position(), self._audio.duration_ms))
        a, b = self._waveview.selection()
        if pos < a:
            a = pos  # end pressed before start -> end follows the start
        self._waveview.set_selection(a, pos)
        self._update_labels()

    def _skip_to_start(self) -> None:
        if not self._audio:
            return
        self._player.setPosition(0)
        self._waveview.set_position(0)
        self._waveview.ensure_visible(0)
        self._update_labels()

    def _skip_to_end(self) -> None:
        if not self._audio:
            return
        dur = self._audio.duration_ms
        self._player.setPosition(dur)
        self._waveview.set_position(dur)
        self._waveview.ensure_visible(dur)
        self._update_labels()

    def _nudge(self, delta: int) -> None:
        if not self._audio:
            return
        pos = max(0, min(self._player.position() + delta, self._audio.duration_ms))
        self._player.setPosition(pos)
        self._waveview.set_position(pos)
        self._update_labels()

    def _on_position(self, pos: int) -> None:
        self._waveview.set_position(pos)
        self._update_labels()

    def _on_selection(self, a: int, b: int) -> None:
        self._update_labels()
        self._waveview.set_position(self._player.position())

    # ---- export -----------------------------------------------------------------

    def _export(self) -> None:
        if not self._audio:
            return
        a, b = self._waveview.selection()
        if b - a < 50:
            QMessageBox.information(self, "Export", "Selection is too short to export.")
            return
        default = Path(default_out_name(self._audio.path))
        out_dir = Path(self._cfg.get("output") or "")
        if out_dir.is_dir():
            default = out_dir / default.name
        path, _ = QFileDialog.getSaveFileName(self, "Export MP3", str(default), "MP3 audio (*.mp3)")
        if not path:
            return
        bitrate = ["128k", "192k", "320k"][self._bitrate.currentIndex()]
        self._export_btn.setEnabled(False)
        self._set_status(f"Exporting {fmt_ms(a)} – {fmt_ms(b)} to MP3 ({bitrate})…")
        seg = self._audio.segment

        def work():
            try:
                export_mp3(seg, a, b, path, bitrate)
            except Exception as exc:  # noqa: BLE001
                self._bridge.export_done.emit(False, str(exc))
                return
            self._bridge.export_done.emit(True, path)

        threading.Thread(target=work, daemon=True).start()

    @Slot(bool, str)
    def _on_export_done(self, ok: bool, info: str) -> None:
        self._export_btn.setEnabled(True)
        if ok:
            self._set_status("Export finished", "ok")
            QMessageBox.information(self, "Export finished", f"Saved to:\n{info}")
        else:
            self._set_status("Export failed", "err")
            QMessageBox.critical(self, "Export failed", info)


def main() -> None:
    import sys

    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    app.setApplicationName("AudioTrimmer")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()