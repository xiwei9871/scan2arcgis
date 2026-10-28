"""Independent check of GSJ sheet registration, using printed black linework instead of fill colour.

Why: gsj_register.py refines registration by fill-colour homogeneity, and the edge-distance
check in gsj_gt.py also uses colour. Both share the recognizer's assumption (colour = unit),
so neither is independent evidence. GSJ prints geologic boundaries as thin black ink lines
whose position does not depend on fill colour; distance from official geo_L contacts to
printed ink is therefore an independent registration measure.

For each candidate homography (frame-only, colour-refined, ink-refined) this reports:
  - distance (200 dpi px) from official contact pixels to the nearest ink pixel, overall and
    per 4x4 cell, against a shuffled-shift baseline (how discriminative the ink signal is);
  - the per-cell best residual shift under the ink objective (0 = locally consistent);
  - neatline-corner displacement relative to the detected frame;
  - 2-fold checkerboard cross-validation of the ink refinement (fit on half the cells,
    measure on the other half).
"""
import json, sys
from pathlib import Path
import cv2, numpy as np, geopandas as gpd, warnings

sys.path.insert(0, str(Path(__file__).parent))
from gsj_gt import lines, to_px  # noqa: E402
warnings.filterwarnings("ignore")


def ink_dist(rgb, valid):
    g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    ink = (g < 100) & valid
    return cv2.distanceTransform((~ink).astype(np.uint8), cv2.DIST_L2, 3), ink


def contact_pts(L, H, shape):
    m = np.zeros(shape, np.uint8)
    kinds = L["LEGEND01"].astype(str)
    for g, k in zip(L.geometry, kinds):
        if "地質境界" not in k: continue
        for ln in lines(g):
            cv2.polylines(m, [np.round(to_px(ln, H)).astype(np.int32).reshape(-1, 1, 2)], False, 1, 1)
    ys, xs = np.nonzero(m)
    return np.stack([xs, ys], 1).astype(np.float64)


def grid_cells(pts, n=4):
    x0, y0 = pts.min(0); x1, y1 = pts.max(0)
    cid = (np.clip(((pts[:, 1] - y0) / (y1 - y0 + 1e-9) * n).astype(int), 0, n - 1) * n
           + np.clip(((pts[:, 0] - x0) / (x1 - x0 + 1e-9) * n).astype(int), 0, n - 1))
    return cid


def sample(dist, pts):
    h, w = dist.shape
    xi = np.clip(np.round(pts[:, 0]).astype(int), 0, w - 1); yi = np.clip(np.round(pts[:, 1]).astype(int), 0, h - 1)
    return dist[yi, xi]


def best_shift(dist, pts, R, step):
    best = (np.inf, 0, 0)
    for dy in range(-R, R + 1, step):
        for dx in range(-R, R + 1, step):
            m = float(np.mean(np.minimum(sample(dist, pts + (dx, dy)), 10)))  # truncated mean: robust to missing ink
            if m < best[0]: best = (m, dx, dy)
    return best


def refine_ink(dist, L, H, shape, use_cells=None, rng=None):
    rng = rng or np.random.default_rng(0)
    for R, step in [(40, 2), (10, 1), (4, 1)]:
        pts = contact_pts(L, H, shape); cid = grid_cells(pts)
        src, dst = [], []
        for c in range(16):
            if use_cells is not None and c not in use_cells: continue
            p = pts[cid == c]
            if len(p) < 300: continue
            p = p[rng.choice(len(p), min(len(p), 6000), replace=False)]
            _, dx, dy = best_shift(dist, p, R, step)
            ctr = p.mean(0); src.append(ctr); dst.append(ctr + (dx, dy))
        if len(src) < 4: break
        Hc, _ = cv2.findHomography(np.array(src), np.array(dst), 0)
        H = Hc @ H
    return H


