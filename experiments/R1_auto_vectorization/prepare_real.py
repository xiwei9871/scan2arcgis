"""Build a working image for a real map: (map ROI, scaled) + (legend strip, scaled) side by side,
detect legend swatches on the strip, and write work.png / work.json.

Why a composite: the legend-driven classifier samples swatch pixels from the same image it classifies,
so the legend must be present at the same scale. The ROI coordinates are recorded so results can be
mapped back to original-image pixels: x_orig = roi_x + x_work / scale (inside the map part).
Usage: prepare_real.py <image> <out_dir> --roi x,y,w,h --legend x,y,w,h --scale s [--min-side n --max-side n]
"""
import argparse, json, sys, hashlib
from pathlib import Path
import numpy as np, cv2
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "src"))
from scan2arcgis.recog.legend_swatches import detect_swatches, ocr_code
ap = argparse.ArgumentParser(); ap.add_argument("image"); ap.add_argument("out")
ap.add_argument("--roi"); ap.add_argument("--legend"); ap.add_argument("--scale", type=float, default=1.0)
ap.add_argument("--min-side", type=int, default=12); ap.add_argument("--max-side", type=int, default=120)
ap.add_argument("--aspect-max", type=float, default=3.5)
a = ap.parse_args()
img = cv2.cvtColor(cv2.imread(a.image), cv2.COLOR_BGR2RGB)
rx, ry, rw, rh = map(int, a.roi.split(",")); lx, ly, lw, lh = map(int, a.legend.split(","))
s = a.scale
roi = cv2.resize(img[ry:ry + rh, rx:rx + rw], None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
leg = cv2.resize(img[ly:ly + lh, lx:lx + lw], None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
H = max(roi.shape[0], leg.shape[0]); W = roi.shape[1] + 8 + leg.shape[1]
work = np.full((H, W, 3), 255, np.uint8); work[:roi.shape[0], :roi.shape[1]] = roi
ox = roi.shape[1] + 8; work[:leg.shape[0], ox:ox + leg.shape[1]] = leg
sw = detect_swatches(work, (ox, 0, leg.shape[1], leg.shape[0]), min_side=a.min_side, max_side=a.max_side, aspect=(0.8, a.aspect_max))
for d in sw:
    d["code_ocr"] = ocr_code(work, d["box"])
out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
cv2.imwrite(str(out / "work.png"), cv2.cvtColor(work, cv2.COLOR_RGB2BGR))
meta = {"source_image": Path(a.image).name, "source_sha256": hashlib.sha256(Path(a.image).read_bytes()).hexdigest(),
        "roi_orig": [rx, ry, rw, rh], "legend_orig": [lx, ly, lw, lh], "scale": s,
        "map_box_work": [0, 0, roi.shape[1], roi.shape[0]], "legend_box_work": [ox, 0, leg.shape[1], leg.shape[0]],
        "swatches": sw, "note": "swatches auto-detected; legend codes NOT read (OCR eng only) -> legend_entry_id used as class name"}
(out / "work.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False))
(out / "swatches.json").write_text(json.dumps(sw, indent=1, ensure_ascii=False))
vis = work.copy()
for d in sw:
    x, y, w, h = d["box"]; cv2.rectangle(vis, (x, y), (x + w, y + h), (255, 0, 0), 2); cv2.putText(vis, d["legend_entry_id"], (x + w + 2, y + h // 2), 0, 0.4, (255, 0, 0), 1)
cv2.imwrite(str(out / "swatch_check.jpg"), cv2.cvtColor(vis[:, ox - 4:], cv2.COLOR_RGB2BGR))
print(len(sw), work.shape, [d["fill_rgb"] for d in sw][:40])
