#!/usr/bin/env python3
"""Mining Suite — one window, two tabs (Signals + Loadout).

Standalone entry for the ``stripped`` branch. Does not go through the
toolbox skill launcher. Both tools stay in-process so OCR keeps
running while you are on the Loadout tab.

The two tools each ship a top-level ``ui`` / ``services`` package, so
Loadout is imported behind a sys.modules snapshot and restored after
construction.
"""
from __future__ import annotations

import os
import queue
import sys

if os.name == "nt" and not os.environ.get("QT_MEDIA_BACKEND"):
    os.environ["QT_MEDIA_BACKEND"] = "windows"

# Standalone: X on the title bar should quit, not hide-for-launcher.
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
from PySide6.QtWidgets import (  # noqa: E402
    QApplication, QTabWidget, QWidget, QVBoxLayout, QLabel,
)
from shared.crash_logger import init_crash_logging  # noqa: E402
from shared.platform_utils import set_dpi_awareness  # noqa: E402
from shared.data_utils import parse_cli_args  # noqa: E402
from shared.qt.base_window import SCWindow  # noqa: E402
from shared.qt.theme import P, apply_theme  # noqa: E402
from shared.qt.title_bar import SCTitleBar  # noqa: E402

ACCENT = "#33dd88"


def _strip_inner_chrome(window) -> None:
    """Hide the nested SCWindow title bar when hosted in a tab."""
    try:
        layout = window.content_layout
        if layout.count() < 1:
            return
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


class MiningSuiteWindow(SCWindow):
    """Single chrome window hosting Signals + Loadout as tabs."""

    def __init__(
        self,
        x: int = 80, y: int = 80,
        w: int = 1200, h: int = 900,
        opacity: float = 1.0,
    ) -> None:
        super().__init__(
            title="Mining",
            width=w, height=h,
            min_w=800, min_h=500,
            opacity=1.0,
            always_on_top=True,
            accent=ACCENT,
        )
        self.restore_geometry_from_args(x, y, w, h, 1.0)

        self._title_bar = SCTitleBar(
            self, title="Mining", accent_color=ACCENT,
        )
        self._title_bar.close_clicked.connect(self.user_close)
        self._title_bar.minimize_clicked.connect(self.showMinimized)
        self.content_layout.addWidget(self._title_bar)

        self._tabs = QTabWidget(self)
        self._tabs.setDocumentMode(True)
        self._tabs.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {P.border};
                background: {P.bg_primary};
            }}
            QTabBar::tab {{
                background: {P.bg_header};
                color: {P.fg_dim};
                padding: 8px 18px;
                margin-right: 2px;
                font-family: Electrolize, Consolas;
                font-size: 10pt;
            }}
            QTabBar::tab:selected {{
                background: {P.bg_card};
                color: {ACCENT};
                font-weight: bold;
            }}
        """)
        self.content_layout.addWidget(self._tabs, 1)

        self._signals = None
        self._loadout = None
        self._build_signals_tab()
        self._build_loadout_tab()
        self._tabs.setCurrentIndex(0)

    def _build_signals_tab(self) -> None:
        host = QWidget(self._tabs)
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
            err.setStyleSheet(f"color: {P.fg}; padding: 16px;")
            lay.addWidget(err)
        self._tabs.addTab(host, "Mining Loadout")


def main() -> None:
    log = init_crash_logging("mining_suite")
    try:
        set_dpi_awareness()
        parsed = parse_cli_args(sys.argv[1:], {"w": 1200, "h": 900})
        app = QApplication(sys.argv)
        apply_theme(app)
        window = MiningSuiteWindow(
            x=parsed["x"], y=parsed["y"],
            w=parsed["w"], h=parsed["h"],
            opacity=1.0,
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
