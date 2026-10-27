"""Refine the lon/lat -> pixel homography of a GSJ sheet using the image itself.

Why: the neatline detector may lock onto the outer frame of a double border, leaving a
scale/offset error of tens of pixels. Edge distance is a weak check on hachured/textured maps,
so we score registration by colour homogeneity: with correct registration, pixels inside each
official unit match that unit's median colour better than any other unit's.

Method: on a 4x4 grid of cells, search the integer shift (in the GT frame) that maximises the
nearest-unit-median accuracy of sampled non-ink pixels; then fit a homography from cell centres
to shifted centres and compose it with the current H. Repeat with a smaller search window.
Every step's per-cell score and shift is written out, so registration quality is reported
rather than assumed.
"""
import json, sys
from pathlib import Path
import cv2, numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from gsj_gt import rings, to_px  # noqa: E402
import geopandas as gpd, warnings  # noqa: E402
warnings.filterwarnings("ignore")

S = 0.5  # work at half resolution (100 dpi) for the search


def rasterize(A, H, shape, cid):
    lab = np.full(shape, -1, np.int32)
    for i in A.geometry.area.sort_values(ascending=False).index:
        r = A.loc[i]
        for rr in rings(r.geometry):
            cv2.fillPoly(lab, [np.round(to_px(rr[0], H)).astype(np.int32)], int(cid[str(r.MAJOR_CODE)]))
    return lab


def cell_scores(L, ink, g, cells, R, step, rng):
    h, w = g.shape
    out = []
    for (cy0, cy1, cx0, cx1) in cells:
        ys, xs = np.nonzero(g[cy0:cy1, cx0:cx1] >= 0)
        if len(ys) < 3000:
            out.append(None); continue
        k = rng.choice(len(ys), min(5000, len(ys)), replace=False)
        ys, xs = ys[k] + cy0, xs[k] + cx0
        lab = g[ys, xs]
        best, zero = None, None
        for dy in range(-R, R + 1, step):
            for dx in range(-R, R + 1, step):
                yy, xx = ys + dy, xs + dx
                ok = (yy >= 0) & (yy < h) & (xx >= 0) & (xx < w)
                yy, xx, ll = yy[ok], xx[ok], lab[ok]
                keep = ~ink[yy, xx]
                col, ll = L[yy[keep], xx[keep]], ll[keep]
                u, inv = np.unique(ll, return_inverse=True)
                med = np.array([np.median(col[inv == j], 0) for j in range(len(u))])
                acc = float((inv == ((col[:, None, :] - med[None]) ** 2).sum(2).argmin(1)).mean())
                if dx == 0 and dy == 0: zero = acc
                if best is None or acc > best[0]: best = (acc, dx, dy)
        out.append({"zero": zero, "best": best[0], "dx": best[1], "dy": best[2],
                    "cx": (cx0 + cx1) / 2, "cy": (cy0 + cy1) / 2})
    return out


def main(img, frame_json, shp_dir, out_json):
    fr = json.load(open(frame_json)); H = np.array(fr["H_lonlat_to_px"], float)
    rgb = cv2.cvtColor(cv2.imread(str(img)), cv2.COLOR_BGR2RGB)
    small = cv2.resize(rgb, None, fx=S, fy=S, interpolation=cv2.INTER_AREA)
    L = cv2.cvtColor(cv2.medianBlur(small, 5), cv2.COLOR_RGB2LAB).astype(np.float32)
    ink = L[..., 0] < 100
    A = gpd.read_file(Path(shp_dir) / "geo_A.shp", encoding="cp932")
    cid = {c: i for i, c in enumerate(sorted(A.MAJOR_CODE.astype(str).unique()))}
    Ssc = np.diag([S, S, 1.0])
    rng = np.random.default_rng(0)
    log = []
    for it, (R, step) in enumerate([(60, 6), (16, 2), (6, 1)]):
        g = rasterize(A, Ssc @ H, small.shape[:2], cid)
        ys, xs = np.nonzero(g >= 0); y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
        n = 4; m = R + 4
        cells = [(int(y0 + (y1 - y0) * a / n) + m, int(y0 + (y1 - y0) * (a + 1) / n) - m,
                  int(x0 + (x1 - x0) * b / n) + m, int(x0 + (x1 - x0) * (b + 1) / n) - m)
                 for a in range(n) for b in range(n)]
        sc = [c for c in cell_scores(L, ink, g, cells, R, step, rng) if c]
        src = np.array([[c["cx"], c["cy"]] for c in sc], np.float64) / S
        dst = src + np.array([[c["dx"], c["dy"]] for c in sc], np.float64) / S
        # a pixel at GT position p shows image content at p + shift -> GT must move by +shift
        Hc, _ = cv2.findHomography(src, dst, 0)
        H = Hc @ H
        log.append({"iter": it, "search_px200": R / S, "cells": sc,
                    "mean_zero": float(np.mean([c["zero"] for c in sc])),
                    "mean_best": float(np.mean([c["best"] for c in sc])),
                    "max_abs_shift_px200": float(np.abs(dst - src).max())})
        print(json.dumps({k: v for k, v in log[-1].items() if k != "cells"}), flush=True)
    # final residual check (no update)
    g = rasterize(A, Ssc @ H, small.shape[:2], cid)
    ys, xs = np.nonzero(g >= 0); y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
    cells = [(int(y0 + (y1 - y0) * a / 4) + 8, int(y0 + (y1 - y0) * (a + 1) / 4) - 8,
              int(x0 + (x1 - x0) * b / 4) + 8, int(x0 + (x1 - x0) * (b + 1) / 4) - 8)
             for a in range(4) for b in range(4)]
    fin = [c for c in cell_scores(L, ink, g, cells, 4, 1, rng) if c]
    res = {"final_mean_acc": float(np.mean([c["zero"] for c in fin])),
           "final_max_residual_shift_px200": float(max(max(abs(c["dx"]), abs(c["dy"])) for c in fin) / S),
           "final_cells": fin}
    print(json.dumps({k: v for k, v in res.items() if k != "final_cells"}))
    fr2 = dict(fr); fr2["H_lonlat_to_px"] = H.tolist(); fr2["registration"] = {"iterations": log, "final": res,
                                                                                  "method": "colour-homogeneity grid refinement"}
    json.dump(fr2, open(out_json, "w"), indent=1)


if __name__ == "__main__":
    main(*sys.argv[1:5])
