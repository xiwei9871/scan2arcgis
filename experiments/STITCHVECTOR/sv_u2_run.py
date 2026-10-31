"""u2 real-sample line+face replication check (plan: sv_u2_plan.json). Descriptive; no new algorithm.
Usage: sv_u2_run.py <json_dir> <out_dir> [--smoke]   (.venv-sv). --smoke runs the same code on a synthetic tile."""
import json, sys, csv, collections
from pathlib import Path
import numpy as np, shapely, pyogrio, geopandas as gpd
from shapely.geometry import LineString, MultiLineString
from PIL import Image, ImageDraw
import sv_common as Cm, sv_synth as S, sv_oracle as O, sv_oracle_v2 as O2, sv_oracle_eval as E, sv_oracle_run as ORUN
import sv_lf as LF, sv_lf_eval as LFE, sv_v3_eval as V3E

ROOT = Path(__file__).resolve().parents[2]; RUNS = ROOT / "runs/stitchvector/oracle_u2_300_v2"
MAPC = 94; P = LF.P
KIND = {"red_line_in_green": "red_line", "red_line_green_edge": "red_line", "red_fault": "red_fault", "red_tooth": "red_tooth",
        "red_curve": "red_curve", "pale_orange_line": "pale_orange"}


def set_source(path, value):
    faces = pyogrio.read_dataframe(path, layer="colour_faces"); layers = [l[0] for l in pyogrio.list_layers(path)]
    L = pyogrio.read_dataframe(path, layer="visual_lines") if "visual_lines" in layers else None
    path.unlink(); faces.to_file(path, layer="colour_faces", driver="GPKG", engine="pyogrio")
    if L is not None: L.assign(source=value).to_file(path, layer="visual_lines", driver="GPKG", engine="pyogrio")


def independence(a, gdir):
    """B2c built normally vs with Oracle inputs removed (empty ORA, protect_mask raising): must be identical."""
    r1 = LF.build(a, "B2c", gdir / "_indep_normal.gpkg"); saved = (O2.ORA, O.protect_mask)
    def boom(*_a, **_k): raise RuntimeError("protect_mask called by the automatic path")
    O2.ORA = {"lines": [], "protected": []}; O.protect_mask = boom
    try: r2 = LF.build(a, "B2c", gdir / "_indep_no_oracle.gpkg")
    finally: O2.ORA, O.protect_mask = saved
    same_geom = len(r1["lines"]) == len(r2["lines"]) and all(shapely.equals_exact(x["geom"], y["geom"], 1e-9) for x, y in zip(r1["lines"], r2["lines"]))
    for f in ("_indep_normal.gpkg", "_indep_no_oracle.gpkg"): (gdir / f).unlink()
    return {"readback_identical": bool((r1["rgb"] == r2["rgb"]).all()), "line_geometry_identical": bool(same_geom)}


def fid(a, rgb, regs):
    d = E.de(a, rgb)
    return {k: {"px": int(m.sum()), "dE50": float(np.percentile(d[m], 50)), "dE90": float(np.percentile(d[m], 90)), "share_dE_le_10": float((d[m] <= 10).mean())}
            for k, m in regs.items() if m.any()}


def presence(a, rgb, olines):
    per = {f["id"]: {"kind": KIND.get(f["kind"], f["kind"]), **O2.presence(a, rgb, f["raw"], P)} for f in olines}
    by = collections.defaultdict(list)
    for v in per.values(): by[v["kind"]].append(v)
    return per, {k: {"present_share_mean": float(np.mean([x["present_share"] for x in v])), "breaks": int(sum(x["breaks_ge2"] for x in v))} for k, v in by.items()}


def bands(a, rgb, gpkg, X_pal, lab, pal, shape):
    layers = [l[0] for l in pyogrio.list_layers(gpkg)]; foot = np.zeros(shape, bool)
    if "visual_lines" in layers:
        L = pyogrio.read_dataframe(gpkg, layer="visual_lines")
        for g, w in zip(L.geometry, L["width_px"]): foot |= O.rmask(g.buffer(max(w / 2, P["r_min"])), shape)
    out = {}
    for q in O2.ORA["protected"]:
        g = LineString(q["axis"]); core = O.rmask(g.buffer(max(q["radius"] - 1, 0.75)), shape); col = np.median(a[core], 0).astype(np.uint8)
        ok = E.de(np.broadcast_to(col, rgb[core].shape)[None], rgb[core][None])[0] <= 15
        pts = shapely.get_coordinates(shapely.line_interpolate_point(g, np.linspace(0, g.length, int(g.length) + 1)))
        x = np.clip(pts[:, 0].astype(int), 0, shape[1] - 1); y = np.clip(pts[:, 1].astype(int), 0, shape[0] - 1)
        out[q["id"]] = {"core_px": int(core.sum()), "band_rgb": col.tolist(), "colour_preserved": float(ok.mean()), "axis_under_line": float(foot[y, x].mean()),
                        "nearest_32_palette_dE": float(E.de(col[None, None], pal[None])[0].min()), "nearest_face_class_dE": float(E.de(col[None, None], X_pal[None])[0].min())}
    return out


