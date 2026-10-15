import runpy, sys, time, numpy as np
sys.argv=["x","__nothing__"]
g=runpy.run_path(__file__.replace("live_seq.py","trace_pipeline.py"))
api=g["api"]; sa=g["signal_anchor"]; sr=g["sr"]; CUR=g["CUR"]; EV=g["EV"]; M=g["MATCHER"]
from PIL import Image
api.set_known_signal_values(g["KNOWN"])
blank=g["INPUTS"]["blank_black_140x60"]
def seq(name, img, n_on=6, n_off=6, dt=1.0):
    api._reset_signal_consensus.__wrapped__(); sa.reset_anchor_cache()
    hits=0; out=[]
    frames=[img]*n_on+[Image.new("RGB", img.size, (0,0,0))]*n_off
    for i,f in enumerate(frames):
        EV.clear(); CUR["img"]=f
        rgb=np.asarray(f.convert("RGB"),dtype=np.uint8)
        m=sa.find_icon(rgb.max(axis=2).astype(np.uint8), min_score=0.55, rgb_image=rgb)
        if m is not None: present=True; hits=min(3,hits+1)
        elif hits>0: hits-=1; present=True
        else: present=False
        v=None
        if present:
            v=sr.scan_region({"x":0,"y":0,"w":f.width,"h":f.height})
        mt=[x.name for x in M.match_all(v,tolerance=10)] if v is not None else None
        stages=sorted({e["stage"] for e in EV if e["stage"].startswith(("ONNX","api._crnn","xlg._tess"))})
        out.append((i,"PANEL" if i<n_on else "BLANK", "gate_hit" if m is not None else ("held" if present else "closed"), v, mt))
        if i in (6,7) and name=="x2.7": open(name+f"_tick{i}.log","w",encoding="utf-8").write(g["LOG"].getvalue())
        g["LOG"].seek(0); g["LOG"].truncate()
        print(name, out[-1], "engines:", [s.replace("ONNX model_","") for s in stages][:12])
        time.sleep(dt)
seq("x2.7", g["INPUTS"]["region_x2.7_(~140x60)"])
#seq("tight_x2", g["INPUTS"]["tight_x2"])
