"""
SCWindow – holographic HUD-style window.

Dark background with glowing cyan border lines, corner brackets,
and scan-line texture.
"""

from __future__ import annotations
import json
import logging
import os
import sys
from typing import Optional

from PySide6.QtCore import Qt, QPoint, QSize, QTimer, QObject, QEvent
from PySide6.QtGui import (
    QGuiApplication, QPainter, QColor, QPen, QBrush, QLinearGradient,
)
from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QApplication

from shared.qt.theme import P

log = logging.getLogger(__name__)

_STATE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "logs",
)


def load_window_state(script_stem: str) -> dict:
    path = os.path.join(_STATE_DIR, f"{script_stem}_window.json")
    try:
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def _save_window_state(window: QMainWindow) -> None:
    key = os.path.splitext(os.path.basename(sys.argv[0]))[0]
    try:
        geom = window.get_geometry_dict()  # type: ignore[attr-defined]
        os.makedirs(_STATE_DIR, exist_ok=True)
        path = os.path.join(_STATE_DIR, f"{key}_window.json")
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(geom, f)
        os.replace(tmp, path)
    except (OSError, AttributeError):
        pass

_GRIP = 14
_GRIP_TOP = 5


class _EdgeResizeFilter(QObject):
    def eventFilter(self, obj, event):  # noqa: C901
        etype = event.type()
        if etype not in (
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseMove,
            QEvent.Type.MouseButtonRelease,
        ):
            return False

        win = obj
        while win is not None:
            if isinstance(win, SCWindow):
                break
            win = win.parent() if hasattr(win, "parent") else None
        if win is None:
            return False

        if isinstance(obj, QWidget):
            top = obj.window()
            if top is not None and top is not win:
                if not win._resizing:
                    return False

        if win._resizing:
            if etype == QEvent.Type.MouseMove:
                delta = event.globalPosition().toPoint() - win._drag_pos
                win._drag_pos = event.globalPosition().toPoint()
                geom = win.geometry()
                edge = win._resize_edge
                mw, mh = win.minimumWidth(), win.minimumHeight()
                if "r" in edge:
                    geom.setWidth(max(mw, geom.width() + delta.x()))
                if "b" in edge:
                    geom.setHeight(max(mh, geom.height() + delta.y()))
                if "l" in edge:
                    nw = max(mw, geom.width() - delta.x())
                    if nw != geom.width():
                        geom.setLeft(geom.left() + (geom.width() - nw))
                if "t" in edge:
                    nh = max(mh, geom.height() - delta.y())
                    if nh != geom.height():
                        geom.setTop(geom.top() + (geom.height() - nh))
                win.setGeometry(geom)
                return True
            if etype == QEvent.Type.MouseButtonRelease:
                win._resizing = False
                win._resize_edge = None
                win.unsetCursor()
                return True
            return False

        try:
            win_pos = obj.mapTo(win, event.position().toPoint())
        except (RuntimeError, TypeError):
            return False

        edge = win._edge_at(win_pos)
        if edge is None:
            return False

        if etype == QEvent.Type.MouseButtonPress and event.button() == Qt.LeftButton:
            win._resizing = True
            win._resize_edge = edge
            win._drag_pos = event.globalPosition().toPoint()
            win.setCursor(win._EDGE_CURSORS.get(edge, Qt.ArrowCursor))
            return True

        if etype == QEvent.Type.MouseMove:
            win.setCursor(win._EDGE_CURSORS.get(edge, Qt.ArrowCursor))
            return True

        return False


_edge_filter_installed = False
_EDGE_W = 1
_BRACKET_LEN = 18
_BRACKET_W = 2
_GLOW_PASSES = 3
_SCANLINE_SPACING = 2
_SCANLINE_ALPHA = 8


