"""Evaluation for the line + face POC. Truth is read here only, never in sv_lf.build. All images are the GPKG readback."""
import numpy as np, shapely, pyogrio
from shapely.geometry import LineString, Polygon
import sv_oracle as O, sv_oracle_v2 as O2, sv_oracle_eval as E, sv_lf as LF

FRAG = 15.0


def mask_of(geoms, shape):
    m = np.zeros(shape, bool)
    for g in geoms: m |= O.rmask(g, shape)
    return m


def presence(a, rgb, axis):
    g = LineString(axis); pts = shapely.get_coordinates(shapely.line_interpolate_point(g, np.linspace(0, g.length, int(g.length) + 1)))
    x = np.clip(pts[:, 0].astype(int), 0, a.shape[1] - 1); y = np.clip(pts[:, 1].astype(int), 0, a.shape[0] - 1)
    return float((E.de(a[y, x][None], rgb[y, x][None])[0] <= FRAG).mean())


def fidelity(a, rgb, line_axes, shape):
    d = E.de(a, rgb); nb = mask_of([LineString(x).buffer(3.0) for x in line_axes], shape) if line_axes else np.zeros(shape, bool)
    out = {}
    for k, m in (("all", np.ones(shape, bool)), ("line_nbhd", nb), ("non_line", ~nb)):
        if m.any(): out[k] = {"dE50": float(np.percentile(d[m], 50)), "dE90": float(np.percentile(d[m], 90)), "share_dE_le_10": float((d[m] <= 10).mean())}
    return out


def bands(a, rgb, gpkg, band_list, shape):
    """core = band axis buffered to (width/2 - 1), at least 0.75 px. preserved = readback colour within 15 dE of the band's
    own colour (median of the original core). drawn_as_line = share of band axis samples covered by a visual_lines footprint."""
    layers = [l[0] for l in pyogrio.list_layers(gpkg)]
    if "visual_lines" in layers:
        L = pyogrio.read_dataframe(gpkg, layer="visual_lines"); foot = mask_of([g.buffer(max(w / 2, LF.P["r_min"])) for g, w in zip(L.geometry, L["width_px"])], shape)
    else: foot = np.zeros(shape, bool)
    out = {}
    for b in band_list:
        g = LineString(b["axis"]); core = O.rmask(g.buffer(max(b["width"] / 2 - 1, 0.75)), shape)
        col = np.median(a[core], 0); ok = E.de(np.broadcast_to(col, rgb[core].shape)[None], rgb[core][None])[0] <= FRAG
        pts = shapely.get_coordinates(shapely.line_interpolate_point(g, np.linspace(0, g.length, int(g.length) + 1)))
        x = np.clip(pts[:, 0].astype(int), 0, shape[1] - 1); y = np.clip(pts[:, 1].astype(int), 0, shape[0] - 1)
        out[b["id"]] = {"width": b["width"], "colour_preserved": float(ok.mean()), "axis_under_line": float(foot[y, x].mean())}
    return out


def false_lines(lines, ink_axes, fill_polys, band_list):
    T = shapely.union_all([LineString(x) for x in ink_axes]).buffer(3) if ink_axes else None
    Ed = shapely.union_all([Polygon(f).exterior for f in fill_polys]).buffer(2.5) if fill_polys else None
    Bd = shapely.union_all([LineString(b["axis"]).buffer(b["width"] / 2 + 2) for b in band_list]) if band_list else None
    out = {"fill_edge": 0.0, "band": 0.0, "other": 0.0}
    for f in lines:
        r = shapely.difference(f["geom"], T) if T is not None else f["geom"]
        if Ed is not None: out["fill_edge"] += shapely.intersection(r, Ed).length; r = shapely.difference(r, Ed)
        if Bd is not None: out["band"] += shapely.intersection(r, Bd).length; r = shapely.difference(r, Bd)
        out["other"] += r.length
    return out


def edit_checks(res, gpkg, shape):
    """On the GPKG: recolour one logical group, and move it by 3 px; count re-rendered pixels that change OUTSIDE
    that group's old and new footprints (must be 0 = no unrelated object changes). Faces are never touched."""
    import geopandas as gpd, shapely.affinity as AF
    if not res["lines"]: return None
    L = pyogrio.read_dataframe(gpkg, layer="visual_lines"); grp = L["logical_id"].value_counts().index[0]
    base, _, _, _ = O2.render_gpkg(gpkg, shape, res["kpal"], LF.P, np.zeros(shape, bool)); out = {"logical_id": str(grp), "features_in_group": int((L["logical_id"] == grp).sum())}
    sel = L["logical_id"] == grp
    old = mask_of([g.buffer(max(w / 2, LF.P["r_min"])) for g, w in zip(L.geometry[sel], L["width_px"][sel])], shape)
    for name, mod in (("recolour", lambda d: d.assign(rgb=np.where(sel, "#00ff00", d["rgb"]))),
                      ("move_dy3", lambda d: d.assign(geometry=[AF.translate(g, 0, 3) if s else g for g, s in zip(d.geometry, sel)]))):
        p2 = gpkg.with_name(gpkg.stem + f"_{name}.gpkg"); faces = pyogrio.read_dataframe(gpkg, layer="colour_faces")
        if p2.exists(): p2.unlink()
        faces.to_file(p2, layer="colour_faces", driver="GPKG", engine="pyogrio"); gpd.GeoDataFrame(mod(L.copy())).to_file(p2, layer="visual_lines", driver="GPKG", engine="pyogrio")
        rgb2, _, _, _ = O2.render_gpkg(p2, shape, res["kpal"], LF.P, np.zeros(shape, bool))
        L2 = pyogrio.read_dataframe(p2, layer="visual_lines"); new = mask_of([g.buffer(max(w / 2, LF.P["r_min"])) for g, w in zip(L2.geometry[sel], L2["width_px"][sel])], shape)
        ch = (rgb2 != base).any(-1); out[name] = {"changed_px": int(ch.sum()), "changed_outside_group_footprint": int((ch & ~(old | new)).sum())}
        p2.unlink()
    return out


def evaluate(a, res, gpkg, ink_axes, ink_meta, band_list, fill_polys):
    shape = a.shape[:2]; fc = res["faces"]
    fv = int(sum(len(l.coords) for l in fc["arcs"])); lv = int(sum(shapely.get_num_coordinates(f["geom"]) for f in res["lines"]))
    return {"faces": len(fc["polys"]), "lines": len(res["lines"]), "logical": len({f["group"] for f in res["lines"]}), "vertices": fv + lv,
            "topology": fc["topology"], "uncovered_px": res["holes"], "memory_vs_gpkg_px": res["memory_vs_gpkg_px"],
            "faces_inferred_only": int((res["obs"] == 0).sum()), "fidelity": fidelity(a, res["rgb"], ink_axes, shape),
            "ink_presence": {m["id"]: {"sub": m.get("sub", m.get("type")), "presence": presence(a, res["rgb"], m["axis"])} for m in ink_meta},
            "bands": bands(a, res["rgb"], gpkg, band_list, shape), "false_lines": false_lines(res["lines"], ink_axes, fill_polys, band_list),
            "edit": edit_checks(res, gpkg, shape)}
