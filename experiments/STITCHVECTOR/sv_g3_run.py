"""Score existing outputs with G1-G3 (plan: sv_g3_plan.json). Read-only.
Usage: sv_g3_run.py <json_dir> [--smoke <gpkg_dir>]   (.venv-sv). --smoke scores freshly built dev outputs (seeds 1201/1301)."""
import json, sys, hashlib, collections
from pathlib import Path
import numpy as np, shapely, pyogrio
from shapely.geometry import LineString, Polygon, box
import sv_synth as S, sv_b2c_scenes as SC, sv_common as Cm, sv_oracle as O, sv_oracle_v2 as O2, sv_g3 as G

HERE = Path(__file__).resolve().parent; ROOT = HERE.parents[1]; RS = ROOT / "runs/stitchvector"
PLAN = json.load(open(HERE / "sv_g3_plan.json"))
METHODS = ["F0", "B0", "B2c"]; SCENE_KINDS = ["pale_ink_on_light", "ink_on_boundary", "edge_only", "bands", "ink_crosses_band"]
FILL_LAB = {"pink": 0, "green": 1, "yellow": 2, "redfill": 3}


def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()


def check_sha(files, listing, base):
    rec = {}
    for ln in open(listing):
        h, rel = ln.split(maxsplit=1); rec[rel.strip()] = h
    bad = [str(f) for f in files if rec.get(str(f.relative_to(base))) != sha(f)]
    if bad: raise SystemExit(f"SHA-256 mismatch: {bad[:5]}")
    return len(files)


def axis_rgb(img, g):
    P = shapely.get_coordinates(shapely.line_interpolate_point(g, np.linspace(0, g.length, max(int(g.length), 1) + 1)))
    x = np.clip(P[:, 0].astype(int), 0, img.shape[1] - 1); y = np.clip(P[:, 1].astype(int), 0, img.shape[0] - 1); return np.median(img[y, x], 0)


def vis_mask(P, blockers):
    if not blockers: return np.ones(len(P), bool)
    U = shapely.union_all(blockers); return ~shapely.contains_xy(U, P[:, 0], P[:, 1])


def runs(c, key, n=3):
    m = np.r_[0, (np.asarray(c) == key).astype(int), 0]; d = np.diff(m); st, en = np.nonzero(d == 1)[0], np.nonzero(d == -1)[0]
    return [int(e - s) for s, e in zip(st, en) if e - s >= n]


def load(gp):
    layers = [l[0] for l in pyogrio.list_layers(gp)]; F = pyogrio.read_dataframe(gp, layer="colour_faces")
    L = pyogrio.read_dataframe(gp, layer="visual_lines") if "visual_lines" in layers else None; return F, L


