"""Instrumented, off-screen run of the Mining Signals HUD pipeline.

usage: python -I trace_case.py <case> <src: crop x0,y0,x1,y1 | blank:WxH> <scale> <mode fast|legacy> [ticks]
Runs from the scratch COPY; user data dirs must be redirected by caller.
Records: every call into tool modules (counts, in/out summaries, empty/flat
inputs, propagated exceptions), every onnxruntime run (model, input
shape/dtype/range), pytesseract / paddle calls, handled (swallowed)
exceptions via sys.monitoring, and producer->consumer object edges.
"""
import os, sys, json, time, types, inspect, logging, subprocess, functools, importlib, traceback, glob
from collections import defaultdict, Counter

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.join(HERE, "app")
TOOL = os.path.join(APP, "tools", "Mining_Signals")
OUT = os.path.join(HERE, "trace")
os.makedirs(OUT, exist_ok=True)
for k in ("LOCALAPPDATA", "APPDATA", "USERPROFILE"):
    assert HERE.lower() in os.environ.get(k, "").lower(), f"{k} not redirected"
os.environ["QT_QPA_PLATFORM"] = "offscreen"
case, src_spec, scale, mode = sys.argv[1], sys.argv[2], float(sys.argv[3]), sys.argv[4]
ticks = int(sys.argv[5]) if len(sys.argv) > 5 else 2
if mode == "legacy":
    os.environ["MINING_SIGNALS_OCR_MODE"] = "legacy"
sys.path.insert(0, APP); sys.path.insert(0, TOOL); os.chdir(TOOL)

LOGREC = []
class _H(logging.Handler):
    def emit(self, r):
        try:
            LOGREC.append((r.levelname, r.name, f"{os.path.basename(r.pathname)}:{r.lineno}", r.getMessage()[:300]))
        except Exception:
            pass
logging.basicConfig(level=logging.DEBUG, handlers=[_H()])

# hidden subprocesses; block real capture
_P = subprocess.Popen
class _HP(_P):
    def __init__(self, *a, **kw):
        kw["creationflags"] = kw.get("creationflags", 0) | 0x08000000
        SUBPROC.append(str(a[0] if a else kw.get("args"))[:200])
        super().__init__(*a, **kw)
SUBPROC = []
subprocess.Popen = _HP
import mss
mss.mss = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("real capture blocked"))

import numpy as np
from PIL import Image

def summ(x, depth=0):
    try:
        if isinstance(x, np.ndarray):
            d = {"nd": list(x.shape), "dt": str(x.dtype)}
            if x.size and x.dtype != object:
                d["min"] = round(float(x.min()), 3); d["max"] = round(float(x.max()), 3)
            return d
        if isinstance(x, Image.Image):
            return {"img": x.mode, "size": list(x.size), "ext": str(x.getextrema())[:60]}
        if isinstance(x, dict):
            return {"dict": list(map(str, x.keys()))[:12]} if depth else {"dict": {str(k): summ(v, 1) for k, v in list(x.items())[:10]}}
        if isinstance(x, (list, tuple)):
            return {type(x).__name__: len(x), "first": summ(x[0], 1) if x and depth == 0 else None}
        if isinstance(x, (int, float, bool, str)) or x is None:
            return repr(x)[:80]
        return type(x).__name__
    except Exception as e:
        return f"<summ err {e!r}>"

def is_empty(x):
    if isinstance(x, np.ndarray):
        return x.size == 0
    if isinstance(x, Image.Image):
        return x.size[0] == 0 or x.size[1] == 0
    return False

def is_flat(x):
    try:
        if isinstance(x, np.ndarray) and x.size > 4 and x.dtype != object:
            return float(x.max()) == float(x.min())
        if isinstance(x, Image.Image) and x.size[0] * x.size[1] > 4:
            e = x.getextrema()
            e = e if isinstance(e[0], tuple) else (e,)
            return all(a == b for a, b in e)
    except Exception:
        pass
    return False

