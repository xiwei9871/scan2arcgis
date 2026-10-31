"""Line detection Phase A: where along the frozen P1 detector (sv_autoline, 32e8a41) does each truth line get lost?
Descriptive only. Usage: sv_ld_stages.py <json_out> <img_dir> <seed> [<seed> ...]   (.venv-sv)

Stages (same code path as sv_autoline.extract, re-run step by step; final output checked identical):
  S1 candidate   contrast > c_ink
  S2 ink         S1 and not protected
  S3 skeleton    skeletonize(S2)
  S4 spur        skeleton chains left after spur removal
  S5 drawn       chains kept after joining + min_len (the chains 2.0 draws)
  S6 output      final simplified geometry
Per truth line, visible samples every 1 px (samples hidden under a LATER-drawn line are excluded). A sample is
covered at a stage if a stage pixel lies within r of it AND that pixel is attributed to this line: its nearest
truth axis is this one and no other axis is within 1.5 px of the pixel (so pixels of a neighbouring line or of a
shared crossing zone are never credited). r = half width + 1 for masks S1/S2, 2 px for S3-S6.
"""
import json, sys
from pathlib import Path
import numpy as np, cv2, shapely
from shapely.geometry import LineString
from scipy import ndimage as ndi
from scipy.ndimage import uniform_filter1d
from skimage.morphology import skeletonize
from PIL import Image, ImageDraw
import sv_synth as S, sv_autoline as AL, sv_d71 as D

TYPES = {"pale_1": "pale", "red_var_2to5": "var_width", "red_touch_fill": "touch_fill"}


def stages(a, p=AL.P):
    con = AL.contrast(a, p["bg_median"]); fills = AL.fill_colours(a, con, p); prot = AL.protected(a, fills, p)
    cand = con > p["c_ink"]; ink = cand & ~prot; sk = skeletonize(ink)
    chains, _ = D.skeleton_chains(sk); chains = [np.array(c, float) for c in chains if len(c) >= 2]
    deg = {}
    for c in chains:
        for e in (tuple(c[0]), tuple(c[-1])): deg[e] = deg.get(e, 0) + 1
    kept = [c for c in chains if not ((deg[tuple(c[0])] == 1) != (deg[tuple(c[-1])] == 1) and len(c) < p["spur"])]
    ends = {}
    for i, c in enumerate(kept): ends.setdefault(tuple(c[0]), []).append((i, True)); ends.setdefault(tuple(c[-1]), []).append((i, False))
    par = list(range(len(kept)))
    def f(i):
        while par[i] != i: par[i] = par[par[i]]; i = par[i]
        return i
    cosmax = np.cos(np.radians(180 - p["join_deg"]))
    for node, es in ends.items():
        if len(es) < 2: continue
        dirs = [(i, s, AL._end_dir(kept[i], p["dir_k"], s)) for i, s in es]; used = set(); pairs = []
        for x in range(len(dirs)):
            for y in range(x + 1, len(dirs)):
                if dirs[x][0] != dirs[y][0]: pairs.append((float(dirs[x][2] @ dirs[y][2]), x, y))
        for cs, x, y in sorted(pairs):
            if cs <= cosmax and x not in used and y not in used: used |= {x, y}; par[f(dirs[x][0])] = f(dirs[y][0])
    groups = {}
    for i in range(len(kept)): groups.setdefault(f(i), []).append(i)
    drawn = []
    for idx in groups.values():
        segs = []
        for i in idx:
            c = kept[i][:, ::-1] + 0.5
            if len(c) > 2 and p["smooth_win"] > 1: c[1:-1] = uniform_filter1d(c, p["smooth_win"], axis=0, mode="nearest")[1:-1]
            segs.append(LineString(c))
        g = shapely.line_merge(shapely.union_all(segs)) if len(segs) > 1 else segs[0]
        if g.length >= p["min_len"]: drawn += idx
    def cm(cs):
        m = np.zeros(a.shape[:2], bool)
        for c in cs: m[c[:, 0].astype(int), c[:, 1].astype(int)] = True
        return m
    out, _ = AL.extract(a, p)
    return {"con": con, "prot": prot, "S1": cand, "S2": ink, "S3": sk, "S4": cm(kept), "S5": cm([kept[i] for i in drawn]), "out": out}