def score_tile(img, inks, fills, bands_, fill_polys, truth_lab, gp, kind_of):
    """inks: [{id, axis, width, kind, blockers}] ; fills: [{id, axis(LineString), blockers}] ; bands_: [{id, axis, width}]"""
    shape = img.shape[:2]; F, L = load(gp); frame = box(0, 0, shape[1], shape[0]).boundary.buffer(0.6)
    FI, LI = G.out_geometry(F, L, frame); fid = G.face_id_raster(F, shape); out = {"ink": {}, "fill": {}, "band": {}}
    ink_geoms = [x["axis"] for x in inks]
    for x in inks:
        P, T = G.truth_samples(x["axis"]); vis = vis_mask(P, x["blockers"]); c = G.classify_ink(P, T, vis, x["width"], FI, LI)[vis]
        out["ink"][x["id"]] = {"kind": kind_of(x), "n": int(vis.sum()), **G.tally(c, G.INK_K), "redraw_runs": runs(c, "missing"), "adjust_runs": runs(c, "needs_fix"),
                               "outline_px": int((c == "face_outline").sum())}
    for x in fills:
        if x["axis"].length < 2: continue
        P, T = G.truth_samples(x["axis"]); vis = vis_mask(P, x["blockers"]); c = G.classify_edge(P, T, vis, FI, LI)[vis]
        out["fill"][x["id"]] = {"n": int(vis.sum()), **G.tally(c, G.EDGE_K), "redraw_runs": runs(c, "missing"), "adjust_runs": runs(c, "needs_fix"), "line_only_runs": runs(c, "line_only")}
    for b in bands_:
        P, T = G.truth_samples(b["axis"]); vis = vis_mask(P, b.get("blockers", [])); bf = G.band_faces(F, b["axis"], b["width"])
        _, c, _ = G.classify_band(b["axis"], b["width"], vis, FI, LI, fid, bf); c = c[vis]
        out["band"][b["id"]] = {"width": b["width"], "n": int(vis.sum()), "band_faces": len(bf), **G.tally(c, G.BAND_K), "redraw_runs": runs(c, "missing"),
                                "adjust_runs": runs(c, "needs_fix") + runs(c, "face_needs_fix"), "has_line_convert_run": bool(runs(c, "line_convert"))}
    sides = [shapely.offset_curve(b["axis"], s * b["width"] / 2) for b in bands_ for s in (1, -1)]
    ink_foot = np.zeros(shape, bool)
    for x in inks: ink_foot |= O.rmask(x["axis"].buffer(x["width"] / 2 + 1.0), shape)
    out["spurious_face_boundary_px"] = G.spurious_boundary(FI, ink_geoms + [x["axis"] for x in fills] + [s for s in sides if not s.is_empty], ink_foot)
    out["face_boundary_px"] = float(len(FI.P) * 0.5); out["faces"] = len(F); out["lines"] = 0 if L is None else len(L)
    groups = G.line_groups(L)
    inkx = [{"axis": x["axis"], "width": x.get("width_truth"), "rgb": axis_rgb(img, x["axis"])} for x in inks]
    out["line_ops"], out["line_groups"] = G.line_ops(groups, inkx, bands_)
    out["face_ops"] = G.face_ops(F, fid, truth_lab, {v: S.FILLS[k] for k, v in FILL_LAB.items()}, ink_foot, shape) if truth_lab is not None else None
    return out


def synth_truth(seed):
    img, truth, faces = S.generate(seed); W = img.shape[1]; inks = []
    for i, t in enumerate(truth["lines"]):
        later = [LineString(u["axis"]).buffer(np.median(u["width"]) / 2 + 0.5) for u in truth["lines"][i + 1:]]
        inks.append({"id": t["id"], "axis": LineString(t["axis"]), "width": float(np.median(t["width"])), "width_truth": float(np.median(t["width"])), "kind": t["id"], "blockers": later})
    ink_all = [LineString(u["axis"]).buffer(np.median(u["width"]) / 2 + 0.5) for u in truth["lines"]]
    band_all = [LineString(b["axis"]).buffer(b["width"] / 2 + 0.5) for b in truth["bands"]]
    order = ["green", "yellow", "redfill"]; tile = box(0, 0, W, W); fills = []
    for i, n in enumerate(order):
        e = shapely.intersection(Polygon(faces[n]).exterior, tile)
        for m in order[i + 1:]: e = shapely.difference(e, Polygon(faces[m]))
        e = shapely.difference(e, tile.boundary.buffer(0.6))
        for j, part in enumerate(shapely.get_parts(shapely.line_merge(e) if e.geom_type == "MultiLineString" else e)):
            if part.geom_type == "LineString": fills.append({"id": f"{n}_{j}", "axis": part, "blockers": ink_all + band_all})
    bands_ = [{"id": b["id"], "axis": LineString(b["axis"]), "width": b["width"], "blockers": ink_all} for b in truth["bands"]]
    lab = np.zeros(img.shape[:2], np.int32)
    for n in order: lab[O.rmask(Polygon(faces[n]), img.shape[:2])] = FILL_LAB[n]
    for b in truth["bands"]: lab[O.rmask(LineString(b["axis"]).buffer(b["width"] / 2), img.shape[:2])] = FILL_LAB["green" if "green" in b["id"] else "yellow"]
    return img, inks, fills, bands_, lab


