"""Stage-by-stage instrumentation of the Mining_Signals signal scanner.
Runs off-screen on the isolated tool copy in scratchpad/signal_test.
Writes only under scale_sig/ (+ the isolated copy's own dump dirs)."""
import sys, os, io, json, time, types, logging, subprocess, functools, traceback, importlib

SP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ST = os.path.join(SP, "signal_test")
TOOL = os.path.join(ST, "Mining_Signals")
OUT = os.path.join(SP, "scale_sig", "trace_out")
FAKE = os.path.join(SP, "scale_sig", "fakeuser")
os.makedirs(OUT, exist_ok=True)
for d in ("AppData/Local", "AppData/Roaming"):
    os.makedirs(os.path.join(FAKE, d), exist_ok=True)
os.environ.update(LOCALAPPDATA=os.path.join(FAKE, "AppData", "Local"),
                  APPDATA=os.path.join(FAKE, "AppData", "Roaming"),
                  USERPROFILE=FAKE, HOME=FAKE, QT_QPA_PLATFORM="offscreen")
os.environ.pop("MINING_SIGNALS_OCR_MODE", None)
sys.dont_write_bytecode = True
sys.path[:0] = [TOOL, r"C:\Users\<USER>\SC_Toolbox\current"]
os.chdir(TOOL)
_orig_popen = subprocess.Popen.__init__
SPAWNED = []
def _popen(self, *a, **k):
    k["creationflags"] = k.get("creationflags", 0) | 0x08000000
    SPAWNED.append(str(a[0])[:120] if a else str(k.get("args"))[:120])
    return _orig_popen(self, *a, **k)
subprocess.Popen.__init__ = _popen
fake_mss = types.ModuleType("mss")
def _no(*a, **k): raise RuntimeError("real screen capture blocked")
fake_mss.mss = _no
sys.modules["mss"] = fake_mss
import PIL.ImageGrab as _ig; _ig.grab = _no

import numpy as np
from PIL import Image

LOG = io.StringIO()
_h = logging.StreamHandler(LOG); _h.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
logging.basicConfig(level=logging.DEBUG, handlers=[_h])
for n in ("PIL", "matplotlib"): logging.getLogger(n).setLevel(logging.WARNING)

# ---------------------------------------------------------------- summarise
def S(x, depth=0):
    try:
        if x is None: return None
        if isinstance(x, np.ndarray):
            if x.size == 0: return f"ndarray{x.shape} {x.dtype} EMPTY"
            return f"ndarray{x.shape} {x.dtype} [{float(x.min()):.3g},{float(x.max()):.3g}] mean={float(x.mean()):.3g}"
        if isinstance(x, Image.Image): return f"PIL {x.mode} {x.size}"
        if isinstance(x, (list, tuple)):
            if depth > 1: return f"{type(x).__name__}[{len(x)}]"
            inner = [S(e, depth+1) for e in list(x)[:6]]
            return f"{type(x).__name__}[{len(x)}]: {inner}"
        if isinstance(x, dict):
            if depth > 1: return f"dict({len(x)})"
            return {k: S(v, depth+1) for k, v in list(x.items())[:12]}
        if isinstance(x, (set, frozenset)): return f"set[{len(x)}]"
        if isinstance(x, float): return round(x, 4)
        if callable(x): return f"<fn {getattr(x,'__name__','?')}>"
        r = repr(x)
        return r if len(r) < 160 else r[:160] + "..."
    except Exception as e:
        return f"<sum err {e}>"

EV = []          # events for current run
DEPTH = [0]
def trace(mod, name, label=None):
    m = sys.modules[mod] if isinstance(mod, str) else mod
    orig = getattr(m, name)
    if getattr(orig, "_traced", False): return
    lab = label or f"{m.__name__.split('.')[-1]}.{name}"
    @functools.wraps(orig)
    def w(*a, **k):
        idx = len(EV)
        EV.append({"stage": lab, "depth": DEPTH[0],
                   "in": [S(v) for v in a], "kw": {kk: S(vv) for kk, vv in k.items()}})
        DEPTH[0] += 1
        try:
            r = orig(*a, **k)
            EV[idx]["out"] = S(r)
            return r
        except Exception as e:
            EV[idx]["exc"] = f"{type(e).__name__}: {e}"
            raise
        finally:
            DEPTH[0] -= 1
    w._traced = True
    setattr(m, name, w)

