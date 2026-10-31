"""Geometry-first metrics G1-G3 for existing StitchVector outputs (rules: sv_g3_plan.json). Read-only scoring.

Truth elements are sampled every 1 px with tangents; output geometry (face boundaries, line centrelines) every 0.5 px.
A truth sample is MATCHED by an output kind if an output sample of that kind lies within TOL px and the tangents differ
by <= DIR_DEG (either orientation). A match is REUSABLE only inside a run of >= RUN_MIN consecutive matched visible samples.
Per-sample classes (first that applies):
  ink line       line_ok | face_outline (polygon edges along the ink, conversion needed) | needs_fix | missing
  fill boundary  face_ok | line_only (boundary exists only as a line: split the face along it) | needs_fix | missing
  band axis      face_ok (both band sides matched by face edges AND a band-dedicated face at the axis)
                 | line_convert (centreline on the axis: re-widen + line-to-face) | face_needs_fix (band face present,
                 sides incomplete) | needs_fix | missing
'needs_fix' = some output geometry within the search radius but not reusable; 'missing' = nothing to reuse (redraw).
Areas and lengths are never added together; every number is either a share of truth samples (1 px each) or an area.
"""
import numpy as np, shapely
from shapely.geometry import LineString, Polygon, box
from scipy.spatial import cKDTree
from scipy import ndimage as ndi

TOL, DIR_DEG, RUN_MIN, COL_DE, WIDTH_TOL, BAND_INSIDE, OWN_SHARE = 1.5, 30.0, 5, 15.0, 1.0, 0.8, 0.6
COS = np.cos(np.radians(DIR_DEG))


def lab(x):
    from skimage.color import rgb2lab
    return rgb2lab(np.asarray(x, np.float64).reshape(-1, 1, 3) / 255.0).reshape(-1, 3)


def de(a, b): return float(np.linalg.norm(lab(a)[0] - lab(b)[0]))


def sample(geoms, step):
    P, T = [], []
    for g in geoms:
        for part in shapely.get_parts(shapely.line_merge(g) if g.geom_type == "MultiLineString" else g):
            if part.geom_type in ("Polygon", "MultiPolygon"):
                for ring in shapely.get_parts(shapely.boundary(part)): P_, T_ = _s(LineString(ring.coords), step); P.append(P_); T.append(T_)
            elif part.geom_type in ("LinearRing",): P_, T_ = _s(LineString(part.coords), step); P.append(P_); T.append(T_)
            elif part.geom_type == "LineString" and part.length > 0: P_, T_ = _s(part, step); P.append(P_); T.append(T_)
    if not P: return np.zeros((0, 2)), np.zeros((0, 2))
    return np.vstack(P), np.vstack(T)


def _s(g, step):
    L = g.length; s = np.arange(0, L + 1e-9, step) if L > 0 else np.array([0.0])
    p = shapely.get_coordinates(shapely.line_interpolate_point(g, s))
    a = shapely.get_coordinates(shapely.line_interpolate_point(g, np.clip(s - 0.75, 0, L))); b = shapely.get_coordinates(shapely.line_interpolate_point(g, np.clip(s + 0.75, 0, L)))
    t = b - a; t /= np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-9); return p, t


class Index:
    def __init__(self, P, T): self.P, self.T = P, T; self.tree = cKDTree(P) if len(P) else None

    def near(self, pts, r):
        if self.tree is None: return np.zeros(len(pts), bool)
        d, _ = self.tree.query(pts, distance_upper_bound=r); return np.isfinite(d)

    def match(self, pts, tan, r=TOL):
        out = np.zeros(len(pts), bool)
        if self.tree is None: return out
        for i, nb in enumerate(self.tree.query_ball_point(pts, r)):
            if nb: out[i] = bool((np.abs(self.T[nb] @ tan[i]) >= COS).any())
        return out


def runs_ok(m, vis):
    """matched samples inside runs of >= RUN_MIN consecutive matched visible samples (hidden samples skipped)."""
    idx = np.nonzero(vis)[0]; mm = m[idx]; ok = np.zeros(len(m), bool)
    z = np.r_[0, mm.astype(int), 0]; d = np.diff(z); st, en = np.nonzero(d == 1)[0], np.nonzero(d == -1)[0]
    for s, e in zip(st, en):
        if e - s >= RUN_MIN: ok[idx[s:e]] = True
    return ok


def truth_samples(g):
    P, T = _s(g, 1.0); return P, T


