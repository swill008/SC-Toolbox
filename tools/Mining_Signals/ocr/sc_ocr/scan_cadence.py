"""Scan cadence and DIAG noise control for Free-Domain OCR.

The UI timer is hard-capped at 500 ms even when config says 3 s.
Glyph [DIAG] lines are logged at WARNING and flood PowerShell / Qt.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)


class _DiagDemote(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        if "[DIAG]" in msg:
            record.levelno = logging.DEBUG
            record.levelname = "DEBUG"
        return True


def quiet_diag() -> None:
    api_log = logging.getLogger("ocr.sc_ocr.api")
    if not any(isinstance(f, _DiagDemote) for f in api_log.filters):
        api_log.addFilter(_DiagDemote())
        log.info("scan_cadence: [DIAG] demoted to DEBUG")


def patch_ui_scan_timer() -> None:
    try:
        from ui.app import MiningSignalsApp
    except Exception as exc:
        log.debug("scan_cadence: ui app not ready (%s)", exc)
        return
    orig = getattr(MiningSignalsApp, "_on_scan_toggle", None)
    if orig is None or getattr(orig, "_card_lock_cadence", False):
        return

    def wrapped(self, checked):
        orig(self, checked)
        timer = getattr(self, "_scan_timer", None)
        if not checked or timer is None:
            return
        try:
            interval_s = float(
                (getattr(self, "_config", None) or {}).get("scan_interval_seconds") or 3
            )
        except (TypeError, ValueError):
            interval_s = 3.0
        ms = max(100, min(10000, int(interval_s * 1000)))
        timer.setInterval(ms)
        log.info("scan_cadence: scan interval set to %d ms", ms)

    wrapped._card_lock_cadence = True
    MiningSignalsApp._on_scan_toggle = wrapped
    log.info("scan_cadence: scan-timer wrap installed")
