"""Run the Mining Signals HUD pipeline on one image crop, offline.

usage: python -I run_case.py <case_name> <x0> <y0> <x1> <y1> <scale> [ticks]
Runs from the scratch COPY of the app; LOCALAPPDATA/APPDATA/USERPROFILE
must already be redirected by the caller (run_all.py).
"""
import os, sys, json, logging, subprocess, copy

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(HERE, "app")
TOOL = os.path.join(APP, "tools", "Mining_Signals")
OUT = os.path.join(HERE, "out")
for k in ("LOCALAPPDATA", "APPDATA", "USERPROFILE"):
    assert HERE.lower() in os.environ.get(k, "").lower(), f"{k} not redirected"
os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, APP)
sys.path.insert(0, TOOL)
os.chdir(TOOL)

name, x0, y0, x1, y1, scale = sys.argv[1], *map(int, sys.argv[2:6]), float(sys.argv[6])
ticks = int(sys.argv[7]) if len(sys.argv) > 7 else 4

logging.basicConfig(
    level=logging.DEBUG,
    filename=os.path.join(OUT, f"{name}.log"), filemode="w",
    format="%(name)s %(levelname)s %(message)s",
)

# Hidden subprocesses only.
_Popen = subprocess.Popen
class _HiddenPopen(_Popen):
    def __init__(self, *a, **kw):
        kw["creationflags"] = kw.get("creationflags", 0) | 0x08000000  # CREATE_NO_WINDOW
        super().__init__(*a, **kw)
subprocess.Popen = _HiddenPopen

# Block any real screen capture.
try:
    import mss
    def _no_mss(*a, **k):
        raise RuntimeError("real screen capture blocked in test")
    mss.mss = _no_mss
except ImportError:
    pass
try:
    from PIL import ImageGrab
    ImageGrab.grab = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("ImageGrab blocked"))
except Exception:
    pass

from PIL import Image
src = Image.open(os.path.join(HERE, "src.png")).convert("RGB")
crop = src.crop((x0, y0, x1, y1))
if scale != 1.0:
    crop = crop.resize((round(crop.width * scale), round(crop.height * scale)), Image.BICUBIC)
_xs = float(os.environ.get("XSCALE", "1.0"))
if _xs != 1.0:  # diagnostic only: horizontal squeeze to test font-width mismatch
    crop = crop.resize((round(crop.width * _xs), crop.height), Image.BICUBIC)
crop.save(os.path.join(OUT, f"{name}_input.png"))
CAPTURES = {"n": 0}

def fake_grab(region, *a, **k):
    CAPTURES["n"] += 1
    return crop.copy()

from ocr.sc_ocr import capture as _cap
_cap.grab = fake_grab
from ocr import screen_reader as _sr
_sr.capture_region = fake_grab
report_tess = _sr.tesseract_status()  # app calls this at startup (ui/app.py:3506) -> sets tesseract_cmd
from ocr.sc_ocr import debug_overlay as _dbg
_dbg.diagnostics_active = lambda: True

REGION = {"x": 3924, "y": 706, "w": 462, "h": 398}  # user's saved hud_region (read-only copy)
report = {"case": name, "crop_box": [x0, y0, x1, y1], "scale": scale,
          "input_size": list(crop.size)}

# Model availability
from ocr import onnx_hud_reader as ohr
try:
    report["ensure_model"] = bool(ohr._ensure_model())
except Exception as e:
    report["ensure_model"] = f"EXC {e!r}"
try:
    from ocr.engine_mode import get_engine_mode
    report["engine_mode"] = get_engine_mode()
except Exception as e:
    report["engine_mode"] = f"EXC {e!r}"

# UI gate: calibration bypass + SCAN RESULTS anchor
from ocr.sc_ocr import calibration as _cal
report["calibration_load"] = _cal.load(REGION)
from ocr.sc_ocr.scan_results_match import find_scan_results_anchor
GATE = os.environ.get("GATE_MODE", "per_tick")
report["gate_mode"] = GATE
try:
  if GATE == "none":
    report["gate_anchor"] = "skipped"
  else:
    a = find_scan_results_anchor(crop.copy())
    report["gate_anchor"] = {k: (float(v) if isinstance(v, (int, float)) else str(v)) for k, v in a.items()} if a else None
except Exception as e:
    report["gate_anchor"] = f"EXC {e!r}"

# Icon voter (signal-scanner location-pin voter incl. gray_cnn)
try:
    from hud_tracker.anchors import icon_voter as iv
    report["icon_voter_availability"] = iv.availability()
    li = iv.localize_icon(crop.copy())
    report["icon_voter_localize"] = json.loads(json.dumps(li, default=str)) if li else None
except Exception as e:
    report["icon_voter"] = f"EXC {e!r}"

def snap_state():
    st = {}
    for k in ("ocr_text", "label_rows", "panel_finder", "value_crops", "locks",
              "panel_pose", "expected_rows", "hud_lines"):
        if k in _dbg._state:
            st[k] = json.loads(json.dumps(_dbg._state[k], default=str))
    return st

ticks_out = []
gate_scores = []
for t in range(ticks):
    if GATE == "per_tick" and t > 0:
        try:
            g = find_scan_results_anchor(crop.copy())
            gate_scores.append(round(float(g["score"]), 3) if g else None)
        except Exception as e:
            gate_scores.append(f"EXC {e!r}")
    try:
        r = ohr.scan_hud_onnx(dict(REGION))
        r = json.loads(json.dumps(r, default=str))
    except Exception as e:
        import traceback
        r = {"EXC": repr(e), "tb": traceback.format_exc()}
    ticks_out.append({"result": r, "state": snap_state()})
report["ticks"] = ticks_out
report["gate_scores_later_ticks"] = gate_scores
report["captures"] = CAPTURES["n"]

# save annotated overlay produced by the app
ov = os.path.join(TOOL, "debug_panel_overlay.png")
if os.path.exists(ov):
    import shutil
    shutil.copy(ov, os.path.join(OUT, f"{name}_overlay.png"))
    report["overlay"] = os.path.join(OUT, f"{name}_overlay.png")

with open(os.path.join(OUT, f"{name}.json"), "w") as f:
    json.dump(report, f, indent=1, default=str)
last = ticks_out[-1]
ga = report["gate_anchor"]
print(name, "gate:", round(ga.get("score", 0), 3) if isinstance(ga, dict) else ga, gate_scores,
      "| first:", {k: ticks_out[0]["result"].get(k) for k in ("mass", "resistance", "instability", "mineral_name", "panel_visible")},
      "| last:", {k: last["result"].get(k) for k in ("mass", "resistance", "instability", "mineral_name", "panel_visible")})
print("  ocr_text:", last["state"].get("ocr_text"))
