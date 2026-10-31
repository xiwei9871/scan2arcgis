"""Edit-cost calibration POC (plan: sv_ec_plan.json). DATA_LEVEL_ONLY: scripted geometry edits on COPIES of GPKGs.
Truth is used only to place a user-like click, to simulate a rough lasso (marked TRUTH_ASSISTED) and to score."""
import shutil
import numpy as np, shapely, pyogrio, geopandas as gpd, networkx as nx
from shapely.geometry import LineString
from scipy import ndimage as ndi
import sv_oracle as O, sv_g3 as G

DE_GROW = 15.0


def load(gp):
    layers = [l[0] for l in pyogrio.list_layers(gp)]; F = pyogrio.read_dataframe(gp, layer="colour_faces")
    return F, (pyogrio.read_dataframe(gp, layer="visual_lines") if "visual_lines" in layers else None)


def rgb_of(s): return [int(s[i:i + 2], 16) for i in (1, 3, 5)]


def adjacency(fid):
    """edge adjacency between face ids from the rasterised face layer (4-neighbour pixel pairs with different ids)."""
    Gr = nx.Graph(); Gr.add_nodes_from(np.unique(fid[fid > 0]).tolist())
    for a, b in ((fid[:, 1:], fid[:, :-1]), (fid[1:], fid[:-1])):
        m = (a != b) & (a > 0) & (b > 0); pairs = np.unique(np.sort(np.c_[a[m], b[m]], 1), axis=0); Gr.add_edges_from(map(tuple, pairs.tolist()))
    return Gr


def regions_of(lab):
    reg = np.zeros(lab.shape, np.int32); n0 = 0
    for v in np.unique(lab):
        l, n = ndi.label(lab == v); reg[l > 0] = l[l > 0] + n0; n0 += n
    return reg


def assign(fid, reg, ink_foot, nf):
    ids = fid.ravel(); g = ids > 0; cnt = np.bincount(ids[g], minlength=nf + 1); inkc = np.bincount(ids[g & ink_foot.ravel()], minlength=nf + 1)
    ink_face = inkc / np.maximum(cnt, 1) >= G.OWN_SHARE; R = int(reg.max()) + 1
    key = ids[g].astype(np.int64) * R + reg.ravel()[g]; uk, uc = np.unique(key, return_counts=True); fi, ri = uk // R, uk % R
    major = np.zeros(nf + 1, np.int64); best = np.zeros(nf + 1)
    for f, r, c in zip(fi, ri, uc):
        if c > best[f]: best[f] = c; major[f] = r
    return major, ink_face, cnt


def audit(gp, img, lab, ink_axes, ink_widths):
    """Part 1: what G3 'merge' and the ink-face exclusion mean."""
    F, L = load(gp); shape = img.shape[:2]; fid = G.face_id_raster(F, shape); nf = len(F); reg = regions_of(lab)
    foot = np.zeros(shape, bool)
    for a, w in zip(ink_axes, ink_widths): foot |= O.rmask(a.buffer(w / 2 + 1.0), shape)
    major, ink_face, cnt = assign(fid, reg, foot, nf); Gr = adjacency(fid)
    per = {}
    for f in range(1, nf + 1):
        if cnt[f] and not ink_face[f]: per.setdefault(int(major[f]), []).append(f)
    merge_g3 = sum(len(v) - 1 for v in per.values()); comps = 0; extra = 0
    for v in per.values():
        k = nx.number_connected_components(Gr.subgraph(v)); comps += k; extra += k - 1
    Lu = shapely.union_all(list(L.geometry)) if L is not None and len(L) else None
    ink_ids = [f for f in range(1, nf + 1) if cnt[f] and ink_face[f]]
    far = [f for f in ink_ids if Lu is None or shapely.distance(F.geometry.iloc[f - 1], Lu) > G.TOL]
    return {"faces": nf, "truth_regions_with_faces": len(per), "G3_merge_faces_minus_1": int(merge_g3),
            "dissolve_ops_one_per_connected_component": int(comps),
            "regions_split_into_non_adjacent_pieces": int(sum(1 for v in per.values() if nx.number_connected_components(Gr.subgraph(v)) > 1)),
            "extra_components_beyond_one_per_region": int(extra),
            "ink_faces_excluded_by_G3": len(ink_ids), "ink_faces_area_px": int(sum(cnt[f] for f in ink_ids)),
            "ink_faces_not_near_any_line": len(far), "ink_faces_not_near_any_line_area_px": int(sum(cnt[f] for f in far))}