# ---- onnxruntime: log every model call with input vs declared signature
import onnxruntime as ort
from onnxruntime.capi import onnxruntime_inference_collection as _oic
_orig_run = _oic.InferenceSession.run
def _run(self, out_names, feed, *a, **k):
    rec = {"stage": "ONNX " + os.path.basename(getattr(self, "_model_path", "?")), "depth": DEPTH[0]}
    try:
        decl = {i.name: (i.shape, i.type) for i in self.get_inputs()}
        rec["declared"] = {k_: str(v) for k_, v in decl.items()}
        rec["in"] = {k_: S(v) for k_, v in feed.items()}
        probs = []
        for k_, v in feed.items():
            d_shape, d_type = decl.get(k_, (None, None))
            if d_type and "float" in d_type and v.dtype != np.float32: probs.append(f"dtype {v.dtype}!=float32")
            if d_shape:
                if len(d_shape) != v.ndim: probs.append(f"rank {v.ndim}!={len(d_shape)}")
                else:
                    for ds, vs in zip(d_shape, v.shape):
                        if isinstance(ds, int) and ds != vs: probs.append(f"shape {v.shape} vs {d_shape}")
            if v.dtype.kind == "f" and v.size and (v.max() > 1.0001 or v.min() < -0.0001):
                probs.append(f"range [{v.min():.3g},{v.max():.3g}] not [0,1]")
            if v.size and float(v.std()) < 1e-6: probs.append("CONSTANT input")
        rec["problems"] = probs
    except Exception as e:
        rec["meta_err"] = repr(e)
    EV.append(rec)
    try:
        r = _orig_run(self, out_names, feed, *a, **k)
        rec["out"] = S(r[0]) if r else None
        return r
    except Exception as e:
        rec["exc"] = repr(e); raise
_oic.InferenceSession.run = _run

# ---- tesseract
import pytesseract
for fn in ("image_to_string", "image_to_data", "image_to_boxes"):
    trace(pytesseract, fn, f"TESS.{fn}")

# ---------------------------------------------------------------- import tool
from ocr import screen_reader as sr
sr._download_tesseract = lambda: False
sr._TESSERACT_EXE = r"C:\Users\<USER>\SC_Toolbox\current\tools\Mining_Signals\tesseract\tesseract.exe"
sr._check_mss = lambda: True
CUR = {"img": None}
sr.capture_region = lambda region: CUR["img"].copy()
sr.capture_region_averaged = lambda region, *a, **k: CUR["img"].copy()
print("tesseract ok:", sr._check_tesseract(), sr.tesseract_status())

from ocr.sc_ocr import api, signal_anchor, debug_overlay, frame_context
from ocr import engine_mode, paddle_client
debug_overlay.diagnostics_active = lambda: True
import hud_tracker.anchors.icon_voter as iv
import hud_tracker.anchors.comma_finder as cf
import hud_tracker.anchors.signal_proportional_segmenter as sps
from ocr.sc_ocr import signal_solve
sys.path.insert(0, os.path.join(TOOL, "scripts"))
import extract_labeled_glyphs as xlg
from services import sheet_fetcher
from services.signal_matcher import SignalMatcher

# lexicon exactly as ui/app.py builds it
rows = json.load(open(os.path.join(TOOL, ".signals_cache.json"), encoding="utf-8"))
rows = (rows.get("rows") if isinstance(rows, dict) else rows) or rows.get("data", {}).get("rows")
rows = rows + sheet_fetcher._EXTRA_ROWS
KNOWN = {int(r.get(str(n), 0)) for r in rows for n in range(1, 21) if r.get(str(n), 0)}
MATCHER = SignalMatcher(rows)

# capture
for n in ("capture_region", "capture_region_averaged", "extract_number", "_preprocess_engine_a",
          "_preprocess_engine_b", "_ocr_engine", "_try_ocr", "_extract_paddle_signal_candidates", "_best_candidate"):
    trace(sr, n, f"screen_reader.{n}")
