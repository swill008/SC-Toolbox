"""Four OCR debug categories shared by Panel Finder and PowerShell.

scan    — one line per tick (mineral / mass / res / inst)
finder  — card square, TOP/BOT bars, follow
crops   — taught vs live box sizes
glyphs  — [DIAG] segmenter flood
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

KEYS = ("scan", "finder", "crops", "glyphs")
_DEFAULTS = {"scan": True, "finder": False, "crops": False, "glyphs": False}
_FLAGS = dict(_DEFAULTS)
_INSTALLED = False
_HOOKED = False

_LOCAL = os.environ.get("LOCALAPPDATA", "")
_PATH = Path(_LOCAL) / "SC_Toolbox" / "sc_ocr" / "debug_levels.json" if _LOCAL else Path("debug_levels.json")

_FILTER_LOGGERS = (
    "ocr.sc_ocr.api",
    "ocr.sc_ocr.card_lock_boot",
    "ocr.sc_ocr.scan_cadence",
    "ocr.sc_ocr.scan_results_match",
    "ocr.onnx_hud_reader",
)


def _load() -> None:
    global _FLAGS
    try:
        data = json.loads(_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            for k in KEYS:
                if k in data:
                    _FLAGS[k] = bool(data[k])
    except Exception:
        pass


def _save() -> None:
    try:
        _PATH.parent.mkdir(parents=True, exist_ok=True)
        _PATH.write_text(json.dumps(_FLAGS, indent=2), encoding="utf-8")
    except Exception:
        pass


def enabled(key: str) -> bool:
    return bool(_FLAGS.get(key, False))


def set_enabled(key: str, on: bool) -> None:
    if key not in KEYS:
        return
    _FLAGS[key] = bool(on)
    _save()
    log.info("debug_levels: %s=%s", key, on)
    _apply_api_level()


def _apply_api_level() -> None:
    api = logging.getLogger("ocr.sc_ocr.api")
    api.setLevel(logging.DEBUG if enabled("glyphs") else logging.INFO)


def classify(record: logging.LogRecord) -> Optional[str]:
    try:
        msg = record.getMessage()
    except Exception:
        return None
    name = record.name or ""
    if "[DIAG]" in msg or "_segment_glyphs" in msg or "COUNT ORACLE" in msg:
        return "glyphs"
    if any(s in msg for s in (
        "tight", "value_crop", "get_row", "fused", "GLOW_PAD", "pad_box",
        "truncated on the right",
    )):
        return "crops"
    if any(s in msg for s in (
        "square", "card_lock_bars", "top_bar", "bot_bar", "PRE-ANCHOR",
        "title-follow", "find_scan_results", "PANEL LOCK",
    )):
        return "finder"
    if "mineral=" in msg or (" mass=" in msg and "resistance=" in msg):
        return "scan"
    if "scan_results" in name or "card_lock" in name:
        return "finder"
    return None


class _CategoryFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        cat = classify(record)
        if cat is None:
            return True
        return enabled(cat)


def install() -> None:
    global _INSTALLED
    _load()
    if not _INSTALLED:
        filt = _CategoryFilter()
        for name in _FILTER_LOGGERS:
            logging.getLogger(name).addFilter(filt)
        _INSTALLED = True
        log.info("debug_levels: installed flags=%s", dict(_FLAGS))
    _apply_api_level()
    hook_panel_finder()


def hook_panel_finder() -> None:
    global _HOOKED
    if _HOOKED:
        return
    try:
        from ui.panel_finder_popout import PanelFinderPopout
    except Exception:
        return
    orig_init = PanelFinderPopout.__init__
    orig_tog = PanelFinderPopout._on_debug_toggled

    def init_wrapped(self, *args, **kwargs):
        orig_init(self, *args, **kwargs)
        try:
            _inject_boxes(self)
        except Exception as exc:
            log.debug("debug_levels inject failed: %s", exc)

    def tog_wrapped(self, on: bool):
        orig_tog(self, on)
        # Undo the old 'set every logger to DEBUG' so the log pane
        # cannot freeze the UI. Glyphs is the only DEBUG bump.
        try:
            from ui.panel_finder_popout import _DEBUG_LOGGERS
        except Exception:
            _DEBUG_LOGGERS = ()
        for name in _DEBUG_LOGGERS:
            if name == "ocr.sc_ocr.api" and enabled("glyphs"):
                logging.getLogger(name).setLevel(logging.DEBUG)
            else:
                lg = logging.getLogger(name)
                if lg.level == logging.DEBUG:
                    lg.setLevel(logging.INFO)
        _apply_api_level()

    PanelFinderPopout.__init__ = init_wrapped
    PanelFinderPopout._on_debug_toggled = tog_wrapped
    _HOOKED = True
    log.info("debug_levels: Panel Finder hook installed")


def _inject_boxes(win) -> None:
    from PySide6.QtWidgets import QCheckBox
    if getattr(win, "_dbg_boxes", None):
        return
    target = None
    for box in win.findChildren(QCheckBox):
        if box.text() in ("Debug Mode", "Log pane"):
            target = box
            break
    if target is None or target.parent() is None:
        return
    lay = target.parent().layout()
    if lay is None:
        return
    tips = {
        "scan": "One line per tick: mineral / mass / res / inst",
        "finder": "Card square, TOP/BOT bars, follow dx/dy",
        "crops": "Taught box vs live crop sizes",
        "glyphs": "Segmenter [DIAG] — floods PowerShell. Last resort.",
    }
    win._dbg_boxes = {}
    insert_at = lay.indexOf(target)
    if insert_at < 0:
        insert_at = lay.count()
    for i, (key, label) in enumerate((
        ("scan", "Scan"),
        ("finder", "Finder"),
        ("crops", "Crops"),
        ("glyphs", "Glyphs"),
    )):
        cb = QCheckBox(label, target.parent())
        cb.setChecked(enabled(key))
        cb.setToolTip(tips[key])
        cb.setStyleSheet(
            "QCheckBox { color: #ccc; font-family: Consolas; font-size: 9pt; }"
        )
        cb.toggled.connect(lambda on, k=key: set_enabled(k, bool(on)))
        win._dbg_boxes[key] = cb
        lay.insertWidget(insert_at + i, cb)