def write_copy(src, dst, F=None, L=None):
    shutil.copyfile(src, dst)
    if F is not None or L is not None:
        F0, L0 = load(src); F = F0 if F is None else F; L = L0 if L is None else L; dst.unlink()
        gpd.GeoDataFrame(F, geometry="geometry").to_file(dst, layer="colour_faces", driver="GPKG", engine="pyogrio")
        if L is not None and len(L): gpd.GeoDataFrame(L, geometry="geometry").to_file(dst, layer="visual_lines", driver="GPKG", engine="pyogrio")
    return dst


def check_copy(dst, shape, fid_before, edit_zone):
    F, L = load(dst); fid = G.face_id_raster(F, shape)
    holes = int(((fid == 0)).sum())
    valid = bool(shapely.coverage_is_valid(np.asarray(F.geometry.values, object)))
    area = float(sum(g.area for g in F.geometry)); H, W = shape
    return {"faces": len(F), "coverage_is_valid_strict": valid, "area_sum_equals_window": abs(area - H * W) < 1e-6, "uncovered_px": holes,
            "lines": 0 if L is None else len(L), "_fid": fid}


def case_fragmented(gp, img, lab, ink_axes, ink_widths, dst_dir, tag):
    """A: pick the non-background truth region with most assigned faces; two truth-free-ish selections; dissolve; recolour."""
    F, L = load(gp); shape = img.shape[:2]; fid = G.face_id_raster(F, shape); nf = len(F); reg = regions_of(lab)
    foot = np.zeros(shape, bool)
    for a, w in zip(ink_axes, ink_widths): foot |= O.rmask(a.buffer(w / 2 + 1.0), shape)
    major, ink_face, cnt = assign(fid, reg, foot, nf); Gr = adjacency(fid)
    bg = int(np.bincount(lab.ravel()).argmax())
    cand = {}
    for f in range(1, nf + 1):
        if cnt[f] and not ink_face[f] and int(lab.ravel()[np.argmax(reg.ravel() == major[f])]) != bg: cand.setdefault(int(major[f]), []).append(f)
    r = max(cand, key=lambda k: len(cand[k])); faces_in = cand[r]; region = reg == r
    seed = max(faces_in, key=lambda f: cnt[f])
    from skimage.color import rgb2lab
    Lab = rgb2lab(img / 255.0)
    med = {f: np.median(Lab[fid == f], 0) for f in range(1, nf + 1) if cnt[f]}
    stored = {f: G.lab(rgb_of(F["rgb"].iloc[f - 1]))[0] for f in range(1, nf + 1)}
    out = {"tag": tag, "truth_region": int(r), "region_px": int(region.sum()), "faces_assigned": len(faces_in),
           "face_components_in_region": int(nx.number_connected_components(Gr.subgraph(faces_in))), "seed_face": int(seed), "selections": {}}
    truth_rgb = np.median(img[region & ~foot], 0)
    def grow(colmap):
        sel, todo = {seed}, [seed]
        while todo:
            f = todo.pop()
            for g in Gr.neighbors(f):
                if g not in sel and g in colmap and np.linalg.norm(colmap[g] - colmap[seed]) <= DE_GROW: sel.add(g); todo.append(g)
        return sel
    er = ndi.binary_erosion(region, iterations=2)
    lasso = {f for f in range(1, nf + 1) if cnt[f] and er[np.clip(int(shapely.get_y(shapely.point_on_surface(F.geometry.iloc[f - 1]))), 0, shape[0] - 1),
                                                             np.clip(int(shapely.get_x(shapely.point_on_surface(F.geometry.iloc[f - 1]))), 0, shape[1] - 1)]}
    for name, sel in (("S1a_grow_stored_colour", grow(stored)), ("S1b_grow_image_colour", grow(med)), ("S2_rough_lasso_TRUTH_ASSISTED", lasso)):
        m = np.isin(fid, list(sel)); prec = float((m & region).sum() / max(m.sum(), 1)); rec = float((m & region).sum() / region.sum())
        merged = shapely.union_all([F.geometry.iloc[f - 1] for f in sel]); parts = len(shapely.get_parts(merged))
        new_rgb = np.median(img[m & ~foot], 0) if (m & ~foot).any() else np.median(img[m], 0)
        keep = F.drop(index=[f - 1 for f in sel]).copy()
        add = gpd.GeoDataFrame({c: [F[c].iloc[seed - 1]] for c in F.columns if c != "geometry"}, geometry=[merged], crs=F.crs)
        add["rgb"] = "#%02x%02x%02x" % tuple(int(v) for v in new_rgb)
        Fn = gpd.GeoDataFrame(pd_concat([keep, add]), geometry="geometry")
        dst = write_copy(gp, dst_dir / f"{tag}_A_{name}.gpkg", F=Fn)
        chk = check_copy(dst, shape, fid, m); fid2 = chk.pop("_fid")
        changed_out = int(((fid2 == len(Fn)) & ~m).sum())          # pixels outside the selection that now belong to the new face
        out["selections"][name] = {"faces_selected": len(sel), "precision_area": prec, "recall_area": rec, "parts_after_one_dissolve": parts,
                                   "ops": {"select": 1, "dissolve": 1, "eyedropper_recolour": 1} if name != "S2_rough_lasso_TRUTH_ASSISTED" else {"lasso_draw": 1, "dissolve": 1, "eyedropper_recolour": 1},
                                   "eyedropper_dE_to_truth_fill": G.de(new_rgb, truth_rgb), "edited_copy": dst.name, "copy_check": chk,
                                   "pixels_outside_selection_now_in_new_face": changed_out}
    return out


