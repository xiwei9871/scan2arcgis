"""C3 on real maps: same work image, same legend swatches -> new (legend RF) vs legacy stratigraphy.

Reference: legacy draft partial labels (gm1/gm2 only, label_status=draft). They carry no legend
codes, so evaluation is class-agnostic: for each reference polygon, purity = share of its pixels
covered by the single dominant predicted label, and best_iou = IoU with the predicted connected
region of that label overlapping it most. Without reference data only observations are reported.
Usage: compare_real.py <work_dir> <out_dir> [--ref labels.geojson] [--legacy-boundary]
"""
import argparse, json, sys, time
from pathlib import Path
import numpy as np, cv2
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "src"))
from scan2arcgis.recog.legend_classifier import LegendClass, classify
from scan2arcgis.adapters import legacy as LG
from scan2arcgis.eval.raster_metrics import class_boundaries, line_buffer_f1, rasterize_polylines

ap = argparse.ArgumentParser(); ap.add_argument("work"); ap.add_argument("out"); ap.add_argument("--ref"); ap.add_argument("--ref-lines")
ap.add_argument("--legacy-boundary", action="store_true"); ap.add_argument("--legacy", default=str(ROOT / "legacy" / "backend"))
a = ap.parse_args()
wd = Path(a.work); out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
meta = json.loads((wd / "work.json").read_text()); rgb = cv2.cvtColor(cv2.imread(str(wd / "work.png")), cv2.COLOR_BGR2RGB)
mx, my, mw, mh = meta["map_box_work"]; valid = np.zeros(rgb.shape[:2], bool); valid[my:my + mh, mx:mx + mw] = True
sw = meta["swatches"]
classes = [LegendClass(i, s["legend_entry_id"], tuple(s["box"]), s["legend_entry_id"]) for i, s in enumerate(sw)]
legend = [{"legend_entry_id": s["legend_entry_id"], "legend_code": s["legend_entry_id"], "class_id": i, "fill_rgb": s["fill_rgb"]} for i, s in enumerate(sw)]
palette = {i: tuple(s["fill_rgb"]) for i, s in enumerate(sw)}
res = {"work": str(wd.name), "source_sha256": meta["source_sha256"], "scale": meta["scale"], "roi_orig": meta["roi_orig"],
       "n_legend_swatches": len(sw), "methods": {}}
preds = {}
for name, kw in [("legend_rf_selftrain", {}), ("legend_rf_selftrain_shadeinv", {"shade_invariant": True})]:
    t = time.perf_counter(); r = classify(rgb, valid, classes, **kw); secs = time.perf_counter() - t
    preds[name] = r.labels
    res["methods"][name] = {"runtime_s": secs, "mean_margin_UNCALIBRATED": float(r.margin[valid].mean()),
                            "low_margin_frac": float((r.margin[valid] < 0.3).mean())}
S = (slice(my, my + mh), slice(mx, mx + mw))
try:
    lab_c, feats, secs = LG.run_stratigraphy(Path(a.legacy), rgb[S], legend)
    lab = np.full(rgb.shape[:2], -1, np.int16); lab[S] = lab_c; preds["legacy_stratigraphy"] = lab
    res["methods"]["legacy_stratigraphy"] = {"runtime_s": secs, "n_polygons": len(feats),
        "unlabeled_frac": float((lab[valid] < 0).mean()),
        "confidence_values_UNCALIBRATED": sorted({round(f["raw_score"], 3) for f in feats if f["raw_score"] is not None})[:8]}
except Exception as e:
    res["methods"]["legacy_stratigraphy"] = {"error": repr(e)}
if a.legacy_boundary:
    try:
        lines, lm, secs = LG.run_boundary(Path(a.legacy), rgb[S])
        res["methods"]["legacy_boundary"] = {"runtime_s": secs, "n_lines": len(lines)}
        preds["_legacy_lines"] = rasterize_polylines([[(x + mx, y + my) for x, y in l] for l in lines], rgb.shape[:2], 1)
    except Exception as e:
        res["methods"]["legacy_boundary"] = {"error": repr(e)}
for name, lab in preds.items():
    if name.startswith("_"): continue
    n, _ = cv2.connectedComponents(((lab >= 0) & valid).astype(np.uint8))
    regions = sum(cv2.connectedComponents(((lab == c) & valid).astype(np.uint8), connectivity=4)[0] - 1 for c in np.unique(lab[valid & (lab >= 0)]))
    res["methods"][name].update({"n_regions": int(regions), "classes_used": int(len(np.unique(lab[valid & (lab >= 0)])))})

