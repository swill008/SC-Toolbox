"""Free-domain card lock: SCAN RESULTS square + taught box crops.

Bar finder owns the card. Taught magenta boxes are offsets inside
that card. OCR only reads those boxes plus a glow pad.

Miss (no top+bottom bar) -> do not move boxes.
"""
from __future__ import annotations

import threading
from typing import Optional

_lock = threading.Lock()
# field -> (x, y, w, h) in the live upscaled HUD image
_tight: dict[str, tuple[int, int, int, int]] = {}
_square: Optional[dict] = None
_last_good_square: Optional[dict] = None

GLOW_PAD = 6
BOTTOM_PAD = 12
HEIGHT_CAP = 72
WIDTH_SPAN_MULT = 2.6


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
    global _square, _last_good_square
    with _lock:
        if isinstance(square, dict) and int(square.get("h") or 0) >= 24:
            _square = dict(square)
            _last_good_square = dict(square)
        else:
            _square = None


def get_square() -> Optional[dict]:
    with _lock:
        return dict(_square) if _square else None


def get_last_good_square() -> Optional[dict]:
    with _lock:
        return dict(_last_good_square) if _last_good_square else None


def pad_box(
    box: tuple[int, int, int, int],
    img_w: int,
    img_h: int,
    pad: int = GLOW_PAD,
    height_cap: int = HEIGHT_CAP,
) -> tuple[int, int, int, int]:
    """Pad taught crop. Extra pad goes DOWN so glyph feet stay in frame.

    If the padded height exceeds ``height_cap``, trim the TOP, never
    the bottom (center-crop was cutting 6/8/9 in half).
    """
    x, y, w, h = (int(v) for v in box)
    p = max(0, int(pad))
    bp = max(p, int(BOTTOM_PAD))
    x0 = max(0, x - p)
    y0 = max(0, y - max(1, p // 3))
    x1 = min(int(img_w), x + w + p)
    y1 = min(int(img_h), y + h + bp)
    cap = max(8, int(height_cap))
    nh = y1 - y0
    if nh > cap:
        y0 = max(0, y1 - cap)
        y1 = min(int(img_h), y0 + cap)
    return (x0, y0, max(1, x1 - x0), max(1, y1 - y0))


def is_fused_span(live_w: int, taught_w: int) -> bool:
    try:
        lw = int(live_w)
        tw = max(1, int(taught_w))
    except (TypeError, ValueError):
        return False
    return lw > int(WIDTH_SPAN_MULT * tw) and lw > 120


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
