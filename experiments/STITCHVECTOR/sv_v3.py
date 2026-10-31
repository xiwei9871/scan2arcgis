"""StitchVector 3.0 minimal line recovery (rules: sv_v3_prereg.json).

Detection is the 2.0 detector (sv_autoline, frozen P1 32e8a41) unchanged. Two small output changes:
  1 colour check at crossings: 2.0 joins skeleton chains straight through a junction when their directions line up.
    3.0 makes the same join only if the two chains also have similar colour (CIE76 dE <= join_col_dE). This stops a red
    and a black line that cross at a shallow angle from being chained into one object. With join_col_dE = inf the
    output is identical to 2.0 (unit-tested). The chains drawn are exactly those 2.0 draws (2.0 drops joined objects
    shorter than min_len; 3.0 decides that on the 2.0 grouping), so splitting never removes ink.
  2 logical_id: the resulting objects are grouped by the frozen line-recovery linker (sv_linker, 58cd05b). Geometry is
    not merged, bridged or dropped: each object keeps its own LineString, the group only adds a shared logical_id.
"""
import numpy as np, cv2, shapely
from shapely.geometry import LineString, MultiLineString
from scipy.ndimage import uniform_filter1d
from skimage.morphology import skeletonize
import sv_autoline as AL, sv_linker as LK, sv_d71 as D

Q = {"join_col_dE": 35.0}


def extract_v3(a, p=AL.P, join_col_dE=Q["join_col_dE"]):
    """Copy of sv_autoline.extract with one extra condition on the straight-through join (colour)."""
    con = AL.contrast(a, p["bg_median"]); fills = AL.fill_colours(a, con, p); prot = AL.protected(a, fills, p)
    ink = (con > p["c_ink"]) & ~prot
    sk = skeletonize(ink); dt = cv2.distanceTransform(np.pad(ink, 1).astype(np.uint8), cv2.DIST_L2, 5)[1:-1, 1:-1]
    chains, _ = D.skeleton_chains(sk)
    chains = [np.array(c, float) for c in chains if len(c) >= 2]
    deg = {}
    for c in chains:
        for e in (tuple(c[0]), tuple(c[-1])): deg[e] = deg.get(e, 0) + 1
    chains = [c for c in chains if not ((deg[tuple(c[0])] == 1) != (deg[tuple(c[-1])] == 1) and len(c) < p["spur"])]
    ccol = AL.lab(np.array([np.median(a[c[:, 0].astype(int), c[:, 1].astype(int)], 0) for c in chains], float)[None])[0] if chains else np.zeros((0, 3))
    ends = {}
    for i, c in enumerate(chains):
        ends.setdefault(tuple(c[0]), []).append((i, True)); ends.setdefault(tuple(c[-1]), []).append((i, False))
    parent = list(range(len(chains)))
    def f(i):
        while parent[i] != i: parent[i] = parent[parent[i]]; i = parent[i]
        return i
    cosmax = np.cos(np.radians(180 - p["join_deg"])); refused = 0
    par20 = list(range(len(chains)))                       # 2.0 grouping (no colour check), used only to decide what is drawn
    def f20(i):
        while par20[i] != i: par20[i] = par20[par20[i]]; i = par20[i]
        return i
    for node, es in ends.items():
        if len(es) < 2: continue
        dirs = [(i, s, AL._end_dir(chains[i], p["dir_k"], s)) for i, s in es]; used = set(); pairs = []
        for x in range(len(dirs)):
            for y in range(x + 1, len(dirs)):
                if dirs[x][0] != dirs[y][0]: pairs.append((float(dirs[x][2] @ dirs[y][2]), x, y))
        for cs, x, y in sorted(pairs):
            if cs <= cosmax and x not in used and y not in used: used |= {x, y}; par20[f20(dirs[x][0])] = f20(dirs[y][0])
    def smooth(c):
        xy = c[:, ::-1] + 0.5
        if len(xy) > 2 and p["smooth_win"] > 1: xy[1:-1] = uniform_filter1d(xy, p["smooth_win"], axis=0, mode="nearest")[1:-1]
        return LineString(xy)
    g20 = {}
    for i in range(len(chains)): g20.setdefault(f20(i), []).append(i)
    drawn = set()
    for idx in g20.values():                               # same length rule as 2.0 (smoothed, merged)
        segs = [smooth(chains[i]) for i in idx]; g = shapely.line_merge(shapely.union_all(segs)) if len(segs) > 1 else segs[0]
        if g.length >= p["min_len"]: drawn |= set(idx)
    for node, es in ends.items():
        if len(es) < 2: continue
        dirs = [(i, s, AL._end_dir(chains[i], p["dir_k"], s)) for i, s in es]; used = set(); pairs = []
        for x in range(len(dirs)):
            for y in range(x + 1, len(dirs)):
                if dirs[x][0] != dirs[y][0]: pairs.append((float(dirs[x][2] @ dirs[y][2]), x, y))
        for cs, x, y in sorted(pairs):
            if cs <= cosmax and x not in used and y not in used:
                if np.linalg.norm(ccol[dirs[x][0]] - ccol[dirs[y][0]]) > join_col_dE: refused += 1; continue
                used |= {x, y}; parent[f(dirs[x][0])] = f(dirs[y][0])
    groups = {}
    for i in range(len(chains)): groups.setdefault(f(i), []).append(i)
    lines = []
    for gid, idx in groups.items():
        segs = []
        for i in idx:
            c = chains[i][:, ::-1] + 0.5
            if len(c) > 2 and p["smooth_win"] > 1: c[1:-1] = uniform_filter1d(c, p["smooth_win"], axis=0, mode="nearest")[1:-1]
            segs.append(LineString(c))
        g = shapely.line_merge(shapely.union_all(segs)) if len(segs) > 1 else segs[0]
        if idx[0] not in drawn: continue                  # same chains as 2.0 are drawn; 3.0 only splits 2.0 objects
        g = g.simplify(p["eps_geom"])
        px = np.vstack([chains[i] for i in idx]).astype(int)
        lines.append({"geom": g, "width": float(np.median(2 * dt[px[:, 0], px[:, 1]] - 1).clip(1)),
                      "rgb": np.median(a[px[:, 0], px[:, 1]], 0).astype(np.uint8), "chains": len(idx)})
    return lines, {"contrast": con, "fills": fills, "protected": prot, "ink": ink, "joins_refused_by_colour": refused}


def group(a, objs):
    """logical_id from the frozen linker; geometry untouched."""
    if not objs: return [], {"links": [], "uncertain": []}
    frags = [{"geom": o["geom"], "rgb": o["rgb"], "width": o["width"]} for o in objs]; r = LK.link(frags, a); out = []
    for lid, lg in enumerate(r["logical"]):
        idx = lg["fragments"]; gs = [objs[i]["geom"] for i in idx]
        out.append({"logical_id": lid, "parts": idx, "geom": MultiLineString(gs) if len(gs) > 1 else gs[0],
                    "width": float(np.median([objs[i]["width"] for i in idx])), "rgb": lg["rgb"]})
    return out, r


def run(a, join_col_dE=Q["join_col_dE"]):
    objs, info = extract_v3(a, AL.P, join_col_dE); lg, r = group(a, objs); return objs, lg, r, info
