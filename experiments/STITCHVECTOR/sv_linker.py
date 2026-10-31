"""S2 line-fragment linker (rules: sv_lr_prereg.json). Label-free.

Input: fragments (LineString in pixel-edge coordinates, rgb, width) and the original RGB image.
Evidence for a link between two fragment ends: gap length, end tangents (measured tan_skip..tan_skip+tan_len px back
from each end, so distorted skeleton tails do not decide), colour and width of the two fragments, and the image along a
cubic Hermite curve between the ends: a sample supports the link if it is ink (contrast > c_low) of the fragments' colour;
a sample that matches the colour of ANOTHER fragment within occl_r px is neutral (occluded by a crossing line).
Pairing: maximum-weight matching over all accepted candidates (each end links at most once). A matched pair whose
cost is within `margin` of the best alternative for either end is withheld as UNCERTAIN. Links are CONFIRMED (short and
fully supported), INFERRED, or INFERRED_OCCLUDED (no visible evidence: continuation hidden by another line).
"""
import numpy as np, networkx as nx, shapely, cv2
from shapely.geometry import LineString
from skimage.color import rgb2lab

P = {"r_max": 24.0, "touch": 1.0, "tan_skip": 2.0, "tan_len": 8.0, "ang_max": 45.0, "ang_max_long": 25.0, "long_d": 8.0, "ang_touch": 30.0, "touch_col_dE": 15.0,
     "bg_median": 15, "c_low": 6.0, "col_dE": 20.0, "frag_col_dE": 35.0, "width_diff": 2.5, "s_min": 0.7, "occl_r": 6.0, "occl_ang": 25.0,
     "occl_dmax": 24.0, "w_ang": 1.0, "w_sup": 1.0, "margin": 0.15, "confirm_d": 3.0, "confirm_s": 0.9}


def lab(x): return rgb2lab(np.asarray(x, np.float64) / 255.0)


def contrast(a, k): return np.sqrt(((lab(a) - lab(cv2.medianBlur(a, k))) ** 2).sum(-1))


def end_info(g, at_start, p):
    L = g.length; c0 = np.asarray(g.coords[0] if at_start else g.coords[-1], float)
    s0 = min(p["tan_skip"], 0.25 * L); s1 = min(p["tan_skip"] + p["tan_len"], L)
    if at_start: a, b = g.interpolate(s0), g.interpolate(s1)
    else: a, b = g.interpolate(L - s0), g.interpolate(L - s1)
    v = np.array([a.x - b.x, a.y - b.y]); n = np.hypot(*v)
    return c0, (v / n if n > 0 else v)


def hermite(pa, ta, pb, tb, n):
    d = np.linalg.norm(pb - pa); m0 = ta * d; m1 = -tb * d; t = (np.arange(1, n + 1) / (n + 1))[:, None]
    h00, h10, h01, h11 = 2 * t ** 3 - 3 * t ** 2 + 1, t ** 3 - 2 * t ** 2 + t, -2 * t ** 3 + 3 * t ** 2, t ** 3 - t ** 2
    return h00 * pa + h10 * m0 + h01 * pb + h11 * m1


def _ang(u, v): return float(np.degrees(np.arccos(np.clip(u @ v, -1, 1))))