def scene_truth(seed, kind):
    img, t = SC.scene(kind, seed); inks = []
    for i, x in enumerate(t["ink"]):
        later = [LineString(u["axis"]).buffer(u["width"] / 2 + 0.5) for u in t["ink"][i + 1:]]
        inks.append({"id": x["id"], "axis": LineString(x["axis"]), "width": x["width"], "width_truth": x["width"], "kind": x["sub"], "blockers": later})
    ink_all = [LineString(u["axis"]).buffer(u["width"] / 2 + 0.5) for u in t["ink"]]
    tile = box(0, 0, img.shape[1], img.shape[0]).boundary.buffer(0.6)
    fills = [{"id": e["id"], "axis": shapely.difference(LineString(e["axis"]).intersection(box(0, 0, img.shape[1], img.shape[0])), tile), "blockers": ink_all}
             for e in t["edges"] if not e["covered_by_ink"]]
    fills = [f for f in fills if f["axis"].geom_type == "LineString"]
    bands_ = [{"id": b["id"], "axis": LineString(b["axis"]), "width": b["width"], "blockers": ink_all} for b in t["bands"]]
    return img, inks, fills, bands_, None


def u2_truth():
    img, _ = Cm.centre_crop(Cm.load("u2"), 300, 300); P = dict(O.P); P.update(O2.PRE["params"]); ol, _ = O2.build(img, P); inks = []
    for i, f in enumerate(ol):
        if len(f["raw"]) < 2: continue
        others = [LineString(g["raw"]).buffer(g["width"] / 2 + 0.5) for j, g in enumerate(ol) if j != i and len(g["raw"]) >= 2]
        inks.append({"id": f["id"], "axis": LineString(f["raw"]), "width": float(f["width"]), "width_truth": None, "kind": f["kind"], "blockers": others})
    ink_all = [x["axis"].buffer(x["width"] / 2 + 0.5) for x in inks]
    bands_ = [{"id": q["id"], "axis": LineString(q["axis"]), "width": 2 * q["radius"], "blockers": ink_all} for q in O2.ORA["protected"]]
    return img, inks, [], bands_, None


def band_repair(img, b, gp):
    F, L = load(gp); g, r = b["axis"], b["width"] / 2; band = g.buffer(r); core = g.buffer(max(r - 1, 0.75))
    bf = [F.geometry.iloc[i - 1] for i in G.band_faces(F, g, b["width"])]; out = {"band_faces": len(bf), "core_area": float(core.area)}
    out["core_by_band_faces"] = float(shapely.intersection(shapely.union_all(bf), core).area / core.area) if bf else 0.0
    if L is None or not len(L): return out
    P, T = G.truth_samples(g); FI, LI = G.out_geometry(F.iloc[:0], L, box(0, 0, 1, 1)); vis = np.ones(len(P), bool)
    tol_only = LI.near(P, G.TOL); dir_runs = G.runs_ok(LI.match(P, T), vis)
    on = L[L.intersects(band.buffer(1.0))]; parts = [shapely.intersection(x, band.buffer(1.0)) for x in on.geometry]; parts = [p for p in parts if p.length >= 3]
    W_ = shapely.union_all([p.buffer(r) for p in parts]) if parts else None
    lids = sorted(set(on["logical_id"])); grp = L[L["logical_id"].isin(lids)]
    out.update({"centreline_cover_tol_only": float(tol_only.mean()), "centreline_cover_dir_runs": float(dir_runs.mean()),
                "gap_runs_px": runs(np.where(dir_runs, "ok", "gap"), "gap", 1), "logical_ids": lids,
                "widened_core_cover": float(shapely.intersection(W_, core).area / core.area) if W_ is not None else 0.0,
                "widened_or_band_faces_core_cover": float(shapely.intersection(shapely.union_all([W_] + bf) if W_ is not None else shapely.union_all(bf), core).area / core.area) if (W_ is not None or bf) else 0.0,
                "widened_area_outside_band_px": float(shapely.difference(W_, band).area) if W_ is not None else 0.0,
                "group_length_outside_band_px": float(sum(shapely.difference(x, band.buffer(1.5)).length for x in grp.geometry)),
                "group_length_total_px": float(sum(x.length for x in grp.geometry))})
    return out


