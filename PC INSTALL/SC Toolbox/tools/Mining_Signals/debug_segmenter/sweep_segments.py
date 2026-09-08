"""Focused sweep on segmentation quality for leading-1 captures."""
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

logging.getLogger("ocr.sc_ocr.api").setLevel(logging.ERROR)


def run_one(png: Path):
    img = Image.open(str(png)).convert("RGB")
    rgb = np.asarray(img, dtype=np.uint8)
    gray = rgb.max(axis=2).astype(np.uint8)

    wmr = _api._load_region2_world_model_for_api()
    if wmr is None:
        return None
    vfrac = (wmr.get("features") or {}).get("value")
    pill = _api._find_pill_for_signal(rgb) if vfrac else None
    if vfrac is None or pill is None:
        return None
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

    work = gray[digits_y1:digits_y2, digits_x1:digits_x2].copy()

    try:
        scripts = ROOT / "scripts"
        if str(scripts) not in sys.path:
            sys.path.insert(0, str(scripts))
        import extract_labeled_glyphs as xlg
        band = xlg._find_main_row_bounds(work)
        if band is not None:
            by1, by2 = band
            work = work[by1:by2, :]
    except Exception:
        pass

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
    return pri_boxes


def main():
    panel_root = Path(
        r"C:\Users\_user\AppData\Roaming\ShipBit\WingmanAI\custom_skills"
        r"\SC_Toolbox_Beta_V1.2\tools\Mining_Signals\training_data_panels"
    )
    items = []
    for png in sorted(panel_root.glob("user_*/region2/*.png")):
        # Honor user-flagged ``.skip`` markers — a sibling
        # ``<stem>.skip`` file means this capture was hand-marked as
        # not worth evaluating (motion blur, occlusion, mislabeled
        # GT). Cheap stat-only check; no read of the marker contents.
        # Without this, the variance numbers got diluted by captures
        # the user already rejected.
        if png.with_suffix(".skip").exists():
            continue
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
        items.append((png, value))

    # Pick 20 diverse: include all leading-1 cases, mix others
    seen_values: dict[str, int] = {}
    sample = []
    for png, gt in items:
        if seen_values.get(gt, 0) >= 2:
            continue
        seen_values[gt] = seen_values.get(gt, 0) + 1
        sample.append((png, gt))
        if len(sample) >= 20:
            break

    n_correct_count = 0  # 5 spans for 5-digit values, 4 for 4-digit
    n_4_or_5 = 0
    print(f"\n{'capture':<42} {'gt':<8} {'#spans':<7} {'expected':<9} {'match':<5}")
    print("-" * 80)
    for png, gt in sample:
        digits = "".join(c for c in gt if c.isdigit())
        expected = len(digits)
        try:
            boxes = run_one(png)
        except Exception as exc:
            print(f"  ERROR {png.name}: {exc}")
            continue
        if boxes is None:
            print(f"{png.name:<42} {gt:<8} skipped")
            continue
        nspans = len(boxes)
        match = (nspans == expected)
        if match:
            n_correct_count += 1
        if 4 <= nspans <= 5:
            n_4_or_5 += 1
        print(f"{png.name:<42} {gt:<8} {nspans:<7} {expected:<9} "
              f"{'YES' if match else 'no'}")

    print("-" * 80)
    print(f"Total: {len(sample)}  exact-count match: {n_correct_count} "
          f"({n_correct_count*100/max(1,len(sample)):.0f}%)  "
          f"4-5 crops: {n_4_or_5} "
          f"({n_4_or_5*100/max(1,len(sample)):.0f}%)")


if __name__ == "__main__":
    main()
