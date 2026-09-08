"""Fun Stats tab — gameplay trivia mined from full Game.log contents.

The heavy full-content scan is owned by the window (shared with the Career tab),
so this tab just renders the FunStats it's handed via ``set_stats`` and shows
progress via ``set_progress``.  It asks the window to start the scan the first
time it becomes visible (and when "Re-analyze" is clicked).
"""
from __future__ import annotations

import logging
from typing import Callable, Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGridLayout, QScrollArea, QProgressBar,
)

from shared.qt.theme import P
from core import log_scanner, fun_stats
from core.fun_stats import FunStats
from ui.stat_widgets import stat_card, section_label, make_bar, facts_box, ACCENT, GOLD, ORANGE

log = logging.getLogger(__name__)


class FunStatsWorker(QThread):
    progress = Signal(int, int)
    done = Signal(object)

    def __init__(self, folder: str, parent=None) -> None:
        super().__init__(parent)
        self._folder = folder
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            paths = log_scanner.find_log_files(self._folder)
            fs = fun_stats.scan_fun_stats(
                paths,
                progress_cb=lambda d, t: self.progress.emit(d, t),
                cancel_cb=lambda: self._cancel)
        except Exception:
            log.exception("fun_stats: scan failed")
            fs = FunStats()
        self.done.emit(fs)


class _ScanTab(QWidget):
    """Shared skeleton: header (title + status + re-analyze), progress, scroll."""

    def __init__(self, title: str, on_request_scan: Callable[[bool], None], parent=None) -> None:
        super().__init__(parent)
        self._on_request_scan = on_request_scan
        self._fs = FunStats()
        self._requested = False

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        head = QHBoxLayout()
        t = QLabel(title)
        t.setStyleSheet(f"font-family: Electrolize, Consolas; font-size: 12pt; font-weight: bold;"
                        f" color: {P.fg_bright}; background: transparent;")
        head.addWidget(t)
        self._status = QLabel("")
        self._status.setStyleSheet(f"font-family: Consolas; font-size: 8pt; color: {P.fg_dim};"
                                   f" background: transparent;")
        head.addWidget(self._status, 1)
        self._refresh = QPushButton("↻ Re-analyze")
        self._refresh.setCursor(Qt.PointingHandCursor)
        self._refresh.setStyleSheet(
            f"QPushButton {{ font-family: Consolas; font-size: 8pt; font-weight: bold;"
            f" color: {ACCENT}; background: transparent; border: 1px solid {ACCENT};"
            f" border-radius: 3px; padding: 4px 12px; }}"
            f"QPushButton:hover {{ background: rgba(68,204,255,0.15); }}")
        self._refresh.clicked.connect(lambda: self._on_request_scan(True))
        head.addWidget(self._refresh)
        root.addLayout(head)

        self._progress = QProgressBar()
        self._progress.setFixedHeight(6)
        self._progress.setTextVisible(False)
        self._progress.hide()
        root.addWidget(self._progress)

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self._content = QWidget()
        self._content.setStyleSheet("background: transparent;")
        self._cl = QVBoxLayout(self._content)
        self._cl.setContentsMargins(0, 0, 6, 0)
        self._cl.setSpacing(10)
        self._scroll.setWidget(self._content)
        root.addWidget(self._scroll, 1)

        ph = QLabel("Open this tab to mine your logs…")
        ph.setAlignment(Qt.AlignCenter)
        ph.setStyleSheet(f"font-family: Consolas; font-size: 9pt; color: {P.fg_dim}; background: transparent;")
        self._cl.addWidget(ph)

    def showEvent(self, ev):
        super().showEvent(ev)
        if not self._requested:
            self._requested = True
            self._on_request_scan(False)

    def set_progress(self, done: int, total: int) -> None:
        self._progress.show()
        if total:
            self._progress.setValue(int(done * 100 / total))
        self._status.setText(f"Analyzing logs… {done:,}/{total:,}")
        self._refresh.setEnabled(False)

    def set_stats(self, fs: FunStats) -> None:
        self._fs = fs
        self._progress.hide()
        self._refresh.setEnabled(True)
        self._status.setText(f"{fs.sessions_scanned:,} sessions analyzed")
        self._render()

    def _clear(self) -> None:
        while self._cl.count():
            item = self._cl.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _render(self) -> None:  # overridden
        pass