def summarise(tiles):
    S_ = {}
    for m in METHODS + ["Oracle_class_tol0"]:
        rows = [t[m] for t in tiles.values() if m in t]
        if not rows: continue
        ink = collections.defaultdict(lambda: collections.Counter()); fill = collections.Counter(); band = collections.Counter(); ops = collections.Counter(); fo = collections.Counter()
        for r in rows:
            for v in r["ink"].values(): ink[v["kind"]].update({k: v[k] for k in G.INK_K + ["n"]}); ink[v["kind"]]["redraw_ops"] += len(v["redraw_runs"]); ink[v["kind"]]["adjust_ops"] += len(v["adjust_runs"]); ink[v["kind"]]["outline_lines"] += int(v["outline_px"] > 0)
            for v in r["fill"].values(): fill.update({k: v[k] for k in G.EDGE_K + ["n"]}); fill["redraw_ops"] += len(v["redraw_runs"]); fill["adjust_ops"] += len(v["adjust_runs"]); fill["split_along_line_ops"] += len(v["line_only_runs"])
            for v in r["band"].values(): band.update({k: v[k] for k in G.BAND_K + ["n"]}); band["redraw_ops"] += len(v["redraw_runs"]); band["adjust_ops"] += len(v["adjust_runs"]); band["line_to_face_ops"] += int(v["has_line_convert_run"])
            ops.update({k: v for k, v in r["line_ops"].items() if isinstance(v, (int, float))}); ops["spurious_face_boundary_px"] += r["spurious_face_boundary_px"]; ops["face_boundary_px"] += r["face_boundary_px"]
            ops["faces"] += r["faces"]; ops["lines"] += r["lines"]
            if r["face_ops"]: fo.update(r["face_ops"])
        def g1(c, keys_ok, keys_conv):
            n = max(c["n"], 1); return {"n": int(c["n"]), "G1a_present": 1 - c["missing"] / n, "G1b_reusable": sum(c[k] for k in keys_ok) / n,
                                        "G1c_convertible": sum(c[k] for k in keys_conv) / n, "redraw_px": int(c["missing"]), "adjust_px": int(sum(c[k] for k in ("needs_fix", "face_needs_fix") if k in c)),
                                        "convert_px": int(sum(c[k] for k in keys_conv))}
        res = {"ink_by_kind": {k: {**g1(c, ["line_ok"], ["face_outline"]), "redraw_ops": c["redraw_ops"], "adjust_ops": c["adjust_ops"], "outline_lines": c["outline_lines"]} for k, c in sorted(ink.items())}}
        allink = sum(ink.values(), collections.Counter()); res["ink_all"] = {**g1(allink, ["line_ok"], ["face_outline"]), "redraw_ops": allink["redraw_ops"], "adjust_ops": allink["adjust_ops"], "outline_lines": allink["outline_lines"]}
        if fill["n"]: res["fill_boundary"] = {**g1(fill, ["face_ok"], ["line_only"]), "redraw_ops": fill["redraw_ops"], "adjust_ops": fill["adjust_ops"], "split_along_line_ops": fill["split_along_line_ops"]}
        if band["n"]: res["band"] = {**g1(band, ["face_ok"], ["line_convert"]), "redraw_ops": band["redraw_ops"], "adjust_ops": band["adjust_ops"], "line_to_face_ops": band["line_to_face_ops"]}
        res["line_ops"] = dict(ops); res["face_ops"] = dict(fo) if fo else None
        red = sum(x.get("redraw_px", 0) + x.get("adjust_px", 0) for x in [res["ink_all"], res.get("fill_boundary", {}), res.get("band", {})])
        conv = res["ink_all"]["convert_px"]; ln = res["line_ops"]
        cost = (ln.get("recolour", 0) + ln.get("rewidth", 0) + ln.get("delete_false", 0) + ln.get("split_cross_line", 0)
                + res.get("fill_boundary", {}).get("split_along_line_ops", 0) + 4 * res.get("band", {}).get("line_to_face_ops", 0)
                + (fo.get("recolour_safe_batch_lower_bound", 0) + fo.get("merge", 0) + fo.get("split", 0) if fo else 0) + (red + conv) / 10)
        res["proxy_cost"] = {"value": float(cost), "note": "illustrative proxy, not user time (sv_g3_plan.json G3.proxy_cost)"}
        S_[m] = res
    return S_


