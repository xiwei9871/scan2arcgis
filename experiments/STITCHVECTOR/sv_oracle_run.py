"""Oracle line/face POC run. Rules: sv_oracle_prereg.json; oracle: oracle/u2_300_oracle.json (both pushed before metrics).
Usage: sv_oracle_run.py <out_dir> [--preview]   (.venv-sv). --preview only renders the oracle traces for visual checking."""
import json, sys, time, csv
from pathlib import Path
import numpy as np
import shapely, pyogrio, geopandas as gpd
from shapely.geometry import box, LineString
from PIL import Image
import sv_common as C
import sv_d71 as D
import sv_oracle as O
import sv_oracle_eval as E

HERE = Path(__file__).resolve().parent
PRE = json.load(open(HERE / "sv_oracle_prereg.json")); ORA = json.load(open(HERE / "oracle/u2_300_oracle.json"))


def up(a, k=3): return np.kron(a, np.ones((k, k, 1), np.uint8))


def preview(a, lines, prot, out):
    v = a.copy()
    for f in lines:
        for x, y in f["raw"]: v[int(y), int(x)] = (0, 90, 255)
    v[prot] = (v[prot] * 0.5 + np.array([0, 255, 0]) * 0.5).astype(np.uint8)
    Image.fromarray(up(v[:, :100], 6)).save(out / "oracle_preview_x6.png")


def complexity(fc, lines):
    fv = int(sum(len(l.coords) for l in fc["arcs"])); lv = int(sum(len(f["geom"].coords) for f in lines))
    return {"faces": len(fc["polys"]), "arcs": len(fc["arcs"]), "face_arc_vertices": fv, "line_features": len(lines),
            "logical_lines": len({f["group"] for f in lines}), "line_vertices": lv, "objects_total": len(fc["polys"]) + len(lines),
            "vertices_total": fv + lv}


def fragmentation(fc, X, lut, shape):
    """For the largest connected region of each major colour class (in X): faces of that class inside it."""
    out = {}
    for c in np.unique(lut[X]):
        l, n = E.class_regions(X, lut, c)
        if n == 0: continue
        sz = np.bincount(l.ravel())[1:]; r = l == 1 + int(np.argmax(sz))
        if r.sum() < 2000: continue
        nf, _ = E.faces_in_region(fc, r, lut, c, shape); out[str(int(c))] = {"region_px": int(r.sum()), "faces_of_class_inside": nf}
    return out


def fidelity(a, q, rgb, masks):
    d = E.de(a, rgb); dq = E.de(q, rgb)
    res = {"vs_original": {"dE50": float(np.percentile(d, 50)), "dE90": float(np.percentile(d, 90)), "exact": float((a == rgb).all(-1).mean())},
           "vs_quantized": {"dE90": float(np.percentile(dq, 90)), "exact": float((q == rgb).all(-1).mean())}}
    for k, m in masks.items():
        if m.any(): res[k] = {"px": int(m.sum()), "dE50_vs_original": float(np.percentile(d[m], 50)), "dE90_vs_original": float(np.percentile(d[m], 90)),
                              "exact_vs_quantized": float((q[m] == rgb[m]).all(-1).mean())}
    return res


def r1_clip(name, off, a, q, masks):
    """Same 300x300 window cut from the existing R1 1000x780 output (crop offset in R1 window = (y240, x350))."""
    f = C.ROOT / f"runs/stitchvector/r1/u2_rawRGB_{name}.gpkg"
    if not f.exists(): return {"available": False}
    t = time.time(); g = pyogrio.read_dataframe(f); oy, ox = PRE["B1"]["offset_in_r1_window_yx"]
    win = box(ox, oy, ox + 300, oy + 300); g = g[g.intersects(win)].copy()
    g["geometry"] = g.geometry.intersection(win).translate(-ox, -oy)
    g = g[~g.geometry.is_empty]; parts = g.explode(index_parts=False); parts = parts[parts.geom_type == "Polygon"]
    feats = [(p, int(k), int(z)) for p, k, z in zip(parts.geometry, parts["rgb_key"], parts["z"])]
    rgb = C.key_rgb(C.render(feats, 300, 300, fill=0)); s = time.time() - t
    return {"available": True, "file": str(f.relative_to(C.ROOT)), "objects": int(len(parts)), "vertices": int(C.n_vertices(parts.geometry)),
            "seconds_read_clip_render": round(s, 2), "fidelity": fidelity(a, q, rgb, masks)}, rgb


