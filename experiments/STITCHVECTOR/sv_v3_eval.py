"""Score 2.0 objects vs 3.0 logical objects against synthetic truth (geometry only).
own_share: a logical object belongs to a truth line if >= 60% of its length is within 2 px of it.
mixed: a logical object running >= 10 px along 2+ truth lines, counting only length that is near ONE line (outside the
  zone where two lines are both within 2 px, so a correct object passing a shallow crossing is not counted).
select_count: logical objects belonging to the line = objects a user must pick to select the whole line."""
import numpy as np, shapely
from shapely.geometry import LineString

TOL = 2.0


def score(objs, truth):
    T = [LineString(t["axis"]) for t in truth["lines"]]; Tb = [g.buffer(TOL) for g in T]
    geoms = [o["geom"] for o in objs]
    al = np.array([[shapely.length(shapely.intersection(g, b)) for b in Tb] for g in geoms]) if geoms else np.zeros((0, len(T)))
    Tx = [shapely.difference(Tb[i], shapely.union_all([Tb[j] for j in range(len(Tb)) if j != i])) for i in range(len(Tb))]
    ax = np.array([[shapely.length(shapely.intersection(g, b)) for b in Tx] for g in geoms]) if geoms else al
    L = np.array([g.length for g in geoms]); sh = al / np.maximum(L[:, None], 1e-9) if len(geoms) else al
    mixed = (ax >= 10).sum(1) >= 2 if len(geoms) else np.zeros(0, bool)      # >= 10 px on 2+ lines OUTSIDE their shared crossing zone
    own = np.where((sh.max(1) >= 0.6) & ~mixed, sh.argmax(1), -1) if len(geoms) else np.zeros(0, int)
    U = shapely.union_all(geoms) if geoms else None; per = {}
    for i, t in enumerate(truth["lines"]):
        g = T[i]; pts = shapely.line_interpolate_point(g, np.linspace(0, g.length, int(g.length) + 1))
        rec = float((shapely.distance(pts, U) <= TOL).mean()) if U is not None else 0.0
        mine = [geoms[j] for j in np.nonzero(own == i)[0]]; Um = shapely.union_all(mine) if mine else None
        rec_own = float((shapely.distance(pts, Um) <= TOL).mean()) if Um is not None else 0.0
        mix_on = int(sum(1 for j in np.nonzero(mixed)[0] if ax[j, i] >= 10))
        per[t["id"]] = {"recall": rec, "recall_own": rec_own, "select_count": len(mine), "mixed_objects_on_line": mix_on}
    return {"objects": len(geoms), "mixed_objects": int(mixed.sum()), "mixed_length": float(L[mixed].sum()) if len(geoms) else 0.0,
            "unowned_objects": int((own == -1).sum() - mixed.sum()) if len(geoms) else 0, "lines": per, "_own": own, "_mixed": mixed}


def verdict(m, rec_ok=0.9, sel_ok=2):
    if m["mixed_objects_on_line"] > 0: return "cross_line_error"
    if m["recall_own"] >= rec_ok and m["select_count"] <= sel_ok: return "acceptable"
    if m["recall_own"] >= rec_ok: return "found_needs_grouping"
    return "visual_miss"
