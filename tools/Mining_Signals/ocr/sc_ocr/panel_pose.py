"""Fingerprint-held panel pose state (verify, don't re-search)."""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional

import numpy as np
from PIL import Image

log = logging.getLogger(__name__)

_TILE_W = 24
_TILE_H = 10
_MATCH_THR = 0.90
_FORCE_REDETECT_EVERY = 20

_lock = threading.Lock()
_state: dict = {
    "rows": None,
    "tiles": None,
    "img_size": None,
    "holds": 0,
    "ts": 0.0,
}


def _band_box(img_w: int, img_h: int, entry) -> Optional[tuple]:
    try:
        y1, y2 = int(entry[0]), int(entry[1])
        lr = int(entry[2]) if len(entry) > 2 else img_w
        x2 = max(24, min(img_w, lr))
        if y2 - y1 < 4 or y2 > img_h or y1 < 0:
            return None
        return (0, y1, x2, y2)
    except Exception:
        return None


def _tile(img: Image.Image, box: tuple) -> Optional[np.ndarray]:
    try:
        t = img.crop(box).convert("L").resize(
            (_TILE_W, _TILE_H), Image.BILINEAR,
        )
        return np.asarray(t, dtype=np.float32)
    except Exception:
        return None


def _sim(a: np.ndarray, b: np.ndarray) -> float:
    fa = a - a.mean()
    fb = b - b.mean()
    den = float(np.sqrt((fa * fa).sum() * (fb * fb).sum())) + 1e-6
    return float((fa * fb).sum() / den)


def observe(img: Image.Image) -> Optional[dict]:
    with _lock:
        rows = _state["rows"]
        tiles = _state["tiles"]
        size = _state["img_size"]
        holds = _state["holds"]
    if not rows or not tiles:
        return None
    if size != img.size:
        return None
    if holds >= _FORCE_REDETECT_EVERY:
        log.debug("panel_pose: forced re-detection after %d holds", holds)
        return None
    for key, (box, ref) in tiles.items():
        cur = _tile(img, box)
        if cur is None:
            return None
        s = _sim(ref, cur)
        if s < _MATCH_THR:
            log.debug(
                "panel_pose: fingerprint break key=%s sim=%.3f "
                "(thr=%.2f) — trying envelope snap", key, s, _MATCH_THR,
            )
            return _snap(img)
    with _lock:
        if _state["rows"] is not rows:
            return None
        _state["holds"] += 1
        held_n = _state["holds"]
    if held_n in (1, _FORCE_REDETECT_EVERY - 1):
        log.debug("panel_pose: pose HELD (%d consecutive)", held_n)
    return dict(rows)


_SNAP_RANGE = 20
_SNAP_AGREE = 2


def _snap(img: Image.Image) -> Optional[dict]:
    import os as _os
    if _os.environ.get("SC_POSE_SNAP") != "1":
        return None
    with _lock:
        rows = _state["rows"]
        tiles = _state["tiles"]
        size = _state["img_size"]
    if not rows or not tiles or size != img.size:
        return None
    deltas: list = []
    sims: list = []
    for _key, (box, ref) in tiles.items():
        bx1, by1, bx2, by2 = box
        bs, bd = -1.0, None
        for dy in range(-_SNAP_RANGE, _SNAP_RANGE + 1):
            if by1 + dy < 0 or by2 + dy > img.height:
                continue
            cur = _tile(img, (bx1, by1 + dy, bx2, by2 + dy))
            if cur is None:
                continue
            s = _sim(ref, cur)
            if s > bs:
                bs, bd = s, dy
        if bd is None:
            return None
        deltas.append(bd)
        sims.append(bs)
    if len(deltas) < 2:
        return None
    if max(deltas) - min(deltas) > _SNAP_AGREE:
        return None
    if min(sims) < _MATCH_THR:
        return None
    dy = int(round(sum(deltas) / len(deltas)))
    if dy == 0:
        return None
    shifted = {
        k: (int(v[0]) + dy, int(v[1]) + dy) + tuple(v[2:])
        for k, v in rows.items()
    }
    store(img, shifted)
    log.info("panel_pose: pose SNAPPED dy=%+d", dy)
    return dict(shifted)


def store(img: Image.Image, rows: dict) -> None:
    if not rows:
        return
    needed = [k for k in ("mass", "resistance", "instability") if k in rows]
    if len(needed) < 2:
        return
    tiles: dict = {}
    w, h = img.size
    for key in needed + (["_mineral_row"] if "_mineral_row" in rows else []):
        box = _band_box(w, h, rows[key])
        if box is None:
            continue
        t = _tile(img, box)
        if t is None:
            continue
        tiles[key] = (box, t)
    if len(tiles) < 2:
        return
    with _lock:
        _state["rows"] = dict(rows)
        _state["tiles"] = tiles
        _state["img_size"] = img.size
        _state["holds"] = 0
        _state["ts"] = time.monotonic()


def reset() -> None:
    with _lock:
        _state["rows"] = None
        _state["tiles"] = None
        _state["img_size"] = None
        _state["holds"] = 0
        _state["ts"] = 0.0
