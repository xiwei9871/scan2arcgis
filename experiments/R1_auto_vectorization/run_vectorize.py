"""E-task PoC: image -> legend-driven labels -> polygons/contacts/faults -> GeoPackage (pixel space, unreferenced)
-> review regions. Works on synthetic cases (with GT) and on real maps (no GT).

Usage:
  python run_vectorize.py synth <case_dir> <out_dir>
  python run_vectorize.py real <image> <legend_swatches.json> <map_box x,y,w,h> <out_dir> [--scale S]
"""
from __future__ import annotations
import argparse, json, sys, time, hashlib, platform
from pathlib import Path
import numpy as np, cv2
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "src"))
from scan2arcgis.recog.legend_classifier import LegendClass, classify  # noqa
from scan2arcgis.recog.lines import fault_candidates  # noqa
from scan2arcgis.vector.polygonize import polygons_from_labels, contacts_from_polygons, trace_skeleton, topology_report  # noqa
from scan2arcgis.export.gpkg import d0_record, write_layers  # noqa
from scan2arcgis.confidence.signals import review_tiles  # noqa
from scan2arcgis.confidence.decide import decide_region, decide_line  # noqa

def git_rev():
    import subprocess
    try: return subprocess.run(["git", "-c", "safe.directory=*", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip() or "unknown"
    except Exception: return "unknown"

def run(rgb, valid, classes, map_id, out: Path, run_id, code_of):
    t0 = time.perf_counter()
    r = classify(rgb, valid, classes, shade_invariant=False)
    t_cls = time.perf_counter() - t0
    polys = polygons_from_labels(r.labels, valid, min_area_px=80, simplify_px=1.0)
    t_poly = time.perf_counter() - t0 - t_cls
    contacts = contacts_from_polygons(polys)
    fmask, fcc, fsc = fault_candidates(rgb, r.labels, valid)
    faults = trace_skeleton(fcc, fsc, min_len=30)
    ver = git_rev()
    prod = ("hybrid", "legend_rf_selftrain", "rf-per-map")  # per-map RF trained on legend swatches (no shipped weights)
    unit_items, poly_conf = [], []
    for k, (g, c) in enumerate(polys):
        m = np.zeros(valid.shape, np.uint8)
        # region signals: mean margin and low-margin fraction (UNCALIBRATED)
        minx, miny, maxx, maxy = [int(v) for v in g.bounds]
        sub = r.margin[miny:maxy + 1, minx:maxx + 1]
        lab_sub = r.labels[miny:maxy + 1, minx:maxx + 1] == c
        mm = sub[lab_sub] if lab_sub.any() else sub.ravel()
        sig = {"mean_margin": float(mm.mean()), "low_margin_frac": float((mm < 0.3).mean()), "area_px": float(g.area),
               "compactness": float(4 * np.pi * g.area / max(1.0, g.length ** 2))}
        hard = [{"check_id": "geom_valid", "status": "PASS" if g.is_valid else "FAIL"},
                {"check_id": "legend_bound", "status": "PASS" if c in code_of else "FAIL"}]
        dec = decide_region(sig, hard)
        unit_items.append((g, d0_record(f"{map_id}_u{k}", map_id, "stratigraphic_unit", code_of.get(c), f"L{c}",
                            sig["mean_margin"], "rf_margin_mean(top1-top2), uncalibrated", prod, ver, run_id, dec, hard, sig)))
        poly_conf.append(sig["mean_margin"])
    contact_items = []
    for k, (ln, ca, cb, ia, ib) in enumerate(contacts):
        sig = {"length_px": float(ln.length), "side_margins": [poly_conf[ia], poly_conf[ib]]}
        hard = [{"check_id": "geom_valid", "status": "PASS" if ln.is_valid else "FAIL"}]
        contact_items.append((ln, d0_record(f"{map_id}_c{k}", map_id, "contact", None, None, float(min(poly_conf[ia], poly_conf[ib])),
                              "min side-region margin, uncalibrated", ("hybrid", "contact_from_polygons", "rf-per-map"), ver, run_id,
                              decide_line(sig, hard, kind="contact"), hard, {**sig, "left_code": code_of.get(ca), "right_code": code_of.get(cb)},
                              derived=[f"{map_id}_u{ia}", f"{map_id}_u{ib}"])))
    fault_items = []
    for k, (ln, sc) in enumerate(faults):
        sig = {"length_px": float(ln.length), "ink_score": sc}
        hard = [{"check_id": "geom_valid", "status": "PASS" if ln.is_valid else "FAIL"}]
        fault_items.append((ln, d0_record(f"{map_id}_f{k}", map_id, "fault", None, None, sc, "skeleton length*elongation heuristic, uncalibrated",
                            ("legacy_rule", "dark_ink_skeleton_v0") if False else ("hybrid", "dark_ink_skeleton_v0", "rule-v0"), ver, run_id,
                            decide_line(sig, hard, kind="fault"), hard, sig)))
    tiles = review_tiles(r.margin, valid, tile=128)
    k = max(1, int(0.1 * len(tiles)))
    from shapely.geometry import box
    review_items = [(box(x, y, x + t, y + t), {"rank": i + 1, "risk_signal": float(rk), "status": "UNCALIBRATED"}) for i, (rk, x, y, t) in enumerate(tiles[:k])]
    summary = write_layers(out / f"{map_id}_r1.gpkg", {"geologic_units": unit_items, "contacts": contact_items, "structures": fault_items})
    import geopandas as gpd
    gpd.GeoDataFrame([d for _, d in review_items], geometry=[g for g, _ in review_items], crs=None).to_file(out / f"{map_id}_r1.gpkg", layer="review_regions", driver="GPKG", engine="pyogrio")
    topo = topology_report(polys, float(valid.sum()))
    decisions = {}
    for layer, items in (("units", unit_items), ("contacts", contact_items), ("faults", fault_items)):
        decisions[layer] = {d: sum(1 for _, rr in items if rr["decision"] == d) for d in ("AUTO_ACCEPT", "AUTO_RETRY", "HUMAN_REVIEW", "BLOCKED", "NONE")}
    return r, polys, contacts, faults, tiles[:k], {"layers": summary, "topology": topo, "decisions": decisions,
            "timings_s": {"classify": t_cls, "polygonize": t_poly, "total": time.perf_counter() - t0}, "producer_version": ver}

def draw(rgb, polys, contacts, faults, review, out_path, palette, scale=1.0):
    vis = (rgb.astype(np.float32) * 0.55).astype(np.uint8)
    for g, c in polys:
        for poly in getattr(g, "geoms", [g]):
            cv2.fillPoly(vis, [np.round(np.asarray(poly.exterior.coords)).astype(np.int32)], palette.get(c, (128, 128, 128)))
    vis = cv2.addWeighted(rgb, 0.4, vis, 0.6, 0)
    for ln, *_ in contacts:
        for l in getattr(ln, "geoms", [ln]):
            cv2.polylines(vis, [np.round(np.asarray(l.coords)).astype(np.int32)], False, (20, 20, 20), max(1, int(1 / scale)))
    for ln, _ in faults:
        cv2.polylines(vis, [np.round(np.asarray(ln.coords)).astype(np.int32)], False, (220, 0, 0), max(2, int(3 / scale)))
    for rk, x, y, t in review:
        cv2.rectangle(vis, (x, y), (x + t, y + t), (255, 0, 255), max(2, int(3 / scale)))
    if scale != 1.0:
        vis = cv2.resize(vis, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    cv2.imwrite(str(out_path), cv2.cvtColor(vis, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 85])

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("mode"); ap.add_argument("args", nargs="+"); ap.add_argument("--scale", type=float, default=1.0)
    a = ap.parse_args()
    if a.mode == "synth":
        case, out = Path(a.args[0]), Path(a.args[1]) / Path(a.args[0]).name; out.mkdir(parents=True, exist_ok=True)
        rgb = cv2.cvtColor(cv2.imread(str(case / "image.png")), cv2.COLOR_BGR2RGB); meta = json.loads((case / "gt.json").read_text())
        x, y, w, h = meta["map_box"]; valid = np.zeros(rgb.shape[:2], bool); valid[y:y + h, x:x + w] = True
        classes = [LegendClass(e["class_id"], e["legend_code"], tuple(e["swatch_box"])) for e in meta["legend"]]
        code_of = {e["class_id"]: e["legend_code"] for e in meta["legend"]}; palette = {e["class_id"]: tuple(e["fill_rgb"]) for e in meta["legend"]}
        map_id = case.name; src_sha = hashlib.sha256((case / "image.png").read_bytes()).hexdigest()
    else:
        img, swj, box, out = Path(a.args[0]), Path(a.args[1]), [int(v) for v in a.args[2].split(",")], Path(a.args[3])
        out.mkdir(parents=True, exist_ok=True)
        from PIL import Image; Image.MAX_IMAGE_PIXELS = None
        rgb = cv2.cvtColor(cv2.imread(str(img)), cv2.COLOR_BGR2RGB)
        sw = json.loads(swj.read_text()); x, y, w, h = box
        valid = np.zeros(rgb.shape[:2], bool); valid[y:y + h, x:x + w] = True
        classes = [LegendClass(i, s.get("code_ocr") or s["legend_entry_id"], tuple(s["box"]), s["legend_entry_id"]) for i, s in enumerate(sw)]
        code_of = {i: (s.get("legend_code") or s["legend_entry_id"]) for i, s in enumerate(sw)}; palette = {i: tuple(s["fill_rgb"]) for i, s in enumerate(sw)}
        map_id = img.stem; src_sha = hashlib.sha256(img.read_bytes()).hexdigest()
    run_id = f"r1_{map_id}_{int(time.time())}"
    r, polys, contacts, faults, review, info = run(rgb, valid, classes, map_id, out, run_id, code_of)
    draw(rgb, polys, contacts, faults, review, out / f"{map_id}_r1_overlay.jpg", palette, a.scale)
    info.update({"map_id": map_id, "source_sha256": src_sha, "run_id": run_id, "coord_space": "image_px_unreferenced",
                 "env": {"python": platform.python_version(), "machine": platform.machine(), "cpus": __import__("os").cpu_count()}})
    (out / f"{map_id}_r1_run.json").write_text(json.dumps(info, indent=1, default=float)); print(json.dumps(info, default=float)[:1500])

if __name__ == "__main__":
    main()
