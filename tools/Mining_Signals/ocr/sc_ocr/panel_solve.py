"""Single rigid-pose authority for the HUD panel."""
from __future__ import annotations

import logging
from typing import Optional

log = logging.getLogger(__name__)

ANCHOR_OFFSETS: dict[str, tuple[float, float]] = {
    "scan_results":      (0.0, 0.0),
    "label_mass":        (0.0, 3.33),
    "label_resistance":  (0.0, 4.98),
    "label_instability": (0.0, 6.64),
}

ROW_CENTER_MULTS: dict[str, float] = {
    "_mineral_row": 2.60,
    "mass":         4.18,
    "resistance":   5.62,
    "instability":  7.06,
}

_ROW_HALF_H_MULT = 0.62
_RES_FLOOR = 8.0
_RES_MULT = 3.0

_LAST_POSE: "Optional[dict]" = None
_LIVE_TS: float = 0.0


def note_live_frame() -> None:
    import time
    global _LIVE_TS
    _LIVE_TS = time.monotonic()


def last_pose() -> "Optional[dict]":
    return _LAST_POSE


def locked_scale() -> "Optional[float]":
    return None


def solve(
    title: "Optional[dict]",
    labels: "Optional[dict]",
) -> "Optional[dict]":
    """Solve one panel pose from title + label matches."""
    global _LAST_POSE
    try:
        from hud_tracker.rigid_body import solve_panel_pose
    except Exception as exc:
        log.debug("panel_solve: rigid_body unavailable: %s", exc)
        return _solve_from_title(title)

    meas: list[tuple[str, float, float]] = []
    if title is not None:
        try:
            meas.append((
                "scan_results",
                float(title["title_x"]), float(title["title_y"]),
            ))
        except Exception:
            pass
    if labels:
        for fld, key in (("mass", "label_mass"),
                         ("resistance", "label_resistance"),
                         ("instability", "label_instability")):
            m = labels.get(fld)
            if m is not None:
                try:
                    meas.append((key, float(m["x"]), float(m["y"])))
                except Exception:
                    pass
    if len(meas) < 2:
        return _solve_from_title(title)

    res = solve_panel_pose(meas, ANCHOR_OFFSETS)
    if res is None:
        return _solve_from_title(title)
    px, py, scale, residuals = res
    if not (4.0 <= float(scale) <= 200.0):
        return _solve_from_title(title)
    _LAST_POSE = {
        "x": float(px), "y": float(py), "scale": float(scale),
        "residuals": dict(residuals or {}),
        "anchors": [m[0] for m in meas],
        "rejected": [],
        "stab": "fresh",
    }
    return dict(_LAST_POSE)


def _solve_from_title(title: "Optional[dict]") -> "Optional[dict]":
    """Fallback: origin + scale from the SCAN RESULTS title box alone."""
    global _LAST_POSE
    if not isinstance(title, dict):
        return None
    try:
        px = float(title.get("title_x", title.get("x", 0)))
        py = float(title.get("title_y", title.get("y", 0)))
        scale = float(title.get("title_h") or title.get("h") or 0)
    except Exception:
        return None
    if scale < 4.0:
        return None
    _LAST_POSE = {
        "x": px, "y": py, "scale": scale,
        "residuals": {},
        "anchors": ["scan_results"],
        "rejected": [],
        "stab": "title-only",
    }
    return dict(_LAST_POSE)


def row_band(pose: dict, field: str, img_h: int,
             label_right: int) -> "Optional[tuple[int, int, int]]":
    if field not in ROW_CENTER_MULTS:
        return None
    cy = pose["y"] + pose["scale"] * ROW_CENTER_MULTS[field]
    half = max(8.0, pose["scale"] * _ROW_HALF_H_MULT)
    y1 = max(0, int(round(cy - half)))
    y2 = min(int(img_h), int(round(cy + half)))
    if y2 - y1 < 6:
        return None
    return (y1, y2, int(label_right))


def title_box(pose: dict) -> "tuple[int, int, int, int]":
    h = int(round(pose["scale"]))
    return (int(round(pose["x"])), int(round(pose["y"])),
            int(round(5.6429 * h)), h)