class FunStatsTab(_ScanTab):
    def __init__(self, on_request_scan, parent=None) -> None:
        super().__init__("Fun Stats", on_request_scan, parent)

    def _render(self) -> None:
        self._clear()
        fs = self._fs
        if fs.is_empty:
            lbl = QLabel("No gameplay events found in the logs yet — go fly!")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet(f"color: {P.fg_dim}; background: transparent; font-family: Consolas;")
            self._cl.addWidget(lbl)
            return

        sys_txt = " · ".join(fs.systems)
        banner = QLabel(
            f"<span style='font-size:13pt; font-weight:bold; color:{ACCENT}'>"
            f"\U0001f9d1‍\U0001f680 Commander {fs.player_handle or 'Unknown'}</span>"
            f"<br><span style='font-size:8pt; color:{P.fg_dim}'>"
            f"{fs.sessions_scanned:,} sessions analyzed · systems explored: {sys_txt}</span>")
        banner.setTextFormat(Qt.RichText)
        banner.setStyleSheet("background: transparent;")
        self._cl.addWidget(banner)

        top_ship = fs.ships.most_common(1)
        top_wep = fs.weapons.most_common(1)
        top_maker = fs.manufacturers.most_common(1)
        top_tool = fs.tool_heads.most_common(1)
        grid = QGridLayout()
        grid.setSpacing(8)
        cards = [
            ("MOST-FLOWN SHIP", top_ship[0][0] if top_ship else "—",
             f"{top_ship[0][1]:,} flights" if top_ship else "", ACCENT),
            ("FAVOURITE WEAPON", top_wep[0][0] if top_wep else "—",
             f"equipped ×{top_wep[0][1]:,}" if top_wep else "", GOLD),
            ("FAVOURITE MAKER", top_maker[0][0] if top_maker else "—",
             f"{top_maker[0][1]:,} flights" if top_maker else "", ORANGE),
            ("MULTITOOL MAIN", top_tool[0][0] if top_tool else "—",
             f"{top_tool[0][1]} swaps" if top_tool else "no tool use", "#33dd88"),
        ]
        for i, (t, v, s, c) in enumerate(cards):
            grid.addWidget(stat_card(t, v, s, c), 0, i)
            grid.setColumnStretch(i, 1)
        self._cl.addLayout(grid)

        self._cl.addWidget(section_label("Ships Commanded  ·  times flown"))
        self._cl.addWidget(make_bar(fs.ships.most_common(8)))
        self._cl.addWidget(section_label("Weapons  ·  times equipped"))
        self._cl.addWidget(make_bar(fs.weapons.most_common(8)))
        note = QLabel("ℹ️ The game only began logging ship piloting + loadout "
                      "events in mid-2025 builds — flights & gear from earlier sessions "
                      "aren't recorded in the logs.")
        note.setWordWrap(True)
        note.setStyleSheet(f"font-family: Consolas; font-size: 7pt; color: {P.fg_dim};"
                           f" background: transparent;")
        self._cl.addWidget(note)

        # Fun facts
        facts: list[str] = []
        if fs.ships:
            facts.append(f"\U0001f680 Commanded <b>{fs.distinct_ships}</b> different hulls")
        if fs.manufacturers:
            maker, n = fs.manufacturers.most_common(1)[0]
            facts.append(f"\U0001f3f7️ Loyal to <b>{maker}</b> ({n:,} flights)")
        if fs.weapons:
            wep, n = fs.weapons.most_common(1)[0]
            facts.append(f"\U0001f52b Go-to gun: <b>{wep}</b> (equipped ×{n:,})")
        if fs.tool_heads:
            head, _ = fs.tool_heads.most_common(1)[0]
            facts.append(f"\U0001f527 Multitool main — favourite head: <b>{head}</b>")
        if fs.consumables:
            facts.append(f"\U0001f489 Field medic — <b>{fs.consumables:,}</b> consumables used")
        if fs.plushies:
            facts.append(f"\U0001f9f8 Plushie collector — <b>{fs.plushies}</b> cuddly companions")
        if fs.total_equips:
            facts.append(f"\U0001f9e5 Fashionista — <b>{fs.total_equips:,}</b> loadout changes")
        sys_parts = [f"{s} ({fs.system_sessions[s]:,})" for s in fs.systems]
        facts.append(f"\U0001fa90 Systems explored: <b>{', '.join(sys_parts)}</b>")
        self._cl.addWidget(facts_box("Fun Facts", facts))
        self._cl.addStretch(1)