FN = defaultdict(lambda: {"calls": 0, "exc": Counter(), "empty_in": 0, "flat_in": 0, "ret_none": 0, "samples": [], "ms": 0.0})
PRODUCED = {}   # id -> producer name
KEEP = []
EDGES = Counter()
ORT = defaultdict(lambda: {"runs": 0, "samples": [], "exc": Counter(), "flat_in": 0, "empty_in": 0})
TESS = []
PADDLE = []
CUR = ["init"]

def _ids(v):
    if isinstance(v, (np.ndarray, Image.Image, dict, list, tuple)):
        yield id(v)
        if isinstance(v, (list, tuple)):
            for e in v[:16]:
                if isinstance(e, (np.ndarray, Image.Image, dict, list, tuple)):
                    yield id(e)
        elif isinstance(v, dict):
            for e in list(v.values())[:16]:
                if isinstance(e, (np.ndarray, Image.Image, dict, list, tuple)):
                    yield id(e)

def wrap(name, f):
    if getattr(f, "_traced", False):
        return f
    @functools.wraps(f)
    def w(*a, **kw):
        rec = FN[name]; rec["calls"] += 1
        args = list(a) + list(kw.values())
        for v in args:
            for i in _ids(v):
                p = PRODUCED.get(i)
                if p and p != name:
                    EDGES[(p, name)] += 1
        if any(is_empty(v) for v in args): rec["empty_in"] += 1
        if any(is_flat(v) for v in args): rec["flat_in"] += 1
        t = time.perf_counter()
        try:
            r = f(*a, **kw)
        except BaseException as e:
            rec["exc"][f"{type(e).__name__}: {str(e)[:120]}"] += 1
            raise
        finally:
            rec["ms"] += (time.perf_counter() - t) * 1000
        if r is None: rec["ret_none"] += 1
        if len(rec["samples"]) < 2 or (r is not None and len(rec["samples"]) < 3 and rec["samples"][-1]["out"] == "None"):
            rec["samples"].append({"in": [summ(v) for v in args[:4]], "out": summ(r)})
        for i in _ids(r):
            PRODUCED[i] = name
        if isinstance(r, (np.ndarray, Image.Image, dict, list, tuple)):
            KEEP.append(r)
        return r
    w._traced = True
    return w

# ── ORT instrumentation (before tool imports) ──
import onnxruntime as ort
_oi, _or = ort.InferenceSession.__init__, ort.InferenceSession.run
def _init(self, path_or_bytes, *a, **k):
    self._trace_name = os.path.basename(path_or_bytes) if isinstance(path_or_bytes, (str, os.PathLike)) else f"<bytes {len(path_or_bytes)}>"
    return _oi(self, path_or_bytes, *a, **k)
def _run(self, output_names, input_feed, *a, **k):
    nm = getattr(self, "_trace_name", "?"); rec = ORT[nm]; rec["runs"] += 1
    rec.setdefault("callers", Counter())[" <- ".join(_caller(2))] += 1
    ins = {n: summ(v) for n, v in input_feed.items()}
    for v in input_feed.values():
        if is_empty(v): rec["empty_in"] += 1
        if isinstance(v, np.ndarray) and v.ndim >= 3:
            flat = sum(1 for s in v.reshape(v.shape[0], -1) if s.size and s.max() == s.min())
            rec["flat_in"] += flat
    try:
        exp = {i.name: (i.shape, i.type) for i in self.get_inputs()}
    except Exception:
        exp = {}
    try:
        out = _or(self, output_names, input_feed, *a, **k)
    except BaseException as e:
        rec["exc"][f"{type(e).__name__}: {str(e)[:160]}"] += 1
        raise
    if len(rec["samples"]) < 2:
        rec["samples"].append({"in": ins, "expected": {k2: str(v2) for k2, v2 in exp.items()}, "out": [summ(o) for o in out[:2]], "caller": CUR[0]})
    return out
ort.InferenceSession.__init__ = _init
ort.InferenceSession.run = _run

