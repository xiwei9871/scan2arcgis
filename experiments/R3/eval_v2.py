"""EVAL_V2 (EVALUATION ONLY). Adds corrected line ground truth; V1 is left untouched.

V1 line GT (frozen): gt_contacts/gt_faults drawn 1 px at 200 dpi, then nearest-downscaled to the
work grid (100 dpi). This fragments lines (08004 contacts: ~15k pieces) and under-counts matches.
V2 line GT: the same official geo_L geometry rasterised directly on the work grid with the same
registration (frame_reg.json) and the same 1 px width. Line metric (line_prf, tol 1.5 px) unchanged.

Usage: eval_v2.py lines   <sheet> <out_json>   -> V1 vs V2 contact/fault P/R/F1 for R1, R2 variants, R3 S2 maps
       eval_v2.py polygonize <sheet> <out_json> [snap_m]  -> geo_L vector line-to-face (route A technique check)
"""
import json, sys, warnings
from pathlib import Path
import cv2, numpy as np, geopandas as gpd
from shapely import ops, geometry as sg, snap, unary_union, polygonize_full

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "R2_real_map"))
from eval_common import Sheet, line_prf, boundary, evaluate  # noqa: E402
from gsj_gt import lines as glines, to_px, rings  # noqa: E402
warnings.filterwarnings("ignore")

YEAR = {"08004": "2012", "08001": "1980"}


def sheet(n):
    return Sheet(f"runs/r2_gsj/{n}/r1", f"data/raw/gsj/{n}/{n}.xlsx", f"runs/r2_gsj/{n}/gt")


def v2_lines(n, sh):
    H = np.diag([sh.scale, sh.scale, 1.0]) @ np.array(json.load(open(f"runs/r2_gsj/{n}/frame_reg.json"))["H_lonlat_to_px"])
    L = gpd.read_file(f"data/raw/gsj/{n}/shp/geo_L.shp", encoding="cp932")
    con = np.zeros(sh.gt.shape, np.uint8); flt = np.zeros(sh.gt.shape, np.uint8)
    for g, k in zip(L.geometry, L["LEGEND01"].astype(str)):
        if "図郭" in k: continue
        tgt = flt if ("断層" in k or "fault" in k.lower()) else (con if "地質境界" in k else None)
        if tgt is None: continue
        for ln in glines(g): cv2.polylines(tgt, [np.round(to_px(ln, H)).astype(np.int32).reshape(-1, 1, 2)], False, 1, 1)
    return con > 0, flt > 0


def cmd_lines(n, out_json):
    sh = sheet(n); mm = sh.mm
    c2, f2 = v2_lines(n, sh)
    preds = {"R1_rf_selftrain": f"runs/r2_gsj/{n}/r1/pred_legend_rf_selftrain.npy",
             "R1_rf": f"runs/r2_gsj/{n}/r1/pred_legend_rf.npy",
             "R1_nearest_color": f"runs/r2_gsj/{n}/r1/pred_legend_nearest_color.npy"}
    maps = {k: np.load(p).astype(np.int32) for k, p in preds.items()}
    z = np.load(f"runs/r3/{n}/s2/s2_maps.npz")
    maps["R3_S2_A1"] = z["A1"].astype(np.int32); maps["R3_S2_B1"] = z["B1"].astype(np.int32)
    res = {"sheet": n, "gt_fragments": {
        "v1_contacts_8cc": int(cv2.connectedComponents(sh.gt_contacts.astype(np.uint8), connectivity=8)[0] - 1),
        "v2_contacts_8cc": int(cv2.connectedComponents(c2.astype(np.uint8), connectivity=8)[0] - 1),
        "v1_contact_px": int((sh.gt_contacts & mm).sum()), "v2_contact_px": int((c2 & mm).sum()),
        "v1_fault_px": int((sh.gt_faults & mm).sum()), "v2_fault_px": int((f2 & mm).sum())},
        "note": "R3 S1 methods (A1/A2t/A3) reuse R1 regions; their region boundaries equal R1_rf_selftrain. "
                "Fault numbers for polygon maps are coverage by area edges, NOT fault detection.", "methods": {}}
    for k, p in maps.items():
        b = boundary(np.where(mm, p, -1)) & mm
        res["methods"][k] = {"contact_v1": line_prf(b, sh.gt_contacts, mm, 1.5), "contact_v2": line_prf(b, c2, mm, 1.5),
                             "fault_cov_v1": line_prf(b, sh.gt_faults, mm, 1.5)["recall"], "fault_cov_v2": line_prf(b, f2, mm, 1.5)["recall"]}
    for k in ("l0", "l0_long"):
        L = z[k]
        res["methods"][f"R3_S2_{k}"] = {"contact_v1": line_prf(L, sh.gt_contacts, mm, 1.5), "contact_v2": line_prf(L, c2, mm, 1.5),
                                        "fault_v1": line_prf(L, sh.gt_faults, mm, 1.5), "fault_v2": line_prf(L, f2, mm, 1.5)}
    json.dump(res, open(out_json, "w"), indent=1, default=float)
    print(n, res["gt_fragments"])
    for k, v in res["methods"].items():
        a, b = v["contact_v1"], v["contact_v2"]
        print(f"  {k:18s} contact F1 v1={a['f1']:.3f} v2={b['f1']:.3f}  P {a['precision']:.3f}->{b['precision']:.3f}  R {a['recall']:.3f}->{b['recall']:.3f}")
    return res


