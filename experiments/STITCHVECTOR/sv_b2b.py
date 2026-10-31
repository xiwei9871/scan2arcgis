"""B2b: B2a + centre-mixing check on the segments B2a adds (rules: sv_b2b_prereg.json).

B0 (frozen 2.0) objects are never touched. For every segment B2a adds, sample every 1 px along it:
  centre = the most deviating of the pixels at -1, 0, +1 px along the normal (the skeleton may sit 1 px off the stroke);
  sides  = mean CIE Lab of the pixels at w/2 + 2 and w/2 + 3 px on each side (outside the stroke, inside a 3 px band);
  dev    = CIE76 distance from the centre colour to the straight segment between the two side colours.
A fill edge is an anti-aliased mix of its two sides, so its centre lies near that segment (small dev); an ink stroke
has its own colour (large dev), whether its two sides are the same colour or not. A sample is unstable if the two
offsets on one side differ by more than side_dE (side region not uniform); the segment value is the median dev over
stable samples. A segment is kept if that median is >= dev_min. Halves are also reported (mixed segments).
"""
import numpy as np, shapely
from shapely.geometry import LineString
import sv_autoline as AL, sv_ld_fix as F

Q = {"dev_min": 8.0, "side_dE": 8.0, "min_stable": 0.3}


def _pt_seg(c, a, b):
    u = b - a; t = np.clip(((c - a) * u).sum(-1) / np.maximum((u * u).sum(-1), 1e-9), 0, 1)
    return np.linalg.norm(c - (a + t[..., None] * u), axis=-1)


def features(L, g, w, q=Q):
    H, W = L.shape[:2]; n = max(int(g.length), 1); s = np.linspace(0, g.length, n + 1)
    P = shapely.get_coordinates(shapely.line_interpolate_point(g, s))
    Pa = shapely.get_coordinates(shapely.line_interpolate_point(g, np.clip(s - 1, 0, g.length)))
    Pb = shapely.get_coordinates(shapely.line_interpolate_point(g, np.clip(s + 1, 0, g.length)))
    T = Pb - Pa; T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-9); N = np.c_[-T[:, 1], T[:, 0]]
    def at(off):
        q_ = P + N * off; x = np.clip(np.floor(q_[:, 0]).astype(int), 0, W - 1); y = np.clip(np.floor(q_[:, 1]).astype(int), 0, H - 1); return L[y, x]
    r1, r2 = w / 2 + 2, w / 2 + 3
    l1, l2, ri1, ri2 = at(-r1), at(-r2), at(r1), at(r2)
    left, right = (l1 + l2) / 2, (ri1 + ri2) / 2
    stable = (np.linalg.norm(l1 - l2, axis=1) <= q["side_dE"]) & (np.linalg.norm(ri1 - ri2, axis=1) <= q["side_dE"])
    dev = np.max(np.stack([_pt_seg(at(o), left, right) for o in (-1.0, 0.0, 1.0)]), 0)
    st = stable
    med = float(np.median(dev[st])) if st.any() else float(np.median(dev))
    h = len(dev) // 2
    half = [float(np.median(dev[:h][st[:h]])) if st[:h].any() else None, float(np.median(dev[h:][st[h:]])) if st[h:].any() else None]
    side_diff = float(np.median(np.linalg.norm(left - right, axis=1)))
    return {"dev_median": med, "stable_share": float(st.mean()), "halves": half, "side_diff_median": side_diff,
            "centre_vs_sides_dL": float(np.median(at(0.0)[:, 0] - np.minimum(left[:, 0], right[:, 0]))), "_dev": dev, "_stable": st}


def added(a, p=AL.P):
    base = F.b0(a, p); allo, _ = F.b2a(a, p); return base, allo[len(base):]


def b2b(a, p=AL.P, q=Q):
    base, add = added(a, p); L = AL.lab(a); keep, info = [], []
    for o in add:
        f = features(L, o["geom"], o["width"], q)
        ok = f["dev_median"] >= q["dev_min"] and f["stable_share"] >= q["min_stable"]
        if not f["stable_share"] >= q["min_stable"]: ok = True          # sides not measurable: keep (do not delete what we cannot judge)
        info.append({**{k: v for k, v in f.items() if not k.startswith("_")}, "kept": bool(ok), "length": float(o["geom"].length)})
        if ok: keep.append(o)
    return base + keep, {"added": len(add), "kept": len(keep), "segments": info}


def label(g, truth, faces, bands, tol=2.0):
    """Length-weighted ground-truth label of a segment: true_line / fill_edge / band_edge / other (evaluation only)."""
    L = g.length; parts = {}
    T = shapely.union_all([LineString(t["axis"]) for t in truth["lines"]]).buffer(tol)
    E = shapely.union_all([shapely.Polygon(f).exterior for f in faces]).buffer(2.5) if faces else None
    B = shapely.union_all([LineString(b["axis"]).buffer(b["width"] / 2 + 2) for b in bands]) if bands else None
    rest = g; parts["true_line"] = shapely.intersection(rest, T).length; rest = shapely.difference(rest, T)
    if E is not None: parts["fill_edge"] = shapely.intersection(rest, E).length; rest = shapely.difference(rest, E)
    if B is not None: parts["band_edge"] = shapely.intersection(rest, B).length; rest = shapely.difference(rest, B)
    parts["other"] = rest.length
    return max(parts, key=parts.get), {k: v / max(L, 1e-9) for k, v in parts.items()}
