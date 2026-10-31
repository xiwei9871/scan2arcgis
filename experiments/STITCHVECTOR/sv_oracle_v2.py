"""Oracle v2 (P0 amendment, rules: sv_oracle_v2_prereg.json). Same oracle file, sample and face method as v1.
Changes, each from the P0 diagnosis (docs/research/stitchvector/oracle_p0_auto_line_synth.md):
  A protected pixels are never painted by lines or symbols in the composite (P > L);
  B line colour = median original colour on the dense trace; closed traces (teeth) become small ink polygons
    (layer small_symbols) instead of buffered centrelines;
  C width stored at full precision; every fidelity number is computed on the composite re-rendered from the GPKG;
  D metrics for full crop, map area (x < map_cols), line neighbourhood (<= 3 px of any trace) and map rest;
  presence is sampled every 1 px along the trace (v1 used the stored points: 2 samples for fixed straight traces).
v1 code and results are unchanged."""
import json, sys, time, csv
from pathlib import Path
import numpy as np, shapely, pyogrio, geopandas as gpd
from shapely.geometry import LineString, shape as shp
import rasterio.features as RF
import sv_common as C, sv_d71 as D, sv_oracle as O, sv_oracle_eval as E

HERE = Path(__file__).resolve().parent
PRE = json.load(open(HERE / "sv_oracle_v2_prereg.json")); ORA = json.load(open(HERE / "oracle/u2_300_oracle.json"))


def dense(raw):
    g = LineString(raw); n = max(int(np.ceil(g.length)), 1)
    return [tuple(c) for c in shapely.get_coordinates(shapely.line_interpolate_point(g, np.linspace(0, g.length, n + 1)))]


def trace_px(raw, shape):
    H, W = shape; d = np.array(dense(raw)); x = np.clip(d[:, 0].astype(int), 0, W - 1); y = np.clip(d[:, 1].astype(int), 0, H - 1)
    return y, x


def symbol_polygon(f, shape, p):
    ink = f["ink"] & O.rmask(LineString(f["raw"]).buffer(p["symbol_r"]), shape)
    polys = [shp(g) for g, v in RF.shapes(ink.astype(np.uint8), mask=ink, connectivity=4, transform=O.ID) if v == 1]
    return shapely.union_all(polys).simplify(p["eps_geom"]) if polys else None


def build(a, p):
    lines, con = O.build_lines(a, ORA, p, p["eps_geom"]); shape = a.shape[:2]; syms = []
    for f in lines:
        y, x = trace_px(f["raw"], shape); f["rgb"] = np.median(a[y, x], 0).astype(np.uint8)
        if f.get("kind") == "red_tooth" or any(o["id"] == f["id"] and o.get("closed") for o in ORA["lines"]):
            g = symbol_polygon(f, shape, p)
            if g is not None and not g.is_empty:
                m = O.rmask(g, shape); f["rgb"] = np.median(a[m], 0).astype(np.uint8) if m.any() else f["rgb"]; f["poly"] = g
    return lines, con


def footprint(f, shape, p, extra=0.0):
    g = f.get("poly")
    return O.rmask(g.buffer(extra) if extra else g, shape) if g is not None else O.rmask(f["geom"].buffer(max(f["width"] / 2, p["r_min"]) + extra), shape)


def write(path, fc, P_, lutX, obs, inf, lines, prot_geoms):
    if path.exists(): path.unlink()
    gpd.GeoDataFrame({"label": fc["vals"].astype(int), "colour_class": lutX[fc["vals"]].astype(int),
                      "rgb": ["#%02x%02x%02x" % tuple(P_[v]) for v in fc["vals"]], "observed_px": obs.astype(int), "inferred_px": inf.astype(int),
                      "source": np.where(obs == 0, "inferred", np.where(inf > 0, "observed+inferred", "observed"))},
                     geometry=fc["polys"]).to_file(path, layer="colour_faces", driver="GPKG", engine="pyogrio")
    L = [f for f in lines if "poly" not in f]; S = [f for f in lines if "poly" in f]
    for name, fs, geom in (("visual_lines", L, lambda f: f["geom"]), ("small_symbols", S, lambda f: f["poly"])):
        if fs:
            gpd.GeoDataFrame({"line_id": [f["id"] for f in fs], "logical_id": [f["group"] for f in fs], "kind": [f["kind"] for f in fs],
                              "width_px": [float(f["width"]) for f in fs], "rgb": ["#%02x%02x%02x" % tuple(f["rgb"]) for f in fs], "source": "oracle",
                              "draw_order": [i for i, _ in enumerate(fs)]}, geometry=[geom(f) for f in fs]).to_file(path, layer=name, driver="GPKG", engine="pyogrio")
    if prot_geoms:
        gpd.GeoDataFrame({"id": [q["id"] for q in ORA["protected"]]}, geometry=prot_geoms).to_file(path, layer="protected_narrow_faces", driver="GPKG", engine="pyogrio")