import pytesseract
for fn in ("image_to_string", "image_to_data", "run_and_get_output"):
    _orig = getattr(pytesseract, fn)
    def _mk(o, fn=fn):
        def t(image, *a, **k):
            rec = {"fn": fn, "caller": " <- ".join(_caller(2)), "in": summ(image), "cfg": str(k.get("config", a[1] if len(a) > 1 else ""))[:80]}
            try:
                r = o(image, *a, **k); rec["out"] = repr(r)[:60] if isinstance(r, str) else summ(r)
                return r
            except BaseException as e:
                rec["exc"] = f"{type(e).__name__}: {str(e)[:100]}"; raise
            finally:
                TESS.append(rec)
        return t
    setattr(pytesseract, fn, _mk(_orig))
    setattr(pytesseract.pytesseract, fn, getattr(pytesseract, fn))

# ── handled exceptions (swallowed) via sys.monitoring ──
HANDLED = Counter()
mon = sys.monitoring; TID = 3
mon.use_tool_id(TID, "hudtrace")
def _caller(n=3):
    fr = sys._getframe(2); out = []
    while fr is not None and len(out) < n:
        fn = fr.f_code.co_filename
        if fn.lower().startswith(TOOL.lower()) and fr.f_code.co_name != "w":
            out.append(f"{os.path.relpath(fn, TOOL).replace(os.sep, '/')}:{fr.f_lineno} {fr.f_code.co_name}")
        fr = fr.f_back
    return out
def _line_of(code, off):
    ln = None
    for s, e, l in code.co_lines():
        if s <= off < e:
            return l
    return ln
def _handled(code, off, exc):
    fnm = code.co_filename
    tb = exc.__traceback__; ln = None
    while tb is not None:
        if tb.tb_frame.f_code is code: ln = tb.tb_lineno
        tb = tb.tb_next
    if fnm.lower().startswith(TOOL.lower()) and not isinstance(exc, (StopIteration, GeneratorExit)):
        HANDLED[(os.path.relpath(fnm, TOOL).replace("\\", "/") + f":{ln}", code.co_qualname, f"{type(exc).__name__}: {str(exc)[:120]}")] += 1
mon.register_callback(TID, mon.events.EXCEPTION_HANDLED, _handled)
mon.set_events(TID, mon.events.EXCEPTION_HANDLED)

# ── import + wrap tool modules ──
SKIP = ("train", "export_", "_aspect", "_v2_", "_v3_", "compare_", "calibrate_", "profile_", "repro_", "test_", "paddle_daemon", "harness")
mods = []
for pat in ("ocr/*.py", "ocr/sc_ocr/*.py", "hud_tracker/*.py", "hud_tracker/anchors/*.py"):
    for p in glob.glob(os.path.join(TOOL, pat)):
        b = os.path.basename(p)[:-3]
        if b.startswith("_") and b != "__init__" or any(s in b for s in SKIP):
            continue
        mn = os.path.relpath(p, TOOL)[:-3].replace(os.sep, ".").replace(".__init__", "")
        try:
            mods.append(importlib.import_module(mn))
        except Exception as e:
            HANDLED[("import " + mn, "", repr(e)[:120])] += 1
originals = {}
for m in mods:
    for k, v in list(vars(m).items()):
        if inspect.isfunction(v) and v.__module__ == m.__name__:
            originals[id(v)] = (f"{m.__name__.split('.')[-1]}.{k}", v)
        elif inspect.isclass(v) and v.__module__ == m.__name__:
            for mk, mv in list(vars(v).items()):
                if inspect.isfunction(mv) and not mk.startswith("__"):
                    setattr(v, mk, wrap(f"{m.__name__.split('.')[-1]}.{k}.{mk}", mv))
wrapped = {i: wrap(n, f) for i, (n, f) in originals.items()}
for m in list(sys.modules.values()):
    try:
        d = vars(m)
    except TypeError:
        continue
    if not getattr(m, "__file__", None) or not str(m.__file__).lower().startswith(TOOL.lower()):
        continue
    for k, v in list(d.items()):
        if id(v) in wrapped and callable(v):
            d[k] = wrapped[id(v)]

# ── input image + fake capture ──
if src_spec.startswith("blank:"):
    W_, H_ = map(int, src_spec[6:].split("x")); crop = Image.new("RGB", (W_, H_), (8, 10, 14))
else:
    x0, y0, x1, y1 = map(int, src_spec.split(","))
    crop = Image.open(os.path.join(HERE, "src.png")).convert("RGB").crop((x0, y0, x1, y1))
