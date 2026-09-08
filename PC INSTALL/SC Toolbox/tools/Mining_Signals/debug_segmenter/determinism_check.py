"""Comprehensive determinism check across all CNN paths.

Runs each capture 5 times, captures the per-CNN classifications + bboxes,
and asserts they are byte-identical across runs.
"""
from __future__ import annotations
import sys
from pathlib import Path
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from ocr.sc_ocr import api as _api  # noqa: E402
from hud_tracker.anchors.signal_proportional_segmenter import (  # noqa: E402
    segment_signal_proportional,
)
from hud_tracker.anchors.icon_voter import localize_icon  # noqa: E402

CAPS = [
    ("cap_20260418_160452_795", 16960, "16,960 canonical"),
    ("cap_20260418_155500_306", 11520, "11,520 canonical"),
    ("cap_20260418_155450_009", 21350, "21,350 (2-leading)"),
    ("cap_20260418_160419_582", 25530, "25,530 (2-leading)"),
    ("cap_20260425_094834_527", 2000, "2,000 (2-leading)"),
    ("cap_20260418_155508_981", 6340, "6,340"),
]
BASE = Path(
    r"C:\Users\_user\AppData\Roaming\ShipBit\WingmanAI"
    r"\custom_skills\SC_Toolbox_Beta_V1.2\tools\Mining_Signals"
    r"\training_data_panels\user_20260418_154408\region2"
)


