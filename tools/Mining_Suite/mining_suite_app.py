#!/usr/bin/env python3
"""Mining Suite — native window, two tabs (Signals + Loadout).

Standalone entry for the ``stripped`` branch. Standard OS chrome
(Fusion dark). Not a toolbox HUD overlay.
"""
from __future__ import annotations

import os
import queue
import sys

if os.name == "nt" and not os.environ.get("QT_MEDIA_BACKEND"):
    os.environ["QT_MEDIA_BACKEND"] = "windows"

os.environ.setdefault("SC_TOOLBOX_EXIT_ON_CLOSE", "1")

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.normpath(os.path.join(_THIS_DIR, "..", ".."))
_SIGNALS_DIR = os.path.normpath(os.path.join(_REPO_ROOT, "tools", "Mining_Signals"))
_LOADOUT_DIR = os.path.normpath(os.path.join(_REPO_ROOT, "skills", "Mining_Loadout"))

sys.path.insert(0, _REPO_ROOT)
sys.path.insert(0, _SIGNALS_DIR)

from shared.app_bootstrap import bootstrap_skill  # noqa: E402
bootstrap_skill(os.path.join(_SIGNALS_DIR, "mining_signals_app.py"))

from PySide6.QtCore import Qt, QTimer  # noqa: E402
from PySide6.QtGui import QAction, QColor, QPalette  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication, QLabel, QMainWindow, QSizePolicy, QTabWidget,
    QVBoxLayout, QWidget,
)
from shared.crash_logger import init_crash_logging  # noqa: E402
from shared.qt.base_window import install_native_child_filter  # noqa: E402
from shared.platform_utils import set_dpi_awareness  # noqa: E402
from shared.data_utils import parse_cli_args  # noqa: E402


def _apply_fusion_dark(app: QApplication) -> None:
    """Plain dark desktop palette — no MobiGlas QSS."""
    app.setStyle("Fusion")
    pal = QPalette()
    bg = QColor("#1e1e1e")
    panel = QColor("#252526")
    text = QColor("#d4d4d4")
    disabled = QColor("#6e6e6e")
    highlight = QColor("#0e639c")
    pal.setColor(QPalette.Window, bg)
    pal.setColor(QPalette.WindowText, text)
    pal.setColor(QPalette.Base, QColor("#1c1c1c"))
    pal.setColor(QPalette.AlternateBase, panel)
    pal.setColor(QPalette.ToolTipBase, panel)
    pal.setColor(QPalette.ToolTipText, text)
    pal.setColor(QPalette.Text, text)
    pal.setColor(QPalette.Button, panel)
    pal.setColor(QPalette.ButtonText, text)
    pal.setColor(QPalette.BrightText, QColor("#ffffff"))
    pal.setColor(QPalette.Highlight, highlight)
    pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    pal.setColor(QPalette.PlaceholderText, disabled)
    pal.setColor(QPalette.Disabled, QPalette.WindowText, disabled)
    pal.setColor(QPalette.Disabled, QPalette.Text, disabled)
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, disabled)
    app.setPalette(pal)
    app.setStyleSheet("")


def _strip_inner_chrome(window) -> None:
    """Hide nested HUD title bars when hosted in a tab."""
    try:
        from shared.qt.title_bar import SCTitleBar
        for bar in window.findChildren(SCTitleBar):
            bar.hide()
    except Exception:
        pass
    try:
        layout = window.content_layout
        if layout.count() >= 1:
            item = layout.itemAt(0)
            bar = item.widget() if item else None
            if bar is not None:
                bar.setVisible(False)
    except Exception:
        pass


def _as_tab_widget(window, parent: QWidget) -> QWidget:
    """Reparent an SCWindow so it can live inside a QTabWidget."""
    window.setParent(parent)
    window.setWindowFlags(Qt.Widget)
    window.setAttribute(Qt.WA_TranslucentBackground, False)
    try:
        window.setWindowFlag(Qt.WindowStaysOnTopHint, False)
    except Exception:
        pass
    if hasattr(window, "set_plain_embed"):
        window.set_plain_embed(True)
    if hasattr(window, "setWindowOpacity"):
        window.setWindowOpacity(1.0)
    window.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    window.setMinimumSize(0, 0)
    central = window.centralWidget() if hasattr(window, "centralWidget") else None
    if central is not None:
        central.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    _strip_inner_chrome(window)
    return window


