"""Small shared widgets for the Fun Stats and Career tabs."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel, QSizePolicy

from shared.qt.theme import P
from ui.charts import BarChart, Bar

ACCENT = "#44ccff"
GOLD = "#ffcc44"
GREEN = "#33dd88"
ORANGE = "#ff8844"


def count_fmt(v: float) -> str:
    return f"{int(round(v)):,}"


def stat_card(title: str, value: str, sub: str = "", accent: str = ACCENT) -> QFrame:
    f = QFrame()
    f.setStyleSheet(f"QFrame {{ background: {P.bg_card}; border: 1px solid {P.border_card}; }}")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(12, 9, 12, 9)
    lay.setSpacing(2)
    t = QLabel(title)
    t.setStyleSheet(f"font-family: Consolas; font-size: 7pt; font-weight: bold;"
                    f" letter-spacing: 1px; color: {P.fg_dim}; background: transparent; border: none;")
    v = QLabel(value)
    v.setWordWrap(True)
    v.setStyleSheet(f"font-family: Electrolize, Consolas; font-size: 14pt; font-weight: bold;"
                    f" color: {accent}; background: transparent; border: none;")
    s = QLabel(sub)
    s.setStyleSheet(f"font-family: Consolas; font-size: 7pt; color: {P.fg_dim};"
                    f" background: transparent; border: none;")
    lay.addWidget(t)
    lay.addWidget(v)
    lay.addWidget(s)
    return f


def section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"font-family: Electrolize, Consolas; font-size: 10pt; font-weight: bold;"
        f" letter-spacing: 1px; color: {P.fg_bright}; background: transparent;")
    return lbl


def make_bar(items: list[tuple[str, int]], min_h: int = 160) -> BarChart:
    chart = BarChart(fit_width=True, value_fmt=count_fmt, axis_fmt=count_fmt)
    chart.setMinimumHeight(min_h)
    chart.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    chart.set_bars([Bar(label=name, value=float(ct), key=name, accent=(i == 0))
                    for i, (name, ct) in enumerate(items)])
    return chart


def facts_box(title: str, facts: list[str], accent: str = GOLD) -> QFrame:
    f = QFrame()
    f.setStyleSheet(f"QFrame {{ background: {P.bg_card}; border: 1px solid {P.border}; }}")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(12, 10, 12, 10)
    lay.setSpacing(4)
    head = QLabel(title)
    head.setStyleSheet(f"font-family: Electrolize, Consolas; font-size: 9pt; font-weight: bold;"
                       f" color: {accent}; background: transparent; border: none;")
    lay.addWidget(head)
    body = QLabel("<br>".join(f"&nbsp;{t}" for t in facts))
    body.setTextFormat(Qt.RichText)
    body.setWordWrap(True)
    body.setAlignment(Qt.AlignTop)
    body.setStyleSheet(f"font-family: Consolas; font-size: 8pt; color: {P.fg};"
                       f" background: transparent; border: none;")
    lay.addWidget(body, 1)
    return f
