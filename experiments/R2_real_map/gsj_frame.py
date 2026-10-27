"""Locate the printed map frame (neatline) of a GSJ 1:50k sheet and fit pixel <-> lon/lat.

The sheet's map area is a lon/lat quadrangle (0.25 deg x 1/6 deg). Its printed neatline is a
thin dark near-rectangle. We find its four sides as the longest straight dark segments near
the outer extent of the map area, intersect them to get corners, and fit a projective
transform from the vector bounds (lon/lat) to those corners.

Why a homography: the printed sheet is a conformal projection of a small quadrangle plus
scan/paper skew; over 0.25 deg a projective fit is accurate to a few pixels at 200 dpi,
which is reported (not hidden) as residual alignment error in the evaluation.
"""
import json, sys
from pathlib import Path
import cv2
import numpy as np

cv2.setNumThreads(4)


def dark_mask(rgb):
    g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    return (g < 110).astype(np.uint8)


def long_lines(mask, axis, min_frac):
    """Return a mask of long axis-aligned runs (axis=0 horizontal, 1 vertical)."""
    h, w = mask.shape
    k = int((w if axis == 0 else h) * min_frac)
    ker = cv2.getStructuringElement(cv2.MORPH_RECT, (k, 1) if axis == 0 else (1, k))
    return cv2.morphologyEx(mask, cv2.MORPH_OPEN, ker)


def fit_side(pts):
    """Least-squares line through points as (a,b,c) with a*x+b*y+c=0."""
    vx, vy, x0, y0 = cv2.fitLine(pts.astype(np.float32), cv2.DIST_HUBER, 0, 0.01, 0.01).ravel()
    return np.array([vy, -vx, vx * y0 - vy * x0], float)


def intersect(l1, l2):
    p = np.cross(l1, l2)
    return p[:2] / p[2]


def find_frame(rgb):
    # GSJ layout: legend column on the left, symbol/index column on the right. The neatline's top
    # and bottom are the longest dark horizontal lines on the sheet; their endpoints locate the
    # left/right sides. A vertical side is refined from the vertical-line mask only when a long
    # enough run exists near that endpoint (older sheets have broken or skewed side lines).
    h, w = rgb.shape[:2]
    m = dark_mask(rgb)
    hor = long_lines(m, 0, 0.30)
    ver = long_lines(m, 1, 0.10)
    rows = np.where(hor.sum(1) > w * 0.25)[0]
    if len(rows) < 2:
        raise RuntimeError(f"top/bottom neatline not found rows={len(rows)}")
    sides, ends = {}, {}
    for name, idx in (("top", rows.min()), ("bottom", rows.max())):
        lo = max(idx - 6, 0)
        ys, xs = np.nonzero(hor[lo:idx + 7, :])
        pts = np.stack([xs, ys + lo], 1)
        sides[name] = fit_side(pts)
        ends[name] = (pts[pts[:, 0].argmin()], pts[pts[:, 0].argmax()])
    y_top, y_bot = rows.min(), rows.max()
    span = y_bot - y_top
    colsum = cv2.blur(ver[y_top:y_bot + 1].astype(np.float32).sum(0)[None], (9, 1)).ravel() * 9
    refined = {}
    for name, k in (("left", 0), ("right", 1)):
        a, b = ends["top"][k], ends["bottom"][k]
        x_est = int(round((a[0] + b[0]) / 2))
        lo, hi = max(x_est - 40, 0), min(x_est + 41, w)
        band = colsum[lo:hi]
        if band.size and band.max() > span * 0.6:
            c = lo + int(band.argmax())
            ys, xs = np.nonzero(ver[y_top:y_bot + 1, max(c - 6, 0):c + 7])
            sides[name] = fit_side(np.stack([xs + max(c - 6, 0), ys + y_top], 1))
            refined[name] = "vertical_line"
        else:
            sides[name] = np.cross([a[0], a[1], 1.0], [b[0], b[1], 1.0])
            refined[name] = "hline_endpoints"
    c = {"tl": intersect(sides["top"], sides["left"]), "tr": intersect(sides["top"], sides["right"]),
         "br": intersect(sides["bottom"], sides["right"]), "bl": intersect(sides["bottom"], sides["left"])}
    out = {k: [float(v[0]), float(v[1])] for k, v in c.items()}
    out["_side_source"] = refined
    return out


def fit_geo(corners, bounds):
    """bounds = (lon_min, lat_min, lon_max, lat_max) of the sheet quadrangle."""
    x0, y0, x1, y1 = bounds
    src = np.array([[x0, y1], [x1, y1], [x1, y0], [x0, y0]], np.float64)   # tl tr br bl in lon/lat
    dst = np.array([corners[k] for k in ("tl", "tr", "br", "bl")], np.float64)  # ignores "_side_source"
    H, _ = cv2.findHomography(src, dst, 0)
    return H


if __name__ == "__main__":
    img, out = Path(sys.argv[1]), Path(sys.argv[2])
    bounds = [float(v) for v in sys.argv[3].split(",")]
    rgb = cv2.cvtColor(cv2.imread(str(img)), cv2.COLOR_BGR2RGB)
    c = find_frame(rgb)
    H = fit_geo(c, bounds)
    out.parent.mkdir(parents=True, exist_ok=True)
    json.dump({"image": img.name, "size": [rgb.shape[1], rgb.shape[0]], "corners_px": c,
               "bounds_lonlat": bounds, "H_lonlat_to_px": H.tolist()}, open(out, "w"), indent=1)
    vis = rgb.copy()
    pts = np.array([c[k] for k in ("tl", "tr", "br", "bl")], np.int32)
    cv2.polylines(vis, [pts], True, (255, 0, 0), 9)
    s = 1600 / max(vis.shape[:2])
    cv2.imwrite(str(out.with_suffix(".jpg")), cv2.cvtColor(cv2.resize(vis, None, fx=s, fy=s, interpolation=cv2.INTER_AREA), cv2.COLOR_RGB2BGR))
    print(json.dumps(c))
