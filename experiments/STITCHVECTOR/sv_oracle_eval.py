"""Oracle POC evaluation: fidelity, complexity, edit tasks C1-C3 (file/geometry level, no QGIS)."""
import numpy as np
import shapely
from shapely.affinity import translate
import rasterio.features as RF
import sv_arcs as A
import sv_d71 as D
import sv_oracle as O

ID = O.ID


def id_raster(polys, shape):
    return RF.rasterize([(p, i + 1) for i, p in enumerate(polys)], out_shape=shape, fill=0, transform=ID,
                        all_touched=False, dtype="int32")


def render_lines(rgb, lines, shape, p):
    out = rgb.copy(); core = np.zeros(shape, np.int32)
    for i, f in enumerate(lines):
        m = O.rmask(f["geom"].buffer(max(f["width"] / 2, p["r_min"])), shape); out[m] = f["rgb"]; core[m] = i + 1
    return out, core


def de(a, b):
    return np.sqrt(((O.lab_of(a) - O.lab_of(b)) ** 2).sum(-1))


def line_presence(a, rgb, raw, p):
    """Along the oracle trace (pixel centres): rendered colour within frag_dE of the original pixel. Breaks = runs >= 2 misses."""
    H, W = a.shape[:2]; xs = np.clip(np.array([q[0] for q in raw]).astype(int), 0, W - 1); ys = np.clip(np.array([q[1] for q in raw]).astype(int), 0, H - 1)
    ok = de(a[ys, xs][None], rgb[ys, xs][None])[0] <= p["frag_dE"]
    miss = np.r_[0, (~ok).astype(int), 0]; d = np.diff(miss); runs = np.nonzero(d == -1)[0] - np.nonzero(d == 1)[0]
    return {"samples": int(len(ok)), "present_share": float(ok.mean()), "breaks_ge2": int((runs >= 2).sum())}


def line_geometry_stats(f, con, shape, p):
    from skimage.morphology import skeletonize
    sk = skeletonize(f["ink"]); ys, xs = np.nonzero(sk)
    d = shapely.distance(f["geom"], shapely.points(xs + 0.5, ys + 0.5)) if len(xs) else np.array([np.nan])
    raw = shapely.LineString(f["raw"])
    foot = O.rmask(f["geom"].buffer(max(f["width"] / 2, p["r_min"])), shape)
    return {"vertices": int(len(f["geom"].coords)), "length_px": round(float(f["geom"].length), 1), "width_est_px": round(f["width"], 2),
            "footprint_width_px": round(float(foot.sum() / max(f["geom"].length, 1)), 2),
            "ink_px": int(f["ink"].sum()), "ink_covered_share": float((foot & f["ink"]).sum() / max(f["ink"].sum(), 1)),
            "footprint_on_ink_share": float((foot & f["ink"]).sum() / max(foot.sum(), 1)),
            "dist_ink_skeleton_to_line_mean": float(np.nanmean(d)), "dist_ink_skeleton_to_line_p95": float(np.nanpercentile(d, 95)),
            "hausdorff_to_trace": float(shapely.hausdorff_distance(f["geom"], raw)), "rgb": [int(v) for v in f["rgb"]]}


def class_regions(X, lut, c):
    from scipy import ndimage as ndi
    m = lut[X] == c; l, n = ndi.label(m, D.S4); return l, n


def faces_in_region(fc, region, lut, c, shape):
    rid = id_raster(fc["polys"], shape); ids = np.unique(rid[region]); ids = ids[ids > 0]
    vals = fc["vals"][ids - 1]; return int((lut[vals] == c).sum()), int(len(np.unique(vals[lut[vals] == c])))


def polyset(polys):
    return set(shapely.to_wkb(shapely.normalize(np.asarray(polys, object))).tolist())