if scale != 1.0:
    crop = crop.resize((round(crop.width * scale), round(crop.height * scale)), Image.BICUBIC)
CAPS = []
def fake_grab(region, *a, **k):
    CAPS.append(dict(region)); return crop.copy()
from ocr.sc_ocr import capture as _cap
from ocr import screen_reader as _sr
_cap.grab = wrap("capture.grab[FAKE]", fake_grab)
_sr.capture_region = wrap("screen_reader.capture_region[FAKE]", fake_grab)
for m in list(sys.modules.values()):
    if getattr(m, "__file__", None) and str(m.__file__).lower().startswith(TOOL.lower()):
        if getattr(m, "capture_region", None) is not None and m is not _sr and not isinstance(m.capture_region, type(_cap)):
            m.capture_region = _sr.capture_region
_sr.tesseract_status()  # app does this at startup (ui/app.py:3506)
try:
    from ocr import paddle_client as _pc
    for k, v in list(vars(_pc).items()):
        if inspect.isfunction(v) and not k.startswith("__"):
            pass  # already wrapped via module wrap
except Exception:
    pass

REGION = {"x": 3924, "y": 706, "w": 462, "h": 398}
from ocr.sc_ocr import calibration as _cal
from ocr.sc_ocr import scan_results_match as _srm
from ocr import onnx_hud_reader as ohr
LOGREC.clear()
results = []
for t in range(ticks):
    CUR[0] = f"tick{t}"
    # replicate ui/app.py:_do_scan gate (lines ~4241-4360)
    bypass = bool(_cal.load(REGION))
    anchor = None
    if not bypass:
        img = _sr.capture_region(REGION)
        anchor = _srm.find_scan_results_anchor(img) if img is not None else None
    gate = {"bypass": bypass, "anchor": summ(anchor)}
    try:
        r = ohr.scan_hud_onnx(dict(REGION))
    except Exception as e:
        r = {"EXC": repr(e), "tb": traceback.format_exc()[-800:]}
    # UI consumption (ui/app.py:4481-4485)
    ui = {k: (r.get(k) if isinstance(r, dict) else None) for k in ("mass", "resistance", "instability", "mineral_name", "panel_visible")}
    results.append({"gate": gate, "would_dispatch": bypass or anchor is not None, "result_keys": list(r.keys()) if isinstance(r, dict) else None, "ui_consumes": ui})
mon.set_events(TID, 0)

out = {
    "case": case, "src": src_spec, "scale": scale, "mode": mode, "input": summ(crop),
    "results": results, "captures": len(CAPS),
    "functions": {k: {**v, "exc": dict(v["exc"]), "ms": round(v["ms"], 1)} for k, v in sorted(FN.items())},
    "ort": {k: {**v, "exc": dict(v["exc"]), "callers": dict(v.get("callers", {}))} for k, v in ORT.items()},
    "tesseract": {"calls": len(TESS), "callers": Counter(x["caller"] for x in TESS if x["fn"] != "run_and_get_output"), "samples": TESS[:4], "exc": Counter(x.get("exc") for x in TESS if x.get("exc"))},
    "subprocesses": SUBPROC,
    "edges": [[a, b, n] for (a, b), n in EDGES.most_common()],
    "handled_exceptions": [[*k, n] for k, n in HANDLED.most_common()],
    "log_warn_err": [r for r in LOGREC if r[0] in ("WARNING", "ERROR", "CRITICAL")][:300],
    "log_engine": [r for r in LOGREC if any(s in r[3] for s in ("gate accepted", "gate SKIPPED", "raw ", "templates field", "STRUCTURAL REJECT", "LOCKED", "vote winner", "EARLY-DIRECT returning", "STABILIZER returned", "legacy", "CRNN", "ONNX loaded", "skipping", "fallback"))][:300],
}
with open(os.path.join(OUT, f"{case}.json"), "w") as f:
    json.dump(out, f, indent=1, default=str)
print(case, mode, "dispatch:", [r["would_dispatch"] for r in results], "ui:", results[-1]["ui_consumes"],
      "| ort models:", {k: v["runs"] for k, v in ORT.items()}, "| tess:", len(TESS), "| handled exc:", sum(HANDLED.values()))