def owner_map(truth, shape):
    H, W = shape; yy, xx = np.mgrid[0:H, 0:W]; P = shapely.points(xx.ravel() + 0.5, yy.ravel() + 0.5)
    d = np.stack([shapely.distance(P, LineString(t["axis"])).reshape(H, W) for t in truth["lines"]])
    o = d.argmin(0); s = np.sort(d, 0)
    o[(s[1] <= 1.5)] = -1                                  # pixel near two axes: crossing zone, credited to nobody
    return o, d


def occluded(truth, li, pts):
    occ = np.zeros(len(pts), bool)
    for t in truth["lines"][li + 1:]:
        occ |= shapely.distance(pts, LineString(t["axis"])) <= np.median(t["width"]) / 2 + 0.5
    return occ


def cover(mask, own, li, pts, r):
    ys, xs = np.nonzero(mask & (own == li))
    if not len(xs): return np.zeros(len(pts), bool)
    U = shapely.multipoints(np.c_[xs + 0.5, ys + 0.5]); return shapely.distance(pts, U) <= r


def analyse(seed):
    img, truth, _ = S.generate(seed); st = stages(img); own, dist = owner_map(truth, img.shape[:2])
    chk_out = st["out"]; res = {}
    for li, t in enumerate(truth["lines"]):
        g = LineString(t["axis"]); pts = shapely.line_interpolate_point(g, np.linspace(0, g.length, int(g.length) + 1))
        vis = ~occluded(truth, li, pts); w = np.asarray(t["width"]); wi = np.interp(np.linspace(0, 1, len(pts)), np.linspace(0, 1, len(w)), w)
        rmask = wi / 2 + 1.0; cov = {}
        for k in ("S1", "S2"): cov[k] = cover(st[k], own, li, pts, rmask)
        for k in ("S3", "S4", "S5"): cov[k] = cover(st[k], own, li, pts, 2.0)
        if chk_out:                                          # output geometry sampled every 0.5 px, same ownership rule
            parts = [q for o in chk_out for q in shapely.get_parts(o["geom"])]
            sp = np.vstack([shapely.get_coordinates(shapely.line_interpolate_point(q, np.arange(0, q.length + 0.5, 0.5))) for q in parts])
            xi_, yi_ = np.clip(sp[:, 0].astype(int), 0, 255), np.clip(sp[:, 1].astype(int), 0, 255)
            sp = sp[own[yi_, xi_] == li]
            cov["S6"] = shapely.distance(pts, shapely.multipoints(sp)) <= 2.0 if len(sp) else np.zeros(len(pts), bool)
        else: cov["S6"] = np.zeros(len(pts), bool)
        xy = shapely.get_coordinates(pts); xi = np.clip(xy[:, 0].astype(int), 0, 255); yi = np.clip(xy[:, 1].astype(int), 0, 255)
        nv = int(vis.sum()); row = {"type": TYPES.get(t["id"], "red_black"), "visible_px": nv}
        for k in ("S1", "S2", "S3", "S4", "S5", "S6"): row[k] = int((cov[k] & vis).sum())
        miss = vis & ~cov["S1"]
        row["S1_miss_contrast_on_axis_median"] = float(np.median(st["con"][yi[miss], xi[miss]])) if miss.any() else None
        lost2 = vis & cov["S1"] & ~cov["S2"]
        row["S2_loss_protected_share"] = float(st["prot"][yi[lost2], xi[lost2]].mean()) if lost2.any() else None
        res[t["id"]] = row
    return img, truth, st, res


