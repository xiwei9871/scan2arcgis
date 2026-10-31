"""Automatic visual-line extraction, label-free (rules: sv_autoline_prereg.json).

1 contrast = CIE76 dE of each pixel to a bg_median x bg_median median of the image (no colour classes, so one
  anti-aliased line with several shades stays one connected ink region: D71 failure 1).
2 fill colours = 16-colour median cut of low-contrast pixels that survive an open_px opening, kept if >= fill_min px.
3 protected (never line): pixels within fill_dE of a fill colour, or within mix_tol (RGB) of the segment between
  two fill colours (anti-aliased fill/fill edges and narrow fill-coloured bands). A line whose colour differs from an
  adjacent fill by more than fill_dE (red ink on red fill) is NOT protected (D71 failure 2).
4 line ink = contrast > c_ink and not protected; skeleton; chains between nodes; spurs < spur px dropped;
  chains joined through junctions when their end directions are within join_deg of straight (logical lines);
  chains shorter than min_len after joining dropped. Smoothed, simplified at eps_geom. Width = 2 * EDT on the
  skeleton (median), colour = median original on the skeleton.
"""
import numpy as np, cv2
from scipy import ndimage as ndi
from scipy.ndimage import uniform_filter1d
from skimage.morphology import skeletonize
from skimage.color import rgb2lab
from PIL import Image
import shapely
from shapely.geometry import LineString
import sv_d71 as D

P = {"bg_median": 15, "c_ink": 12.0, "open_px": 7, "fill_min": 300, "fill_dE": 10.0, "mix_tol": 12.0,
     "spur": 4, "join_deg": 35.0, "dir_k": 5, "min_len": 10.0, "smooth_win": 5, "eps_geom": 1.0}


def lab(x): return rgb2lab(np.asarray(x, np.float64) / 255.0)


def contrast(a, k): return np.sqrt(((lab(a) - lab(cv2.medianBlur(a, k))) ** 2).sum(-1))


def fill_colours(a, con, p):
    low = con < p["c_ink"]; wide = ndi.binary_opening(low, np.ones((p["open_px"], p["open_px"]), bool))
    q = Image.fromarray(a).quantize(colors=16, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    l = np.asarray(q); pal = np.asarray(q.getpalette()[:48], np.uint8).reshape(-1, 3)
    cnt = np.bincount(l[wide], minlength=16); keep = np.nonzero(cnt >= p["fill_min"])[0]
    cols = []
    for k in keep: cols.append(np.median(a[wide & (l == k)], 0))
    cols = np.array(cols, float); out = []
    for c in cols:                                            # merge near-duplicate fill shades
        if not any(np.linalg.norm(lab(c[None, None])[0, 0] - lab(o[None, None])[0, 0]) < p["fill_dE"] for o in out): out.append(c)
    return np.array(out)


def protected(a, fills, p):
    L = lab(a); FL = lab(fills[None])[0]
    near = np.sqrt(((L[..., None, :] - FL[None, None]) ** 2).sum(-1)).min(-1) < p["fill_dE"]
    A = a.astype(float); mix = np.zeros(a.shape[:2], bool)
    for i in range(len(fills)):
        for j in range(i + 1, len(fills)):
            u = fills[j] - fills[i]; t = np.clip(((A - fills[i]) @ u) / max(u @ u, 1e-9), 0, 1)
            mix |= np.linalg.norm(A - (fills[i] + t[..., None] * u), axis=-1) < p["mix_tol"]
    return near | mix


def _end_dir(c, k, at_start):
    seg = c[:k + 1] if at_start else c[::-1][:k + 1]
    v = seg[0] - seg[-1]; n = np.hypot(*v); return v / n if n > 0 else v


def extract(a, p=P):
    con = contrast(a, p["bg_median"]); fills = fill_colours(a, con, p); prot = protected(a, fills, p)
    ink = (con > p["c_ink"]) & ~prot
    sk = skeletonize(ink); dt = cv2.distanceTransform(np.pad(ink, 1).astype(np.uint8), cv2.DIST_L2, 5)[1:-1, 1:-1]
    chains, _ = D.skeleton_chains(sk)
    chains = [np.array(c, float) for c in chains if len(c) >= 2]
    deg = {}
    for c in chains:
        for e in (tuple(c[0]), tuple(c[-1])): deg[e] = deg.get(e, 0) + 1
    chains = [c for c in chains if not ((deg[tuple(c[0])] == 1) != (deg[tuple(c[-1])] == 1) and len(c) < p["spur"])]
    ends = {}
    for i, c in enumerate(chains):
        ends.setdefault(tuple(c[0]), []).append((i, True)); ends.setdefault(tuple(c[-1]), []).append((i, False))
    parent = list(range(len(chains)))
    def f(i):
        while parent[i] != i: parent[i] = parent[parent[i]]; i = parent[i]
        return i
    cosmax = np.cos(np.radians(180 - p["join_deg"]))
    for node, es in ends.items():
        if len(es) < 2: continue
        dirs = [(i, s, _end_dir(chains[i], p["dir_k"], s)) for i, s in es]; used = set(); pairs = []
        for x in range(len(dirs)):
            for y in range(x + 1, len(dirs)):
                if dirs[x][0] != dirs[y][0]: pairs.append((float(dirs[x][2] @ dirs[y][2]), x, y))
        for cs, x, y in sorted(pairs):
            if cs <= cosmax and x not in used and y not in used: used |= {x, y}; parent[f(dirs[x][0])] = f(dirs[y][0])
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
        if g.length < p["min_len"]: continue
        g = g.simplify(p["eps_geom"])
        px = np.vstack([chains[i] for i in idx]).astype(int)
        lines.append({"geom": g, "width": float(np.median(2 * dt[px[:, 0], px[:, 1]] - 1).clip(1)),
                      "rgb": np.median(a[px[:, 0], px[:, 1]], 0).astype(np.uint8), "chains": len(idx)})
    return lines, {"contrast": con, "fills": fills, "protected": prot, "ink": ink}
