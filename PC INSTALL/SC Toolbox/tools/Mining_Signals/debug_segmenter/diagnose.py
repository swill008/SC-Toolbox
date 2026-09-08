"""Headless reproduction of the region2 signature segmenter bug.

Mirrors the runtime path in ``ocr.sc_ocr.api._signal_recognize_pil`` for a
single capture and prints what each pipeline stage does to the binary
mask + glyph spans. Saves debug images for visual inspection.

Usage::
    python -m debug_segmenter.diagnose <path-to-region2.png>
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
from PIL import Image

# Ensure we can import the runtime sc_ocr package from the repo root.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Verbose logging so the api module's [DIAG] WARNING lines surface.
logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(message)s")

from ocr.sc_ocr import api as _api  # noqa: E402

logging.getLogger("ocr.sc_ocr.api").setLevel(logging.DEBUG)


def _save_gray(path: Path, arr: np.ndarray) -> None:
    Image.fromarray(arr.astype(np.uint8), mode="L").save(str(path))


def _save_rgb(path: Path, arr: np.ndarray) -> None:
    Image.fromarray(arr.astype(np.uint8), mode="RGB").save(str(path))


def diagnose(png_path: Path, gt_value: str, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    cap_id = png_path.stem
    log = logging.getLogger("diag")

    img = Image.open(str(png_path)).convert("RGB")
    rgb = np.asarray(img, dtype=np.uint8)
    gray = rgb.max(axis=2).astype(np.uint8)

    log.info("─── %s gt=%s shape=%s ───", cap_id, gt_value, gray.shape)

    # ── Reproduce crop_box derivation (world_model_region2 path) ──
    crop_box: Optional[Tuple[int, int, int, int]] = None
    wmr = _api._load_region2_world_model_for_api()
    if wmr is not None:
        vfrac = (wmr.get("features") or {}).get("value")
        pill = _api._find_pill_for_signal(rgb) if vfrac else None
        if vfrac and pill is not None:
            px, py, pw, ph = pill
            vx = int(round(px + float(vfrac["x_frac"]["mean"]) * pw))
            vy = int(round(py + float(vfrac["y_frac"]["mean"]) * ph))
            vw = int(round(float(vfrac["w_frac"]["mean"]) * pw))
            vh = int(round(float(vfrac["h_frac"]["mean"]) * ph))
            try:
                from hud_tracker.anchors.icon_voter import (
                    localize_icon as _li,
                )
                icon_loc = _li(rgb)
                if icon_loc is not None:
                    ix, iy, iw, ih = icon_loc["bbox"]
                    icon_anchor = ix + iw + max(2, int(pw * 0.03))
                    delta = vx - icon_anchor
                    vx = icon_anchor
                    vw = vw + delta
                    log.info("icon-anchored vx=%d (delta=%+d)", vx, -delta)
            except Exception as exc:
                log.info("icon refinement skipped: %s", exc)
            rhs_ceiling = px + pw - max(2, int(pw * 0.05))
            digits_x2 = min(vx + vw, rhs_ceiling, gray.shape[1])
            digits_x1 = max(0, vx)
            digits_y1 = max(0, vy)
            digits_y2 = min(vy + vh, gray.shape[0])
            if digits_x2 - digits_x1 >= 20 and digits_y2 - digits_y1 >= 8:
                crop_box = (digits_x1, digits_y1, digits_x2, digits_y2)

    if crop_box is None:
        log.error("crop_box derivation FAILED — wmr=%s pill=%s", bool(wmr),
                  bool(_api._find_pill_for_signal(rgb)) if wmr else None)
        return {"capture": cap_id, "gt": gt_value, "error": "no crop_box"}

    x1, y1, x2, y2 = crop_box
    log.info("crop_box=%s (W=%d, H=%d)", crop_box, x2 - x1, y2 - y1)
    work = gray[y1:y2, x1:x2].copy()
    work_rgb = rgb[y1:y2, x1:x2].copy()

    _save_gray(out_dir / f"{cap_id}_00_cropbox_gray.png", work)
    _save_rgb(out_dir / f"{cap_id}_00_cropbox_rgb.png", work_rgb)

    # ── Row-isolate (skip for manual; we have automatic) ──
    try:
        import sys
        scripts = ROOT / "scripts"
        if str(scripts) not in sys.path:
            sys.path.insert(0, str(scripts))
        import extract_labeled_glyphs as xlg  # type: ignore
        band = (
            xlg._find_main_row_bounds(work)
            if hasattr(xlg, "_find_main_row_bounds") else None
        )
        if band is not None:
            by1, by2 = band
            log.info("row-isolate: y[%d:%d] (was h=%d)", by1, by2, work.shape[0])
            work = work[by1:by2, :]
            work_rgb = work_rgb[by1:by2, :]
    except Exception as exc:
        log.info("row-isolate skipped: %s", exc)

    # ── Contrast stretch + Lanczos upscale (matches runtime) ──
    w_arr = work.astype(np.float32)
    mn, mx = float(w_arr.min()), float(w_arr.max())
    if mx - mn > 8:
        w_arr = (w_arr - mn) * (255.0 / (mx - mn))
        work = np.clip(w_arr, 0, 255).astype(np.uint8)
    h_pre = work.shape[0]
    if h_pre < 28:
        scale_up = max(2, 32 // max(1, h_pre))
        pil = Image.fromarray(work, mode="L").resize(
            (work.shape[1] * scale_up, h_pre * scale_up), Image.LANCZOS,
        )
        work = np.asarray(pil, dtype=np.uint8)
        pil_rgb = Image.fromarray(work_rgb, mode="RGB").resize(
            (work_rgb.shape[1] * scale_up, work_rgb.shape[0] * scale_up),
            Image.LANCZOS,
        )
        work_rgb = np.asarray(pil_rgb, dtype=np.uint8)
        log.info("Lanczos %dx upscale: h=%d -> %d", scale_up, h_pre, work.shape[0])

    _save_gray(out_dir / f"{cap_id}_01_work.png", work)
    _save_rgb(out_dir / f"{cap_id}_01_work_rgb.png", work_rgb)

    # ── Polarity + binarize ──
    work_canon = _api._canonicalize_polarity(work)
    _save_gray(out_dir / f"{cap_id}_02_work_canon.png", work_canon)

    hud_bin = _api._adaptive_binarize_multi(work_canon, expected_count=5)
    _save_gray(out_dir / f"{cap_id}_03_bin_pre_comma.png", hud_bin)

    hud_bin = _api._strip_pill_outline_bridges(hud_bin)
    _save_gray(out_dir / f"{cap_id}_03b_bin_post_strip.png", hud_bin)

    hud_bin = _api._mask_commas_in_signature_band(hud_bin)
    _save_gray(out_dir / f"{cap_id}_04_bin_post_comma.png", hud_bin)

    # ── Segment ──
    pri_crops, pri_boxes = _api._segment_glyphs(
        work_canon, hud_bin, disable_gap_cut=True,
    )
    log.info("[after _segment_glyphs] %d crops, boxes=%s", len(pri_crops), pri_boxes)

    pri_crops, pri_boxes = _api._trim_comma_fused_into_signature_boxes(
        pri_crops, pri_boxes, work_canon, hud_bin,
    )
    log.info("[after trim_comma_fused] %d crops, boxes=%s",
             len(pri_crops), pri_boxes)

    pri_crops, pri_boxes = _api._drop_blacklisted_signature_glyphs(
        pri_crops, pri_boxes,
    )
    log.info("[after drop_blacklisted] %d crops, boxes=%s",
             len(pri_crops), pri_boxes)

    pri_crops, pri_boxes = _api._enforce_comma_signature_structure(
        pri_crops, pri_boxes,
    )
    log.info("[after enforce_comma] %d crops, boxes=%s",
             len(pri_crops), pri_boxes)

    pri_crops, pri_boxes = _api._split_wide_signature_spans(
        work_canon, hud_bin, pri_crops, pri_boxes, expected_count=5,
    )
    log.info("[after split_wide] %d crops, boxes=%s",
             len(pri_crops), pri_boxes)

    # Save each glyph crop produced by the gray segmenter.
    for i, box in enumerate(pri_boxes):
        bx, by, bw, bh = box
        glyph = work_canon[by:by + bh, bx:bx + bw]
        _save_gray(out_dir / f"{cap_id}_05_gray_glyph{i}.png", glyph)

    # ── Classify ──
    pri_results = _api._classify_crops_signal(pri_crops) if pri_crops else []
    if not pri_results and pri_crops:
        pri_results = _api._classify_crops(pri_crops)

    gray_text = "".join(c for c, _ in pri_results)
    log.info("GRAY classification: %s (%d crops, gt=%s)",
             pri_results, len(pri_crops), gt_value)

    # RGB path slice
    rgb_crops_seg = []
    h_w_rgb, w_w_rgb = work_rgb.shape[:2]
    for box in (pri_boxes or []):
        bx, by, bw, bh = box
        if bw < 1 or bh < 1:
            continue
        if bx + bw > w_w_rgb or by + bh > h_w_rgb:
            continue
        glyph_rgb = work_rgb[by:by + bh, bx:bx + bw].astype(np.float32)
        pad = 2
        padded = np.full(
            (bh + pad * 2, bw + pad * 2, 3), 255.0, dtype=np.float32,
        )
        padded[pad:pad + bh, pad:pad + bw] = glyph_rgb
        pil_rgb_glyph = Image.fromarray(
            padded.astype(np.uint8), mode="RGB",
        ).resize((28, 28), Image.BILINEAR)
        rgb_crops_seg.append(np.asarray(pil_rgb_glyph, dtype=np.uint8))

    rgb_results = _api._classify_crops_signal_rgb(rgb_crops_seg) if rgb_crops_seg else []
    rgb_text = "".join(c for c, _ in rgb_results)
    log.info("RGB classification: %s (%d crops, gt=%s)",
             rgb_results, len(rgb_crops_seg), gt_value)

    return {
        "capture": cap_id,
        "gt": gt_value,
        "crop_box": list(crop_box),
        "n_pri_crops": len(pri_crops),
        "n_rgb_crops": len(rgb_crops_seg),
        "boxes": pri_boxes,
        "gray_results": pri_results,
        "rgb_results": rgb_results,
        "gray_text": gray_text,
        "rgb_text": rgb_text,
    }


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: python diagnose.py <png> <gt-value>")
        sys.exit(1)
    png = Path(sys.argv[1])
    gt = sys.argv[2]
    out = Path(__file__).parent
    res = diagnose(png, gt, out)
    print(json.dumps(res, indent=2, default=str))