def main(json_dir, smoke_dir=None):
    jd = Path(json_dir); jd.mkdir(parents=True, exist_ok=True); res = {"plan": "sv_g3_plan.json"}
    if smoke_dir:
        gd = Path(smoke_dir); seeds, sseeds = [1201], [1301]
    else:
        gd = RS / "v3_linefaces/gpkg"; seeds, sseeds = [7001, 7002, 7003, 7004, 7005], [7101, 7102, 7103, 7104, 7105]
        files = sorted(gd.glob("synth_*.gpkg")) + sorted(gd.glob("scene_*.gpkg"))
        res["sha_checked_synthetic"] = check_sha(files, HERE / "lf/linefaces_test_artifacts_sha256.txt", RS / "v3_linefaces")
        u2f = [RS / f"v3_u2_real/gpkg/u2_{m}.gpkg" for m in METHODS]
        res["sha_checked_u2"] = check_sha(u2f, HERE / "u2real/u2_artifacts_sha256.txt", RS / "v3_u2_real")
        if sha(RS / "oracle_u2_300_v2/O1_class_tol0.gpkg") != "c499d548dc492d932fecade8b57a734db339e5810a8763d6148de434c671428c": raise SystemExit("Oracle SHA mismatch")
    syn, sce = {}, {}
    for s in seeds:
        img, inks, fills, bands_, lab = synth_truth(s)
        syn[str(s)] = {m: score_tile(img, inks, fills, bands_, None, lab, gd / f"synth_{s}_{m}.gpkg", lambda x: x["kind"]) for m in METHODS}
    for s in sseeds:
        for k in SCENE_KINDS:
            img, inks, fills, bands_, _ = scene_truth(s, k)
            sce[f"{s}_{k}"] = {m: score_tile(img, inks, fills, bands_, None, None, gd / f"scene_{s}_{k}_{m}.gpkg", lambda x: x["kind"]) for m in METHODS}
    res["synthetic_tiles"] = syn; res["scenes"] = sce; res["summary_synthetic"] = summarise(syn); res["summary_scenes"] = summarise(sce)
    if not smoke_dir:
        img, inks, fills, bands_, _ = u2_truth(); u2 = {}
        for m in METHODS: u2[m] = score_tile(img, inks, fills, bands_, None, None, RS / f"v3_u2_real/gpkg/u2_{m}.gpkg", lambda x: x["kind"])
        u2["Oracle_class_tol0"] = score_tile(img, inks, fills, bands_, None, None, RS / "oracle_u2_300_v2/O1_class_tol0.gpkg", lambda x: x["kind"])
        res["u2"] = u2; res["summary_u2"] = summarise({"u2": u2})
        res["u2_band_repair"] = {b["id"]: {m: band_repair(img, b, RS / f"v3_u2_real/gpkg/u2_{m}.gpkg") for m in ("B0", "B2c")} for b in bands_}
    json.dump(res, open(jd / ("g3_smoke.json" if smoke_dir else "g3_result.json"), "w"), indent=1, default=float)
    for part in ("summary_synthetic", "summary_scenes", "summary_u2"):
        if part not in res: continue
        print("==", part)
        for m, x in res[part].items():
            print(" ", m.ljust(18), "ink G1a/b/c", round(x["ink_all"]["G1a_present"], 2), round(x["ink_all"]["G1b_reusable"], 2), round(x["ink_all"]["G1c_convertible"], 2),
                  "| fill", None if "fill_boundary" not in x else (round(x["fill_boundary"]["G1a_present"], 2), round(x["fill_boundary"]["G1b_reusable"], 2), round(x["fill_boundary"]["G1c_convertible"], 2)),
                  "| band", None if "band" not in x else (round(x["band"]["G1a_present"], 2), round(x["band"]["G1b_reusable"], 2), round(x["band"]["G1c_convertible"], 2)),
                  "| cost", round(x["proxy_cost"]["value"], 1))


if __name__ == "__main__":
    a = sys.argv[1:]; main(a[0], a[a.index("--smoke") + 1] if "--smoke" in a else None)