trace(paddle_client, "is_available"); trace(paddle_client, "recognize")
trace(frame_context, "max_channel")
API_FNS = ["_load_region2_world_model_for_api", "_find_pill_for_signal", "_signal_mark_icon_seen",
    "_signal_scanning_timeout_exceeded", "_classify_signal_via_crnn_rgb", "_canonicalize_polarity",
    "_adaptive_binarize_multi", "_strip_pill_outline_bridges", "_mask_commas_in_signature_band",
    "_segment_glyphs", "_trim_comma_fused_into_signature_boxes", "_drop_blacklisted_signature_glyphs",
    "_enforce_comma_signature_structure", "_split_wide_signature_spans", "_merge_narrow_signature_spans",
    "_classify_crops_signal", "_classify_crops_signal_topk", "_classify_crops", "_classify_crops_signal_inv",
    "_classify_crops_inv", "_apply_eight_vs_zero_rule", "_strip_non_digit_signature_secondary",
    "_apply_zero_six_eight_secondary_tiebreak", "_classify_crops_signal_rgb", "_classify_crops_signal_rgb_inv",
    "_dump_glyphs", "_dump_value_crop", "_dump_signature_winner", "_vote_on_digit_string",
    "_signal_voter_panel_decision", "_read_signal_glyph_crnns", "_crnn_recognize", "_signal_cnn_per_digit",
    "_signal_cnn_at_tess_boxes", "_signal_read_tight_local", "_signal_accept_candidate",
    "_snap_signal_units_05", "_reset_signal_consensus", "_aspect_pad_resize_28"]
for n in API_FNS:
    if hasattr(api, n): trace(api, n, f"api.{n}")
    else: print("MISSING api fn", n)
trace(api, "_signal_recognize_pil", "api._signal_recognize_pil")
for n in ("find_icon", "find_digit_crop_box", "find_digit_cluster", "_cnn_filter_icon_candidates", "last_crop_mode"):
    if hasattr(signal_anchor, n): trace(signal_anchor, n, f"signal_anchor.{n}")
for n in ("localize_icon", "vote_on_icon_candidate", "_vote_rgb_cnn", "_vote_gray_cnn", "_vote_geometry", "_vote_contour"):
    trace(iv, n, f"icon_voter.{n}")
if getattr(iv, "find_icon_rgb_ncc", None): trace(iv, "find_icon_rgb_ncc", "icon_voter.find_icon_rgb_ncc")
for n in dir(iv):
    if n.startswith("find_icon_by_geometry"): trace(iv, n, f"icon_voter.{n}")
trace(cf, "find_comma_voted", "comma_finder.find_comma_voted")
trace(sps, "segment_signal_proportional", "proportional_segmenter")
trace(signal_solve, "solve", "signal_solve.solve")
for n in ("_find_main_row_bounds", "_isolate_main_row", "_tesseract_char_boxes", "_locate_icon_via_blacklist_match"):
    if hasattr(xlg, n): trace(xlg, n, f"xlg.{n}")
trace(MATCHER, "match_all", "SignalMatcher.match_all")
# scan_region looks up _signal_recognize_pil via `from .sc_ocr.api import` at call time -> traced attr is used.
trace(sr, "scan_region", "screen_reader.scan_region")

# ---------------------------------------------------------------- inputs
full = Image.open(os.path.join(ST, "full.png")).convert("RGB")
def up(im, f): return im.resize((round(im.width * f), round(im.height * f)), Image.LANCZOS)
cx, cy = 998, 278
reg_small = full.crop((cx - 26, cy - 11, cx + 26, cy + 11))
INPUTS = {
    "tight_x2": up(full.crop((970, 266, 1026, 290)), 2),
    "region_x1.5": up(reg_small, 1.5),
    "region_x2.7_(~140x60)": up(reg_small, 2.7),
    "region140x60_native": full.crop((cx - 70, cy - 30, cx + 70, cy + 30)),
    "blank_black_140x60": Image.new("RGB", (140, 60), (0, 0, 0)),
    "noise_140x60": Image.fromarray(np.random.RandomState(0).randint(0, 255, (60, 140, 3), dtype=np.uint8)),
}

def reset_state():
    api._reset_signal_consensus.__wrapped__()
    try: signal_anchor.reset_anchor_cache()
    except Exception: pass

