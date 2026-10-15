import sys
from PIL import Image, ImageDraw
OUT = sys.argv[1]
src = r"E:\Users\<USER>\Documents\GitHub\SC-Toolbox\test_images\5k2k\hud_scan_results_taranite_2_native_5120x2160.jpg"
im = Image.open(src).convert("RGB")
print("src", im.size)
raw = im.crop((3590,716,4026,1038))
raw.save(OUT+r"\crop_raw_436x322.png")
W,H = raw.size
REF_H=670
rs = raw.resize((max(1,int(round(W*(REF_H/H)))),REF_H), Image.LANCZOS)
rs.save(OUT+r"\crop_resized_907x670.png")
print("raw",raw.size,"resized",rs.size)
boxes = {"_mineral_row":(14,70,218,37),"mass":(220,117,81,31),"resistance":(214,161,66,34),"instability":(212,202,95,35)}
cols = {"_mineral_row":(0,230,100),"mass":(0,200,255),"resistance":(200,100,255),"instability":(255,100,200)}
for name,img in (("raw_436x322",raw),("resized_907x670",rs)):
    c = img.copy(); d = ImageDraw.Draw(c)
    for f,(x,y,w,h) in boxes.items():
        d.rectangle((x,y,x+w-1,y+h-1), outline=cols[f], width=2); d.text((x+2,y+2),f,fill=cols[f])
    c.save(OUT+rf"\overlay_boxes_on_{name}.png")
# also corrected: scale boxes into resized space
s = rs.size[1]/H; sx = rs.size[0]/W
print("scale", sx, s)
c = rs.copy(); d = ImageDraw.Draw(c)
for f,(x,y,w,h) in boxes.items():
    X,Y,WW,HH = round(x*sx),round(y*s),round(w*sx),round(h*s)
    print(f, (X,Y,WW,HH))
    d.rectangle((X,Y,X+WW-1,Y+HH-1), outline=cols[f], width=3)
c.save(OUT+r"\overlay_boxes_scaled_on_resized_907x670.png")