def write_gpkg(path, fc, X, pal, lut, obs, inf, lines, prot_geoms):
    if path.exists(): path.unlink()
    gf = gpd.GeoDataFrame({"label": fc["vals"].astype(int), "colour_class": lut[fc["vals"]].astype(int),
                           "rgb": ["#%02x%02x%02x" % tuple(pal[v]) for v in fc["vals"]], "observed_px": obs.astype(int), "inferred_px": inf.astype(int),
                           "source": np.where(obs == 0, "inferred", np.where(inf > 0, "observed+inferred", "observed"))}, geometry=fc["polys"])
    gf.to_file(path, layer="colour_faces", driver="GPKG", engine="pyogrio")
    if lines:
        gl = gpd.GeoDataFrame({"line_id": [f["id"] for f in lines], "logical_id": [f["group"] for f in lines], "kind": [f["kind"] for f in lines],
                               "width_px": [round(f["width"], 2) for f in lines], "rgb": ["#%02x%02x%02x" % tuple(f["rgb"]) for f in lines],
                               "source": "oracle"}, geometry=[f["geom"] for f in lines])
        gl.to_file(path, layer="visual_lines", driver="GPKG", engine="pyogrio")
    if prot_geoms:
        gpd.GeoDataFrame({"id": [q["id"] for q in ORA["protected"]]}, geometry=prot_geoms).to_file(path, layer="protected_narrow_faces", driver="GPKG", engine="pyogrio")


def readback(path, shape, pal, p):
    t = time.time(); f = pyogrio.read_dataframe(path, layer="colour_faces")
    import rasterio.features as RF
    R = RF.rasterize([(g, int(v)) for g, v in zip(f.geometry, f["label"])], out_shape=shape, fill=-1, transform=O.ID, dtype="int64")
    rgb = pal[np.clip(R, 0, len(pal) - 1)]
    if "visual_lines" in [l[0] for l in pyogrio.list_layers(path)]:
        L = pyogrio.read_dataframe(path, layer="visual_lines")
        for g, w, c in zip(L.geometry, L["width_px"], L["rgb"]):
            m = O.rmask(g.buffer(max(w / 2, p["r_min"])), shape); rgb[m] = [int(c[i:i + 2], 16) for i in (1, 3, 5)]
    return rgb, int((R < 0).sum()), round(time.time() - t, 2)