def cmd_polygonize(n, out_json, snap_m=None):
    """Route-A technique check in vector space. geo_A is used ONLY for the final scoring block."""
    sh = sheet(n); mm = sh.mm; s = sh.scale
    snap_m = float(snap_m) if snap_m else 2.0
    L = gpd.read_file(f"data/raw/gsj/{n}/shp/geo_L.shp", encoding="cp932")
    crs = L.estimate_utm_crs(); Lm = L.to_crs(crs)
    frame = Lm[Lm["LEGEND01"].astype(str).str.contains("図郭")]
    use = Lm[~Lm["LEGEND01"].astype(str).str.contains("図郭")]
    geo = [g for g in use.geometry if g is not None]
    fr = unary_union(list(frame.geometry)) if len(frame) else None
    allg = geo + ([fr] if fr is not None else [])
    merged = unary_union(allg)                       # node all lines at intersections
    snapped = snap(merged, merged, snap_m)           # close gaps <= snap_m metres (no geo_A used)
    noded = unary_union(snapped)
    polys, dangles, cuts, invalid = polygonize_full([noded])
    faces = [p for p in polys.geoms]
    # closure stats
    endpoints = []
    for ln in (noded.geoms if hasattr(noded, "geoms") else [noded]):
        if ln.geom_type == "LineString": endpoints += [ln.coords[0], ln.coords[-1]]
    from collections import Counter
    deg = Counter((round(x, 3), round(y, 3)) for x, y in endpoints)
    dangling_nodes = sum(1 for v in deg.values() if v == 1)
    sheet_area = sg.box(*gpd.GeoSeries([fr], crs=crs).total_bounds).area if fr is not None else None
    face_area = sum(p.area for p in faces)
    inval = sum(1 for p in faces if not p.is_valid)
    # rasterise faces on the work grid (lon/lat -> px via registration); face id per pixel
    H = np.diag([s, s, 1.0]) @ np.array(json.load(open(f"runs/r2_gsj/{n}/frame_reg.json"))["H_lonlat_to_px"])
    fg = gpd.GeoSeries(faces, crs=crs).to_crs(L.crs)
    face = np.full(sh.gt.shape, -1, np.int32)
    order = np.argsort([-p.area for p in faces])
    for i in order:
        g = fg.iloc[i]
        for rr in rings(g):
            cv2.fillPoly(face, [np.round(to_px(rr[0], H)).astype(np.int32)], int(i))
    # ---- scoring (geo_A enters only here) ----
    v = sh.valid; F, G = face[v], sh.gt[v]
    covered = float((F >= 0).mean())
    # each face -> majority official unit (ideal labelling of these faces)
    lab = np.full(sh.gt.shape, -1, np.int32)
    if (F >= 0).any():
        M = np.zeros((len(faces), len(sh.symbols)), np.int64); sel = F >= 0
        np.add.at(M, (F[sel], G[sel]), 1)
        maj = M.argmax(1); purity = float(M.max(1).sum() / max(M.sum(), 1))
        lab[face >= 0] = maj[face[face >= 0]]
    else: purity = 0.0
    e = evaluate(lab, sh.gt, mm, sh.units, 1.5)
    # R1 majority vote on these faces (route-A with R1 as region classifier)
    r1 = np.load(f"runs/r2_gsj/{n}/r1/pred_legend_rf_selftrain.npy").astype(np.int32)
    vote = np.full(sh.gt.shape, -1, np.int32)
    if (F >= 0).any():
        sel2 = mm & (face >= 0) & (r1 >= 0)
        V = np.zeros((len(faces), int(r1.max()) + 1), np.int64); np.add.at(V, (face[sel2], r1[sel2]), 1)
        vm = V.argmax(1); vote[face >= 0] = vm[face[face >= 0]]
    ev2 = evaluate(vote, sh.gt, mm, sh.units, 1.5)
    n_inst = sum(cv2.connectedComponents(((sh.gt == j) & mm).astype(np.uint8), connectivity=4)[0] - 1 for j in range(len(sh.symbols)))
    res = {"sheet": n, "method": "vector: unary_union (node) -> shapely.snap(tolerance) -> polygonize_full; geo_A not used",
           "snap_tolerance_m": snap_m, "crs_metric": str(crs),
           "n_input_lines": len(geo), "n_faces": len(faces), "n_official_instances": int(n_inst),
           "dangles": len(list(dangles.geoms)), "cut_edges": len(list(cuts.geoms)), "invalid_rings": len(list(invalid.geoms)),
           "dangling_nodes": dangling_nodes, "invalid_faces": inval,
           "face_area_over_sheet_area": (face_area / sheet_area) if sheet_area else None,
           "map_px_covered_by_faces": covered,
           "score_faces_ideal_label": {"face_purity_vs_geo_A": purity, "ub_pixel_acc": e["pixel_acc_matched"], "ub_miou": e["miou_matched_all_units"],
                                       "note": "upper bound of THESE faces: each face given its majority official unit"},
           "score_faces_R1_vote": {"ub_pixel_acc": ev2["pixel_acc_matched"], "ub_miou": ev2["miou_matched_all_units"]},
           "reference_geo_A_ideal_regions_R1_vote_miou": json.load(open(f"experiments/R2_real_map/results/diagnostics/{n}_oracle.json"))["methods"]["R_vote"]["miou"]}
    json.dump(res, open(out_json, "w"), indent=1, default=float)
    print(json.dumps({k: (round(x, 4) if isinstance(x, float) else x) for k, x in res.items()}, ensure_ascii=False, default=float))
    return res


if __name__ == "__main__":
    c = sys.argv[1]
    if c == "lines": cmd_lines(sys.argv[2], sys.argv[3])
    elif c == "polygonize": cmd_polygonize(sys.argv[2], sys.argv[3], *(sys.argv[4:5] or []))
