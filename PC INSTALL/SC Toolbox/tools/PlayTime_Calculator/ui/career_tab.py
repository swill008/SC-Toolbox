"""Career tab — your Star Citizen working life, from the mission/trade logs.

Built on REAL mission lifecycle events (``<EndMission>`` + the mission generator
name), so it reports actual completed-contract counts by type and employer —
not the ship-presence guess the Fun Stats tab used to use.

Honesty note rendered in the UI: mission *payouts* and wallet balances are not
in the client logs (they're server-side), so everything here is contract /
activity *volume*, never aUEC earned.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QGridLayout

from shared.qt.theme import P
from core.fun_stats import FunStats
from ui.fun_stats_tab import _ScanTab
from ui.stat_widgets import stat_card, section_label, make_bar, facts_box, ACCENT, GOLD, GREEN, ORANGE


class CareerTab(_ScanTab):
    def __init__(self, on_request_scan, parent=None) -> None:
        super().__init__("Career", on_request_scan, parent)

    def _render(self) -> None:
        self._clear()
        fs = self._fs
        if fs.missions_total == 0 and not fs.activities and not fs.trade_sells:
            lbl = QLabel("No mission or trade activity found in the logs yet.")
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet(f"color: {P.fg_dim}; background: transparent; font-family: Consolas;")
            self._cl.addWidget(lbl)
            return

        # Headline banner
        banner = QLabel(
            f"<span style='font-size:15pt; font-weight:bold; color:{ACCENT}'>"
            f"\U0001f4cb {fs.missions_complete:,} missions completed</span>"
            f"<br><span style='font-size:8pt; color:{P.fg_dim}'>"
            f"{fs.completion_rate:.0f}% completion rate · "
            f"{fs.missions_abandon:,} abandoned · {fs.missions_fail:,} failed · "
            f"{fs.missions_total:,} accepted</span>")
        banner.setTextFormat(Qt.RichText)
        banner.setStyleSheet("background: transparent;")
        self._cl.addWidget(banner)

        # Hero cards
        top_type = next((c for c, _ in fs.mission_types.most_common() if c != "Other"), "Mixed")
        top_type_n = fs.mission_types.get(top_type, 0)
        top_emp = fs.mission_employers.most_common(1)
        top_term = fs.trade_terminals.most_common(1)
        grid = QGridLayout()
        grid.setSpacing(8)
        cards = [
            ("TOP CONTRACT", top_type, f"{top_type_n:,} completed", ACCENT),
            ("TOP EMPLOYER", top_emp[0][0] if top_emp else "—",
             f"{top_emp[0][1]:,} contracts" if top_emp else "", ORANGE),
            ("COMPLETION RATE", f"{fs.completion_rate:.0f}%",
             f"{fs.missions_complete:,} of {fs.missions_total:,}", GREEN),
            ("TRADING", f"{fs.trade_sells:,}",
             f"sells · busiest {top_term[0][0]}" if top_term else "commodity sells", GOLD),
        ]
        for i, (t, v, s, c) in enumerate(cards):
            grid.addWidget(stat_card(t, v, s, c), 0, i)
            grid.setColumnStretch(i, 1)
        self._cl.addLayout(grid)

        # Contracts by type
        if fs.mission_types:
            self._cl.addWidget(section_label("Contracts by Type  ·  completed"))
            self._cl.addWidget(make_bar(fs.mission_types.most_common()))

        # Employers + side facts
        self._cl.addWidget(section_label("Top Employers  &  Side Hustles"))
        split = QHBoxLayout()
        split.setSpacing(10)
        if fs.mission_employers:
            emp_chart = make_bar(fs.mission_employers.most_common(8), min_h=170)
            split.addWidget(emp_chart, 3)

        side: list[str] = []
        if fs.activities.get("Mining"):
            side.append(f"⛏️ Mining ship out in <b>{fs.activities['Mining']:,}</b> sessions")
        if fs.activities.get("Salvage"):
            side.append(f"♻️ Salvage ship out in <b>{fs.activities['Salvage']:,}</b> sessions")
        if fs.trade_sells:
            terms = ", ".join(t for t, _ in fs.trade_terminals.most_common(3))
            side.append(f"\U0001f4b0 <b>{fs.trade_sells:,}</b> commodity sells "
                        f"(top: {terms})")
        if fs.missions_complete:
            side.append(f"\U0001f3c6 <b>{fs.missions_complete:,}</b> contracts cleared for "
                        f"<b>{len(fs.mission_employers)}</b> employers")
        side.append("<span style='color:%s'>ℹ️ Payouts/aUEC aren't in the logs "
                    "(server-side) — these are activity counts, not earnings.</span>" % P.fg_dim)
        split.addWidget(facts_box("Trade & Freeform", side, accent=GREEN), 2)
        self._cl.addLayout(split)
        self._cl.addStretch(1)