def per_call(png_path: Path) -> dict:
    img = Image.open(str(png_path)).convert("RGB")
    rgb = np.asarray(img, dtype=np.uint8)
    gray = rgb.max(axis=2).astype(np.uint8)
    wmr = _api._load_region2_world_model_for_api()
    if wmr is None:
        return {"err": "no wmr"}
    vfrac = wmr["features"]["value"]
    pill = _api._find_pill_for_signal(rgb)
    if pill is None:
        return {"err": "no pill"}
    px, py, pw, ph = pill
    vx = int(round(px + float(vfrac["x_frac"]["mean"]) * pw))
    vy = int(round(py + float(vfrac["y_frac"]["mean"]) * ph))
    vw = int(round(float(vfrac["w_frac"]["mean"]) * pw))
    vh = int(round(float(vfrac["h_frac"]["mean"]) * ph))
    icon_loc = localize_icon(rgb)
    if icon_loc is None:
        return {"err": "no icon"}
    ix, iy, iw, ih = icon_loc["bbox"]
    icon_anchor = ix + iw + max(2, int(pw * 0.03))
    delta = vx - icon_anchor
    vx = icon_anchor
    vw = vw + delta
    rhs_ceiling = px + pw - max(2, int(pw * 0.05))
    digits_x2 = min(vx + vw, rhs_ceiling, gray.shape[1])
    digits_x1 = max(0, vx)
    digits_y1 = max(0, vy)
    digits_y2 = min(vy + vh, gray.shape[0])
    crop_box = (digits_x1, digits_y1, digits_x2, digits_y2)
    x1, y1, x2, y2 = crop_box
    work = gray[y1:y2, x1:x2].copy()
    work_rgb = rgb[y1:y2, x1:x2].copy()

    # Row-isolate
    sys.path.insert(0, str(ROOT / "scripts"))
    import extract_labeled_glyphs as xlg  # type: ignore
    band = xlg._find_main_row_bounds(work) if hasattr(
        xlg, "_find_main_row_bounds"
    ) else None
    if band is not None:
        by1, by2 = band
        work = work[by1:by2, :]
        work_rgb = work_rgb[by1:by2, :]
    w_arr = work.astype(np.float32)
    mn, mx = float(w_arr.min()), float(w_arr.max())
    if mx - mn > 8:
        w_arr = (w_arr - mn) * (255.0 / (mx - mn))
        work = np.clip(w_arr, 0, 255).astype(np.uint8)
    h_pre = work.shape[0]
    if h_pre < 28:
        scale_up = max(2, 32 // max(1, h_pre))
        pil = Image.fromarray(work, mode="L").resize(
            (work.shape[1] * scale_up, h_pre * scale_up),
            Image.LANCZOS,
        )
        work = np.asarray(pil, dtype=np.uint8)
        pil_rgb = Image.fromarray(work_rgb, mode="RGB").resize(
            (work_rgb.shape[1] * scale_up, work_rgb.shape[0] * scale_up),
            Image.LANCZOS,
        )
        work_rgb = np.asarray(pil_rgb, dtype=np.uint8)

    work_canon = _api._canonicalize_polarity(work)

    # Run proportional segmenter
    prop_pil = Image.fromarray(work_rgb, mode="RGB")
    prop = segment_signal_proportional(
        prop_pil,
        classifier=_api._classify_crops_signal,
        classifier_topk=_api._classify_crops_signal_topk,
        lexicon=_api._KNOWN_SIGNAL_VALUES if _api._KNOWN_SIGNAL_VALUES else None,
    )
    if prop is None:
        return {"err": "no prop", "crop_box": crop_box}
    digit_only = [
        d for d in prop.get("digits") or [] if not d.get("is_comma")
    ]
    bboxes = [tuple(int(v) for v in d["bbox"]) for d in digit_only]
    seg_classes = [
        (str(d.get("classification", "?")), float(d.get("confidence", 0.0)))
        for d in digit_only
    ]

    # Re-extract crops at the bboxes from work_canon (production)
    pri_crops = []
    for bb in bboxes:
        bx, by, bw, bh = bb
        if bx + bw > work_canon.shape[1] or by + bh > work_canon.shape[0]:
            continue
        g = work_canon[by:by + bh, bx:bx + bw].astype(np.float32)
        pad = 2
        padded = np.full(
            (g.shape[0] + pad * 2, g.shape[1] + pad * 2),
            255.0, dtype=np.float32,
        )
        padded[pad:pad + g.shape[0], pad:pad + g.shape[1]] = g
        pil = Image.fromarray(padded.astype(np.uint8)).resize(
            (28, 28), Image.BILINEAR,
        )
        pri_crops.append(np.array(pil, dtype=np.float32) / 255.0)

    rgb_crops = []
    for bb in bboxes:
        bx, by, bw, bh = bb
        if bx + bw > work_rgb.shape[1] or by + bh > work_rgb.shape[0]:
            continue
        rg = work_rgb[by:by + bh, bx:bx + bw].astype(np.float32)
        pad = 2
        padded = np.full(
            (bh + pad * 2, bw + pad * 2, 3), 255.0, dtype=np.float32,
        )
        padded[pad:pad + bh, pad:pad + bw] = rg
        pil = Image.fromarray(
            padded.astype(np.uint8), mode="RGB",
        ).resize((28, 28), Image.BILINEAR)
        rgb_crops.append(np.asarray(pil, dtype=np.uint8))

    pri = _api._classify_crops_signal(pri_crops) if pri_crops else []
    sec = _api._classify_crops_signal_inv(pri_crops) if pri_crops else []
    rgb_r = (
        _api._classify_crops_signal_rgb(rgb_crops) if rgb_crops else []
    )
    rgb_inv_r = (
        _api._classify_crops_signal_rgb_inv(rgb_crops)
        if rgb_crops else []
    )

    return {
        "crop_box": crop_box,
        "bboxes": bboxes,
        "seg_classes": seg_classes,
        "pri": pri,
        "sec": sec,
        "rgb": rgb_r,
        "rgb_inv": rgb_inv_r,
    }


def assess(name: str, gt: int, label: str) -> dict:
    p = BASE / f"{name}.png"
    if not p.exists():
        print(f"missing: {p}")
        return {}
    runs = [per_call(p) for _ in range(5)]
    bboxes_set = {tuple(r.get("bboxes") or ()) for r in runs}
    pri_set = {
        tuple([(c, round(co, 4)) for c, co in (r.get("pri") or [])])
        for r in runs
    }
    sec_set = {
        tuple([(c, round(co, 4)) for c, co in (r.get("sec") or [])])
        for r in runs
    }
    rgb_set = {
        tuple([(c, round(co, 4)) for c, co in (r.get("rgb") or [])])
        for r in runs
    }
    rgb_inv_set = {
        tuple([(c, round(co, 4)) for c, co in (r.get("rgb_inv") or [])])
        for r in runs
    }
    print(f"\n=== {name} (GT={gt}, {label}) ===")
    r0 = runs[0]
    if not r0.get("bboxes"):
        print(f"  ERROR: {r0.get('err')}")
        return {}
    print(f"  cb={r0['crop_box']} bboxes={r0['bboxes']}")
    print(f"  seg_classes={r0['seg_classes']}")
    pri_str = "".join(c for c, _ in (r0.get("pri") or []))
    sec_str = "".join(c for c, _ in (r0.get("sec") or []))
    rgb_str = "".join(c for c, _ in (r0.get("rgb") or []))
    rgb_inv_str = "".join(c for c, _ in (r0.get("rgb_inv") or []))
    print(f"  pri={pri_str!r} sec={sec_str!r} rgb={rgb_str!r} rgb_inv={rgb_inv_str!r}")
    print(
        f"  Determinism: bboxes={len(bboxes_set)} pri={len(pri_set)} "
        f"sec={len(sec_set)} rgb={len(rgb_set)} rgb_inv={len(rgb_inv_set)}"
    )
    all_one = all(len(s) == 1 for s in (
        bboxes_set, pri_set, sec_set, rgb_set, rgb_inv_set
    ))
    print(f"  *** ALL DETERMINISTIC: {all_one} ***")
    return {
        "all_one": all_one,
        "pri_str": pri_str,
        "sec_str": sec_str,
        "rgb_str": rgb_str,
        "rgb_inv_str": rgb_inv_str,
        "gt": gt,
    }


for stem, gt, label in CAPS:
    assess(stem, gt, label)
