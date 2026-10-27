"""Fairness check for the legacy stratigraphy baseline on real maps.
Variant A: legend colours from detected swatches (as in compare_real.py).
Variant B: explicit full map_mask (no auto mask estimation).
Variant C: map_fill_color re-sampled from the MAP itself (median of pixels the new method assigned to each class)
           -- this favours legacy, so if C is still poor the conclusion is robust.
"""
import sys, json, time
from pathlib import Path
import numpy as np, cv2
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "src"))
from scan2arcgis.adapters import legacy as LG
from scan2arcgis.recog.legend_classifier import LegendClass, classify
wd = Path(sys.argv[1]); meta = json.loads((wd / "work.json").read_text())
rgb = cv2.cvtColor(cv2.imread(str(wd / "work.png")), cv2.COLOR_BGR2RGB)
mx, my, mw, mh = meta["map_box_work"]; S = (slice(my, my + mh), slice(mx, mx + mw))
valid = np.zeros(rgb.shape[:2], bool); valid[S] = True; sw = meta["swatches"]
legend = [{"legend_entry_id": s["legend_entry_id"], "legend_code": s["legend_entry_id"], "class_id": i, "fill_rgb": s["fill_rgb"]} for i, s in enumerate(sw)]
Strat, _ = LG._import_legacy(ROOT / "legacy" / "backend")
crop = np.ascontiguousarray(rgb[S][..., ::-1])
res = {}
def run(name, leg, mask=None):
    t = time.perf_counter(); out = Strat().run(crop, legend_entries=LG.legend_dicts(leg), return_geojson=True, map_mask=mask)
    lab = np.full(crop.shape[:2], -1, np.int32)
    for f in out["features"]:
        LG._fill_geometry(lab, f["geometry"], 1)
    res[name] = {"n_polygons": len(out["features"]), "labeled_frac": float((lab >= 0).mean()), "secs": time.perf_counter() - t}
run("A_swatch_colours", legend)
run("B_full_map_mask", legend, np.full(crop.shape[:2], 255, np.uint8))
r = classify(rgb, valid, [LegendClass(i, s["legend_entry_id"], tuple(s["box"])) for i, s in enumerate(sw)])
legC = []
for e in legend:
    m = (r.labels == e["class_id"]) & valid & ~r.ink
    if m.sum() > 50:
        legC.append({**e, "fill_rgb": [int(v) for v in np.median(rgb[m], 0)]})
run("C_map_sampled_colours", legC, np.full(crop.shape[:2], 255, np.uint8))
print(wd.name, json.dumps(res))
(wd / "legacy_fairness.json").write_text(json.dumps(res, indent=1))
