"""Line detection single-factor fixes on top of the frozen 2.0 detector (rules: sv_ld_prereg.json).

B0  frozen 2.0 (sv_autoline.extract), unchanged.
B1  short-chain rescue: 2.0 drops joined groups shorter than min_len. B1 keeps every 2.0 object unchanged and adds back a
    dropped short group only if the frozen linker (sv_linker, 58cd05b) puts it in the same logical group as other pieces
    whose total length is >= min_len (evidence: gap, direction, colour, width and ink along the bridge). Pure addition:
    2.0 geometry is never altered or removed.
B2  hysteresis: candidate = contrast > c_low connected to contrast > c_ink (skimage.filters.apply_hysteresis_threshold),
    everything else identical to 2.0 (protection, skeleton, spur, join, min_len).
B2a additive hysteresis: every 2.0 object kept unchanged; from the B2 output only the parts farther than add_r px from
    the 2.0 drawing and at least min_len long are added (so 2.0 lines are never moved, split or removed).
"""
import numpy as np, cv2, shapely
from shapely.geometry import LineString, MultiLineString
from scipy.ndimage import uniform_filter1d
from skimage.morphology import skeletonize
from skimage.filters import apply_hysteresis_threshold
import sv_autoline as AL, sv_linker as LK, sv_d71 as D

Q = {"c_low": 8.0, "add_r": 1.5}


def _pipeline(a, ink, p):
    """2.0 steps after the ink mask; returns (drawn objects, dropped short groups) as dicts with geom/width/rgb."""
    sk = skeletonize(ink); dt = cv2.distanceTransform(np.pad(ink, 1).astype(np.uint8), cv2.DIST_L2, 5)[1:-1, 1:-1]
    chains, _ = D.skeleton_chains(sk); chains = [np.array(c, float) for c in chains if len(c) >= 2]
    deg = {}
    for c in chains:
        for e in (tuple(c[0]), tuple(c[-1])): deg[e] = deg.get(e, 0) + 1
    chains = [c for c in chains if not ((deg[tuple(c[0])] == 1) != (deg[tuple(c[-1])] == 1) and len(c) < p["spur"])]
    ends = {}
    for i, c in enumerate(chains): ends.setdefault(tuple(c[0]), []).append((i, True)); ends.setdefault(tuple(c[-1]), []).append((i, False))
    par = list(range(len(chains)))
    def f(i):
        while par[i] != i: par[i] = par[par[i]]; i = par[i]
        return i
    cosmax = np.cos(np.radians(180 - p["join_deg"]))
    for node, es in ends.items():
        if len(es) < 2: continue
        dirs = [(i, s, AL._end_dir(chains[i], p["dir_k"], s)) for i, s in es]; used = set(); pairs = []
        for x in range(len(dirs)):
            for y in range(x + 1, len(dirs)):
                if dirs[x][0] != dirs[y][0]: pairs.append((float(dirs[x][2] @ dirs[y][2]), x, y))
        for cs, x, y in sorted(pairs):
            if cs <= cosmax and x not in used and y not in used: used |= {x, y}; par[f(dirs[x][0])] = f(dirs[y][0])
    groups = {}
    for i in range(len(chains)): groups.setdefault(f(i), []).append(i)
    drawn, short = [], []
    for idx in groups.values():
        segs = []
        for i in idx:
            c = chains[i][:, ::-1] + 0.5
            if len(c) > 2 and p["smooth_win"] > 1: c[1:-1] = uniform_filter1d(c, p["smooth_win"], axis=0, mode="nearest")[1:-1]
            segs.append(LineString(c))
        g = shapely.line_merge(shapely.union_all(segs)) if len(segs) > 1 else segs[0]
        px = np.vstack([chains[i] for i in idx]).astype(int)
        o = {"geom": g.simplify(p["eps_geom"]), "width": float(np.median(2 * dt[px[:, 0], px[:, 1]] - 1).clip(1)),
             "rgb": np.median(a[px[:, 0], px[:, 1]], 0).astype(np.uint8), "chains": len(idx)}
        (drawn if g.length >= p["min_len"] else short).append(o)
    return drawn, short


def ink_mask(a, p, hyst=None):
    con = AL.contrast(a, p["bg_median"]); fills = AL.fill_colours(a, con, p); prot = AL.protected(a, fills, p)
    cand = apply_hysteresis_threshold(con, hyst, p["c_ink"]) if hyst is not None else con > p["c_ink"]
    return cand & ~prot, con, prot


def b0(a, p=AL.P):
    return AL.extract(a, p)[0]


def b1(a, p=AL.P):
    ink, _, _ = ink_mask(a, p); drawn, short = _pipeline(a, ink, p)
    short = [s for s in short if s["geom"].length >= 2.0]
    if not short: return drawn, {"short_groups": 0, "rescued": 0}
    allf = drawn + short; r = LK.link([{"geom": o["geom"], "rgb": o["rgb"], "width": o["width"]} for o in allf], a)
    keep = []
    for lg in r["logical"]:
        idx = lg["fragments"]
        if sum(allf[i]["geom"].length for i in idx) >= p["min_len"]: keep += [i for i in idx if i >= len(drawn)]
    return drawn + [allf[i] for i in sorted(keep)], {"short_groups": len(short), "rescued": len(keep)}


def b2(a, p=AL.P, c_low=Q["c_low"]):
    ink, _, _ = ink_mask(a, p, c_low); drawn, _ = _pipeline(a, ink, p); return drawn, {}


def b2a(a, p=AL.P, c_low=Q["c_low"], add_r=Q["add_r"]):
    base = b0(a, p); new, _ = b2(a, p, c_low)
    if not base: return new, {"added": len(new)}
    U = shapely.union_all([o["geom"] for o in base]).buffer(add_r); add = []
    for o in new:
        for part in shapely.get_parts(shapely.difference(o["geom"], U)):
            if part.geom_type == "LineString" and part.length >= p["min_len"]: add.append({**o, "geom": part})
    return base + add, {"added": len(add)}