def out_geometry(F, L, frame):
    fb = [shapely.difference(shapely.boundary(g), frame) for g in F.geometry]
    FP, FT = sample([g for g in fb if not g.is_empty], 0.5)
    if L is not None and len(L): LP, LT = sample(list(L.geometry), 0.5)
    else: LP, LT = np.zeros((0, 2)), np.zeros((0, 2))
    return Index(FP, FT), Index(LP, LT)


def classify_ink(P, T, vis, w, FI, LI):
    lm = runs_ok(LI.match(P, T), vis); fm = runs_ok(FI.match(P, T, w / 2 + TOL), vis) & ~lm
    anyg = (FI.near(P, w / 2 + TOL) | LI.near(P, w / 2 + TOL)) & ~lm & ~fm
    return np.select([lm, fm, anyg], ["line_ok", "face_outline", "needs_fix"], "missing")


def classify_edge(P, T, vis, FI, LI):
    fm = runs_ok(FI.match(P, T), vis); lm = runs_ok(LI.match(P, T), vis) & ~fm
    anyg = (FI.near(P, TOL + 1) | LI.near(P, TOL + 1)) & ~fm & ~lm
    return np.select([fm, lm, anyg], ["face_ok", "line_only", "needs_fix"], "missing")


def classify_band(g, w, vis, FI, LI, face_id, band_face_ids):
    P, T = truth_samples(g); N = np.c_[-T[:, 1], T[:, 0]]
    sl = runs_ok(FI.match(P + N * w / 2, T), vis); sr = runs_ok(FI.match(P - N * w / 2, T), vis)
    H, W = face_id.shape; xi = np.clip(P[:, 0].astype(int), 0, W - 1); yi = np.clip(P[:, 1].astype(int), 0, H - 1)
    bf = np.isin(face_id[yi, xi], list(band_face_ids)) if band_face_ids else np.zeros(len(P), bool)
    fo = sl & sr & bf; lc = runs_ok(LI.match(P, T), vis) & ~fo; fn = bf & ~fo & ~lc
    anyg = (FI.near(P, w / 2 + TOL) | LI.near(P, w / 2 + TOL)) & ~fo & ~lc & ~fn
    return P, np.select([fo, lc, fn, anyg], ["face_ok", "line_convert", "face_needs_fix", "needs_fix"], "missing"), face_id[yi, xi]


def face_id_raster(F, shape):
    import rasterio.features as RF
    from affine import Affine
    return RF.rasterize([(g, i + 1) for i, g in enumerate(F.geometry)], out_shape=shape, fill=0, transform=Affine.identity(), dtype="int32")


def band_faces(F, g, w):
    near = g.buffer(w / 2 + 1.5); return {i + 1 for i, geom in enumerate(F.geometry) if geom.intersects(near) and shapely.intersection(geom, near).area / geom.area >= BAND_INSIDE}


def tally(classes, keys):
    c = np.asarray(classes); return {k: int((c == k).sum()) for k in keys}


INK_K = ["line_ok", "face_outline", "needs_fix", "missing"]
EDGE_K = ["face_ok", "line_only", "needs_fix", "missing"]
BAND_K = ["face_ok", "line_convert", "face_needs_fix", "needs_fix", "missing"]


def line_groups(L):
    if L is None or not len(L): return []
    out = []
    for lid in L["logical_id"].unique():
        sel = L[L["logical_id"] == lid]
        out.append({"logical_id": str(lid), "geom": shapely.union_all(list(sel.geometry)), "length": float(sum(g.length for g in sel.geometry)),
                    "width": float(np.median(sel["width_px"])), "rgb": [int(sel["rgb"].iloc[0][i:i + 2], 16) for i in (1, 3, 5)], "features": int(len(sel))})
    return out


