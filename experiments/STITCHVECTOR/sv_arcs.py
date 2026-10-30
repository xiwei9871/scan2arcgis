"""R2 amendment 1: integer label partition + one shared arc network.

The label image (one label per pixel) is the only truth. Boundaries between differently labelled pixels (and the
window border) form a planar graph on the integer pixel-corner grid. Chains between nodes (degree != 2) are arcs;
each arc is stored and simplified ONCE, so neighbouring faces always share the same simplified geometry.
Faces are rebuilt from all arcs with shapely.polygonize and labelled by a pixel inside them.

Progressive 4 -> 2 -> 1 -> 0: arcs start at tolerance 4; after each stage the faces are rasterised and compared with
the label image; arcs near mismatching pixels (and arcs that cross other arcs) drop to the next tolerance. Arcs
that render correctly keep their coarser geometry. Tolerance 0 = exact pixel-edge arc, so the last stage is exact.
"""
import numpy as np, shapely
from shapely.geometry import LineString, Polygon
import rasterio.features as RF
from rasterio.transform import Affine

ID = Affine.identity()


def boundary_edges(lab):
    """Unit edges on the corner grid that separate different labels (window border included)."""
    H, W = lab.shape; P = np.pad(lab, 1, constant_values=-(10 ** 9))
    hz = P[:-1, 1:-1] != P[1:, 1:-1]          # (H+1, W): edge (x,y)-(x+1,y) between rows y-1 and y
    vt = P[1:-1, :-1] != P[1:-1, 1:]          # (H, W+1): edge (x,y)-(x,y+1) between cols x-1 and x
    return hz, vt


def arcs_from_labels(lab):
    """-> list of exact arcs, each an (N,2) float array of corner coordinates (x, y)."""
    H, W = lab.shape; hz, vt = boundary_edges(lab)
    adj = {}
    def add(a, b):
        adj.setdefault(a, []).append(b); adj.setdefault(b, []).append(a)
    for y, x in zip(*np.nonzero(hz)): add((x, y), (x + 1, y))
    for y, x in zip(*np.nonzero(vt)): add((x, y), (x, y + 1))
    used = set(); arcs = []
    def key(a, b): return (a, b) if a < b else (b, a)
    def walk(s, n):
        pts = [s, n]; used.add(key(s, n)); prev, cur = s, n
        while len(adj[cur]) == 2:
            nxt = adj[cur][0] if adj[cur][1] == prev else adj[cur][1]
            if key(cur, nxt) in used: break
            used.add(key(cur, nxt)); pts.append(nxt); prev, cur = cur, nxt
        return pts
    for v, nb in adj.items():
        if len(nb) != 2:
            for n in nb:
                if key(v, n) not in used: arcs.append(np.array(walk(v, n), float))
    for v, nb in adj.items():                 # closed loops with no node (islands)
        for n in nb:
            if key(v, n) not in used: arcs.append(np.array(walk(v, n), float))
    return arcs


def _split_at(a, keep):
    """Split an open polyline at interior vertices flagged in keep (bool per vertex)."""
    idx = [0] + [i for i in range(1, len(a) - 1) if keep[i]] + [len(a) - 1]
    return [a[i:j + 1] for i, j in zip(idx[:-1], idx[1:])]


def simplify_arc(a, t, corners=None):
    if t == 0 or len(a) <= 2: return a
    if corners is not None:                   # window corners are fixed vertices (found by the synthetic planar
        keep = np.zeros(len(a), bool)         # test: an arc turning a corner lost a 32 px triangle)
        for c in corners: keep |= (a == c).all(1)
        if keep[1:-1].any():
            parts = [simplify_arc(q, t) for q in _split_at(a, keep)]
            return np.vstack([parts[0]] + [q[1:] for q in parts[1:]])
    if (a[0] == a[-1]).all():                 # closed: split at the farthest point so it cannot collapse
        k = int(np.argmax(((a - a[0]) ** 2).sum(1)))
        p = np.asarray(shapely.simplify(LineString(a[:k + 1]), t).coords)
        q = np.asarray(shapely.simplify(LineString(a[k:]), t).coords)
        r = np.vstack([p, q[1:]])
        # a closed arc bounds an isolated face; if simplification leaves < 3 distinct vertices (zero-area ring)
        # the face would vanish, so keep the exact arc (found by the synthetic planar test before any real run)
        if len(r) < 4 or Polygon(r).area <= 0: return a
        return r
    return np.asarray(shapely.simplify(LineString(a), t).coords)