def render_gpkg(path, shape, P_, p, prot):
    t = time.time(); f = pyogrio.read_dataframe(path, layer="colour_faces")
    R = RF.rasterize([(g, int(v)) for g, v in zip(f.geometry, f["label"])], out_shape=shape, fill=-1, transform=O.ID, dtype="int64")
    rgb = P_[np.clip(R, 0, len(P_) - 1)]; layers = [l[0] for l in pyogrio.list_layers(path)]; nline = 0
    for name in ("visual_lines", "small_symbols"):
        if name not in layers: continue
        L = pyogrio.read_dataframe(path, layer=name).sort_values("draw_order")
        for g, w, c in zip(L.geometry, L["width_px"], L["rgb"]):
            m = O.rmask(g if g.geom_type in ("Polygon", "MultiPolygon") else g.buffer(max(w / 2, p["r_min"])), shape) & ~prot
            rgb[m] = [int(c[i:i + 2], 16) for i in (1, 3, 5)]; nline += 1
    return rgb, int((R < 0).sum()), round(time.time() - t, 2), R


def regions(shape, lines, prot, map_cols):
    H, W = shape; mp = np.zeros(shape, bool); mp[:, :map_cols] = True
    nb = np.zeros(shape, bool)
    for f in lines: nb |= O.rmask(LineString(f["raw"]).buffer(3.0), shape)
    return {"full": np.ones(shape, bool), "map": mp, "line_nbhd": nb & mp, "map_rest": mp & ~nb & ~prot, "protected": prot}


def fid(a, q, rgb, regs):
    d = E.de(a, rgb); dq = E.de(q, rgb); out = {}
    for k, m in regs.items():
        if m.any(): out[k] = {"px": int(m.sum()), "dE50": float(np.percentile(d[m], 50)), "dE90": float(np.percentile(d[m], 90)),
                              "exact_vs_original": float((a[m] == rgb[m]).all(-1).mean()), "exact_vs_quantized": float((q[m] == rgb[m]).all(-1).mean()),
                              "dE90_vs_quantized": float(np.percentile(dq[m], 90))}
    return out


def presence(a, rgb, raw, p):
    y, x = trace_px(raw, a.shape[:2]); ok = E.de(a[y, x][None], rgb[y, x][None])[0] <= p["frag_dE"]
    miss = np.r_[0, (~ok).astype(int), 0]; dd = np.diff(miss); runs = np.nonzero(dd == -1)[0] - np.nonzero(dd == 1)[0]
    return {"samples": int(len(ok)), "present_share": float(ok.mean()), "breaks_ge2": int((runs >= 2).sum())}