SILENT_PAT = ("swallowed", "failed", "skipped", "raised", "unavailable", "error", "Traceback", "not defined")
def run_case(case, img, mode, region, known, patches=None, tagmode=None):
    EV.clear(); LOG.seek(0); LOG.truncate()
    CUR["img"] = img
    api.set_known_signal_values(known)
    reset_state()
    saved = {}
    for (m, n), fn in (patches or {}).items():
        saved[(m, n)] = getattr(m, n); setattr(m, n, fn)
    t0 = time.time()
    res = {}
    try:
        # (0) UI anchor gate exactly as ui/app.py _do_scan
        rgb = np.asarray(img.convert("RGB"), dtype=np.uint8)
        gate = signal_anchor.find_icon(rgb.max(axis=2).astype(np.uint8), min_score=0.55, rgb_image=rgb)
        res["ui_gate_sig_present"] = gate is not None
        res["ui_gate"] = S(gate)
        if mode == "legacy": os.environ["MINING_SIGNALS_OCR_MODE"] = "legacy"
        else: os.environ.pop("MINING_SIGNALS_OCR_MODE", None)
        if region == "none":
            v = api._signal_recognize_pil(img, region=None)
        else:
            v = sr.scan_region({"x": 0, "y": 0, "w": img.width, "h": img.height})
        res["value"] = v
        res["matches"] = S(MATCHER.match_all(v, tolerance=10)) if v is not None else None
    except Exception as e:
        res["exc"] = traceback.format_exc()
    finally:
        os.environ.pop("MINING_SIGNALS_OCR_MODE", None)
        for (m, n), fn in saved.items(): setattr(m, n, fn)
    res["secs"] = round(time.time() - t0, 2)
    logtxt = LOG.getvalue()
    res["silent"] = [l for l in logtxt.splitlines()
                     if any(p.lower() in l.lower() for p in SILENT_PAT) and "PIL" not in l][:60]
    res["gate_lines"] = [l for l in logtxt.splitlines() if "sc_ocr.signal:" in l][:80]
    res["events"] = list(EV)
    tag = f"{case}__{tagmode or mode}__{region}"
    open(os.path.join(OUT, tag + ".log"), "w", encoding="utf-8").write(logtxt)
    json.dump(res, open(os.path.join(OUT, tag + ".json"), "w"), indent=1, default=str)
    return res

def none_fn(*a, **k): return None
STARVED = {1}   # lexicon loaded but nothing real in it -> every lexicon-gated accept refuses
RUNS = []
for case, img in INPUTS.items():
    RUNS.append((case, img, "fast", "region", KNOWN, None))
    RUNS.append((case, img, "fast", "none", KNOWN, None))
    RUNS.append((case, img, "legacy", "region", KNOWN, None))
for case in ("tight_x2", "region_x2.7_(~140x60)"):
    img = INPUTS[case]
    RUNS.append((case, img, "fast-starved", "none", STARVED, None))
    RUNS.append((case, img, "fast-starved-noGrayCRNN", "none", STARVED, {(api, "_crnn_recognize"): none_fn}))
only = sys.argv[1:]
summary = {}
for case, img, mode, region, known, patches in RUNS:
    tag = f"{case}__{mode}__{region}"
    if only and not any(o in tag for o in only): continue
    r = run_case(case, img, "legacy" if mode == "legacy" else "fast", region, known, patches, tagmode=mode)
    called = []
    for e in r["events"]:
        if e["stage"] not in called: called.append(e["stage"])
    summary[tag] = {"value": r.get("value"), "gate": r["ui_gate_sig_present"], "secs": r["secs"],
                    "exc": r.get("exc"), "stages": called,
                    "onnx_problems": sorted({(e["stage"], p) for e in r["events"] if e["stage"].startswith("ONNX") for p in e.get("problems", [])}),
                    "stage_exc": [(e["stage"], e["exc"]) for e in r["events"] if e.get("exc")],
                    "silent": r["silent"][:25]}
    print("\n=====", tag, "value=", r.get("value"), "gate=", r["ui_gate_sig_present"], r["secs"], "s")
    print(" stages:", called)
    print(" onnx problems:", summary[tag]["onnx_problems"])
    print(" stage exceptions:", summary[tag]["stage_exc"])
json.dump(summary, open(os.path.join(OUT, "summary.json"), "w"), indent=1, default=str)
print("SPAWNED:", SPAWNED)
