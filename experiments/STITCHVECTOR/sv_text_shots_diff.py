"""Pixel check of the four browser screenshots (same view: scale S, offset X0,Y0 in canvas px).
Compares 2_b2c_vector vs 3_edited_text_off inside each text box and outside all boxes, and builds
zoomed before/after sheets (original | B2c vector | edited text off | edited text on)."""
import hashlib, json, sys
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
D = Path.home() / "geomap2arcgis/runs/stitchvector/editor_text/shots"; S, X0, Y0 = 4.5, 20, 10
BOXES = {"E-O": (3, 25, 35, 42), "Ar2E": (0, 195, 52, 225), "yun": (24, 59, 41, 76)}
names = ["1_original_png", "2_b2c_vector", "3_edited_text_off", "4_edited_text_on"]
im = {n: np.asarray(Image.open(D / f"{n}.png").convert("RGB")).astype(int) for n in names}
H, W = im[names[0]].shape[:2]
def scr(b, pad=0):
    x0, y0, x1, y1 = b
    return [max(int(X0 + (x0 - pad) * S), 0), max(int(Y0 + (y0 - pad) * S), 0), min(int(X0 + (x1 + pad) * S), W), min(int(Y0 + (y1 + pad) * S), H)]
def changed(a, b): return np.abs(a - b).sum(axis=2) > 30
mapmask = np.zeros((H, W), bool); mapmask[Y0:int(Y0 + 300 * S), X0:int(X0 + 300 * S)] = True
inbox = np.zeros((H, W), bool)
R = {"view": {"scale": S, "offset": [X0, Y0], "screenshot_px": [W, H]}, "boxes": {}}
for k, b in BOXES.items():
    x0, y0, x1, y1 = scr(b); inbox[y0:y1, x0:x1] = True
    c23 = changed(im["2_b2c_vector"], im["3_edited_text_off"])[y0:y1, x0:x1]
    c34 = changed(im["3_edited_text_off"], im["4_edited_text_on"])[y0:y1, x0:x1]
    R["boxes"][k] = {"screen_box": [x0, y0, x1, y1], "px": int(c23.size),
                     "changed_b2c_to_edited_text_off": int(c23.sum()), "share": round(float(c23.mean()), 3),
                     "changed_by_text_layer_on": int(c34.sum())}
# outside: pixels outside every box (box grown by 2 image px for anti-aliasing) inside the map window
grow = np.zeros((H, W), bool)
for b in BOXES.values():
    x0, y0, x1, y1 = scr(b, 2); grow[y0:y1, x0:x1] = True
out = mapmask & ~grow; c = changed(im["2_b2c_vector"], im["3_edited_text_off"]) & out
ys, xs = np.nonzero(c)
R["outside_boxes"] = {"screen_px_checked": int(out.sum()), "changed_screen_px": int(c.sum()),
                      "changed_image_px_approx": int(round(c.sum() / S / S)),
                      "changed_image_xy": sorted({(int((x - X0) / S), int((y - Y0) / S)) for x, y in zip(xs, ys)})[:20]}
# zoomed sheets
for k, b in BOXES.items():
    x0, y0, x1, y1 = scr(b, 8); tiles = []
    for n in names:
        t = Image.fromarray(im[n][y0:y1, x0:x1].astype(np.uint8)); t = t.resize((t.width * 2, t.height * 2), Image.NEAREST)
        dr = ImageDraw.Draw(t); bx = scr(b); dr.rectangle([(bx[0] - x0) * 2, (bx[1] - y0) * 2, (bx[2] - x0) * 2, (bx[3] - y0) * 2], outline=(255, 214, 0), width=2)
        tiles.append(t)
    sheet = Image.new("RGB", (sum(t.width for t in tiles) + 30, tiles[0].height + 30), "white"); dr = ImageDraw.Draw(sheet); x = 0
    for n, t in zip(["original", "B2c vector", "edited, text off", "edited, text on"], tiles): sheet.paste(t, (x, 30)); dr.text((x + 4, 8), n, fill="black"); x += t.width + 10
    sheet.save(D / f"zoom_{k}.png")
R["sha256"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(D.glob("*.png"))}
o = Path(__file__).resolve().parents[0] / "text_layer/text_shots_diff.json"; json.dump(R, open(o, "w"), indent=1)
print(json.dumps({k: v for k, v in R.items() if k != "sha256"}, indent=1))