def edit_info(gpkg, olines, res):
    layers = [l[0] for l in pyogrio.list_layers(gpkg)]; info = {"layers": layers}
    if "visual_lines" not in layers: return info
    L = pyogrio.read_dataframe(gpkg, layer="visual_lines")
    info.update({"line_features": len(L), "logical_groups": int(L["logical_id"].nunique()), "logical_id_null": int(L["logical_id"].isna().sum()),
                 "source_values": sorted(L["source"].unique().tolist()), "line_vertices": int(sum(shapely.get_num_coordinates(g) for g in L.geometry))})
    groups = [{"geom": MultiLineString([q for g in L.geometry[L["logical_id"] == lid] for q in shapely.get_parts(g)])} for lid in L["logical_id"].unique()]
    truth = {"lines": [{"id": f["id"], "axis": f["raw"]} for f in olines if f["kind"] != "red_tooth" and len(f["raw"]) >= 2]}
    sc = V3E.score(groups, truth); info["cross_line_groups_vs_oracle_traces"] = sc["mixed_objects"]
    info["data_edit"] = LFE.edit_checks(res, gpkg, res["X"].shape) if res is not None else None
    return info


def up(m, k): return np.kron(m, np.ones((k, k, 1), np.uint8))


def lines_over(a, lines, k):
    im = Image.fromarray(up(a[:, :MAPC], k)); d = ImageDraw.Draw(im)
    for f in lines:
        for q in shapely.get_parts(f["geom"]): d.line([(x * k, y * k) for x, y in q.coords], fill=(0, 90, 255), width=max(1, k // 2))
    return im


def save_images(idir, a, rgbs, lines, zooms):
    idir.mkdir(parents=True, exist_ok=True)
    Image.fromarray(a).save(idir / "original_1x.png"); Image.fromarray(up(a[:, :MAPC], 4)).save(idir / "original_map_x4.png")
    for k, rgb in rgbs.items():
        Image.fromarray(rgb).save(idir / f"{k}_1x.png"); Image.fromarray(up(rgb[:, :MAPC], 4)).save(idir / f"{k}_map_x4.png")
    err = np.clip(E.de(a, rgbs["B2c"]) * 6, 0, 255).astype(np.uint8); Image.fromarray(up(np.stack([err] * 3, -1)[:, :MAPC], 4)).save(idir / "B2c_error_dEx6_map_x4.png")
    diff = (rgbs["B0"] != rgbs["B2c"]).any(-1); dv = (a * 0.35 + 255 * 0.65).astype(np.uint8); dv[diff] = (230, 0, 0)
    Image.fromarray(up(dv[:, :MAPC], 4)).save(idir / "B0_vs_B2c_diff_map_x4.png")
    for k in ("B0", "B2c"): lines_over(a, lines[k], 4).save(idir / f"{k}_lines_over_original_map_x4.png")
    cols = ["original"] + list(rgbs) + ["B2c_error"]
    for name, (x0, y0) in zooms.items():
        x0, y0 = int(np.clip(x0, 0, MAPC - 40)), int(np.clip(y0, 0, 300 - 40)); tiles = []
        for c in cols:
            src = a if c == "original" else (np.stack([err] * 3, -1) if c == "B2c_error" else rgbs[c])
            t = Image.fromarray(up(src[y0:y0 + 40, x0:x0 + 40], 6)); ImageDraw.Draw(t).text((2, 2), c, fill=(0, 0, 0)); tiles.append(np.asarray(t))
        Image.fromarray(np.hstack(tiles)).save(idir / f"zoom_{name}_x6.png")


def main(json_dir, out_dir, smoke=False):
    jd, od = Path(json_dir), Path(out_dir); gdir = od / "gpkg"; idir = od / "img"
    for d in (jd, gdir): d.mkdir(parents=True, exist_ok=True)
    if smoke: a = np.full((300, 300, 3), 255, np.uint8); a[22:278, 0:256] = S.generate(1201)[0]; off = None
    else: a, off = Cm.centre_crop(Cm.load("u2"), 300, 300)
    shape = a.shape[:2]; lab, pal = Cm.quantize(a, 32); X, kpal = LF.labels(a)
    olines, _ = O2.build(a, P); prot = O.protect_mask(O2.ORA, shape); regs = O2.regions(shape, olines, prot, MAPC)
    regs = {"full": regs["full"], "map": regs["map"], "map_line_nbhd": regs["line_nbhd"], "map_rest": regs["map_rest"], "bands": regs["protected"]}
    res = {"plan": "sv_u2_plan.json", "smoke": smoke, "crop_offset_yx": list(off) if off else None, "regions_px": {k: int(m.sum()) for k, m in regs.items()},
           "independence": independence(a, gdir), "methods": {}}
    rgbs, lines, built = {}, {}, {}
    for m in ("F0", "B0", "B2c"):
        gp = gdir / f"u2_{m}.gpkg"; r = LF.build(a, m, gp); before = r["rgb"]
        if m != "F0": set_source(gp, f"auto_{m}")
        rgb, holes, _, _ = O2.render_gpkg(gp, shape, kpal, P, np.zeros(shape, bool)); built[m] = r; rgbs[m] = rgb; lines[m] = r["lines"]
        res["methods"][m] = {"gpkg": gp.name, "readback_unchanged_after_source_fix": bool((rgb == before).all()), "faces": len(r["faces"]["polys"]),
                             "face_vertices": int(sum(len(l.coords) for l in r["faces"]["arcs"])), "topology": r["faces"]["topology"], "uncovered_px": holes,
                             "memory_vs_gpkg_px": r["memory_vs_gpkg_px"], "faces_inferred_only": int((r["obs"] == 0).sum()), "inferred_px_in_map": int((r["removed"] & regs["map"]).sum())}
    for name, f, pal_ in (("Oracle_class_tol0", "O1_class_tol0.gpkg", kpal), ("Oracle_32_tol0", "O1_32_tol0.gpkg", pal)):
        rgb, holes, _, _ = O2.render_gpkg(RUNS / f, shape, pal_, P, prot); rgbs[name] = rgb
        fl = pyogrio.read_dataframe(RUNS / f, layer="colour_faces")
        res["methods"][name] = {"gpkg": str((RUNS / f).relative_to(ROOT)), "faces": len(fl), "uncovered_px": holes, "reference_only": True}
    fb, _, _, _ = O2.render_gpkg(RUNS / "B0_class_tol0.gpkg", shape, kpal, P, np.zeros(shape, bool))
    res["independence"]["oracle_faces_only_class_tol0_equals_auto_F0"] = bool((fb == rgbs["F0"]).all())
    vt = ORUN.r1_clip("spline_s1", off, a, a, {}) if not smoke else None
    if isinstance(vt, tuple): rgbs["VTracer_spline_s1"] = vt[1]; res["methods"]["VTracer_spline_s1"] = {"objects": vt[0]["objects"], "vertices": vt[0]["vertices"], "reference_only": True}
    T = shapely.union_all([LineString(f["raw"]) for f in olines if len(f["raw"]) >= 2]).buffer(3.0); mapbox = shapely.box(0, 0, MAPC, 300)
    for m, rgb in rgbs.items():
        x = res["methods"][m]; x["fidelity"] = fid(a, rgb, regs); x["line_presence"], x["line_presence_by_kind"] = presence(a, rgb, olines)
        gp = gdir / f"u2_{m}.gpkg" if m in ("F0", "B0", "B2c") else (RUNS / x["gpkg"].split("/")[-1] if m.startswith("Oracle") else None)
        if gp is not None: x["bands"] = bands(a, rgb, gp, kpal, lab, pal, shape)
        if m in ("B0", "B2c"):
            far = [shapely.difference(f["geom"], T) for f in lines[m]]
            x["auto_line_length_far_from_oracle_traces"] = {"in_map": float(sum(shapely.intersection(g, mapbox).length for g in far)),
                                                            "outside_map": float(sum(shapely.difference(g, mapbox).length for g in far)), "total_line_length": float(sum(f["geom"].length for f in lines[m]))}
            x["edit"] = edit_info(gp, olines, built[m]); x["vertices_total"] = x["face_vertices"] + x["edit"]["line_vertices"]
        if m.startswith("Oracle"): x["edit"] = edit_info(gp, olines, None)
    json.dump(res, open(jd / ("u2_smoke.json" if smoke else "u2_result.json"), "w"), indent=1, default=float)
    with open(jd / ("u2_smoke.csv" if smoke else "u2_summary.csv"), "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["method", "region", "dE50", "dE90", "share_dE_le_10"])
        for m, x in res["methods"].items():
            for k, v in x["fidelity"].items(): w.writerow([m, k, round(v["dE50"], 2), round(v["dE90"], 2), round(v["share_dE_le_10"], 4)])
    zooms = {"PN1_green_lens": (32, 210), "PN2_green_grey_strip": (12, 130), "G1_pale_line": (40, 40), "G2_pale_line": (40, 136), "F1_fault_teeth": (40, 55),
             "text_Ar2E": (12, 196), "LOOP": (35, 180)}
    save_images(idir, a, {k: v for k, v in rgbs.items() if k != "Oracle_32_tol0"}, lines, zooms)
    print(json.dumps({"independence": res["independence"], **{m: {k: x["fidelity"][k]["dE90"] for k in x["fidelity"]} for m, x in res["methods"].items()}}, indent=0, default=float))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], "--smoke" in sys.argv)