def report(dist, L, H, shape, rng):
    pts = contact_pts(L, H, shape); d = sample(dist, pts); cid = grid_cells(pts)
    # baseline: same lines displaced by a random 15-40 px shift (what "unregistered" looks like)
    base = []
    for _ in range(8):
        a = rng.uniform(0, 2 * np.pi); r = rng.uniform(15, 40)
        base.append(np.median(sample(dist, pts + (r * np.cos(a), r * np.sin(a)))))
    cells = []
    for c in range(16):
        p = pts[cid == c]
        if len(p) < 300: continue
        p = p[rng.choice(len(p), min(len(p), 6000), replace=False)]
        m, dx, dy = best_shift(dist, p, 6, 1)
        cells.append({"cell": c, "n": int(len(p)), "median_px": float(np.median(sample(dist, p))),
                      "resid_dx": dx, "resid_dy": dy})
    return {"n_contact_px": int(len(pts)), "median_px": float(np.median(d)), "p90_px": float(np.percentile(d, 90)),
            "frac_le_1px": float((d <= 1).mean()), "frac_le_2px": float((d <= 2).mean()), "frac_le_3px": float((d <= 3).mean()),
            "baseline_shifted_median_px": float(np.median(base)),
            "max_cell_residual_shift_px": float(max(max(abs(c["resid_dx"]), abs(c["resid_dy"])) for c in cells)),
            "cells": cells}


def corners_of(H, b):
    q = np.array([[b[0], b[3]], [b[2], b[3]], [b[2], b[1]], [b[0], b[1]]], np.float64)
    return to_px(q, H)


def main(img, frame_json, frame_reg_json, shp_dir, out_json):
    rgb = cv2.cvtColor(cv2.imread(str(img)), cv2.COLOR_BGR2RGB); shape = rgb.shape[:2]
    fr = json.load(open(frame_json)); frr = json.load(open(frame_reg_json))
    b = fr["bounds_lonlat"]; H0 = np.array(fr["H_lonlat_to_px"]); Hc = np.array(frr["H_lonlat_to_px"])
    c0 = np.array([fr["corners_px"][k] for k in ("tl", "tr", "br", "bl")])
    valid = np.zeros(shape, np.uint8); cv2.fillPoly(valid, [np.round(c0).astype(np.int32)], 1)
    valid = cv2.erode(valid, np.ones((25, 25), np.uint8)).astype(bool)   # drop the neatline itself
    dist, ink = ink_dist(rgb, valid)
    L = gpd.read_file(Path(shp_dir) / "geo_L.shp", encoding="cp932")
    rng = np.random.default_rng(0)
    Hi = refine_ink(dist, L, H0, shape)
    out = {"ink_px_frac_in_map": float(ink.sum() / valid.sum()), "candidates": {}}
    for name, H in [("frame_only", H0), ("colour_refined", Hc), ("ink_refined", Hi)]:
        r = report(dist, L, H, shape, rng)
        r["corner_shift_vs_frame_px"] = [float(v) for v in np.linalg.norm(corners_of(H, b) - c0, axis=1)]
        out["candidates"][name] = r
        print(name, json.dumps({k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items() if k != "cells"}), flush=True)
    # colour-refined vs ink-refined: displacement of contact pixels between the two (independent agreement)
    p = contact_pts(L, Hc, shape)
    lonlat = cv2.perspectiveTransform(p[None], np.linalg.inv(Hc))[0]
    dd = np.linalg.norm(to_px(lonlat, Hi) - p, axis=1)
    out["colour_vs_ink_displacement_px"] = {"median": float(np.median(dd)), "p90": float(np.percentile(dd, 90)), "max": float(dd.max())}
    print("colour_vs_ink_displacement_px", out["colour_vs_ink_displacement_px"])
    # 2-fold checkerboard CV of ink refinement
    A = {c for c in range(16) if (c // 4 + c % 4) % 2 == 0}; B = set(range(16)) - A
    cv = []
    for fit, test in [(A, B), (B, A)]:
        Hf = refine_ink(dist, L, H0, shape, use_cells=fit)
        pts = contact_pts(L, Hf, shape); cid = grid_cells(pts)
        sel = np.isin(cid, list(test)); d = sample(dist, pts[sel])
        cv.append({"median_px": float(np.median(d)), "frac_le_2px": float((d <= 2).mean())})
    out["ink_refinement_cv_heldout_cells"] = cv
    print("cv", cv)
    out["H_ink_refined"] = Hi.tolist()
    json.dump(out, open(out_json, "w"), indent=1)
    fr_i = dict(fr); fr_i["H_lonlat_to_px"] = Hi.tolist(); fr_i["registration"] = {"method": "ink-line grid refinement"}
    json.dump(fr_i, open(Path(out_json).with_name("frame_ink.json"), "w"), indent=1)


if __name__ == "__main__":
    main(*sys.argv[1:6])