def link(frags, img, p=P, con=None):
    """frags: list of dicts with geom (LineString), rgb, width. Returns dict with links, uncertain, ends, logical."""
    H, W = img.shape[:2]; con = contrast(img, p["bg_median"]) if con is None else con; L_img = lab(img)
    geoms = [f["geom"] for f in frags]; cols = lab(np.array([f["rgb"] for f in frags], float)[None])[0]
    widths = np.array([float(f["width"]) for f in frags]); ftree = shapely.STRtree(np.asarray(geoms, object))
    ends = []
    for i, g in enumerate(geoms):
        for s in (0, 1):
            c, t = end_info(g, s == 0, p); ends.append({"id": (i, s), "frag": i, "pos": c, "tan": t})
    pts = shapely.points(np.array([e["pos"] for e in ends])); etree = shapely.STRtree(pts)
    cand = {}
    for ia, ib in zip(*etree.query(pts, predicate="dwithin", distance=p["r_max"])):
        if ia >= ib: continue
        A, B = ends[ia], ends[ib]
        if A["frag"] == B["frag"]: continue
        if np.linalg.norm(cols[A["frag"]] - cols[B["frag"]]) > p["frag_col_dE"] or abs(widths[A["frag"]] - widths[B["frag"]]) > p["width_diff"]: continue
        d = float(np.linalg.norm(B["pos"] - A["pos"]))
        if d <= p["touch"]:
            bend = 180 - _ang(A["tan"], B["tan"])
            if bend > p["ang_touch"] or np.linalg.norm(cols[A["frag"]] - cols[B["frag"]]) > p["touch_col_dE"]: continue
            ta = tb = bend / 2; sup, occ, status = 1.0, 0.0, "CONFIRMED"
        else:
            u = (B["pos"] - A["pos"]) / d; ta, tb = _ang(A["tan"], u), _ang(B["tan"], -u)
            amax = p["ang_max"] if d <= p["long_d"] else p["ang_max_long"]
            if ta > amax or tb > amax: continue
            curve = hermite(A["pos"], A["tan"], B["pos"], B["tan"], max(int(np.ceil(d)), 2))
            xs = np.clip(np.floor(curve[:, 0]).astype(int), 0, W - 1); ys = np.clip(np.floor(curve[:, 1]).astype(int), 0, H - 1)
            col_ab = (cols[A["frag"]] + cols[B["frag"]]) / 2; sl = L_img[ys, xs]
            own = (con[ys, xs] > p["c_low"]) & (np.linalg.norm(sl - col_ab, axis=1) < p["col_dE"])
            neutral = np.zeros(len(curve), bool)
            for k, q in enumerate(shapely.points(curve)):
                near = [j for j in ftree.query(q, predicate="dwithin", distance=p["occl_r"]) if j not in (A["frag"], B["frag"])]
                neutral[k] = any(np.linalg.norm(sl[k] - cols[j]) < p["col_dE"] for j in near)
            counted = ~neutral | own; occ = float(1 - counted.mean())
            if counted.sum() == 0:
                if d > p["occl_dmax"] or ta > p["occl_ang"] or tb > p["occl_ang"]: continue
                sup, status = 0.5, "INFERRED_OCCLUDED"
            else:
                sup = float(own[counted].mean())
                if sup < p["s_min"]: continue
                status = "CONFIRMED" if d <= p["confirm_d"] and sup >= p["confirm_s"] else "INFERRED"
        cost = d / p["r_max"] + p["w_ang"] * (ta + tb) / 180 + p["w_sup"] * (1 - sup)
        cand[(ia, ib)] = {"d": d, "theta": [ta, tb], "support": sup, "occluded_share": occ, "status": status, "cost": cost}
    G = nx.Graph()
    for (a, b), c in cand.items(): G.add_edge(a, b, weight=10.0 - c["cost"])
    M = nx.max_weight_matching(G)
    links, unc = [], []
    for a, b in M:
        a, b = min(a, b), max(a, b); c = cand[(a, b)]
        alt = [cand[k]["cost"] for k in cand if k != (a, b) and (a in k or b in k)]
        rec = {"a": ends[a]["id"], "b": ends[b]["id"], **c}
        (unc if alt and min(alt) - c["cost"] < p["margin"] else links).append(rec)
    linked = {r["a"] for r in links} | {r["b"] for r in links}; uncs = {r["a"] for r in unc} | {r["b"] for r in unc}
    end_state = {e["id"]: ("LINKED" if e["id"] in linked else "UNCERTAIN" if e["id"] in uncs else
                           ("CANDIDATES_REJECTED" if any(ends.index(e) in k for k in cand) else "END")) for e in ends}
    parent = list(range(len(frags)))
    def f(i):
        while parent[i] != i: parent[i] = parent[parent[i]]; i = parent[i]
        return i
    for r in links: parent[f(r["a"][0])] = f(r["b"][0])
    groups = {}
    for i in range(len(frags)): groups.setdefault(f(i), []).append(i)
    logical = []
    for idx in groups.values():
        segs = [geoms[i] for i in idx]
        for r in links:
            if r["a"][0] in idx:
                A = ends[2 * r["a"][0] + r["a"][1]]; B = ends[2 * r["b"][0] + r["b"][1]]
                segs.append(LineString(np.vstack([A["pos"], hermite(A["pos"], A["tan"], B["pos"], B["tan"], max(int(np.ceil(r["d"])), 2)), B["pos"]])))
        g = shapely.line_merge(shapely.union_all(segs)) if len(segs) > 1 else segs[0]
        logical.append({"fragments": idx, "geom": g, "width": float(np.median(widths[idx])),
                        "rgb": np.median(np.array([frags[i]["rgb"] for i in idx]), 0).astype(np.uint8)})
    return {"links": links, "uncertain": unc, "ends": end_state, "logical": logical, "candidates": len(cand)}
