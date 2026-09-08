"""Run the full _signal_recognize_pil pipeline across multiple captures
and report whether reads are deterministic across runs.
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

CAPS = [
    ("cap_20260418_160452_795", "16,960", 16960),
    ("cap_20260418_155500_306", "11,520", 11520),
    ("cap_20260425_094821_678", "11,520", 11520),
    ("cap_20260418_155450_009", "21,350", 21350),
    ("cap_20260418_160419_582", "25,530", 25530),
    ("cap_20260425_094834_527", "2,000", 2000),
    ("cap_20260418_155508_981", "6,340", 6340),
    ("cap_20260425_094826_151", "7,710", 7710),
]
BASE = Path(
    r"C:\Users\_user\AppData\Roaming\ShipBit\WingmanAI"
    r"\custom_skills\SC_Toolbox_Beta_V1.2\tools\Mining_Signals"
    r"\training_data_panels\user_20260418_154408\region2"
)

if len(sys.argv) > 1:
    cap_filter = sys.argv[1]
else:
    cap_filter = None


def run_one(png_path: Path, gt: int, n_runs: int = 5) -> None:
    print(f"\n=== {png_path.name} (GT={gt}) ===")
    img = Image.open(str(png_path)).convert("RGB")
    reads = []
    # Reset BEFORE the run loop so we don't carry over from the
    # previous capture, but let the hysteresis evolve within this
    # capture's runs (closer to the user's repeated-scan scenario).
    _api._RECENT_SIGNAL_READS.clear()
    _api._STABLE_SIGNAL = None
    for i in range(n_runs):
        r = _api._signal_recognize_pil(img.copy())
        reads.append(r)
    unique = set(reads)
    print(f"  {n_runs} runs reads: {reads}")
    print(f"  unique values: {unique}")
    if len(unique) > 1:
        print(f"  *** NON-DETERMINISTIC ***")
    if gt in reads:
        print(f"  matches GT in {reads.count(gt)}/{n_runs} runs")


for stem, gt_str, gt_int in CAPS:
    if cap_filter and cap_filter not in stem:
        continue
    p = BASE / f"{stem}.png"
    if not p.exists():
        print(f"missing: {p}")
        continue
    run_one(p, gt_int)
