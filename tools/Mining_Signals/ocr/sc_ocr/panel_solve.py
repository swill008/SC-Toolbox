"""Single rigid-pose authority for the HUD panel (the welded skeleton).

The HUD is a RIGID template: SCAN RESULTS, the mineral name, and the
MASS / RESISTANCE / INSTABILITY rows all sit at FIXED offsets from one
panel origin, scaled by one factor. Knowing where any two anchors are
determines where everything is. Yet historically each detector
searched for itself independently, so a dust-matched title, a wandering
mineral band, or a jumping value crop could each be wrong on its own —
the heart ending up in the foot.

This module welds them. Each scan, ALL anchor observations (title +
the three labels) feed ONE least-squares pose solve
(``hud_tracker.rigid_body.solve_panel_pose``); a high-residual anchor
(the dust title, the off mineral) is an OUTLIER and is rejected, then
the pose is re-solved from the survivors; and EVERY box is then derived
as ``origin + scale * template_offset``. The disagreements become
structurally impossible: you cannot have the title right and the
mineral wrong when the mineral is a fixed offset below the title.

Proven on 66 hand-annotated panels (2026-06-13): one pose places every
row CENTER within ~1px median / <=5px on 92-94% of panels — tighter
and far more robust than the independent detectors it replaces. The
constants below are calibrated against those annotations.
"""
from __future__ import annotations

import logging
from typing import Optional

log = logging.getLogger(__name__)

# Anchor template offsets (dy in title-height units from the panel
# origin = SCAN RESULTS top-left). dx is ~0 (the HUD left-aligns).
# These are the label TOP-LEFT offsets the solver fits against.
ANCHOR_OFFSETS: dict[str, tuple[float, float]] = {
    "scan_results":      (0.0, 0.0),
    "label_mass":        (0.0, 3.33),
    "label_resistance":  (0.0, 4.98),
    "label_instability": (0.0, 6.64),
}

# Row-CENTER multipliers (title-h units, origin->row center), CALIBRATED
# on the annotated set (med row-center error <=0.3px after these).
ROW_CENTER_MULTS: dict[str, float] = {
    "_mineral_row": 2.60,   # estimate (between title and mass; no clean GT)
    "mass":         4.18,
    "resistance":   5.62,
    "instability":  7.06,
}

# Row band half-height as a fraction of scale (title height). The HUD
# value text is ~0.55x the title height; a generous half-band.
_ROW_HALF_H_MULT = 0.62

# Outlier rejection: an anchor whose residual exceeds max(_RES_FLOOR,
# _RES_MULT x median) does not fit the rigid body and is dropped.
_RES_FLOOR = 8.0
_RES_MULT = 3.0

# Temporal stabilization constants + scale lock + live heartbeat.
_HOLD_DEADBAND = 9.0
_HOLD_EMA = 0.4
_HOLD_TELEPORT = 60.0
_SCALE_LO = 0.65
_SCALE_HI = 1.55
_SCALE_LOCK_TOL = 0.10
_SCALE_LOCK_TTL = 60.0
_SCALE_FIT_FRAC = 0.35
_SCALE_RELOCK_MIN = 0.20
_LOCKED_SCALE: "Optional[float]" = None
_LOCKED_SCALE_TS: float = 0.0
_CAND_SCALE: "Optional[float]" = None
_MAX_HELD_REJECTS = 6
_REJECT_RUN: int = 0
_VEL_DECAY = 0.45
_AB_STATIONARY = 0.45
_AB_TRACK = 0.75
_VEL_X: float = 0.0
_VEL_Y: float = 0.0
_PREV_MX: "Optional[float]" = None
_PREV_MY: "Optional[float]" = None
_LIVE_GATE_SEC = 12.0
_HOLD_TTL_SEC = 15.0
_LAST_POSE: "Optional[dict]" = None
_LAST_POSE_TS: float = 0.0
_LIVE_TS: float = 0.0


def note_live_frame() -> None:
    """Heartbeat from the LIVE capture loop — call once per real frame."""
    global _LIVE_TS
    import time
    _LIVE_TS = time.monotonic()


def last_pose() -> "Optional[dict]":
    return _LAST_POSE


def locked_scale() -> "Optional[float]":
    return _LOCKED_SCALE


