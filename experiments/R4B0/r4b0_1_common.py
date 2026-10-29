"""R4-B0.1 shared code (rules: experiments/R4B0/r4b0_1_preregistration.json, committed before any run).

A1  M2_DISTANCE_SEEDS_BOUNDARY_TERRAIN: markers = hybrid_markers(M2 dist head) exactly as M2_hybrid;
    watershed elevation = M2 boundary probability (high probability = barrier); no other change.
C1  sub-pixel line width ("ink mass") estimator:
      bh   = gray black-hat (ellipse 15 px), float
      cand = bh > CAND_T ; components = 8-connected components of cand
      C    = 255 (fixed full gray range; an image-derived contrast falls with thin-line width under
             resampling and cancels the scale signal - found on synthetic lines before pre-registration)
      per component j:
        L_j    = sum over its skeleton pixels of 1 / max(|cos t|, |sin t|), t = local line direction from the
                 structure tensor of the smoothed cand mask (orientation-unbiased digital length)
        b_j    = median bh over the ring 1.5 < d <= 3.5 px around the component (local background)
        mass_j = sum of max(bh - b_j, 0) over pixels with d <= 1.5 px (d = distance to the nearest cand pixel of j)
        w_j    = mass_j / (C * L_j)            [px; linear in scale under area-averaging resampling]
      accepted if L_j >= MIN_LEN, L_j / max(w_j, 0.25) >= MIN_ELONG, mean coherence on skeleton >= MIN_COH,
      junction pixels per 100 px length <= MAX_JUNC, cand area / L_j <= MAX_FOOT
      estimate = length-weighted median of w_j over accepted components
"""
import json, sys
from pathlib import Path
import cv2, numpy as np
from scipy import ndimage as ndi
from skimage.morphology import skeletonize
from skimage.segmentation import watershed

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments/R4A"))
from r4a2_1_seeds import hybrid_markers  # noqa: E402

PR1 = json.load(open(ROOT / "experiments/R4B0/r4b0_1_preregistration.json"))
LW = PR1["c1"]["estimator"]


def a1_regions(prob, dist):
    mk = hybrid_markers(dist)
    return watershed(prob.astype(np.float32), mk).astype(np.int32), mk


def _wmedian(v, w):
    if len(v) == 0: return None
    o = np.argsort(v); c = np.cumsum(w[o])
    return float(v[o][np.searchsorted(c, 0.5 * c[-1])])


