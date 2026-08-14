"""Waveform widget with draggable trim handles, zoom and ruler."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QWidget

BG = QColor("#101216")
PANEL = QColor("#171a21")
ACCENT = QColor("#ffb347")
ACCENT2 = QColor("#ff8c42")
SEL = QColor("#5dd6b0")
SEL_DIM = QColor("#2c3a44")
TEXT = QColor("#e6e8ee")
DIM = QColor("#8a91a3")
GRID = QColor(255, 255, 255, 24)
HANDLE_STEP_CANDIDATES = (100, 200, 500, 1000, 2000, 5000, 10000, 20000, 30000, 60000, 120000, 300000, 600000)

HANDLE_W = 9
MIN_PPX = 0.5


def fmt_ms(ms: int, tenths: bool = True) -> str:
    ms = max(0, int(ms))
    h, rem = divmod(ms, 3600000)
    m, rem = divmod(rem, 60000)
    s, t = divmod(rem, 1000)
    if tenths:
        ti = f"{s}.{t // 100}"
    else:
        ti = f"{s:02d}"
    if h:
        return f"{h}:{m:02d}:{ti}"
    return f"{m}:{ti}"


class WaveformWidget(QWidget):
    selection_changed = Signal(int, int)
    pos_changed = Signal(int)
    play_requested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._duration = 0
        self._sel = (0, 0)
        self._pos = 0
        self._peaks: list[tuple[float, float]] = []
        self._peaks_start = 0
        self._peaks_end = 0
        self._view_start = 0
        self._ppx = 0.0  # ms per pixel; 0 => fit
        self._pad = 20.0  # horizontal gutter in px
        self._drag: str | None = None
        self._drag_anchor = 0
        self._move_sel_origin: tuple[int, int] | None = None
        self._pan_origin_x = 0.0
        self._pan_start_ms = 0.0
        self.setMinimumHeight(170)
        self.setMouseTracking(True)
        self.setCursor(Qt.ArrowCursor)

    # ---- public API ---------------------------------------------------------

    def set_duration(self, ms: int) -> None:
        self._duration = max(1, ms)
        third = int(self._duration / 3)
        self._sel = (third, min(self._duration, third + int(self._duration * 0.2)))
        self._pos = 0
        self._fit_view()

    def set_selection(self, a: int, b: int) -> None:
        self._sel = (max(0, a), min(self._duration, b))
        self._ensure_visible(min(self._sel), HANDLE_W * 2)

    def position(self) -> int:
        return self._pos

    def set_position(self, ms: int) -> None:
        self._pos = max(0, min(int(ms), self._duration))
        self.update()

    def set_peaks(self, start_ms: int, end_ms: int, data: list[tuple[float, float]]) -> None:
        self._peaks_start, self._peaks_end = start_ms, end_ms
        self._peaks = data
        self.update()

    def selection(self) -> tuple[int, int]:
        return self._sel

    def zoom_fit(self) -> None:
        self._fit_view()

    def zoom_in(self) -> None:
        center = self._ms_at(self.width() / 2)
        self._zoom_around(center, 1 / 2.2)

    def zoom_out(self) -> None:
        center = self._ms_at(self.width() / 2)
        self._zoom_around(center, 2.2)

    # ---- internals -------------------------------------------------------------

    def _fit_view(self) -> None:
        cw = max(self.width() - 2 * self._pad, 1)
        self._ppx = 0  # fit flag
        self._view_start = 0
        if self._duration > 0:
            self._ppx = self._duration / cw
        self.update()

    def _ms_at(self, x: float) -> float:
        return self._view_start + (x - self._pad) * self._ppx

    def _x_at(self, ms: float) -> float:
        return self._pad + (ms - self._view_start) / self._ppx

    def _zoom_around(self, anchor_ms: float, factor: float) -> None:
        if self._duration <= 0:
            return
        w = max(self.width(), 1)
        old_ppx = self._ppx or (self._duration / max(w - 2 * self._pad, 1))
        new_ppx = min(max(old_ppx * factor, MIN_PPX), self._duration / 20.0)
        anchor_x = (anchor_ms - self._view_start) / old_ppx
        self._view_start = max(0.0, anchor_ms - anchor_x * new_ppx)
        self._ppx = new_ppx
        self._ensure_visible(self._pos, 0)
        self.update()

    def _ensure_visible(self, ms: int, margin_px: float) -> None:
        if not self._ppx:
            return
        x = self._x_at(ms)
        w = self.width()
        if x < margin_px or x > w - margin_px:
            self._view_start = max(0.0, ms - 0.5 * w * self._ppx)
            self.update()

    def _is_fit(self) -> bool:
        cw = max(self.width() - 2 * self._pad, 1)
        return bool(self._ppx) and abs(self._ppx - self._duration / cw) < 1e-6 and self._view_start < 1e-6

    def _pan_by(self, dx_px: float) -> None:
        w = max(self.width() - 2 * self._pad, 1)
        span = w * self._ppx
        new_start = self._pan_start_ms - dx_px * self._ppx
        self._view_start = max(0.0, min(new_start, max(0.0, self._duration - span)))
        self.update()

    def _edge_pan(self, x: float) -> None:
        if self._is_fit():
            return
        w = self.width()
        edge = 26
        nudge_px = 0.0
        if x < edge:
            nudge_px = -(1 - x / edge) * 24
        elif x > w - edge:
            nudge_px = (1 - (w - x) / edge) * 24
        if nudge_px:
            span = w * self._ppx
            self._view_start = max(0.0, min(self._view_start + nudge_px * self._ppx, self._duration - span))

    def buckets_needed(self) -> int:
        return max(32, int(self.width() * 0.2))

    def visible_range(self) -> tuple[int, int]:
        if not self._ppx:
            return (0, self._duration)
        w = max(self.width() - 2 * self._pad, 1)
        a = int(self._view_start)
        b = int(self._view_start + w * self._ppx) + 1
        return (max(0, a), min(self._duration, b))

    def _handle_rects(self) -> tuple[QRectF | None, QRectF | None]:
        if not self._duration or self._sel[0] >= self._sel[1]:
            return (None, None)
        a, b = self._sel
        if not self._ppx:
            left = QRectF(max(self._pad, self._x_at(a) - HANDLE_W), 0, HANDLE_W, self.height())
            right = QRectF(min(self.width() - self._pad - HANDLE_W, self._x_at(b)), 0, HANDLE_W, self.height())
        else:
            left = QRectF(self._x_at(a) - HANDLE_W / 2, 0, HANDLE_W, self.height())
            right = QRectF(self._x_at(b) - HANDLE_W / 2, 0, HANDLE_W, self.height())
        return (left, right)

    def _hit_test(self, x: float) -> str:
        px = self._x_at(self._pos)
        if self._duration and -2 <= px <= self.width() + 2 and abs(x - px) <= 9:
            return "pos"
        left, right = self._handle_rects()
        if left and left.adjusted(-2, 0, 2, 0).contains(x, self.height() / 2):
            return "sel-l"
        if right and right.adjusted(-2, 0, 2, 0).contains(x, self.height() / 2):
            return "sel-r"
        a, b = self._sel
        if b > a and self._x_at(a) < x < self._x_at(b):
            return "move"
        return "seek"

    # ---- events ----------------------------------------------------------------

    def resizeEvent(self, ev) -> None:
        super().resizeEvent(ev)
        if self._duration:
            self.update()

    def wheelEvent(self, ev) -> None:
        if not self._duration:
            return
        anchor = self._ms_at(ev.position().x())
        factor = 1.18 if ev.angleDelta().y() > 0 else 1 / 1.18
        self._zoom_around(anchor, factor)

    def mousePressEvent(self, ev) -> None:
        if not self._duration:
            return
        x = ev.position().x()
        if ev.button() in (Qt.MiddleButton, Qt.RightButton):
            self._drag = "pan"
            self._pan_origin_x = x
            self._pan_start_ms = self._view_start
            self.setCursor(Qt.ClosedHandCursor)
            return
        mode = self._hit_test(x)
        self._drag = mode
        self._drag_anchor = int(self._ms_at(x))
        if mode == "move":
            self._move_sel_origin = (self._sel[0], self._drag_anchor)
            self.setCursor(Qt.SizeAllCursor)
        elif mode in ("sel-l", "sel-r"):
            self.setCursor(Qt.SizeHorCursor)
        elif mode == "pos":
            self.setCursor(Qt.SizeHorCursor)
        else:
            if not self._is_fit():
                self._drag = "pan?"
                self._pan_origin_x = x
                self._pan_start_ms = self._view_start
                self.setCursor(Qt.ClosedHandCursor)
            else:
                self._drag = None

    def mouseMoveEvent(self, ev) -> None:
        x = ev.position().x()
        if not self._duration:
            return
        if self._drag == "sel-l":
            ms = int(self._ms_at(x))
            a, b = self._sel
            if self._ppx:
                ms = max(0, min(ms, b - 1))
            else:
                ms = max(0, min(int(ms), b - 1))
            a = ms
            self._sel = (a, b)
            self.selection_changed.emit(*self._sel)
        elif self._drag == "sel-r":
            ms = int(self._ms_at(x))
            a, b = self._sel
            if self._ppx:
                ms = max(a + 1, min(ms, self._duration))
            else:
                ms = max(int(a + 1), min(int(ms), self._duration))
            self._sel = (a, ms)
            self.selection_changed.emit(*self._sel)
        elif self._drag == "move" and self._move_sel_origin:
            orig_a, orig_anchor = self._move_sel_origin
            a, b = self._sel
            delta = int(self._ms_at(x)) - orig_anchor
            w = b - a
            new_a = max(0, min(orig_a + delta, self._duration - w))
            self._sel = (new_a, new_a + w)
            self.selection_changed.emit(*self._sel)
        elif self._drag == "pos":
            pos = int(self._ms_at(x))
            self._pos = max(0, min(pos, self._duration))
            self.pos_changed.emit(self._pos)
        elif self._drag in ("pan", "pan?"):
            if self._drag == "pan?" and abs(x - self._pan_origin_x) <= 5:
                return
            self._drag = "pan"
            self._pan_by(x - self._pan_origin_x)
            self._pan_origin_x = x
            self._pan_start_ms = self._view_start
        else:
            mode = self._hit_test(x)
            cursors = {"sel-l": Qt.SizeHorCursor, "sel-r": Qt.SizeHorCursor, "move": Qt.SizeAllCursor, "pos": Qt.SizeHorCursor}
            self.setCursor(cursors.get(mode, Qt.OpenHandCursor if not self._is_fit() else Qt.ArrowCursor))
        if self._drag in ("sel-l", "sel-r", "move", "pos"):
            self._edge_pan(x)
        self.update()

    def mouseReleaseEvent(self, ev) -> None:
        self._drag = None
        self._move_sel_origin = None

    def mouseDoubleClickEvent(self, ev) -> None:
        if not self._duration:
            return
        self._sel = (0, self._duration)
        self.selection_changed.emit(*self._sel)
        self._fit_view()

    # ---- drawing ---------------------------------------------------------------

    def paintEvent(self, ev) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), BG)

        if not self._duration:
            p.setPen(QPen(DIM))
            p.setFont(QFont("Segoe UI", 13))
            p.drawText(self.rect(), Qt.AlignCenter, "Open an audio file or drop it here")
            return

        mid = h / 2
        amp = h / 4 - 8

        # grid + ruler
        step = self._ruler_step()
        p.setFont(QFont("Consolas", 8))
        fm = QFontMetrics(p.font())
        tick_h = 5
        first = int(self._view_start // step) * step if self._ppx else 0
        last = int((self._view_start + (w - 2 * self._pad) * self._ppx) if self._ppx else self._duration)
        x = self._x_at(first)
        t = first
        while x <= w and t <= last:
            p.setPen(QPen(GRID, 1))
            p.drawLine(int(x), 0, int(x), h - tick_h - 12)
            p.setPen(QPen(DIM))
            label = fmt_ms(t, tenths=False)
            p.drawText(QRectF(int(x) - 30, h - 11, 60, 10), Qt.AlignCenter, label)
            t += step
            x += step / self._ppx if self._ppx else step / (self._duration / max(w, 1))

        # selection shading
        a, b = self._sel
        if b > a:
            ax = self._x_at(a)
            bx = self._x_at(b)
            p.fillRect(QRectF(ax, 0, bx - ax, h - 13), QColor(SEL_DIM.red(), SEL_DIM.green(), SEL_DIM.blue(), 150))

        # waveform
        self._paint_peaks(p, mid, amp, w, h)

        # selection border + handles
        if b > a:
            ax = self._x_at(a)
            bx = self._x_at(b)
            pen = QPen(SEL, 1.4)
            p.setPen(pen)
            p.drawLine(int(ax), 4, int(ax), h - 13)
            p.drawLine(int(bx), 4, int(bx), h - 13)
            self._paint_handle(p, ax, w, h, "l")
            self._paint_handle(p, bx, w, h, "r")

        # playhead
        if self._pos >= 0:
            px = self._x_at(self._pos)
            if 0 <= px <= w:
                p.setPen(QPen(QColor("#ffffff") if not (a < self._pos < b) else SEL, 1.6))
                p.drawLine(int(px), int(14), int(px), h - 13)
                p.setPen(Qt.NoPen)
                p.setBrush(QBrush(ACCENT))
                p.drawPolygon([QPointF(px - 5, 2), QPointF(px + 5, 2), QPointF(px, 14)])

    def _paint_peaks(self, p: QPainter, mid: float, amp: float, w: int, h: int) -> None:
        if not self._peaks:
            return
        v_span = self._peaks_end - self._peaks_start
        if v_span <= 0:
            return
        start_ms = self._view_start if self._ppx else 0
        end_ms = self._view_start + ((w - 2 * self._pad) * self._ppx) if self._ppx else self._duration
        p1 = start_ms / max(1, v_span)
        p2 = max(p1, end_ms / max(1, v_span))
        n = len(self._peaks)
        lo_i = max(0, int(p1 * n))
        hi_i = min(n, int(p2 * n) + 1)
        px_per_bucket = w / max(1, hi_i - lo_i)

        a, b = self._sel
        sel_pen = QPen(SEL, 1.0)
        dim_pen = QPen(QColor(ACCENT.red(), ACCENT.green(), ACCENT.blue(), 130), 1.0)

        seg_len = hi_i - lo_i
        cols = max(16, int(w / 12))
        stride = max(1, seg_len // cols)
        for i in range(lo_i, hi_i, stride):
            lo_b, hi_b = i, min(i + stride, hi_i)
            mn = min((self._peaks[k][0] for k in range(lo_b, hi_b)), default=0.0)
            mx = max((self._peaks[k][1] for k in range(lo_b, hi_b)), default=0.0)
            t0 = self._peaks_start + (lo_b / n) * v_span
            t1 = self._peaks_start + (hi_b / n) * v_span
            x0 = self._x_at(t0)
            x1 = self._x_at(t1)
            if x1 < -2 or x0 > w + 2:
                continue
            in_sel = t1 > a and t0 < b
            p.setPen(sel_pen if in_sel else dim_pen)
            y_top = mid - max(mx, -mn) * amp
            y_bot = mid + max(mx, -mn) * amp
            p.drawLine(int(x0), int(y_top), int(x0), int(y_bot))

    def _paint_handle(self, p: QPainter, x: float, w: int, h: int, side: str) -> None:
        r = QRectF(x - HANDLE_W / 2, 8, HANDLE_W, 46)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(SEL))
        p.drawRoundedRect(r, 3, 3)
        p.setBrush(QBrush(BG))
        tri_h = 6
        if side == "l":
            tip = r.left() + 2.5
            poly = [QPointF(tip, r.center().y() - tri_h / 2), QPointF(tip, r.center().y() + tri_h / 2), QPointF(tip + tri_h, r.center().y())]
        else:
            tip = r.right() - 2.5
            poly = [QPointF(tip, r.center().y() - tri_h / 2), QPointF(tip, r.center().y() + tri_h / 2), QPointF(tip - tri_h, r.center().y())]
        p.drawPolygon(poly)

    def _ruler_step(self) -> int:
        w = max(self.width(), 1)
        if self._ppx:
            target = 90 * self._ppx
        else:
            target = 90 * self._duration / w
        for c in HANDLE_STEP_CANDIDATES:
            if c >= target:
                return c
        return HANDLE_STEP_CANDIDATES[-1]