def c1_move_line(lab, a, pal, lines, group, dy, level, p, fc_B):
    """O1: translate the features of one logical line by dy px. B0 proxy: move the same line pixels in the label image
    and re-polygonize; count polygons that would have to be edited (removed / created)."""
    H, W = lab.shape; sel = [i for i, f in enumerate(lines) if f["group"] == group]
    new = [dict(f) for f in lines]
    for i in sel: new[i]["geom"] = translate(lines[i]["geom"], 0, dy)
    core = np.zeros((H, W), bool)
    for i in sel: core |= O.rmask(lines[i]["geom"].buffer(max(lines[i]["width"] / 2, p["r_min"])), (H, W))
    lab2 = D.fill(lab, core); ys, xs = np.nonzero(core); ok = (ys + dy >= 0) & (ys + dy < H)
    lab2[ys[ok] + dy, xs[ok]] = lab[ys[ok], xs[ok]]
    fb2 = O.faces(lab2, level); s0, s1 = polyset(fc_B["polys"]), polyset(fb2["polys"])
    return new, {"O1_features_edited": len(sel), "O1_logical_objects_edited": 1, "O1_face_polygons_edited": 0,
                 "O1_vertices_moved": int(sum(len(lines[i]["geom"].coords) for i in sel)),
                 "O1_lines_simple": bool(all(new[i]["geom"].is_simple for i in sel)),
                 "B0_polygons_removed_or_changed": len(s0 - s1), "B0_polygons_created": len(s1 - s0),
                 "B0_faces_before_after": [len(fc_B["polys"]), len(fb2["polys"])], "B0_topology_after": fb2["topology"]}


def arc_sides(arc, X, lut):
    c = np.asarray(arc.coords); H, W = X.shape
    seg = np.argmax(((c[1:] - c[:-1]) ** 2).sum(1)); m = (c[seg] + c[seg + 1]) / 2; v = c[seg + 1] - c[seg]
    n = np.array([-v[1], v[0]]) / max(np.hypot(*v), 1e-9); out = []
    for s in (0.5, -0.5):
        x, y = m + s * n; out.append(int(lut[X[int(np.clip(np.floor(y), 0, H - 1)), int(np.clip(np.floor(x), 0, W - 1))]]))
    return tuple(sorted(out))


def boundary_arcs(fc, X, lut, pair):
    return [i for i, l in enumerate(fc["arcs"]) if arc_sides(l, X, lut) == tuple(sorted(pair))]


def c3_shared_boundary(fc, X, lut, pair, shift):
    """Move interior vertices of the longest arc between two colour classes. Shared-arc rebuild vs editing only one of the
    two Simple Features polygons (no topology)."""
    idx = boundary_arcs(fc, X, lut, pair)
    cand = [i for i in idx if len(fc["arcs"][i].coords) >= 3]
    if not cand: return {"arcs_on_boundary": len(idx), "edited": False}
    k = max(cand, key=lambda i: fc["arcs"][i].length); arcs = list(fc["arcs"]); c = np.asarray(arcs[k].coords).copy()
    for sx, sy in ((shift, 0), (-shift, 0), (0, shift), (0, -shift)):
        c2 = c.copy(); c2[1:-1] += (sx, sy); trial = arcs[:k] + [shapely.LineString(c2)] + arcs[k + 1:]
        if not len(A.crossing_arcs(trial)): break
    else:
        return {"arcs_on_boundary": len(idx), "edited": False, "reason": "every shift crosses another arc"}
    polys = list(shapely.get_parts(shapely.polygonize(np.asarray(trial, object))))
    H, W = X.shape; topo = A.topology(polys, H, W)
    old = np.asarray(fc["polys"], object); tree = shapely.STRtree(old); adj = tree.query(arcs[k], predicate="intersects")
    adj = [int(j) for j in adj if shapely.length(shapely.intersection(old[j].boundary, arcs[k])) > 0.5][:2]
    newp = np.asarray(polys, object); t2 = shapely.STRtree(newp)
    def match(j):
        cand = t2.query(shapely.point_on_surface(old[j]), predicate="intersects")
        return newp[max(cand, key=lambda q: shapely.area(shapely.intersection(newp[q], old[j])))] if len(cand) else None
    gap = ovl = None
    if len(adj) == 2:
        a0, b0 = old[adj[0]], old[adj[1]]; a1 = match(adj[0])
        if a1 is not None:
            gap = float(shapely.area(shapely.difference(shapely.union(a0, b0), shapely.union(a1, b0))))
            ovl = float(shapely.area(shapely.intersection(a1, b0)))
    return {"arcs_on_boundary": len(idx), "edited": True, "arc_vertices_moved": int(len(c) - 2), "shift": [sx, sy],
            "shared_arc_faces_before_after": [len(fc["polys"]), len(polys)], "shared_arc_topology_after": {kk: bool(v) for kk, v in topo.items()},
            "shared_arc_objects_edited": 1, "simple_features_one_polygon_only": {"gap_area_px": gap, "overlap_area_px": ovl},
            "simple_features_objects_to_edit_consistently": 2}