def pd_concat(frames):
    import pandas as pd
    return pd.concat(frames, ignore_index=True)


def line_to_face(F, img, line_geoms, width):
    poly = shapely.union_all([g.buffer(width / 2) for g in line_geoms])
    keep, touched = [], 0
    for i, g in enumerate(F.geometry):
        if g.intersects(poly):
            d = shapely.difference(g, poly); touched += 1
            if d.is_empty: continue
            keep.append((i, d))
        else: keep.append((i, g))
    rows = F.iloc[[i for i, _ in keep]].copy(); rows["geometry"] = [g for _, g in keep]
    m = O.rmask(poly, img.shape[:2]); rgb = np.median(img[m], 0) if m.any() else np.array([0, 0, 0])
    add = gpd.GeoDataFrame({c: [F[c].iloc[0]] for c in F.columns if c != "geometry"}, geometry=[poly], crs=F.crs)
    add["rgb"] = "#%02x%02x%02x" % tuple(int(v) for v in rgb); add["source"] = "edited_line_to_face"
    return gpd.GeoDataFrame(pd_concat([rows, add]), geometry="geometry"), poly, touched, rgb


def case_band(gp, img, band_axis, band_w, dst_dir, tag, split_outside=False, redraw_gaps=False):
    """B / C: line-to-face for a band from its existing line group(s); C splits groups at the band outline and redraws gaps."""
    F, L = load(gp); shape = img.shape[:2]; band = band_axis.buffer(band_w / 2); core = band_axis.buffer(max(band_w / 2 - 1, 0.75))
    on = L[L.intersects(band.buffer(1.0))]; lids = sorted(set(on["logical_id"])); grp = L[L["logical_id"].isin(lids)]
    ops = {"select_group": len(lids), "set_width": 1, "line_to_face_buffer": 1, "difference_with_faces_below": 1, "eyedropper_recolour": 1}
    geoms = list(grp.geometry); info = {"tag": tag, "logical_ids": lids, "features": int(len(grp)), "group_length_px": float(sum(g.length for g in geoms))}
    outline = band.buffer(1.5)
    if split_outside:
        inside = [shapely.intersection(g, outline) for g in geoms]; inside = [p for x in inside for p in shapely.get_parts(x) if p.length >= 2]
        cut = sum(len(shapely.get_parts(shapely.intersection(g, outline.boundary))) for g in geoms)
        info["split_points_TRUTH_ASSISTED"] = int(cut); info["length_removed_outside_band_px"] = float(sum(g.length for g in geoms) - sum(p.length for p in inside))
        ops["split_at_points"] = int(cut); ops["delete_outside_parts"] = 1; geoms = inside
    P, T = G.truth_samples(band_axis); U = shapely.union_all(geoms) if geoms else None
    cov = shapely.distance(shapely.points(P), U) <= G.TOL if U is not None else np.zeros(len(P), bool)
    info["axis_covered_by_line_before"] = float(cov.mean())
    gap = np.r_[0, (~cov).astype(int), 0]; d = np.diff(gap); st, en = np.nonzero(d == 1)[0], np.nonzero(d == -1)[0]
    gaps = [(int(s), int(e)) for s, e in zip(st, en)]; info["gaps_px"] = [e - s for s, e in gaps]
    if redraw_gaps and gaps:
        draws = [LineString(P[max(s - 1, 0):min(e + 1, len(P))]) for s, e in gaps if e - s >= 2]
        info["redraw_length_px"] = float(sum(x.length for x in draws)); ops["redraw_traces"] = len(draws); geoms = geoms + draws
    Fn, poly, touched, rgb = line_to_face(F, img, geoms, band_w)
    dst = write_copy(gp, dst_dir / f"{tag}.gpkg", F=Fn, L=L[~L["logical_id"].isin(lids)] if len(L[~L["logical_id"].isin(lids)]) else None)
    fid0 = G.face_id_raster(F, shape); chk = check_copy(dst, shape, fid0, None); chk.pop("_fid")
    bm = O.rmask(core, shape); band_rgb = np.median(img[bm], 0)
    covp = shapely.distance(shapely.points(P), poly) <= 0.5
    info.update({"faces_touched_by_difference": touched, "core_cover_after": float(shapely.intersection(poly, core).area / core.area),
                 "area_outside_band_px2": float(shapely.difference(poly, band).area), "axis_still_uncovered_px": int((~covp).sum()),
                 "new_face_colour_dE_to_band": G.de(rgb, band_rgb), "edited_copy": dst.name, "copy_check": chk, "ops": ops})
    return info