class _HoloSurface(QWidget):
    def __init__(self, parent=None, accent: str = ""):
        super().__init__(parent)
        self._accent_hex = accent or P.accent
        self._accent = QColor(self._accent_hex)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent;")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        w, h = self.width(), self.height()
        r = self.rect()

        bg = QColor(P.bg_primary)
        bg.setAlpha(255)
        painter.fillRect(r, bg)

        scan_color = QColor(255, 255, 255, _SCANLINE_ALPHA)
        painter.setPen(QPen(scan_color, 1))
        y = 0
        while y < h:
            painter.drawLine(0, y, w, y)
            y += _SCANLINE_SPACING

        for i in range(_GLOW_PASSES, 0, -1):
            glow = QColor(self._accent)
            glow.setAlpha(int(12 * i))
            painter.setPen(QPen(glow, 1))
            offset = i
            painter.drawRect(offset, offset, w - 1 - 2 * offset, h - 1 - 2 * offset)

        edge = QColor(self._accent)
        edge.setAlpha(140)
        painter.setPen(QPen(edge, _EDGE_W))
        painter.drawRect(0, 0, w - 1, h - 1)

        top_glow = QLinearGradient(0, 0, 0, 6)
        gc = QColor(self._accent)
        gc.setAlpha(50)
        top_glow.setColorAt(0.0, gc)
        gc2 = QColor(self._accent)
        gc2.setAlpha(0)
        top_glow.setColorAt(1.0, gc2)
        painter.fillRect(1, 1, w - 2, 6, top_glow)

        bracket_color = QColor(self._accent)
        bracket_color.setAlpha(220)
        pen = QPen(bracket_color, _BRACKET_W)
        painter.setPen(pen)
        bl = _BRACKET_LEN
        painter.drawLine(0, 0, bl, 0)
        painter.drawLine(0, 0, 0, bl)
        painter.drawLine(w - 1, 0, w - 1 - bl, 0)
        painter.drawLine(w - 1, 0, w - 1, bl)
        painter.drawLine(0, h - 1, bl, h - 1)
        painter.drawLine(0, h - 1, 0, h - 1 - bl)
        painter.drawLine(w - 1, h - 1, w - 1 - bl, h - 1)
        painter.drawLine(w - 1, h - 1, w - 1, h - 1 - bl)

        bglow = QColor(self._accent)
        bglow.setAlpha(30)
        painter.setPen(QPen(bglow, _BRACKET_W + 4))
        painter.drawLine(0, 0, bl, 0)
        painter.drawLine(0, 0, 0, bl)
        painter.drawLine(w - 1, 0, w - 1 - bl, 0)
        painter.drawLine(w - 1, 0, w - 1, bl)
        painter.drawLine(0, h - 1, bl, h - 1)
        painter.drawLine(0, h - 1, 0, h - 1 - bl)
        painter.drawLine(w - 1, h - 1, w - 1 - bl, h - 1)
        painter.drawLine(w - 1, h - 1, w - 1, h - 1 - bl)

        grip_color = QColor(self._accent)
        grip_color.setAlpha(100)
        painter.setPen(QPen(grip_color, 1))
        g = _GRIP
        for dx in range(3, g, 4):
            painter.drawLine(w - 1 - dx, h - 1, w - 1, h - 1 - dx)
            painter.drawLine(dx, h - 1, 0, h - 1 - dx)
            painter.drawLine(w - 1 - dx, 0, w - 1, dx)
            painter.drawLine(dx, 0, 0, dx)

        painter.end()
        super().paintEvent(event)