def stage_sheet(img, truth, st, lid, k=6):
    t = [x for x in truth["lines"] if x["id"] == lid][0]; g = LineString(t["axis"])
    x0, y0, x1, y1 = [int(v) for v in g.buffer(6).bounds]; x0, y0 = max(0, x0), max(0, y0); x1, y1 = min(256, x1), min(256, y1)
    if (x1 - x0) * (y1 - y0) > 110 * 110:                                   # long line: crop around its worst stretch
        c = np.asarray(g.interpolate(0.5, normalized=True).coords[0]); x0, y0 = int(max(0, c[0] - 50)), int(max(0, c[1] - 50)); x1, y1 = min(256, x0 + 100), min(256, y0 + 100)
    def up(m): return np.kron(m, np.ones((k, k, 1) if m.ndim == 3 else (k, k), m.dtype))
    crop = lambda m: m[y0:y1, x0:x1]
    def mask_panel(m, col):
        base = (crop(img) * 0.35 + 255 * 0.65).astype(np.uint8); base[crop(m)] = col; return up(base)
    con = np.clip(crop(st["con"]) * 6, 0, 255).astype(np.uint8); con = up(np.stack([con] * 3, -1))
    outp = (crop(img) * 0.35 + 255 * 0.65).astype(np.uint8); outp = Image.fromarray(up(outp)); d = ImageDraw.Draw(outp)
    for o in st["out"]:
        for part in shapely.get_parts(o["geom"]): d.line([((x - x0) * k, (y - y0) * k) for x, y in part.coords], fill=(0, 90, 255), width=2)
    panels = [up(crop(img)), con, mask_panel(st["prot"], (0, 180, 0)), mask_panel(st["S2"], (230, 0, 0)), mask_panel(st["S3"], (0, 0, 0)),
              mask_panel(st["S4"], (0, 0, 0)), mask_panel(st["S5"], (0, 0, 200)), np.asarray(outp)]
    names = ["original", "contrast x6", "protected (green)", "ink mask (red)", "skeleton", "after spur", "drawn chains (2.0)", "output (2.0)"]
    gax = [((x - x0) * k, (y - y0) * k) for x, y in g.coords]
    ims = []
    for pnl in panels:
        im = Image.fromarray(np.ascontiguousarray(pnl)); ImageDraw.Draw(im).line(gax, fill=(255, 150, 0), width=1); ims.append(im)
    w, h = ims[0].size; sh = Image.new("RGB", (4 * (w + 6), 2 * (h + 18)), "white"); dd = ImageDraw.Draw(sh)
    for i, (im, n) in enumerate(zip(ims, names)):
        X, Y = (i % 4) * (w + 6), (i // 4) * (h + 18); sh.paste(im, (X, Y + 16)); dd.text((X + 2, Y + 2), n + " (orange = truth axis)", fill="black")
    return sh


def main(out, img_dir, seeds):
    Path(img_dir).mkdir(parents=True, exist_ok=True); res = {"seeds": seeds, "tiles": {}, "by_type": {}}
    for s in seeds:
        img, truth, st, r = analyse(s); res["tiles"][str(s)] = r
        for lid in TYPES: stage_sheet(img, truth, st, lid).save(Path(img_dir) / f"stages_{s}_{lid}.png")
    agg = {}
    for t in res["tiles"].values():
        for lid, row in t.items():
            a = agg.setdefault(row["type"], {k: 0 for k in ("visible_px", "S1", "S2", "S3", "S4", "S5", "S6")})
            for k in a: a[k] += row[k]
    for typ, a in agg.items():
        v = max(a["visible_px"], 1); prev = v; steps = {}
        for k, n in (("S1_candidate", "S1"), ("S2_ink", "S2"), ("S3_skeleton", "S3"), ("S4_spur", "S4"), ("S5_drawn", "S5"), ("S6_output", "S6")):
            steps[k] = {"kept_share": a[n] / v, "lost_here_share": (prev - a[n]) / v}; prev = a[n]
        res["by_type"][typ] = {"visible_px": a["visible_px"], "stages": steps}
    json.dump(res, open(out, "w"), indent=1, default=float)
    for typ, x in res["by_type"].items():
        print(typ.ljust(11), x["visible_px"], " ".join(f"{k}:{v['kept_share']:.2f}(-{v['lost_here_share']:.2f})" for k, v in x["stages"].items()))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], [int(x) for x in sys.argv[3:]])
