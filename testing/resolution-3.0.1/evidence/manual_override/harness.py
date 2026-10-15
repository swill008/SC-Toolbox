"""Offline scan_hud_onnx harness. argv: mode(original|corrected) outdir"""
import os, sys, json, shutil, logging
MODE, OUT = sys.argv[1], os.path.abspath(sys.argv[2])
FORCE = len(sys.argv) > 3 and sys.argv[3] == "force"
HERE = os.path.dirname(os.path.abspath(__file__))
os.makedirs(OUT, exist_ok=True)
FAKE = os.path.join(HERE, "fake_localappdata_" + MODE)
os.makedirs(os.path.join(FAKE, "SC_Toolbox", "sc_ocr"), exist_ok=True)
os.environ["LOCALAPPDATA"] = FAKE
os.environ["QT_QPA_PLATFORM"] = "offscreen"
src_cal = os.path.join(HERE, "calibration_copy.json")
cal = json.load(open(src_cal))
KEY = "3590,716,436,322"
if MODE == "corrected":
    sx, sy = 907/436, 670/322
    mo = cal["calibrations"][KEY]["$manual_overrides"]
    for f, b in mo.items():
        mo[f] = {"x": round(b["x"]*sx), "y": round(b["y"]*sy), "w": round(b["w"]*sx), "h": round(b["h"]*sy)}
    print("corrected boxes:", json.dumps(mo))
if MODE == "tight":
    sx, sy = 907/436, 670/322
    mo = cal["calibrations"][KEY]["$manual_overrides"]
    for f, b in mo.items():
        x, y, w, h = b["x"]*sx, b["y"]*sy, b["w"]*sx, b["h"]*sy
        cy = y + h/2; nh = min(round(h), 48)
        mo[f] = {"x": round(x) - 10, "y": round(cy - nh/2), "w": round(w) + 10, "h": nh}
    print("tight boxes:", json.dumps(mo))
json.dump(cal, open(os.path.join(FAKE, "SC_Toolbox", "sc_ocr", "calibration.json"), "w"), indent=1)

MS = os.path.join(HERE, "ms_copy")
sys.path.insert(0, MS)
os.chdir(OUT)
logging.basicConfig(level=logging.INFO, filename=os.path.join(OUT, "run.log"), filemode="w",
                    format="%(name)s %(levelname)s %(message)s")
from PIL import Image
crop = Image.open(os.path.join(HERE, "crop_raw_436x322.png")).convert("RGB")
region = {"x": 3590, "y": 716, "w": 436, "h": 322}

from ocr.sc_ocr import calibration as C
assert str(C.CALIBRATION_PATH).startswith(FAKE), C.CALIBRATION_PATH
from ocr.sc_ocr import capture
capture.grab = lambda r: crop.copy()
from ocr.sc_ocr import api
from ocr import onnx_hud_reader as ohr

rec = {"label_rows": [], "value_crops": []}
if FORCE:
    os.environ["SC_POSE_HOLD"] = "0"
    _orig_body = ohr._find_label_rows_impl_body
    def _body(img):
        reg = ohr._get_current_region()
        if reg is not None and C.get_manual_override_mode(reg):
            logging.getLogger("harness").info("FORCED manual override first (simulated fix)")
            return ohr._build_manual_override_label_rows(reg, img.width, img.height)
        return _orig_body(img)
    ohr._find_label_rows_impl_body = _body
_orig_flr = ohr._find_label_rows
def _flr(img):
    r = _orig_flr(img)
    rec["label_rows"].append({"img_size": list(img.size), "rows": {k: list(v) for k, v in (r or {}).items()}})
    return r
ohr._find_label_rows = _flr
_orig_fvc = api._find_value_crop
n = [0]
def _fvc(img, gray, y1, y2, x_min=0):
    c = _orig_fvc(img, gray, y1, y2, x_min=x_min)
    n[0] += 1
    info = {"i": n[0], "img_size": list(img.size), "y1": y1, "y2": y2, "x_min": x_min,
            "crop_rect_xyxy": None if c is None else [max(0, x_min), y1, max(0, x_min) + c.size[0], y2]}
    if c is not None:
        p = os.path.join(OUT, f"valuecrop_{n[0]:02d}_y{y1}-{y2}_x{x_min}.png"); c.save(p); info["png"] = p
    rec["value_crops"].append(info)
    return c
api._find_value_crop = _fvc
_orig_ovc = api._ocr_value_crop
def _ovc(vc, field=""):
    t = _orig_ovc(vc, field)
    rec["value_crops"].append({"ocr_field": field, "text": t[0], "crop_size": list(vc.size) if vc is not None else None})
    return t
api._ocr_value_crop = _ovc

results = []
for i in range(3):
    r = api.scan_hud_onnx(region)
    results.append({k: r.get(k) for k in ("mass", "resistance", "instability", "mineral_name", "panel_visible")})
    print("scan", i, results[-1])
json.dump({"results": results, **rec}, open(os.path.join(OUT, "record.json"), "w"), indent=1, default=str)
# save the reader-space frame with label-row bands drawn
from PIL import ImageDraw
rs = crop.resize((907, 670), Image.LANCZOS); d = ImageDraw.Draw(rs)
for f, (ys, ye, xv) in (rec["label_rows"][0]["rows"] if rec["label_rows"] else {}).items():
    d.rectangle((xv, ys, 906, ye), outline=(255, 255, 0), width=2); d.text((xv + 2, ys + 2), f, fill=(255, 255, 0))
rs.save(os.path.join(OUT, "label_rows_as_applied_907x670.png"))
print("label_rows:", rec["label_rows"][0] if rec["label_rows"] else None)