def solve(
    title: "Optional[dict]",
    labels: "Optional[dict]",
) -> "Optional[dict]":
    """Solve ONE panel pose from the available anchors."""
    try:
        from hud_tracker.rigid_body import solve_panel_pose
    except Exception as exc:
        log.debug("panel_solve: rigid_body unavailable: %s", exc)
        return None

    meas: list[tuple[str, float, float]] = []
    if title is not None:
        meas.append((
            "scan_results",
            float(title["title_x"]), float(title["title_y"]),
        ))
    if labels:
        for fld, key in (("mass", "label_mass"),
                        ("resistance", "label_resistance"),
                        ("instability", "label_instability")):
            m = labels.get(fld)
            if m is not None:
                meas.append((key, float(m["x"]), float(m["y"])))
    if len(meas) < 2:
        return None

    res = solve_panel_pose(meas, ANCHOR_OFFSETS)
    if res is None:
        return None
    px, py, scale, residuals = res
    rejected: list[str] = []

    global _LAST_POSE, _LAST_POSE_TS, _REJECT_RUN
    global _VEL_X, _VEL_Y, _PREV_MX, _PREV_MY
    import time as _t
    _now = _t.monotonic()
    _live = _LIVE_TS > 0.0 and (_now - _LIVE_TS) <= _LIVE_GATE_SEC
    _held = (
        _LAST_POSE is not None and _live
        and (_now - _LAST_POSE_TS) <= _HOLD_TTL_SEC
    )

    if residuals and len(meas) >= 3:
        rv = sorted(residuals.values())
        med = rv[len(rv) // 2]
        thr = max(_RES_FLOOR, _RES_MULT * med)
        bad = [k for k, v in residuals.items() if v > thr]
        if bad and (len(meas) - len(bad)) >= 2:
            meas2 = [m for m in meas if m[0] not in bad]
            res2 = solve_panel_pose(meas2, ANCHOR_OFFSETS)
            if res2 is not None:
                px, py, scale, residuals = res2
                rejected = bad
                log.info(
                    "panel_solve: rejected outlier anchor(s) %s "
                    "(residual>%.1f) — re-solved pose from %d anchors",
                    bad, thr, len(meas2),
                )

    if not (4.0 <= scale <= 200.0):
        return None

    global _LOCKED_SCALE, _LOCKED_SCALE_TS, _CAND_SCALE
    _scale_rejected = False
    if _live:
        _locked = (_LOCKED_SCALE is not None
                   and (_now - _LOCKED_SCALE_TS) <= _SCALE_LOCK_TTL)
        if _locked:
            _rf = solve_panel_pose(
                meas, ANCHOR_OFFSETS, fixed_scale=_LOCKED_SCALE,
            )
            _fit_ok = False
            if _rf is not None:
                _rr = _rf[3] or {}
                _rmed = (sorted(_rr.values())[len(_rr) // 2]
                         if _rr else 0.0)
                if _rmed <= max(_RES_FLOOR,
                                _SCALE_FIT_FRAC * _LOCKED_SCALE):
                    px, py, scale = _rf[0], _rf[1], float(_LOCKED_SCALE)
                    _LOCKED_SCALE_TS = _now
                    _CAND_SCALE = None
                    _fit_ok = True
            if not _fit_ok:
                if (_CAND_SCALE is not None
                        and abs(scale - _CAND_SCALE)
                        <= _SCALE_LOCK_TOL * max(scale, _CAND_SCALE)
                        and abs(scale - _LOCKED_SCALE)
                        > _SCALE_RELOCK_MIN * _LOCKED_SCALE):
                    _LOCKED_SCALE = 0.5 * (scale + _CAND_SCALE)
                    _LOCKED_SCALE_TS = _now
                    _CAND_SCALE = None
                    scale = float(_LOCKED_SCALE)
                    log.warning("panel_solve: scale RE-LOCKED to %.1f",
                                _LOCKED_SCALE)
                else:
                    _CAND_SCALE = scale
                    scale = float(_LOCKED_SCALE)
                    _scale_rejected = True
        else:
            if (_CAND_SCALE is not None
                    and abs(scale - _CAND_SCALE)
                    <= _SCALE_LOCK_TOL * max(scale, _CAND_SCALE)):
                _LOCKED_SCALE = 0.5 * (scale + _CAND_SCALE)
                _LOCKED_SCALE_TS = _now
                _CAND_SCALE = None
                scale = float(_LOCKED_SCALE)
                log.warning("panel_solve: scale LOCKED at %.1f",
                            _LOCKED_SCALE)
            else:
                _CAND_SCALE = scale

    stab = "fresh"
    if _held:
        _hx, _hy = _LAST_POSE["x"], _LAST_POSE["y"]
        if _scale_rejected:
            _REJECT_RUN += 1
            if _REJECT_RUN <= _MAX_HELD_REJECTS:
                _LAST_POSE_TS = _now
            _LAST_POSE = {**_LAST_POSE, "stab": "reject"}
            return dict(_LAST_POSE)
        _REJECT_RUN = 0
        if _PREV_MX is not None:
            _VEL_X = _VEL_DECAY * _VEL_X + (1 - _VEL_DECAY) * (px - _PREV_MX)
            _VEL_Y = _VEL_DECAY * _VEL_Y + (1 - _VEL_DECAY) * (py - _PREV_MY)
        _PREV_MX, _PREV_MY = px, py
        _spd = (_VEL_X * _VEL_X + _VEL_Y * _VEL_Y) ** 0.5
        if _spd < _AB_STATIONARY:
            _VEL_X = _VEL_Y = 0.0
            _dx, _dy = px - _hx, py - _hy
            _dist = (_dx * _dx + _dy * _dy) ** 0.5
            if _dist <= _HOLD_DEADBAND:
                px, py = _hx, _hy
                stab = "hold"
            elif _dist <= _HOLD_TELEPORT:
                px = _hx + _HOLD_EMA * _dx
                py = _hy + _HOLD_EMA * _dy
                stab = "ema"
            else:
                stab = "accept"
                _PREV_MX, _PREV_MY = px, py
        else:
            _predx, _predy = _hx + _VEL_X, _hy + _VEL_Y
            _dx, _dy = px - _predx, py - _predy
            _dist = (_dx * _dx + _dy * _dy) ** 0.5
            if _dist <= _HOLD_TELEPORT:
                px = _predx + _AB_TRACK * _dx
                py = _predy + _AB_TRACK * _dy
                stab = "track"
            else:
                stab = "accept"
                _VEL_X = _VEL_Y = 0.0
                _PREV_MX, _PREV_MY = px, py

    _REJECT_RUN = 0
    if stab == "fresh":
        _VEL_X = _VEL_Y = 0.0
        _PREV_MX, _PREV_MY = px, py
    _LAST_POSE = {
        "x": float(px), "y": float(py), "scale": float(scale),
        "residuals": dict(residuals or {}),
        "anchors": [m[0] for m in meas if m[0] not in rejected],
        "rejected": rejected,
        "stab": stab,
    }
    _LAST_POSE_TS = _now
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
