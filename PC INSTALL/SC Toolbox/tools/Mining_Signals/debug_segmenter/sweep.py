"""20-capture sweep to verify the segmenter fix.

For each labeled region2 capture, runs the production pipeline and
reports per-capture and aggregate accuracy.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

from ocr.sc_ocr import api as _api  # noqa: E402

logging.getLogger("ocr.sc_ocr.api").setLevel(logging.WARNING)


def _load_sweep_captures(n: int) -> list[tuple[Path, str]]:
    """Pick a diverse set of N captures with labeled values."""
    panel_root = Path(
        r"C:\Users\_user\AppData\Roaming\ShipBit\WingmanAI\custom_skills"
        r"\SC_Toolbox_Beta_V1.2\tools\Mining_Signals\training_data_panels"
    )
    out: list[tuple[Path, str]] = []
    seen_values: dict[str, int] = {}
    for png in sorted(panel_root.glob("user_*/region2/*.png")):
        json_path = png.with_suffix(".json")
        if not json_path.exists():
            continue
        try:
            data = json.loads(json_path.read_text())
        except Exception:
            continue
        value = str(data.get("value", "")).strip()
        if not value:
            continue
        # Cap each unique value at 3 captures so the sweep covers a
        # diverse set of values, not 20 copies of "11,520".
        if seen_values.get(value, 0) >= 3:
            continue
        seen_values[value] = seen_values.get(value, 0) + 1
        out.append((png, value))
        if len(out) >= n:
            break
    return out


def run_one(png: Path) -> tuple[str, str]:
    """Run the production pipeline. Returns (gray_text, rgb_text).

    We invoke ``_signal_recognize_pil`` after monkey-patching the
    segmentation block to capture the per-glyph CNN reads. To keep
    things simple, we instead reproduce the segmentation pipeline
    and run the CNNs directly.
    """
    img = Image.open(str(png)).convert("RGB")
    rgb = np.asarray(img, dtype=np.uint8)
    gray = rgb.max(axis=2).astype(np.uint8)

    # Mirror the world-model crop derivation
    wmr = _api._load_region2_world_model_for_api()
    if wmr is None:
        return ("", "")
    vfrac = (wmr.get("features") or {}).get("value")
    pill = _api._find_pill_for_signal(rgb) if vfrac else None
    if vfrac is None or pill is None:
        return ("", "")
    px, py, pw, ph = pill
    vx = int(round(px + float(vfrac["x_frac"]["mean"]) * pw))
    vy = int(round(py + float(vfrac["y_frac"]["mean"]) * ph))
    vw = int(round(float(vfrac["w_frac"]["mean"]) * pw))
    vh = int(round(float(vfrac["h_frac"]["mean"]) * ph))
    try:
        from hud_tracker.anchors.icon_voter import localize_icon as _li
        icon_loc = _li(rgb)
        if icon_loc is not None:
            ix, iy, iw, ih = icon_loc["bbox"]
            icon_anchor = ix + iw + max(2, int(pw * 0.03))
            delta = vx - icon_anchor
            vx = icon_anchor
            vw = vw + delta
    except Exception:
        pass
    rhs_ceiling = px + pw - max(2, int(pw * 0.05))
    digits_x2 = min(vx + vw, rhs_ceiling, gray.shape[1])
    digits_x1 = max(0, vx)
    digits_y1 = max(0, vy)
    digits_y2 = min(vy + vh, gray.shape[0])
    if digits_x2 - digits_x1 < 20 or digits_y2 - digits_y1 < 8:
        return ("", "")

    work = gray[digits_y1:digits_y2, digits_x1:digits_x2].copy()
    work_rgb = rgb[digits_y1:digits_y2, digits_x1:digits_x2].copy()

    # row isolate
    try:
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
            work = work[by1:by2, :]
            work_rgb = work_rgb[by1:by2, :]
    except Exception:
        pass

    # contrast + Lanczos
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

    work_canon = _api._canonicalize_polarity(work)
    hud_bin = _api._adaptive_binarize_multi(work_canon, expected_count=5)
    hud_bin = _api._strip_pill_outline_bridges(hud_bin)
    hud_bin = _api._mask_commas_in_signature_band(hud_bin)
    pri_crops, pri_boxes = _api._segment_glyphs(
        work_canon, hud_bin, disable_gap_cut=True,
    )
    pri_crops, pri_boxes = _api._trim_comma_fused_into_signature_boxes(
        pri_crops, pri_boxes, work_canon, hud_bin,
    )
    pri_crops, pri_boxes = _api._drop_blacklisted_signature_glyphs(
        pri_crops, pri_boxes,
    )
    pri_crops, pri_boxes = _api._enforce_comma_signature_structure(
        pri_crops, pri_boxes,
    )
    pri_crops, pri_boxes = _api._split_wide_signature_spans(
        work_canon, hud_bin, pri_crops, pri_boxes, expected_count=5,
    )

    pri_results = _api._classify_crops_signal(pri_crops) if pri_crops else []
    if not pri_results and pri_crops:
        pri_results = _api._classify_crops(pri_crops)
    gray_text = "".join(c for c, _ in pri_results)

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

    return (gray_text, rgb_text)


def _digits_only(s: str) -> str:
    return "".join(c for c in s if c.isdigit())


def main():
    captures = _load_sweep_captures(20)
    rows = []
    n_gray_match = 0
    n_rgb_match = 0
    n_either = 0
    n_n_spans_correct = 0  # count of crops produced matches 4-5
    for png, gt in captures:
        gt_digits = _digits_only(gt)
        try:
            gray_text, rgb_text = run_one(png)
        except Exception as exc:
            print(f"  ERROR {png.name}: {exc}")
            rows.append((png.name, gt, "ERR", "ERR", False, False, 0, 0))
            continue
        gray_digits = _digits_only(gray_text)
        rgb_digits = _digits_only(rgb_text)
        gray_match = (gray_digits == gt_digits)
        rgb_match = (rgb_digits == gt_digits)
        if gray_match: n_gray_match += 1
        if rgb_match: n_rgb_match += 1
        if gray_match or rgb_match: n_either += 1
        rows.append((
            png.name, gt, gray_text, rgb_text,
            gray_match, rgb_match,
            len(gray_text), len(rgb_text),
        ))

    print(f"\n{'capture':<40} {'gt':<8} {'gray':<10} {'rgb':<10} {'gOK':<4} {'rOK':<4} {'#g':<3} {'#r':<3}")
    print("-" * 90)
    for r in rows:
        print(f"{r[0]:<40} {r[1]:<8} {r[2]:<10} {r[3]:<10} "
              f"{'YES' if r[4] else 'no ':<3} {'YES' if r[5] else 'no ':<3} "
              f"{r[6]:<3} {r[7]:<3}")
    print("-" * 90)
    print(f"Total: {len(captures)}  gray match: {n_gray_match} "
          f"({n_gray_match*100/max(1,len(captures)):.0f}%)  "
          f"rgb match: {n_rgb_match} "
          f"({n_rgb_match*100/max(1,len(captures)):.0f}%)  "
          f"either: {n_either} ({n_either*100/max(1,len(captures)):.0f}%)")


if __name__ == "__main__":
    main()
