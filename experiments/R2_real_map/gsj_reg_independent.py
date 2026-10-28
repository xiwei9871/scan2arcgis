"""Fill-colour-independent registration check for GSJ sheets.

Signal: black-hat (closing - image) of the grey image, which responds to thin dark lines and is
~0 on colour steps between flat fills. GSJ prints geologic contacts and the neatline as thin
lines, but contours/text also respond, so a per-pixel test is not discriminative (see
gsj_reg_check.py). Instead, average the black-hat patch around many official contact pixels:
lines unrelated to the contacts (contours, hachures, text) average to a flat background, while
the printed contact line produces a peak at the true offset. The peak position is the
residual misregistration; the peak contrast says whether the signal is trustworthy.

The same is done for the four projected neatline sides (1-D perpendicular profile).
Nothing here uses fill colour or the unit labels, only geo_L geometry and the homography.
"""
import json, sys
from pathlib import Path
import cv2, numpy as np, geopandas as gpd, warnings

sys.path.insert(0, str(Path(__file__).parent))
from gsj_gt import lines, to_px  # noqa: E402
from gsj_reg_check import contact_pts, grid_cells  # noqa: E402
warnings.filterwarnings("ignore")
R = 20


def blackhat(rgb):
    g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    return cv2.morphologyEx(g, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))).astype(np.float32)


def mean_patch(bh, pts, rng, n_max=15000):
    h, w = bh.shape
    p = np.round(pts).astype(int)
    p = p[(p[:, 0] >= R) & (p[:, 0] < w - R) & (p[:, 1] >= R) & (p[:, 1] < h - R)]
    if len(p) > n_max: p = p[rng.choice(len(p), n_max, replace=False)]
    oy, ox = np.mgrid[-R:R + 1, -R:R + 1]
    acc = np.zeros((2 * R + 1, 2 * R + 1), np.float64)
    for chunk in np.array_split(p, max(1, len(p) // 2000)):
        acc += bh[chunk[:, 1, None, None] + oy[None], chunk[:, 0, None, None] + ox[None]].sum(0)
    return acc / len(p), len(p)


def peak(patch):
    bg = np.median(patch); sd = patch.std() + 1e-9
    y, x = np.unravel_index(np.argmax(patch), patch.shape)
    def sub(a, b, c): d = a - 2 * b + c; return 0.0 if abs(d) < 1e-9 else 0.5 * (a - c) / d
    dx = x - R + (sub(patch[y, x - 1], patch[y, x], patch[y, x + 1]) if 0 < x < 2 * R else 0)
    dy = y - R + (sub(patch[y - 1, x], patch[y, x], patch[y + 1, x]) if 0 < y < 2 * R else 0)
    centre = patch[R, R]
    return {"dx": float(dx), "dy": float(dy), "contrast_z": float((patch.max() - bg) / sd),
            "centre_vs_peak": float((centre - bg) / (patch.max() - bg + 1e-9))}


def side_profiles(bh, H, b):
    q = np.array([[b[0], b[3]], [b[2], b[3]], [b[2], b[1]], [b[0], b[1]]], np.float64)
    c = to_px(q, H); out = {}
    for name, (i, j) in {"top": (0, 1), "right": (1, 2), "bottom": (2, 3), "left": (3, 0)}.items():
        a, e = c[i], c[j]; t = np.linspace(0.05, 0.95, 4000)[:, None]
        pts = a + t * (e - a); d = (e - a) / np.linalg.norm(e - a); nrm = np.array([-d[1], d[0]])
        offs = np.arange(-60, 61)
        prof = []
        for o in offs:
            pp = np.round(pts + o * nrm).astype(int)
            ok = (pp[:, 0] >= 0) & (pp[:, 0] < bh.shape[1]) & (pp[:, 1] >= 0) & (pp[:, 1] < bh.shape[0])
            prof.append(bh[pp[ok, 1], pp[ok, 0]].mean() if ok.any() else 0)
        prof = np.array(prof)
        # report the strongest line within +-60 px; the true neatline should be at 0
        k = int(np.argmax(prof))
        out[name] = {"peak_offset_px": int(offs[k]), "peak": float(prof[k]), "at_zero": float(prof[60]),
                     "profile_median": float(np.median(prof))}
    return out


def main(img, shp_dir, out_json, *frames):
    rgb = cv2.cvtColor(cv2.imread(str(img)), cv2.COLOR_BGR2RGB); bh = blackhat(rgb)
    L = gpd.read_file(Path(shp_dir) / "geo_L.shp", encoding="cp932")
    res = {"signal": "black-hat 9px ellipse, mean patch around official geo_L contacts", "candidates": {}}
    for fj in frames:
        name, path = fj.split("=")
        fr = json.load(open(path)); H = np.array(fr["H_lonlat_to_px"]); b = fr["bounds_lonlat"]
        rng = np.random.default_rng(0)
        pts = contact_pts(L, H, bh.shape); cid = grid_cells(pts)
        gp, n = mean_patch(bh, pts, rng); g = peak(gp); g["n"] = n
        # null: same contact geometry displaced by 30 px (signal should vanish / move to the edge)
        npatch, _ = mean_patch(bh, pts + (30, 30), rng); null = peak(npatch)
        cells = []
        for c in range(16):
            p = pts[cid == c]
            if len(p) < 400: continue
            cp, m = mean_patch(bh, p, rng); pk = peak(cp); pk.update({"cell": c, "n": m}); cells.append(pk)
        good = [c for c in cells if c["contrast_z"] > 3]
        res["candidates"][name] = {
            "global": g, "null_shift30": null, "cells": cells,
            "cells_trusted": len(good),
            "cell_offset_abs_median_px": float(np.median([np.hypot(c["dx"], c["dy"]) for c in good])) if good else None,
            "cell_offset_abs_max_px": float(max(np.hypot(c["dx"], c["dy"]) for c in good)) if good else None,
            "neatline": side_profiles(bh, H, b)}
        r = res["candidates"][name]
        print(name, "global", {k: round(v, 2) for k, v in g.items()}, "null_z", round(null["contrast_z"], 2),
              "cells trusted", r["cells_trusted"], "/", len(cells), "|off| med/max", r["cell_offset_abs_median_px"], r["cell_offset_abs_max_px"],
              "neatline", {k: v["peak_offset_px"] for k, v in r["neatline"].items()}, flush=True)
    json.dump(res, open(out_json, "w"), indent=1, default=float)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], *sys.argv[4:])