def _import_loadout_window():
    """Load MiningLoadoutWindow without permanently stealing ``ui``."""
    saved = {}
    prefixes = ("ui", "services", "models", "controllers")
    for key in list(sys.modules):
        if key in prefixes or any(key.startswith(p + ".") for p in prefixes):
            saved[key] = sys.modules.pop(key)
    path_was = list(sys.path)
    try:
        if _LOADOUT_DIR not in sys.path:
            sys.path.insert(0, _LOADOUT_DIR)
        from ui.main_window import MiningLoadoutWindow  # type: ignore
        return MiningLoadoutWindow
    finally:
        sys.path[:] = path_was
        for key in list(sys.modules):
            if key in prefixes or any(key.startswith(p + ".") for p in prefixes):
                sys.modules.pop(key, None)
        sys.modules.update(saved)


class MiningSuiteWindow(QMainWindow):
    """Native OS window hosting Signals + Loadout as tabs."""

    def __init__(
        self,
        x: int = 80, y: int = 80,
        w: int = 1200, h: int = 900,
    ) -> None:
        super().__init__()
        self.setWindowTitle("Mining")
        self.resize(max(800, w), max(500, h))
        self.move(x, y)

        self._tabs = QTabWidget(self)
        self._tabs.setDocumentMode(False)
        self.setCentralWidget(self._tabs)

        self._signals = None
        self._loadout = None
        self._build_menu()
        self._build_signals_tab()
        self._build_loadout_tab()
        self._tabs.setCurrentIndex(0)

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        quit_act = QAction("E&xit", self)
        quit_act.setShortcut("Ctrl+Q")
        quit_act.triggered.connect(self.close)
        file_menu.addAction(quit_act)

        view_menu = self.menuBar().addMenu("&View")
        pin = QAction("Always on top", self)
        pin.setCheckable(True)
        pin.setChecked(False)
        pin.toggled.connect(self._set_always_on_top)
        view_menu.addAction(pin)

    def _set_always_on_top(self, on: bool) -> None:
        flags = self.windowFlags()
        if on:
            flags |= Qt.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()

    def _build_signals_tab(self) -> None:
        host = QWidget(self._tabs)
        host.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        lay = QVBoxLayout(host)
        lay.setContentsMargins(0, 0, 0, 0)
        from ui.app import MiningSignalsApp
        self._signals = MiningSignalsApp(
            x=0, y=0, w=980, h=960, opacity=1.0,
        )
        embedded = _as_tab_widget(self._signals, host)
        lay.addWidget(embedded, 1)
        self._tabs.addTab(host, "Mining Signals")

    def _build_loadout_tab(self) -> None:
        host = QWidget(self._tabs)
        host.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        lay = QVBoxLayout(host)
        lay.setContentsMargins(0, 0, 0, 0)
        try:
            MiningLoadoutWindow = _import_loadout_window()
            self._loadout = MiningLoadoutWindow(
                cmd_queue=queue.Queue(),
                win_x=0, win_y=0,
                win_w=1200, win_h=720,
                refresh_interval=86400.0,
                opacity=1.0,
            )
            embedded = _as_tab_widget(self._loadout, host)
            lay.addWidget(embedded, 1)
            QTimer.singleShot(400, self._loadout._start_load)
            if hasattr(self._loadout, "_start_poll_queue"):
                try:
                    self._loadout._start_poll_queue()
                except Exception:
                    pass
        except Exception as exc:
            err = QLabel(
                "Mining Loadout could not start:\n\n"
                f"{exc}\n\n"
                "Signals still works. Loadout lives in "
                "skills/Mining_Loadout."
            )
            err.setWordWrap(True)
            err.setStyleSheet("padding: 16px;")
            lay.addWidget(err)
        self._tabs.addTab(host, "Mining Loadout")


def main() -> None:
    log = init_crash_logging("mining_suite")
    try:
        set_dpi_awareness()
        parsed = parse_cli_args(sys.argv[1:], {"w": 1200, "h": 900})
        app = QApplication(sys.argv)
        _apply_fusion_dark(app)
        install_native_child_filter(app)
        window = MiningSuiteWindow(
            x=parsed["x"], y=parsed["y"],
            w=parsed["w"], h=parsed["h"],
        )
        window.show()
        window.raise_()
        window.activateWindow()
        sys.exit(app.exec())
    except Exception:
        log.critical("FATAL crash in mining_suite main()", exc_info=True)
        raise


if __name__ == "__main__":
    main()