def main(out_dir, prev=False):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True); p = dict(O.P); p.update(PRE["params"])
    a, off = C.centre_crop(C.load("u2"), 300, 300); lab, pal = C.quantize(a, 32); q = pal[lab]; shape = lab.shape
    t = time.time(); lines, con = O.build_lines(a, ORA, p, p["eps_geom"]); t_lines = time.time() - t
    prot = O.protect_mask(ORA, shape)
    if prev: preview(a, lines, prot, out); return
    core, rem = O.footprints(lines, shape, p, prot)
    K, lut, cent = D.colour_classes(lab, pal, p["merge_dE"]); kpal = O.class_palette(lab, lut, pal)
    res = {"prereg": "sv_oracle_prereg.json", "oracle": "oracle/u2_300_oracle.json", "crop_offset_yx": list(off), "params": p,
           "oracle_lines": len(lines), "oracle_logical_lines": len({f["group"] for f in lines}), "line_build_seconds": round(t_lines, 2)}
    masks = {"line_core_px": core > 0, "line_removed_px": rem, "protected_px": prot, "rest_px": ~rem & ~prot}
    runs = {}
    for labels, tol in PRE["configs"]:
        tag = f"{labels}_tol{tol}"; X, P_ = (lab, pal) if labels == "32" else (lut[lab], kpal)
        lutX = lut if labels == "32" else np.arange(len(kpal))
        t = time.time(); fb = O.faces(X, tol); sb = time.time() - t
        F = D.fill(X, rem); t = time.time(); fo = O.faces(F, tol); so = time.time() - t
        obs, inf = O.provenance(F, rem, fo)
        rgbO, _ = E.render_lines(P_[F], lines, shape, p)
        r = {"B0": {**{"complexity": complexity(fb, [])}, "seconds": round(sb, 2), "topology": fb["topology"], "mismatch_px": fb["mismatch_px"],
                    "fragmentation": fragmentation(fb, X, lutX, shape), "fidelity": fidelity(a, q, P_[X], masks)},
             "O1": {"complexity": complexity(fo, lines), "seconds": round(so + t_lines, 2), "topology": fo["topology"], "mismatch_px_face_layer": fo["mismatch_px"],
                    "fragmentation": fragmentation(fo, F, lutX, shape), "fidelity": fidelity(a, q, rgbO, masks),
                    "face_layer_only_fidelity": fidelity(a, q, P_[F], masks),
                    "faces_inferred_only": int((obs == 0).sum()), "faces_with_inferred_px": int((inf > 0).sum()),
                    "protected_px_label_unchanged": float((F[prot] == X[prot]).mean()) if prot.any() else None,
                    "protected_faces_touching": int(len(np.unique(E.id_raster(fo["polys"], shape)[prot])))}}
        gp = out / f"O1_{tag}.gpkg"; t = time.time(); write_gpkg(gp, fo, F, P_, lutX, obs, inf, lines, [LineString(q_["axis"]).buffer(q_["radius"]) for q_ in ORA["protected"]])
        r["O1"]["gpkg_bytes"] = gp.stat().st_size; r["O1"]["gpkg_write_seconds"] = round(time.time() - t, 2)
        rb, holes, srb = readback(gp, shape, P_, p); r["O1"]["readback"] = {"seconds": srb, "uncovered_px": holes, "px_differs_from_memory": int((rb != rgbO).any(-1).sum())}
        gb = out / f"B0_{tag}.gpkg"; write_gpkg(gb, fb, X, P_, lutX, np.ones(len(fb["polys"])), np.zeros(len(fb["polys"])), [], [])
        r["B0"]["gpkg_bytes"] = gb.stat().st_size
        g0 = PRE["edit_tasks"]["C1_group"]; _, c1 = E.c1_move_line(X, a, P_, lines, g0, PRE["edit_tasks"]["C1_dy"], tol, fb); r["C1"] = c1
        pair = PRE["edit_tasks"]["C3_classes_rgb"]; cls = [int(lut[O.nearest_pal(c, pal)]) for c in pair]
        r["C3_B0"] = E.c3_shared_boundary(fb, X, lutX, cls, PRE["edit_tasks"]["C3_shift"])
        r["C3_O1"] = E.c3_shared_boundary(fo, F, lutX, cls, PRE["edit_tasks"]["C3_shift"])
        c2 = str(int(lut[O.nearest_pal(PRE["edit_tasks"]["C2_class_rgb"], pal)]))
        r["C2"] = {"B0": r["B0"]["fragmentation"].get(c2), "O1": r["O1"]["fragmentation"].get(c2)}
        runs[tag] = r
        if tag == PRE["primary"]:
            Image.fromarray(up(P_[F])).save(out / "face_layer_x3.png"); Image.fromarray(up(rgbO)).save(out / "composite_O1_x3.png")
            Image.fromarray(np.clip(E.de(a, rgbO) * 6, 0, 255).astype(np.uint8)).resize((900, 900), 0).save(out / "error_O1_dE_x6scale.png")
    res["runs"] = runs
    res["lines"] = [{"id": f["id"], "group": f["group"], "kind": f["kind"], **E.line_geometry_stats(f, con, shape, p),
                     "presence_O1": E.line_presence(a, E.render_lines(pal[D.fill(lab, rem)], lines, shape, p)[0], f["raw"], p),
                     "presence_B0": E.line_presence(a, q, f["raw"], p)} for f in lines]
    B1 = {}
    for name in PRE["B1"]["configs"]:
        r1 = r1_clip(name, off, a, q, masks)
        if isinstance(r1, tuple):
            B1[name], rgb1 = r1
            B1[name]["line_presence"] = [E.line_presence(a, rgb1, f["raw"], p) for f in lines]
        else: B1[name] = r1
    res["B1"] = B1
    lv = np.full(a.shape, 255, np.uint8); lv, _ = E.render_lines(lv, lines, shape, p)
    Image.fromarray(up(a)).save(out / "original_x3.png"); Image.fromarray(up(lv)).save(out / "line_layer_x3.png")
    Image.fromarray(np.hstack([up(a[:, :100], 6), up(pal[D.fill(lab, rem)][:, :100], 6), up(E.render_lines(pal[D.fill(lab, rem)], lines, shape, p)[0][:, :100], 6)])).save(out / "compare_strip_x6.png")
    json.dump(res, open(out / "oracle_result.json", "w"), indent=1, default=float)
    with open(out / "complexity.csv", "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["labels", "method", "faces", "line_features", "logical_lines", "objects_total", "vertices_total", "gpkg_bytes"])
        for tag, r in runs.items():
            for m in ("B0", "O1"):
                c = r[m]["complexity"]; w.writerow([tag, m, c["faces"], c["line_features"], c["logical_lines"], c["objects_total"], c["vertices_total"], r[m]["gpkg_bytes"]])
        for name, b in B1.items():
            if b.get("available"): w.writerow(["raw RGB", f"B1_{name}", b["objects"], 0, 0, b["objects"], b["vertices"], ""])
    print(json.dumps({tag: {m: r[m]["complexity"] for m in ("B0", "O1")} for tag, r in runs.items()}, indent=0))


if __name__ == "__main__":
    main(sys.argv[1], "--preview" in sys.argv)
