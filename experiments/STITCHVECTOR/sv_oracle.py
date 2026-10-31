"""StitchVector Oracle line/face POC (rules: sv_oracle_prereg.json).

Oracle linework = hand waypoints (oracle/u2_300_oracle.json) snapped to the image by a minimum-cost path on a
label-free contrast map. It is a controlled ideal input, not an automatic line detector.
O1 = oracle vector lines on top + colour faces rebuilt from the label image with the line footprint filled from the
nearest non-line pixel (INFERRED, flagged). Faces use sv_arcs (shared arc network, strict coverage).
"""
import time
import numpy as np, cv2
from scipy import ndimage as ndi
from scipy.ndimage import uniform_filter1d
from skimage.graph import route_through_array
from skimage.color import rgb2lab
from skimage.morphology import skeletonize
import shapely
from shapely.geometry import LineString, Polygon
import rasterio.features as RF
from affine import Affine
import sv_arcs as A
import sv_d71 as D

ID = Affine.identity()
P = {"bg_median": 15, "snap_r": 3, "smooth_win": 5, "eps_geom": 1.0, "halo": 1.0, "corridor": 3.0, "c_ink": 12.0, "w_min": 1.0,
     "w_max": 6.0, "r_min": 0.71, "merge_dE": 10.0, "frag_dE": 15.0}


def lab_of(rgb):
    return rgb2lab(np.asarray(rgb, np.float64) / 255.0)


def contrast_map(a, k):
    return np.sqrt(((lab_of(a) - lab_of(cv2.medianBlur(a, k))) ** 2).sum(-1))


def cost_map(con):
    return 1.0 / (1.0 + con) ** 2 + 1e-3


def rmask(geom, shape):
    if geom is None or geom.is_empty: return np.zeros(shape, bool)
    return RF.rasterize([(geom, 1)], out_shape=shape, fill=0, transform=ID, all_touched=False, dtype="uint8") > 0


def snap_point(cost, x, y, r):
    H, W = cost.shape; x = int(np.clip(round(x), 0, W - 1)); y = int(np.clip(round(y), 0, H - 1))
    y0, y1, x0, x1 = max(0, y - r), min(H, y + r + 1), max(0, x - r), min(W, x + r + 1)
    i = np.unravel_index(np.argmin(cost[y0:y1, x0:x1]), (y1 - y0, x1 - x0)); return (y0 + i[0], x0 + i[1])


def trace(cost, waypoints, closed, r):
    pts = [snap_point(cost, x, y, r) for x, y in waypoints]
    if closed: pts = pts + [pts[0]]
    path = [pts[0]]
    for s, e in zip(pts[:-1], pts[1:]):
        seg, _ = route_through_array(cost, s, e, fully_connected=True, geometric=True); path += [tuple(q) for q in seg[1:]]
    return [(x + 0.5, y + 0.5) for y, x in path]


def measure(a, con, g, shape, p):
    corr = rmask(g.buffer(p["corridor"]), shape); ink = corr & (con > p["c_ink"])
    near = corr & rmask(g.buffer(1.0), shape)
    half = max(p["c_ink"], 0.5 * float(np.percentile(con[near], 90))) if near.any() else p["c_ink"]
    w = float(np.clip((corr & (con > half)).sum() / max(g.length, 1.0), p["w_min"], p["w_max"]))   # FWHM of contrast
    core = rmask(g.buffer(max(w / 2, p["r_min"])), shape) & ink
    src = core if core.any() else (ink if ink.any() else corr)
    return w, np.median(a[src], 0).astype(np.uint8), ink


def build_lines(a, oracle, p, eps):
    shape = a.shape[:2]; con = contrast_map(a, p["bg_median"]); cost = cost_map(con); out = []
    for o in oracle["lines"]:
        raw = o.get("traced") or trace(cost, o["waypoints"], o.get("closed", False), p["snap_r"])
        c = np.asarray(raw, float)
        if "traced" not in o and p["smooth_win"] > 1 and len(c) > 2:      # 8-connected staircase -> fewer vertices at eps
            c[1:-1] = uniform_filter1d(c, p["smooth_win"], axis=0, mode="nearest")[1:-1]
        g = LineString(c).simplify(eps, preserve_topology=False) if eps > 0 else LineString(c)
        w, col, ink = measure(a, con, g, shape, p)
        out.append({"id": o["id"], "kind": o["kind"], "group": o.get("group", o["id"]), "raw": raw, "geom": g, "width": w, "rgb": col, "ink": ink})
    return out, con


def footprints(lines, shape, p, protect):
    core = np.zeros(shape, np.int32); rem = np.zeros(shape, bool)
    for i, f in enumerate(lines):
        r = max(f["width"] / 2, p["r_min"])
        core[rmask(f["geom"].buffer(r), shape)] = i + 1; rem |= rmask(f["geom"].buffer(r + p["halo"]), shape)
    return core, rem & ~protect


def protect_mask(oracle, shape):
    m = np.zeros(shape, bool)
    for q in oracle.get("protected", []): m |= rmask(LineString(q["axis"]).buffer(q["radius"]), shape)
    return m


def nearest_pal(rgb, pal):
    return int(np.argmin(((lab_of(pal[None])[0] - lab_of(np.asarray(rgb)[None, None])[0, 0]) ** 2).sum(-1)))


def class_palette(lab, lut, pal):
    cnt = np.bincount(lab.ravel(), minlength=len(pal)); n = int(lut.max()) + 1; out = np.zeros((n, 3), np.uint8)
    for k in range(n):
        ent = np.nonzero(lut == k)[0]; out[k] = pal[ent[np.argmax(cnt[ent])]]
    return out


def faces(X, tol):
    t = time.time(); polys, vals, arcs, _ = A.single_pass(X, tol); s = time.time() - t
    H, W = X.shape; R = A.render(polys, vals, H, W)
    return {"polys": polys, "vals": np.asarray(vals), "arcs": arcs, "seconds": round(s, 2), "mismatch_px": int((R != X).sum()),
            "topology": {k: bool(v) for k, v in A.topology(polys, H, W).items()}}


def composite(Fimg, fpal, lines, core, pal_for_labels=None):
    rgb = fpal[Fimg].copy(); labl = Fimg.copy()
    for i, f in enumerate(lines):
        m = core == i + 1; rgb[m] = f["rgb"]
        if pal_for_labels is not None: labl[m] = nearest_pal(f["rgb"], pal_for_labels)
    return rgb, labl


def provenance(Fimg, rem, fc):
    """Per face: observed vs inferred pixel counts (face = 4-connected same-label component of the filled image)."""
    B, n = D.face_labels(Fimg); obs = np.bincount(B[~rem], minlength=n + 1); inf = np.bincount(B[rem], minlength=n + 1)
    rp = shapely.point_on_surface(np.asarray(fc["polys"], object)); H, W = Fimg.shape
    xs = np.clip(np.floor(shapely.get_x(rp)).astype(int), 0, W - 1); ys = np.clip(np.floor(shapely.get_y(rp)).astype(int), 0, H - 1)
    cid = B[ys, xs]; return obs[cid], inf[cid]