def line_ops(groups, inks, bands_):
    """inks: list of dict(axis LineString, width, rgb or None); bands_: list of dict(axis, width). Per-group classification."""
    ops = {"recolour": 0, "rewidth": 0, "split_cross_line": 0, "delete_false": 0, "false_length": 0.0, "band_groups": 0, "groups": len(groups)}
    det = []
    for G in groups:
        g = G["geom"]; L = max(G["length"], 1e-9)
        sh = [shapely.intersection(g, x["axis"].buffer(2.0)).length / L for x in inks]
        bsh = [shapely.intersection(g, b["axis"].buffer(b["width"] / 2 + 1.5)).length / L for b in bands_]
        excl = []
        for i, x in enumerate(inks):
            others = shapely.union_all([y["axis"].buffer(2.0) for j, y in enumerate(inks) if j != i]) if len(inks) > 1 else None
            zone = x["axis"].buffer(2.0) if others is None else shapely.difference(x["axis"].buffer(2.0), others)
            excl.append(shapely.intersection(g, zone).length)
        cross = sum(e >= 10 for e in excl) >= 2
        k = int(np.argmax(sh)) if sh else -1; owner = k if (k >= 0 and sh[k] >= OWN_SHARE and not cross) else -1
        kind = "cross_line" if cross else ("ink" if owner >= 0 else ("band" if bsh and max(bsh) >= OWN_SHARE else "false"))
        r = {"logical_id": G["logical_id"], "kind": kind, "length": G["length"], "features": G["features"]}
        if kind == "ink":
            x = inks[owner]
            if x.get("rgb") is not None and de(G["rgb"], x["rgb"]) > COL_DE: ops["recolour"] += 1; r["recolour"] = True
            if x.get("width") is not None and abs(G["width"] - x["width"]) > WIDTH_TOL: ops["rewidth"] += 1; r["rewidth"] = True
        elif kind == "cross_line": ops["split_cross_line"] += 1
        elif kind == "band": ops["band_groups"] += 1
        else: ops["delete_false"] += 1; ops["false_length"] += G["length"]
        det.append(r)
    return ops, det


def face_ops(F, fid, truth_lab, truth_rgb, ink_foot, shape):
    """Synthetic only. Per output face: majority truth label / region; ink faces; recolour (individual and safe-batch);
    merges = sum over truth regions of (faces assigned - 1); splits = faces whose 2nd truth label share >= 10% and >= 20 px."""
    regions = np.zeros(shape, np.int32); n0 = 0
    for v in np.unique(truth_lab):
        l, n = ndi.label(truth_lab == v); regions[l > 0] = l[l > 0] + n0; n0 += n
    nf = len(F); ids = fid.ravel(); good = ids > 0
    cnt = np.bincount(ids[good], minlength=nf + 1)
    inkc = np.bincount(ids[good & ink_foot.ravel()], minlength=nf + 1)
    ink_face = inkc / np.maximum(cnt, 1) >= OWN_SHARE
    key = ids[good].astype(np.int64) * (int(regions.max()) + 1) + regions.ravel()[good]
    uk, uc = np.unique(key, return_counts=True); fi, ri = uk // (int(regions.max()) + 1), uk % (int(regions.max()) + 1)
    major = np.zeros(nf + 1, np.int64); majc = np.zeros(nf + 1); second = np.zeros(nf + 1)
    for f, r, c in zip(fi, ri, uc):
        if c > majc[f]: second[f] = majc[f]; majc[f] = c; major[f] = r
        elif c > second[f]: second[f] = c
    reg_lab = {r: int(truth_lab.ravel()[np.argmax(regions.ravel() == r)]) for r in np.unique(regions)}
    rgb = [[int(s[i:i + 2], 16) for i in (1, 3, 5)] for s in F["rgb"]]
    per_region = {}; recol = []; split = 0
    for f in range(1, nf + 1):
        if cnt[f] == 0 or ink_face[f]: continue
        per_region.setdefault(int(major[f]), []).append(f)
        tl = reg_lab[int(major[f])]
        if de(rgb[f - 1], truth_rgb[tl]) > COL_DE: recol.append((tuple(rgb[f - 1]), tl, f))
        if second[f] >= max(20, 0.1 * cnt[f]): split += 1
    merges = sum(max(len(v) - 1, 0) for v in per_region.values())
    by_col = {}
    for f in range(1, nf + 1):
        if cnt[f] and not ink_face[f]: by_col.setdefault(tuple(rgb[f - 1]), set()).add(reg_lab[int(major[f])])
    batches = set(); unsafe = 0
    for col, tl, f in recol:
        if by_col[col] == {tl}: batches.add((col, tl))
        else: unsafe += 1
    return {"faces": nf, "ink_faces": int(ink_face[1:].sum()), "recolour_individual": len(recol), "recolour_safe_batch_lower_bound": len(batches) + unsafe,
            "merge": int(merges), "split": int(split), "truth_regions_covered": len(per_region)}


def spurious_boundary(FI, truth_lines_all, ink_foot):
    if not len(FI.P): return 0.0
    T = cKDTree(np.vstack([_s(g, 0.5)[0] for g in truth_lines_all])) if truth_lines_all else None
    far = np.ones(len(FI.P), bool) if T is None else ~np.isfinite(T.query(FI.P, distance_upper_bound=TOL)[0])
    H, W = ink_foot.shape; xi = np.clip(FI.P[:, 0].astype(int), 0, W - 1); yi = np.clip(FI.P[:, 1].astype(int), 0, H - 1)
    return float((far & ~ink_foot[yi, xi]).sum() * 0.5)
