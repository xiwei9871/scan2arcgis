"""Recovery P2: freeze the current R2 (float-geometry repair) failure scene on one real crop (u2, centre 300x300,
32 colours). Runs the code at the current commit unchanged and records what is wrong; it does not fix anything.
Outputs: JSON (committed) + label image / geometry / defect layers (local only)."""
import json, subprocess, sys, time
from pathlib import Path
import numpy as np, shapely
import geopandas as gpd
import sv_common as C
import sv_r2 as R

OUT_LOCAL = C.ROOT / "runs/stitchvector/r2_failcase"; OUT_JSON = C.ROOT / "experiments/STITCHVECTOR/r2_failcase/failcase.json"


def defects(feats):
    g = np.asarray([x for x, _ in feats], object)
    inv = shapely.coverage_invalid_edges(g)
    bad = np.flatnonzero(~shapely.is_empty(inv))
    tree = shapely.STRtree(g); a, b = tree.query(g, predicate="intersects"); m = a < b
    ov = shapely.area(shapely.intersection(g[a[m]], g[b[m]]))
    union = shapely.union_all(g)
    return {"features": int(len(g)), "features_with_invalid_shared_edges": int(len(bad)),
            "invalid_edge_total_length": float(shapely.length(inv[bad]).sum()),
            "invalid_edge_geom_types": sorted(set(shapely.get_type_id(inv[bad]).tolist())),
            "pairwise_overlap_area_total": float(ov.sum()), "pairwise_overlap_pairs_gt_1e-9": int((ov > 1e-9).sum()),
            "area_sum": float(shapely.area(g).sum()), "union_area": float(shapely.area(union)),
            "invalid_edge_bbox_samples": [list(map(float, shapely.bounds(inv[i]))) for i in bad[:10]]}, inv, bad


def main():
    sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=C.ROOT).stdout.strip()
    a, off = C.centre_crop(C.load("u2"), 300, 300); lab, pal = C.quantize(a, 32); h, w = lab.shape
    OUT_LOCAL.mkdir(parents=True, exist_ok=True); OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    np.save(OUT_LOCAL / "target_labels.npy", lab)
    raw = C.polygonize(lab); d_raw, _, _ = defects([(g, v) for g, v in raw])
    t = time.time(); feats, log = R.progressive(lab, check=True); sec = round(time.time() - t, 2)
    d_fin, inv, bad = defects(feats)
    final = R.render(feats, h, w)
    gpd.GeoDataFrame({"label": [v for _, v in feats]}, geometry=[g for g, _ in feats]).to_file(
        OUT_LOCAL / "r2_final.gpkg", layer="features", driver="GPKG", engine="pyogrio")
    if len(bad):
        gpd.GeoDataFrame({"feature": bad}, geometry=list(inv[bad])).to_file(
            OUT_LOCAL / "r2_final.gpkg", layer="invalid_shared_edges", driver="GPKG", engine="pyogrio")
    res = {"title": "R2 float-geometry repair: frozen failure scene (recovery P2)", "code_sha": sha,
           "sample": "u2", "crop_offset_yx": list(off), "size": [h, w], "palette_colours": 32,
           "seconds_progressive": sec, "peak_rss_gb": round(C.peak_rss_gb(), 3), "stage_log": log,
           "final_label_mismatch_px": int((final != lab).sum()),
           "raw_rasterio_polygonize_defects": d_raw, "final_r2_defects": d_fin,
           "classification": {
            "pixel_partition": "correct iff final_label_mismatch_px == 0",
            "area_rule_preregistered": "area_sum == union_area == window",
            "gis_shared_edge_topology": "coverage_invalid_edges empty; FAILS when shared edges carry different vertex sets (T-junctions)",
            "note": "raw polygonize already fails the GIS shared-edge test, so the defect is not only introduced by repair"}}
    json.dump(res, open(OUT_JSON, "w"), indent=1, default=float)
    print(json.dumps({k: res[k] for k in ("code_sha", "seconds_progressive", "final_label_mismatch_px")}),
          "\nraw", d_raw | {"invalid_edge_bbox_samples": "..."}, "\nfinal", d_fin | {"invalid_edge_bbox_samples": "..."})


if __name__ == "__main__":
    main()
