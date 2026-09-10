"""SC-OCR: custom OCR engine for Star Citizen HUD/terminal text."""
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
except Exception as _boot_exc:
    import logging as _logging
    _logging.getLogger(__name__).warning(
        "card_lock_boot install skipped: %s", _boot_exc,
    )

try:
    from . import scan_cadence as _scan_cadence
    _scan_cadence.quiet_diag()
except Exception:
    pass

try:
    from . import debug_levels as _debug_levels
    _debug_levels.install()
except Exception:
    pass

__all__ = ["scan_region", "scan_hud_onnx", "scan_refinery"]