class SCWindow(QMainWindow):
    def __init__(
        self,
        title: str = "SC Toolbox",
        width: int = 1000,
        height: int = 700,
        min_w: int = 400,
        min_h: int = 200,
        opacity: float = 1.0,
        always_on_top: bool = True,
        accent: str = "",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)

        flags = Qt.FramelessWindowHint
        if always_on_top:
            flags |= Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowTitle(title)
        self.setMinimumSize(QSize(min_w, min_h))
        self.resize(width, height)
        self.setWindowOpacity(1.0)

        self._central = _HoloSurface(self, accent=accent)
        self.setCentralWidget(self._central)
        self._layout = QVBoxLayout(self._central)
        self._layout.setContentsMargins(1, 1, 1, 1)
        self._layout.setSpacing(0)

        self._resizing = False
        self._resize_edge = None
        self._drag_pos = QPoint()
        self.setMouseTracking(True)

        global _edge_filter_installed
        if not _edge_filter_installed:
            app = QApplication.instance()
            if app:
                app.installEventFilter(_EdgeResizeFilter(app))
                _edge_filter_installed = True

        self._default_width = width
        self._default_height = height
        self._collapsed = False
        self._expanded_height = height
        self._original_min_h = min_h

    @property
    def content_layout(self) -> QVBoxLayout:
        return self._layout

    def closeEvent(self, event) -> None:
        _save_window_state(self)
        super().closeEvent(event)

    def set_opacity(self, value: float) -> None:
        self.setWindowOpacity(1.0)

    def reset_layout(self) -> None:
        self.resize(self._default_width, self._default_height)
        screen = QGuiApplication.primaryScreen()
        if screen:
            sg = screen.availableGeometry()
            x = sg.x() + (sg.width() - self._default_width) // 2
            y = sg.y() + (sg.height() - self._default_height) // 2
            self.move(x, y)

    def toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
            saved = getattr(self, "_pre_fullscreen_geom", None)
            if saved is not None:
                self.setGeometry(saved)
        else:
            self._pre_fullscreen_geom = self.geometry()
            self.showFullScreen()

    def reset_scale(self) -> None:
        from PySide6.QtWidgets import QGraphicsView
        for view in self.findChildren(QGraphicsView):
            view.resetTransform()

    def toggle_collapse(self) -> None:
        self._collapsed = not self._collapsed
        for i in range(1, self._layout.count()):
            item = self._layout.itemAt(i)
            w = item.widget() if item else None
            if w:
                w.setVisible(not self._collapsed)
        if self._collapsed:
            self._expanded_height = self.height()
            self.setMinimumHeight(38)
            self.resize(self.width(), 38)
        else:
            self.setMinimumHeight(self._original_min_h)
            self.resize(self.width(), self._expanded_height)

    def user_close(self) -> None:
        if os.environ.get("SC_TOOLBOX_EXIT_ON_CLOSE") == "1":
            _save_window_state(self)
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance()
            if app:
                app.quit()
        else:
            self.hide()

    def toggle_visibility(self) -> None:
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()

    def schedule(self, delay_ms: int, fn) -> None:
        QTimer.singleShot(delay_ms, fn)

    def move_to(self, x: int, y: int) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen:
            geom = screen.availableGeometry()
            x = max(geom.x(), min(x, geom.right() - self.width()))
            y = max(geom.y(), min(y, geom.bottom() - self.height()))
        self.move(x, y)

    def restore_geometry_from_args(self, x: int, y: int, w: int, h: int, opacity: float) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen:
            sg = screen.availableGeometry()
            x = max(sg.x(), min(x, sg.right() - w))
            y = max(sg.y(), min(y, sg.bottom() - h))
        self.resize(w, h)
        self.move(x, y)
        self.set_opacity(1.0)

    def get_geometry_dict(self, prefix: str = "") -> dict:
        pos = self.pos()
        size = self.size()
        return {
            f"{prefix}x": pos.x(),
            f"{prefix}y": pos.y(),
            f"{prefix}w": size.width(),
            f"{prefix}h": size.height(),
            f"{prefix}opacity": self.windowOpacity(),
        }

    def _edge_at(self, pos: QPoint) -> Optional[str]:
        r = self.rect()
        x, y = pos.x(), pos.y()
        on_left = x < _GRIP
        on_right = x > r.width() - _GRIP
        on_top = y < _GRIP_TOP
        on_bottom = y > r.height() - _GRIP
        if on_top and on_left: return "tl"
        if on_top and on_right: return "tr"
        if on_bottom and on_left: return "bl"
        if on_bottom and on_right: return "br"
        if on_top: return "t"
        if on_bottom: return "b"
        if on_left: return "l"
        if on_right: return "r"
        return None

    _EDGE_CURSORS = {
        "t": Qt.SizeVerCursor, "b": Qt.SizeVerCursor,
        "l": Qt.SizeHorCursor, "r": Qt.SizeHorCursor,
        "tl": Qt.SizeFDiagCursor, "br": Qt.SizeFDiagCursor,
        "tr": Qt.SizeBDiagCursor, "bl": Qt.SizeBDiagCursor,
    }

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            edge = self._edge_at(event.position().toPoint())
            if edge:
                self._resizing = True
                self._resize_edge = edge
                self._drag_pos = event.globalPosition().toPoint()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resizing and self._resize_edge:
            delta = event.globalPosition().toPoint() - self._drag_pos
            self._drag_pos = event.globalPosition().toPoint()
            geom = self.geometry()
            edge = self._resize_edge
            mw, mh = self.minimumWidth(), self.minimumHeight()
            if "r" in edge: geom.setWidth(max(mw, geom.width() + delta.x()))
            if "b" in edge: geom.setHeight(max(mh, geom.height() + delta.y()))
            if "l" in edge:
                nw = max(mw, geom.width() - delta.x())
                if nw != geom.width(): geom.setLeft(geom.left() + (geom.width() - nw))
            if "t" in edge:
                nh = max(mh, geom.height() - delta.y())
                if nh != geom.height(): geom.setTop(geom.top() + (geom.height() - nh))
            self.setGeometry(geom)
            event.accept()
            return
        edge = self._edge_at(event.position().toPoint())
        if edge:
            self.setCursor(self._EDGE_CURSORS.get(edge, Qt.ArrowCursor))
        else:
            self.unsetCursor()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._resizing:
            self._resizing = False
            self._resize_edge = None
            event.accept()
            return
        super().mouseReleaseEvent(event)
