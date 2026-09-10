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


class _DiagDemote(logging.Filter):
    """Keep glyph [DIAG] off PowerShell unless DEBUG is on."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        if "[DIAG]" in msg:
            record.levelno = logging.DEBUG
            record.levelname = "DEBUG"
        return True


def _quiet_diag() -> None:
    api_log = logging.getLogger("ocr.sc_ocr.api")
    if not any(isinstance(f, _DiagDemote) for f in api_log.filters):
        api_log.addFilter(_DiagDemote())
    log.info("card_lock_boot: [DIAG] demoted to DEBUG")


def _install() -> None:
    from . import scan_results_match as srm
    from . import debug_overlay as dbg
    from . import calibration as cal

    _quiet_diag()
    _patch_square(srm)
    _patch_overlay(dbg)
    _patch_skeleton()
    _patch_find_label_rows()
    _patch_crops(cal)
    hook_overlay_autorefresh()
    log.info("card_lock_boot: patches applied")


def _bar_peaks(img):
    """Horizontal bright-run peaks. Same detector the square finder uses."""
    import numpy as np
    try:
        gray = np.asarray(img.convert("L"), dtype=np.uint8)
    except Exception:
        return [], 0, 0
    H, W = gray.shape[:2]
    if H < 40 or W < 40:
        return [], H, W
    if float(np.median(gray)) > 130:
        gray = 255 - gray
    thr = max(70, int(np.percentile(gray, 78)))
    binary = gray >= thr
    underline_run = max(16, int(0.22 * W))
    cands = []
    for y in range(H):
        row = binary[y]
        best = 0
        best_s = 0
        cur_s = None
        for i, v in enumerate(row):
            if v:
                if cur_s is None:
                    cur_s = i
            elif cur_s is not None:
                run = i - cur_s
                if run > best:
                    best = run
                    best_s = cur_s
                cur_s = None
        if cur_s is not None:
            run = W - cur_s
            if run > best:
                best = run
                best_s = cur_s
        if best < underline_run:
            continue
        cands.append({"y": y, "x": int(best_s), "w": int(best)})
    if not cands:
        return [], H, W
    by_y = {c["y"]: c for c in cands}
    peaks = []
    for c in cands:
        y = c["y"]
        left = by_y.get(y - 1)
        right = by_y.get(y + 1)
        if left and left["w"] > c["w"]:
            continue
        if right and right["w"] > c["w"]:
            continue
        peaks.append(c)
    return peaks or cands, H, W


def _snap_bot_to_easy(img, out, hint_boxes):
    """Rewrite square bottom to the line under EASY, not the inst rule.

    Orig finder used min(y) of bars at inst.bottom-8, so BOT LOCK sat
    on the digits. Search strictly BELOW the value rows and take the
    lowest wide bar in that band (under EASY / above COMPOSITION).
    Miss -> return None so follow freezes taught boxes.
    """
    if not isinstance(out, dict):
        return None
    peaks, H, W = _bar_peaks(img)
    if not peaks or H < 40:
        log.info("card_lock_boot: EASY snap — no bars, freeze")
        return None
    min_run = max(24, int(0.38 * W))
    y_bot_min = int(0.58 * H)
    y_bot_max = int(0.88 * H)
    if hint_boxes:
        bots = []
        for box in hint_boxes.values():
            if not isinstance(box, dict):
                continue
            try:
                bots.append(int(box["y"]) + int(box.get("h") or 0))
            except (KeyError, TypeError, ValueError):
                continue
        if bots:
            y_bot_min = max(bots) + 12
            y_bot_max = min(H - 1, max(y_bot_min + 8, int(0.92 * H)))
    top_y = int(out.get("top_y") or out.get("y") or 0)
    pool = [
        c for c in peaks
        if y_bot_min <= c["y"] <= y_bot_max
        and c["y"] > top_y + 12
        and c["w"] >= min_run
    ]
    if not pool:
        pool = [
            c for c in peaks
            if y_bot_min <= c["y"] <= y_bot_max and c["y"] > top_y + 12
        ]
    if not pool:
        log.info(
            "card_lock_boot: EASY bar miss win=%d-%d peaks=%d — freeze",
            y_bot_min, y_bot_max, len(peaks),
        )
        return None
    bot = max(pool, key=lambda c: c["y"])
    y = int(out.get("top_y") or out["y"])
    y2 = int(bot["y"])
    h = y2 - y
    if h < 24:
        log.info("card_lock_boot: EASY square too short h=%d — freeze", h)
        return None
    x = min(int(out["x"]), int(bot["x"]))
    x1 = max(int(out["x"] + out["w"]), int(bot["x"] + bot["w"]))
    out = dict(out)
    out["x"] = x
    out["y"] = y
    out["w"] = x1 - x
    out["h"] = h
    out["top_y"] = y
    out["bot_y"] = y2
    out["bot_bar"] = (int(bot["x"]), y2, int(bot["w"]))
    out.setdefault(
        "top_bar",
        (int(out["x"]), y, int(out["w"])),
    )
    log.info(
        "card_lock_boot: EASY bot_y=%d top_y=%d h=%d (not inst bar)",
        y2, y, h,
    )
    return out


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
        if not use_title:
            title = {"score": 0.0, "title_h": 0, "title_w": 0, "title_x": 0, "title_y": 0}
        out = orig(
            img,
            hint_boxes=hint_boxes,
            search_top=search_top,
            search_bot=search_bot,
            title=title,
        )
        out = _snap_bot_to_easy(img, out, hint_boxes)
        if isinstance(out, dict):
            out.setdefault(
                "top_bar",
                (int(out["x"]), int(out.get("top_y") or out["y"]), int(out["w"])),
            )
            out.setdefault(
                "bot_bar",
                (int(out["x"]), int(out.get("bot_y") or (out["y"] + out["h"])), int(out["w"])),
            )
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

    orig_write = dbg.write

    def write_with_gen() -> None:
        orig_write()
        try:
            import time
            path = getattr(dbg, "OUT_PATH", None)
            if path:
                with open(str(path) + ".gen", "w") as gf:
                    gf.write(str(int(time.time() * 1000)))
        except Exception:
            pass

    dbg.write = write_with_gen


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
        for field, box in cl.all_tight().items():
            dbg.set_value_crop(field, box)
    except Exception as exc:
        log.debug("card_lock_boot overlay failed: %s", exc)


def _stash_tight(fields, out, sx, img_w, img_h) -> None:
    from . import card_lock as cl
    from . import debug_overlay as dbg
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
        padded = cl.pad_box(raw, img_w, img_h)
        tight[field] = padded
        dbg.set_value_crop(field, padded)
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
                    lpx = float(live_sq["x"])
                    lpy = float(live_sq["y"])
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
                                "card_lock_boot: square follow TRANSLATE "
                                "dx=%d dy=%d live=%s",
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
            best_d = 10**9
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


def hook_overlay_autorefresh() -> None:
    """Reload Panel Finder when overlay .gen stamp changes.

    Windows in-place PNG saves often keep the same mtime, so _tick
    skipped the new frame until the user hit refresh.
    """
    try:
        from ui.panel_finder_popout import PanelFinderPopout
    except Exception as exc:
        log.debug("card_lock_boot: panel finder not ready (%s)", exc)
        return
    orig = getattr(PanelFinderPopout, "_tick", None)
    if orig is None or getattr(orig, "_gen_reload", False):
        return

    def wrapped(self, *args, **kwargs):
        try:
            import os
            path = getattr(self, "_overlay_path", None)
            gen = ""
            if path is not None:
                gen_path = str(path) + ".gen"
                if os.path.isfile(gen_path):
                    with open(gen_path, "r", encoding="utf-8") as fh:
                        gen = fh.read()
            if getattr(self, "_last_overlay_gen", None) != gen:
                self._last_mtime = 0.0
                self._last_overlay_gen = gen
        except Exception:
            try:
                self._last_mtime = 0.0
            except Exception:
                pass
        return orig(self, *args, **kwargs)

    wrapped._gen_reload = True
    PanelFinderPopout._tick = wrapped
    log.info("card_lock_boot: overlay auto-refresh hooked")


def patch_ui_scan_timer() -> None:
    """Honor config scan_interval_seconds (default 3). The app clamps to 500 ms."""
    try:
        from ui.app import MiningSignalsApp
    except Exception as exc:
        log.debug("card_lock_boot: ui app not ready (%s)", exc)
        return
    orig = getattr(MiningSignalsApp, "_on_scan_toggle", None)
    if orig is None or getattr(orig, "_card_lock_cadence", False):
        return

    def wrapped(self, checked):
        orig(self, checked)
        timer = getattr(self, "_scan_timer", None)
        if not checked or timer is None:
            return
        try:
            interval_s = float((getattr(self, "_config", None) or {}).get("scan_interval_seconds") or 3)
        except (TypeError, ValueError):
            interval_s = 3.0
        ms = max(100, min(10000, int(interval_s * 1000)))
        timer.setInterval(ms)
        log.info("card_lock_boot: scan interval set to %d ms", ms)

    wrapped._card_lock_cadence = True
    MiningSignalsApp._on_scan_toggle = wrapped
    log.info("card_lock_boot: scan-timer wrap installed")
    hook_overlay_autorefresh()