# reference evaluation (class-agnostic), coordinates: orig -> work
def to_work(pts):
    rx, ry = meta["roi_orig"][:2]; s = meta["scale"]
    return [((x - rx) * s + mx, (y - ry) * s + my) for x, y in pts]
if a.ref:
    ref = json.loads(Path(a.ref).read_text()); ev = {}
    for name, lab in preds.items():
        if name.startswith("_"): continue
        rows = []
        for f in ref["features"]:
            m = np.zeros(rgb.shape[:2], np.uint8)
            cv2.fillPoly(m, [np.round(np.array(to_work(f["geometry"]["coordinates"][0]))).astype(np.int32)], 1)
            m = (m > 0) & valid
            if m.sum() < 100: continue
            v = lab[m]; vv = v[v >= 0]
            if len(vv) == 0: rows.append({"label": f["properties"].get("label"), "purity": 0.0, "best_iou": 0.0}); continue
            c = np.bincount(vv).argmax(); purity = float((v == c).mean())
            ncc, cc = cv2.connectedComponents(((lab == c) & valid).astype(np.uint8), connectivity=4)
            ids, cnt = np.unique(cc[m & (cc > 0)], return_counts=True); best = ids[cnt.argmax()]
            reg = cc == best; iou = float((reg & m).sum() / (reg | m).sum())
            rows.append({"label": f["properties"].get("label"), "purity": purity, "best_iou": iou, "dominant": sw[c]["legend_entry_id"]})
        ev[name] = {"per_polygon": rows, "mean_purity": float(np.mean([r["purity"] for r in rows])) if rows else None,
                    "mean_best_iou": float(np.mean([r["best_iou"] for r in rows])) if rows else None}
    res["reference_eval"] = {"reference": "legacy draft_partial_label (not reviewed)", "metric": "class-agnostic purity / best_iou", "results": ev}
if a.ref_lines:
    ref = json.loads(Path(a.ref_lines).read_text())
    gl = rasterize_polylines([to_work(f["geometry"]["coordinates"]) for f in ref["features"]], rgb.shape[:2], 1) & valid
    near = cv2.dilate(gl.astype(np.uint8), np.ones((41, 41), np.uint8)) > 0   # evaluate only around labelled lines
    lev = {}
    for name, lab in preds.items():
        m = lab if name.startswith("_") else class_boundaries(lab, valid)
        r = line_buffer_f1(m & near, gl, 3.0, valid); lev[name] = {"recall_tol3px": r["recall"], "precision_in_corridor": r["precision"]}
    res["reference_lines_eval"] = {"note": "draft labels cover few lines; precision measured only inside a 20px corridor", "results": lev}
(out / "compare.json").write_text(json.dumps(res, indent=1, default=float, ensure_ascii=False))
tiles = []
for name, lab in preds.items():
    if name.startswith("_"): continue
    col = np.zeros_like(rgb)
    for c, p in palette.items(): col[lab == c] = p
    vis = (0.3 * rgb + 0.7 * col).astype(np.uint8); vis[(lab < 0) & valid] = (0, 0, 0)
    vis[class_boundaries(lab, valid)] = (30, 30, 30)
    v = vis[S]; cv2.putText(v, name, (10, 40), 0, 1.2, (255, 0, 0), 3); tiles.append(v)
orig = rgb[S].copy(); cv2.putText(orig, "input", (10, 40), 0, 1.2, (255, 0, 0), 3)
grid = np.concatenate([orig] + tiles, 1)
cv2.imwrite(str(out / "compare_side_by_side.jpg"), cv2.cvtColor(cv2.resize(grid, None, fx=0.35, fy=0.35, interpolation=cv2.INTER_AREA), cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 85])
print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk in ("runtime_s", "n_regions", "unlabeled_frac", "n_polygons", "error")} for k, v in res["methods"].items()}, default=float))
print(json.dumps({k: (v["mean_purity"], v["mean_best_iou"]) for k, v in res.get("reference_eval", {}).get("results", {}).items()}, default=float))
print(json.dumps(res.get("reference_lines_eval", {}).get("results", {}), default=float))