def case_lost_band(gp, img, band_axis, band_w, tag):
    """D: what is left of a band whose colour was lost in the face palette."""
    F, L = load(gp); band = band_axis.buffer(band_w / 2); core = band_axis.buffer(max(band_w / 2 - 1, 0.75))
    bf = [F.geometry.iloc[i - 1] for i in G.band_faces(F, band_axis, band_w)]
    P, T = G.truth_samples(band_axis); vis = np.ones(len(P), bool)
    _, LI = G.out_geometry(F.iloc[:0], L, shapely.box(0, 0, 1, 1)) if L is not None else (None, None)
    cl = float(G.runs_ok(LI.match(P, T), vis).mean()) if LI is not None else 0.0
    FI, _ = G.out_geometry(F, None, shapely.box(0, 0, img.shape[1], img.shape[0]).boundary.buffer(0.6)); N = np.c_[-T[:, 1], T[:, 0]]
    sides = float((G.runs_ok(FI.match(P + N * band_w / 2, T), vis) & G.runs_ok(FI.match(P - N * band_w / 2, T), vis)).mean())
    biggest = max(F.geometry, key=lambda g: shapely.intersection(g, core).area)
    return {"tag": tag, "band_width": band_w, "axis_length_px": float(band_axis.length), "band_dedicated_faces": len(bf),
            "core_by_band_faces": float(shapely.intersection(shapely.union_all(bf), core).area / core.area) if bf else 0.0,
            "both_sides_matched_by_face_edges": sides, "centreline_cover_dir_runs": cl,
            "largest_face_core_share": float(shapely.intersection(biggest, core).area / core.area), "largest_face_area_px": float(biggest.area),
            "repair": ("recolour band faces" if bf and shapely.intersection(shapely.union_all(bf), core).area / core.area >= 0.8 else
                       "line_to_face from centreline" if cl >= 0.8 else "redraw band polygon"),
            "redraw_boundary_px_if_polygon": float(2 * band_axis.length)}
