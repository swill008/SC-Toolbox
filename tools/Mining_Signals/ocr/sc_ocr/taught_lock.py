"""Taught-box lock: never call the old p_sy scaler.

Installed after card_lock_boot. Replaces
``_label_rows_from_learned_skeleton`` so boxes are taught w×h
upsampled by HUD sx/sy, then translated by square dx/dy only.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)
_installed = False


def install() -> None:
    global _installed
    if _installed:
        return
    from .. import onnx_hud_reader as hud
    from . import calibration as cal
    from . import card_lock as cl
    from . import debug_overlay as dbg
    from .scan_results_match import find_scan_results_square

    orig = hud._label_rows_from_learned_skeleton

    def _rows_from_taught(fields, sx, sy, img_w, img_h):
        rows = {}
        for f, spec in (fields or {}).items():
            if not isinstance(spec, dict):
                continue
            try:
                x = int(round(int(spec["x"]) * sx))
                y = int(round(int(spec["y"]) * sy))
                h = max(4, int(round(int(spec["h"]) * sy)))
            except (KeyError, TypeError, ValueError):
                continue
            y1 = max(0, min(img_h, y))
            y2 = max(0, min(img_h, y + h))
            if y2 - y1 >= 4:
                rows[str(f)] = (y1, y2, max(0, min(img_w - 1, x)))
        return rows

    def wrapped(region, img_w, img_h, title_box=None, live_anchor=None, img=None):
        del title_box, live_anchor
        sk = cal.get_learned_skeleton(region)
        fields = (sk or {}).get("fields") or {}
        if not fields:
            return orig(region, img_w, img_h, title_box=None, live_anchor=None, img=img)
        taught_panel = (sk or {}).get("panel") if sk else None
        sx, sy = hud._hud_region_to_img_scale(
            region, img_w, img_h,
            (sk or {}).get("capture_w") if sk else None,
            (sk or {}).get("capture_h") if sk else None,
        )
        rows = _rows_from_taught(fields, sx, sy, img_w, img_h)
        live_sq = None
        hint = {}
        if img is not None:
            for f, spec in fields.items():
                if not isinstance(spec, dict):
                    continue
                try:
                    hint[f] = {
                        "x": int(round(int(spec["x"]) * sx)),
                        "y": int(round(int(spec["y"]) * sy)),
                        "w": int(round(int(spec.get("w") or 1) * sx)),
                        "h": int(round(int(spec["h"]) * sy)),
                    }
                except (KeyError, TypeError, ValueError):
                    continue
            live_sq = find_scan_results_square(
                img, hint_boxes=hint or None, title=None, use_title=False,
            )
        if isinstance(live_sq, dict) and int(live_sq.get("h") or 0) >= 24:
            hud._set_cached_panel_square(live_sq)
            cl.set_square(live_sq)
            if isinstance(taught_panel, dict) and int(taught_panel.get("h") or 0) >= 24 and rows:
                tpx = int(taught_panel["x"]) * sx
                tpy = int(taught_panel["y"]) * sy
                dx = int(round(float(live_sq["x"]) - tpx))
                dy = int(round(float(live_sq["y"]) - tpy))
                if abs(dx) <= 160 and abs(dy) <= 160:
                    shifted = {}
                    for f, spec in fields.items():
                        if f not in rows or not isinstance(spec, dict):
                            continue
                        bx = int(spec["x"]) * sx
                        by = int(spec["y"]) * sy
                        bh = int(spec["h"]) * sy
                        nx = int(round(bx + dx))
                        ny = int(round(by + dy))
                        nh = max(4, int(round(bh)))
                        ny1 = max(0, min(img_h, ny))
                        ny2 = max(0, min(img_h, ny + nh))
                        if ny2 - ny1 >= 4:
                            shifted[f] = (ny1, ny2, max(0, min(img_w - 1, nx)))
                    if shifted:
                        rows.update(shifted)
                        log.info(
                            "taught_lock: TRANSLATE dx=%d dy=%d live=%s",
                            dx, dy,
                            {k: live_sq.get(k) for k in ("x", "y", "w", "h")},
                        )
        else:
            hud._set_cached_panel_square(None)
            log.info("taught_lock: square miss — taught boxes frozen")
        tight = {}
        for field, spec in fields.items():
            if field not in rows or not isinstance(spec, dict):
                continue
            try:
                tw = max(1, int(round(int(spec.get("w") or 1) * sx)))
            except (TypeError, ValueError):
                tw = 24
            y1, y2, x0 = rows[field]
            raw = (int(x0), int(y1), int(tw), max(4, int(y2 - y1)))
            if cl.is_fused_span(tw, int(spec.get("w") or tw)):
                continue
            padded = cl.pad_box(raw, img_w, img_h)
            tight[field] = padded
            dbg.set_value_crop(field, padded)
        if tight:
            cl.set_all_tight(tight)
            log.info("taught_lock: crops=%s", tight)
        try:
            from . import card_lock_boot as _boot
            _boot._push_overlay("taught_lock", live_sq, rows)
        except Exception as exc:
            log.warning("taught_lock overlay failed: %s", exc)
        log.info(
            "taught_lock: rows=%s (p_sy scaler skipped)",
            {k: v[:2] for k, v in rows.items()},
        )
        return rows

    hud._label_rows_from_learned_skeleton = wrapped
    _installed = True
    log.info("taught_lock: installed — orig p_sy scaler bypassed")
