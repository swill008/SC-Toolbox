"""Free-domain card lock: one SCAN RESULTS square + taught box crops.

Tight value boxes live here so api.scan_hud_onnx can crop the magenta
rectangles instead of running _find_value_crop across the whole row.
No detectors. Placement owns the boxes; OCR only reads them.
"""
from __future__ import annotations

import threading
from typing import Optional

_lock = threading.Lock()
# field -> (x, y, w, h) in the live upscaled HUD image
_tight: dict[str, tuple[int, int, int, int]] = {}
_square: Optional[dict] = None


def reset() -> None:
    global _square
    with _lock:
        _tight.clear()
        _square = None


def set_tight(field: str, box: tuple[int, int, int, int]) -> None:
    x, y, w, h = (int(v) for v in box)
    if w < 4 or h < 4:
        return
    with _lock:
        _tight[str(field)] = (x, y, w, h)


def set_all_tight(boxes: dict[str, tuple[int, int, int, int]]) -> None:
    with _lock:
        _tight.clear()
        for field, box in (boxes or {}).items():
            try:
                x, y, w, h = (int(v) for v in box)
            except (TypeError, ValueError):
                continue
            if w >= 4 and h >= 4:
                _tight[str(field)] = (x, y, w, h)


def get_tight(field: str) -> Optional[tuple[int, int, int, int]]:
    with _lock:
        box = _tight.get(str(field))
        return tuple(box) if box else None


def all_tight() -> dict[str, tuple[int, int, int, int]]:
    with _lock:
        return dict(_tight)


def set_square(square: Optional[dict]) -> None:
    global _square
    with _lock:
        _square = dict(square) if isinstance(square, dict) else None


def get_square() -> Optional[dict]:
    with _lock:
        return dict(_square) if _square else None


def title_is_real_card(title: Optional[dict], img_w: int, img_h: int) -> bool:
    """Reject 95x17 SCAN RESULTS chips. Real title is a wide banner."""
    if not isinstance(title, dict):
        return False
    try:
        score = float(title.get("score") or 0.0)
        w = int(title.get("title_w") or 0)
        h = int(title.get("title_h") or 0)
    except (TypeError, ValueError):
        return False
    if score < 0.55 or h < 20:
        return False
    if img_w > 0 and w < int(0.28 * img_w):
        return False
    if img_h > 0 and h > int(0.22 * img_h):
        return False
    return True
