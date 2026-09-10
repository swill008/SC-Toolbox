"""Install Free-Domain card lock at import time.

Keeps the huge api.py / onnx_hud_reader.py trees untouched and patches
the live scan path so OCR reads glow-padded taught boxes inside the
TOP+BOT bar square.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)
_installed = False


def install() -> None:
    global _installed
    if _installed:
        return
    try:
        _install()
        _installed = True
        log.info("card_lock_boot: installed (bars + tight crops)")
    except Exception as exc:
        log.warning("card_lock_boot: install failed: %s", exc)


def _install() -> None:
    from . import scan_results_match as srm
    from . import debug_overlay as dbg
    from . import calibration as cal

    _patch_square(srm)
    _patch_overlay(dbg)
    _patch_skeleton()
    _patch_find_label_rows()
    _patch_crops(cal)
    log.info("card_lock_boot: patches applied")


def _patch_square(srm) -> None:
    orig = srm.find_scan_results_square

    def wrapped(
        img,
        *,
        hint_boxes=None,
        search_top=None,
        search_bot=None,
        title=None,
        use_title=False,
        **_kw,
    ):
        # Dummy title keeps the old finder from running NCC / chip lock.
        if not use_title:
            title = {"score": 0.0, "title_h": 0, "title_w": 0, "title_x": 0, "title_y": 0}
        out = orig(
            img,
            hint_boxes=hint_boxes,
            search_top=search_top,
            search_bot=search_bot,
            title=title,
        )
        if isinstance(out, dict):
            out.setdefault("top_bar", (int(out["x"]), int(out.get("top_y") or out["y"]), int(out["w"])))
            out.setdefault("bot_bar", (int(out["x"]), int(out.get("bot_y") or (out["y"] + out["h"])), int(out["w"])))
        return out

    srm.find_scan_results_square = wrapped


def _patch_overlay(dbg) -> None:
    orig = dbg.set_panel_finder

    def wrapped(*args, **kwargs):
        top_bar = kwargs.pop("top_bar", None)
        bot_bar = kwargs.pop("bot_bar", None)
        clear_title = kwargs.pop("clear_title", False)
        orig(*args, **kwargs)
        pf = dbg._state.get("panel_finder")
        if not isinstance(pf, dict):
            return
        if clear_title:
            pf["title_box"] = None
            pf["title_box_ts"] = 0
        if top_bar is not None:
            pf["top_bar"] = tuple(int(v) for v in top_bar)
        if bot_bar is not None:
            pf["bot_bar"] = tuple(int(v) for v in bot_bar)

    dbg.set_panel_finder = wrapped


def _push_overlay(source: str, sq, rows) -> None:
    try:
        from . import debug_overlay as dbg
        from . import card_lock as cl
        mn = rows.get("_mineral_row") if rows else None
        mass = rows.get("mass") if rows else None
        pbox = top = bot = tbar = bbar = None
        if isinstance(sq, dict) and int(sq.get("h") or 0) >= 24:
            pbox = (int(sq["x"]), int(sq["y"]), int(sq["w"]), int(sq["h"]))
            top = int(sq.get("top_y") or sq["y"])
            bot = int(sq.get("bot_y") or (sq["y"] + sq["h"]))
            if sq.get("top_bar"):
                tbar = tuple(int(v) for v in sq["top_bar"])
            if sq.get("bot_bar"):
                bbar = tuple(int(v) for v in sq["bot_bar"])
            cl.set_square(sq)
        else:
            cl.set_square(None)
        dbg.set_panel_finder(
            top_y=top,
            mineral_y_top=mn[0] if mn else None,
            mineral_y_bot=mn[1] if mn else None,
            mineral_center=((mn[0] + mn[1]) // 2 if mn else None),
            pitch=((mass[1] - mass[0]) if mass else None),
            bot_line_y=bot,
            source=source,
            title_box=None,
            panel_box=pbox,
            top_bar=tbar,
            bot_bar=bbar,
            clear_title=True,
        )
    except Exception as exc:
        log.debug("card_lock_boot overlay failed: %s", exc)


def _stash_tight(fields, out, sx, img_w, img_h) -> None:
    from . import card_lock as cl
    tight = {}
    for field, spec in (fields or {}).items():
        if field not in out or not isinstance(spec, dict):
            continue
        try:
            tw = max(1, int(round(int(spec.get("w") or 1) * sx)))
        except (TypeError, ValueError):
            tw = 24
        y1, y2, x0 = out[field]
        raw = (int(x0), int(y1), int(tw), max(4, int(y2 - y1)))
        if cl.is_fused_span(tw, int(spec.get("w") or tw)):
            log.info("card_lock_boot: refuse fused %s live_w=%d", field, tw)
            continue
        tight[field] = cl.pad_box(raw, img_w, img_h)
    if tight:
        cl.set_all_tight(tight)
        log.info("card_lock_boot: tight crops padded=%s", tight)


def _patch_skeleton() -> None:
    from .. import onnx_hud_reader as hud

    orig = hud._label_rows_from_learned_skeleton

    def wrapped(region, img_w, img_h, title_box=None, live_anchor=None, img=None):
        del title_box, live_anchor
        rows = orig(region, img_w, img_h, title_box=None, live_anchor=None, img=img)
        try:
            from . import calibration as cal
            from . import card_lock as cl
            from .scan_results_match import find_scan_results_square
            sk = cal.get_learned_skeleton(region)
            fields = (sk or {}).get("fields") or {}
            taught_panel = (sk or {}).get("panel") if sk else None
            sx, sy = hud._hud_region_to_img_scale(
                region, img_w, img_h,
                (sk or {}).get("capture_w") if sk else None,
                (sk or {}).get("capture_h") if sk else None,
            )
            live_sq = None
            if img is not None:
                hint = {}
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
                    tpw = max(1.0, int(taught_panel["w"]) * sx)
                    tph = max(1.0, int(taught_panel["h"]) * sy)
                    lpx = float(live_sq["x"])
                    lpy = float(live_sq["y"])
                    lpw = max(1.0, float(live_sq["w"]))
                    lph = max(1.0, float(live_sq["h"]))
                    scale_ok = 0.70 <= (lph / tph) <= 1.40 and 0.70 <= (lpw / tpw) <= 1.40
                    p_sx = (lpw / tpw) if scale_ok else 1.0
                    p_sy = (lph / tph) if scale_ok else 1.0
                    dx = int(round(lpx - tpx))
                    dy = int(round(lpy - tpy))
                    if abs(dx) <= 160 and abs(dy) <= 160:
                        shifted = {}
                        for f, spec in fields.items():
                            if f not in rows or not isinstance(spec, dict):
                                continue
                            bx = int(spec["x"]) * sx
                            by = int(spec["y"]) * sy
                            bh = int(spec["h"]) * sy
                            nx = int(round(lpx + (bx - tpx) * p_sx))
                            ny = int(round(lpy + (by - tpy) * p_sy))
                            nh = max(4, int(round(bh * p_sy)))
                            ny1 = max(0, min(img_h, ny))
                            ny2 = max(0, min(img_h, ny + nh))
                            if ny2 - ny1 >= 4:
                                shifted[f] = (ny1, ny2, max(0, min(img_w - 1, nx)))
                        if shifted:
                            rows.update(shifted)
                            log.info(
                                "card_lock_boot: square follow dx=%d dy=%d live=%s",
                                dx, dy,
                                {k: live_sq.get(k) for k in ("x", "y", "w", "h")},
                            )
            else:
                hud._set_cached_panel_square(None)
                log.info("card_lock_boot: square miss — boxes frozen")
            _stash_tight(fields, rows, sx, img_w, img_h)
            _push_overlay("card_lock_bars", live_sq, rows)
        except Exception as exc:
            log.debug("card_lock_boot skeleton wrap failed: %s", exc)
        return rows

    hud._label_rows_from_learned_skeleton = wrapped


def _patch_find_label_rows() -> None:
    from .. import onnx_hud_reader as hud

    orig = hud._find_label_rows_impl_body

    def wrapped(img):
        region = hud._get_current_region()
        if region is not None:
            try:
                from . import calibration as cal
                if cal.get_learned_skeleton(region):
                    rows = hud._label_rows_from_learned_skeleton(
                        region, img.width, img.height,
                        live_anchor=None, img=img,
                    )
                    if rows and "mass" in rows and "resistance" in rows:
                        log.info(
                            "card_lock_boot: skeleton rows=%s — skip PRE-ANCHOR",
                            {k: v[:2] for k, v in rows.items()},
                        )
                        hud._emit_label_rows_overlay(rows)
                        return rows
            except Exception as exc:
                log.debug("card_lock_boot early skeleton failed: %s", exc)
        return orig(img)

    hud._find_label_rows_impl_body = wrapped


def _patch_crops(cal) -> None:
    from .. import onnx_hud_reader as hud
    try:
        from . import api as api_mod
    except Exception:
        api_mod = None

    orig_get_row = cal.get_row

    def get_row(region, field, dy=0):
        from . import card_lock as cl
        box = cl.get_tight(str(field))
        if box is not None:
            x, y, w, h = box
            log.info("card_lock_boot: get_row %s -> tight %s", field, box)
            return {"x": int(x), "y": int(y), "w": int(w), "h": int(h)}
        return orig_get_row(region, field, dy=dy)

    cal.get_row = get_row

    orig_fvc = hud._find_value_crop

    def find_value_crop(img, gray, y1, y2, x_min=0):
        from . import card_lock as cl
        tight = cl.all_tight()
        if tight:
            best = None
            best_d = 10 ** 9
            for field, (x, y, w, h) in tight.items():
                cy = y + h / 2.0
                mid = (int(y1) + int(y2)) / 2.0
                d = abs(cy - mid)
                if d < best_d:
                    best_d = d
                    best = (field, x, y, w, h)
            if best is not None and best_d <= 40:
                field, x, y, w, h = best
                x0, y0 = max(0, x), max(0, y)
                x1 = min(img.width, x + w)
                y1c = min(img.height, y + h)
                if x1 - x0 >= 4 and y1c - y0 >= 6:
                    log.info(
                        "card_lock_boot: value_crop %s box=(%d,%d,%d,%d) match_d=%.1f",
                        field, x0, y0, x1 - x0, y1c - y0, best_d,
                    )
                    return img.crop((x0, y0, x1, y1c))
            log.info("card_lock_boot: skip full-row detect (tight stash exists)")
            return None
        return orig_fvc(img, gray, y1, y2, x_min=x_min)

    hud._find_value_crop = find_value_crop
    if api_mod is not None and getattr(api_mod, "_find_value_crop", None) is not None:
        api_mod._find_value_crop = find_value_crop