def crossing_arcs(lines):
    """Indices of arcs that intersect another arc anywhere except at shared endpoints."""
    g = np.asarray(lines, object); tree = shapely.STRtree(g)
    i, j = tree.query(g, predicate="intersects"); m = i < j; i, j = i[m], j[m]
    bad = set()
    ends = [shapely.multipoints([l.coords[0], l.coords[-1]]) for l in g]
    for a, b in zip(i, j):
        x = shapely.intersection(g[a], g[b])
        if x.is_empty: continue
        if not shapely.covered_by(x, shapely.intersection(ends[a], ends[b]).buffer(1e-9)): bad.update((a, b))
    return np.array(sorted(bad), int)


def faces(lines, lab):
    """Polygonize all arcs; label each face by the label image at a pixel inside it."""
    H, W = lab.shape
    polys = list(shapely.get_parts(shapely.polygonize(np.asarray(lines, object))))
    rp = shapely.point_on_surface(np.asarray(polys, object))
    xs = np.clip(np.floor(shapely.get_x(rp)).astype(int), 0, W - 1); ys = np.clip(np.floor(shapely.get_y(rp)).astype(int), 0, H - 1)
    return polys, lab[ys, xs]


def render(polys, vals, h, w):
    s = [(p, int(v)) for p, v in zip(polys, vals)]
    return RF.rasterize(s, out_shape=(h, w), fill=-1, transform=ID, all_touched=False, dtype="int64")


def build(arcs, tol, lab):
    H, W = lab.shape; corners = np.array([[0, 0], [W, 0], [W, H], [0, H]], float)
    lines = [LineString(simplify_arc(a, t, corners)) for a, t in zip(arcs, tol)]
    return lines, *faces(lines, lab)


def progressive(lab, stages=(4, 2, 1, 0)):
    """Returns (polys, vals, lines, log). Final stage tolerance 0 is exact by construction."""
    H, W = lab.shape; arcs = arcs_from_labels(lab); exact = [LineString(a) for a in arcs]
    tree = shapely.STRtree(np.asarray(exact, object))
    tol = np.full(len(arcs), stages[0], float); log = []
    for si, t in enumerate(stages):
        while True:                           # validity fallback inside a stage: crossing arcs go to 0
            lines, polys, vals = build(arcs, tol, lab); bad = crossing_arcs(lines)
            bad = bad[tol[bad] > 0] if len(bad) else bad
            if not len(bad): break
            tol[bad] = 0
        R = render(polys, vals, H, W); res = R != lab
        rec = {"stage_tol": t, "arcs": len(arcs), "arcs_at_tol": {str(k): int((tol == k).sum()) for k in np.unique(tol)},
               "faces": len(polys), "vertices": int(sum(len(l.coords) for l in lines)), "mismatch_px": int(res.sum())}
        log.append(rec)
        if not res.any() or si == len(stages) - 1: break
        ys, xs = np.nonzero(res)
        pts = shapely.points(xs + 0.5, ys + 0.5)
        _, hit = tree.query(pts, predicate="dwithin", distance=t + 1.0)
        hit = np.unique(hit); nxt = stages[si + 1]
        hit = hit[tol[hit] > nxt]; tol[hit] = nxt; rec["arcs_lowered"] = int(len(hit))
    return polys, vals, lines, log


def single_pass(lab, t):
    arcs = arcs_from_labels(lab); tol = np.full(len(arcs), float(t))
    while True:
        lines, polys, vals = build(arcs, tol, lab); bad = crossing_arcs(lines)
        bad = bad[tol[bad] > 0] if len(bad) else bad
        if not len(bad): break
        tol[bad] = 0
    return polys, vals, lines, int((tol == 0).sum()) if t > 0 else 0


def topology(polys, h, w):
    g = np.asarray(polys, object); s = float(shapely.area(g).sum()); u = float(shapely.area(shapely.union_all(g)))
    return {"area_sum_equals_window": abs(s - h * w) < 1e-6, "union_area_equals_window": abs(u - h * w) < 1e-6,
            "coverage_is_valid_strict": bool(shapely.coverage_is_valid(g))}
