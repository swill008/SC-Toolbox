"""Single rigid-pose authority for the SIGNATURE panel (region2 skeleton).

The sibling of ``panel_solve``, but region2 has different physics, so the
design is different (per the project owner, 2026-06-14):

  * region2 does NOT jitter much — temporal hold is secondary here.
  * what matters is that everything stays SNAPPED TOGETHER.
  * the PILL finder + the COMMA are enough to snap it consistently.

So the icon is NOT the anchor (its NCC latches onto digit circle-on-stick
silhouettes — the known failure mode). Instead:

  PILL  = the panel FRAME.
  COMMA = the digit-grid landmark INSIDE the value.

Together: PILL snaps WHERE the value is, COMMA snaps HOW the digits align.
"""
from __future__ import annotations

import logging
from typing import Optional

log = logging.getLogger(__name__)

VALUE_DX = 0.420
VALUE_DY = 0.263
VALUE_W = 0.527
VALUE_H = 0.556

_PILL_H_MIN = 14.0
_PILL_H_MAX = 90.0

_LAST_POSE: "Optional[dict]" = None


def last_pose() -> "Optional[dict]":
    """Most recent solved signature pose, or None."""
    return _LAST_POSE


def value_box(pose: dict) -> "tuple[int, int, int, int]":
    """Derive the signature VALUE crop (x, y, w, h) rigidly from the pill."""
    px, py = pose["x"], pose["y"]
    pw, ph = pose["pill_w"], pose["pill_h"]
    return (int(round(px + VALUE_DX * pw)),
            int(round(py + VALUE_DY * ph)),
            int(round(VALUE_W * pw)),
            int(round(VALUE_H * ph)))


def solve(pill: "Optional[tuple]",
          comma_x: "Optional[float]" = None) -> "Optional[dict]":
    """Solve the signature pose from the PILL (+ optional comma)."""
    if pill is None:
        return None
    px, py, pw, ph = (float(pill[0]), float(pill[1]),
                      float(pill[2]), float(pill[3]))
    if not (_PILL_H_MIN <= ph <= _PILL_H_MAX) or pw <= 0:
        log.debug("signal_solve: implausible pill h=%.1f w=%.1f — reject",
                  ph, pw)
        return None

    global _LAST_POSE
    pose = {
        "x": px, "y": py, "pill_w": pw, "pill_h": ph,
        "comma_x": (float(comma_x) if comma_x is not None else None),
        "stab": "fresh",
    }
    pose["value_box"] = value_box(pose)
    _LAST_POSE = pose
    return dict(pose)
