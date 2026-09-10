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

_LOCAL = os.environ.get("LOCALAPPDATA", "")
_PATH = Path(_LOCAL) / "SC_Toolbox" / "sc_ocr" / "debug_levels.json" if _LOCAL else Path("debug_levels.json")


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
    if _INSTALLED:
        return
    filt = _CategoryFilter()
    for name in (
        "ocr.sc_ocr.api",
        "ocr.sc_ocr.card_lock_boot",
        "ocr.sc_ocr.scan_cadence",
        "ocr.sc_ocr.scan_results_match",
        "ocr.onnx_hud_reader",
    ):
        logging.getLogger(name).addFilter(filt)
    _INSTALLED = True
    log.info("debug_levels: installed flags=%s", dict(_FLAGS))