def line_width(rgb):
    g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    bh = cv2.morphologyEx(g, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15))).astype(np.float32)
    cand = bh > LW["cand_threshold"]
    H, W = cand.shape
    if cand.sum() == 0: return {"median_width_px": None, "accepted_components": 0, "accepted_length_px": 0.0}
    C = float(LW["contrast_constant"])
    n, cc = cv2.connectedComponents(cand.astype(np.uint8), connectivity=8)
    m = cv2.GaussianBlur(cand.astype(np.float32), (0, 0), 1.0)
    gx, gy = cv2.Sobel(m, cv2.CV_32F, 1, 0), cv2.Sobel(m, cv2.CV_32F, 0, 1)
    Jxx, Jyy, Jxy = (cv2.GaussianBlur(a, (0, 0), 2.0) for a in (gx * gx, gy * gy, gx * gy))
    coh = np.sqrt((Jxx - Jyy) ** 2 + 4 * Jxy ** 2) / (Jxx + Jyy + 1e-9)
    theta = 0.5 * np.arctan2(2 * Jxy, Jxx - Jyy) + np.pi / 2                       # line direction
    sk = skeletonize(cand)
    nb = ndi.convolve(sk.astype(np.uint8), np.ones((3, 3), np.uint8), mode="constant") - 1
    junc = sk & (nb >= 3)
    step = 1.0 / np.maximum(np.abs(np.cos(theta)), np.abs(np.sin(theta)))
    lab_sk = cc[sk]
    L = np.bincount(lab_sk, weights=step[sk], minlength=n)
    COH = np.bincount(lab_sk, weights=coh[sk], minlength=n) / np.maximum(np.bincount(lab_sk, minlength=n), 1)
    J = np.bincount(cc[junc], minlength=n)
    A = np.bincount(cc[cand], minlength=n)
    ang = np.bincount(lab_sk, weights=np.cos(2 * theta[sk]), minlength=n), np.bincount(lab_sk, weights=np.sin(2 * theta[sk]), minlength=n)
    ori = np.degrees(0.5 * np.arctan2(ang[1], ang[0])) % 180
    d, idx = ndi.distance_transform_edt(~cand, return_indices=True)
    near = cc[idx[0], idx[1]]
    ring = (d > 1.5) & (d <= 3.5); core = d <= 1.5
    ids = np.arange(n)
    b = np.zeros(n, np.float32)
    has_ring = np.bincount(near[ring], minlength=n) > 0
    b[has_ring] = ndi.median(bh, labels=np.where(ring, near, 0), index=ids[has_ring])
    mass = np.bincount(near[core], weights=np.maximum(bh[core] - b[near[core]], 0), minlength=n)
    w = mass / (C * np.maximum(L, 1e-9))
    acc = (L >= LW["min_length_px"]) & (L / np.maximum(w, 0.25) >= LW["min_elongation"]) & (COH >= LW["min_coherence"]) \
          & (J / np.maximum(L, 1e-9) * 100 <= LW["max_junctions_per_100px"]) & (A / np.maximum(L, 1e-9) <= LW["max_footprint_px"])
    acc[0] = False
    k = np.flatnonzero(acc)
    # spatial reliability: length-weighted median per 3x3 cell (component assigned by skeleton centroid)
    ys, xs = np.nonzero(sk); cy = np.bincount(lab_sk, weights=ys, minlength=n) / np.maximum(np.bincount(lab_sk, minlength=n), 1)
    cx = np.bincount(lab_sk, weights=xs, minlength=n) / np.maximum(np.bincount(lab_sk, minlength=n), 1)
    cell = (np.clip(cy * 3 // H, 0, 2) * 3 + np.clip(cx * 3 // W, 0, 2)).astype(int)
    cells = [_wmedian(w[k[cell[k] == c]], L[k[cell[k] == c]]) for c in range(9) if L[k[cell[k] == c]].sum() >= LW["cell_min_length_px"]]
    cv = float(np.std(cells) / np.mean(cells)) if len(cells) >= 2 else None
    def grp(sel): kk = k[sel[k]]; return {"n": int(len(kk)), "median": _wmedian(w[kk], L[kk])}
    dist90 = np.minimum(ori % 90, 90 - ori % 90)                                       # 0 = axial, 45 = diagonal
    out = {"median_width_px": _wmedian(w[k], L[k]), "accepted_components": int(len(k)), "accepted_length_px": round(float(L[k].sum()), 1),
           "candidate_components": int(n - 1), "ink_contrast_C": round(C, 2),
           "axial": grp(dist90 <= 15), "diagonal": grp(dist90 >= 30),
           "long_only_ge60": grp(L >= 60), "cells_used": len(cells), "cell_median_cv": None if cv is None else round(cv, 4)}
    a, dg = out["axial"], out["diagonal"]
    out["direction_ratio_diag_over_axial"] = round(dg["median"] / a["median"], 4) if a["median"] and dg["median"] else None
    out["long_only_rel_change"] = round(abs(out["long_only_ge60"]["median"] / out["median_width_px"] - 1), 4) if out["long_only_ge60"]["median"] and out["median_width_px"] else None
    out["enough_samples"] = bool(len(k) >= LW["min_components"] and L[k].sum() >= LW["min_total_length_px"])
    out["spatially_consistent"] = bool(len(cells) >= LW["min_cells"] and cv is not None and cv <= LW["max_cell_cv"])
    return out
