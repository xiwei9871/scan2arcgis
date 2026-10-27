"""AUTO_RETRY PoC: run two feature variants and pick by an unsupervised criterion
(mean classifier margin over the map, UNCALIBRATED). Compares with the oracle choice."""
import sys, json, time
from pathlib import Path
import numpy as np, cv2
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "src"))
from scan2arcgis.recog.legend_classifier import LegendClass, classify
from scan2arcgis.eval.raster_metrics import pixel_metrics
suite = Path(sys.argv[1]); out = Path(sys.argv[2]); cases = sys.argv[3:] or sorted(p.name for p in suite.iterdir())
res = json.loads(out.read_text()) if out.exists() else {}
for c in cases:
    if c in res: continue
    d = suite / c; img = cv2.cvtColor(cv2.imread(str(d / "image.png")), cv2.COLOR_BGR2RGB)
    gt = np.load(d / "gt_labels.npy"); meta = json.loads((d / "gt.json").read_text())
    mm = np.zeros(gt.shape, bool); x, y, w, h = meta["map_box"]; mm[y:y + h, x:x + w] = True
    cls = [LegendClass(e["class_id"], e["legend_code"], tuple(e["swatch_box"])) for e in meta["legend"]]
    row = {}
    for v in (False, True):
        r = classify(img, mm, cls, shade_invariant=v)
        row[r.method] = {"miou": pixel_metrics(r.labels, gt, mm)["miou"], "mean_margin": float(r.margin[mm].mean()),
                         "low_margin_frac": float((r.margin[mm] < 0.3).mean())}
    k = list(row); pick = max(k, key=lambda m: row[m]["mean_margin"]); oracle = max(k, key=lambda m: row[m]["miou"])
    row["_picked"] = pick; row["_oracle"] = oracle
    res[c] = row; out.write_text(json.dumps(res, indent=1)); print(c, {m: round(row[m]["miou"], 3) for m in k}, "pick", pick == oracle)