def main(out_dir):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True); p = dict(O.P); p.update(PRE["params"])
    a, off = C.centre_crop(C.load("u2"), 300, 300); lab, pal = C.quantize(a, 32); q = pal[lab]; shape = lab.shape
    lines, con = build(a, p); prot = O.protect_mask(ORA, shape)
    core = np.zeros(shape, bool); rem = np.zeros(shape, bool)
    for f in lines: core |= footprint(f, shape, p); rem |= footprint(f, shape, p, p["halo"])
    rem &= ~prot; regs = regions(shape, lines, prot, PRE["map_cols"])
    K, lut, _ = D.colour_classes(lab, pal, p["merge_dE"]); kpal = O.class_palette(lab, lut, pal)
    res = {"prereg": "sv_oracle_v2_prereg.json", "v1_result_kept": "oracle/u2_300_result/", "params": p, "regions_px": {k: int(m.sum()) for k, m in regs.items()},
           "lines": len([f for f in lines if "poly" not in f]), "small_symbols": len([f for f in lines if "poly" in f]), "logical": len({f["group"] for f in lines}), "runs": {}}
    pink = int(lut[O.nearest_pal([255, 222, 236], pal)]); green = int(lut[O.nearest_pal([211, 229, 161], pal)])
    for labels, tol in PRE["configs"]:
        tag = f"{labels}_tol{tol}"; X, P_ = (lab, pal) if labels == "32" else (lut[lab], kpal); lutX = lut if labels == "32" else np.arange(len(kpal))
        fb = O.faces(X, tol); F = D.fill(X, rem); fo = O.faces(F, tol); obs, inf = O.provenance(F, rem, fo)
        r = {}
        for m, fc, Xm, ls in (("B0", fb, X, []), ("O1", fo, F, lines)):
            gp = out / f"{m}_{tag}.gpkg"; ob, ib = (obs, inf) if m == "O1" else (np.ones(len(fc["polys"])), np.zeros(len(fc["polys"])))
            write(gp, fc, P_, lutX, ob, ib, ls, [LineString(z["axis"]).buffer(z["radius"]) for z in ORA["protected"]] if m == "O1" else [])
            rgb, holes, srb, R = render_gpkg(gp, shape, P_, p, prot)
            fv = int(sum(len(l.coords) for l in fc["arcs"])); lv = int(sum(shapely.get_num_coordinates(f.get("poly", f["geom"])) for f in ls))
            r[m] = {"faces": len(fc["polys"]), "line_features": len([f for f in ls if "poly" not in f]), "symbol_features": len([f for f in ls if "poly" in f]),
                    "logical_objects": len({f["group"] for f in ls}), "objects_total": len(fc["polys"]) + len(ls), "vertices_total": fv + lv,
                    "gpkg_bytes": gp.stat().st_size, "readback_seconds": srb, "uncovered_px": holes, "topology": fc["topology"],
                    "fidelity_from_gpkg": fid(a, q, rgb, regs), "protected_exact_vs_labels": float((rgb[prot] == P_[X][prot]).all(-1).mean()),
                    "pink_class_faces": int((lutX[fc["vals"]] == pink).sum()), "green_class_faces": int((lutX[fc["vals"]] == green).sum()),
                    "faces_le5px": int((shapely.area(np.asarray(fc["polys"], object)) <= 5).sum())}
            if m == "O1":
                r[m]["presence"] = {f["id"]: presence(a, rgb, f["raw"], p) for f in lines}
                r[m]["faces_inferred_only"] = int((obs == 0).sum()); r[m]["non_simple"] = [f["id"] for f in lines if not f.get("poly", f["geom"]).is_valid or ("poly" not in f and not f["geom"].is_simple)]
            else:
                r[m]["presence"] = {f["id"]: presence(a, rgb, f["raw"], p) for f in lines}
            if m == "O1" and tag == PRE["primary"]:
                from PIL import Image
                k = 6; Image.fromarray(np.hstack([np.kron(a[:, :94], np.ones((k, k, 1), np.uint8)), np.kron(rgb[:, :94], np.ones((k, k, 1), np.uint8))])).save(out / "v2_compare_map_x6.png")
                Image.fromarray(np.clip(E.de(a, rgb)[:, :94] * 6, 0, 255).astype(np.uint8)).resize((94 * 6, 300 * 6), 0).save(out / "v2_error_map_x6.png")
        g0 = PRE["edit_tasks"]["C1_group"]; _, c1 = E.c1_move_line(X, a, P_, lines, g0, PRE["edit_tasks"]["C1_dy"], tol, p, fb); r["C1"] = c1
        res["runs"][tag] = r
    res["line_meta"] = {f["id"]: {"kind": f["kind"], "group": f["group"], "repr": "small_symbol_polygon" if "poly" in f else "centreline",
                                 "width": float(f["width"]), "rgb": [int(v) for v in f["rgb"]],
                                 "vertices": int(shapely.get_num_coordinates(f.get("poly", f["geom"])))} for f in lines}
    json.dump(res, open(out / "oracle_v2_result.json", "w"), indent=1, default=float)
    with open(out / "oracle_v2_summary.csv", "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["config", "method", "faces", "lines", "symbols", "logical", "objects", "vertices", "map_dE90", "line_nbhd_dE90", "map_rest_dE90", "protected_exact", "presence_mean", "breaks"])
        for tag, r in res["runs"].items():
            for m in ("B0", "O1"):
                x = r[m]; fdk = x["fidelity_from_gpkg"]; pr = list(x["presence"].values())
                w.writerow([tag, m, x["faces"], x["line_features"], x["symbol_features"], x["logical_objects"], x["objects_total"], x["vertices_total"],
                            round(fdk["map"]["dE90"], 2), round(fdk["line_nbhd"]["dE90"], 2), round(fdk["map_rest"]["dE90"], 2), round(x["protected_exact_vs_labels"], 4),
                            round(float(np.mean([z["present_share"] for z in pr])), 3), sum(z["breaks_ge2"] for z in pr)])
    print(open(out / "oracle_v2_summary.csv").read())


if __name__ == "__main__":
    main(sys.argv[1])
