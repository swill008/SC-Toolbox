"""SC-OCR: custom OCR engine for Star Citizen HUD/terminal text.

Replaces the previous three-engine stack (Tesseract + ONNX CNN +
PaddleOCR sidecar) with a single surgical pipeline of cheap
deterministic stages. Designed for a constrained alphabet on a
known sci-fi font at user-defined rectangles.

Pipeline:
    capture → preprocess → segment → classify → validate → (learn)

Public API preserves the legacy call signatures so ``ui/app.py``
doesn't need to change:

    from ocr.sc_ocr.api import scan_region, scan_hud_onnx, scan_refinery

See plan at ``.claude/plans/bright-swimming-piglet.md``.
"""
from __future__ import annotations

import os as _os
for _var in ("OMP_NUM_THREADS", "MKL_NUM_THREADS",
             "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS",
             "NUMEXPR_NUM_THREADS"):
    _os.environ.setdefault(_var, "1")

from .api import (  # noqa: E402
    scan_region,
    scan_hud_onnx,
    scan_refinery,
)

try:
    from . import card_lock_boot as _card_lock_boot
    _card_lock_boot.install()
except Exception:
    pass

try:
    from . import scan_cadence as _scan_cadence
    _scan_cadence.quiet_diag()
except Exception:
    pass

__all__ = ["scan_region", "scan_hud_onnx", "scan_refinery"]
