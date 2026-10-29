"""R4-A2.1 P3: M2 watershed seed rules (prediction-time code: takes a distance map only, never geo_A).

old_markers  frozen R4-A2 rule: connected components of (dist >= 3 px) with area >= 50 px.
new_markers  R4-A2.1 scale-adaptive rule: regional maxima of the distance field after an h-maxima
             transform of log(1 + dist). Two maxima stay separate only if the drop to the saddle between
             them satisfies (peak + 1) / (saddle + 1) >= RATIO, i.e. a relative (scale-free) contrast.
             RATIO = 2 is fixed a priori: a true boundary drives the distance to 0, so any maximum with
             dist >= 1 px separated by a boundary passes ((r + 1) / 1 >= 2), while a neck inside one unit
             must at least halve (r + 1) to split it. Maxima need dist >= MIN_DIST (= 0.9 px: any pixel that
             is not itself a boundary pixel), and no area threshold. Measured limit (tests/r4a/test_r4a2_1.py,
             official-style distance): with SMOOTH = 1 a straight strip is seeded from 7 px width up; 3-6 px
             strips are not (peak dist <= 1.91 px is flattened by the blur / fails the ratio-2 contrast).
             Parameters were not changed after this was found (no parameter search).
             The input is smoothed (Gaussian sigma SMOOTH px) first to suppress single-pixel noise in
             predicted maps; on the official map this changes little.
segment      watershed on -dist from the given markers (frozen M2 post-processing, markers swapped).
"""
import cv2, numpy as np
from skimage.morphology import h_maxima
from skimage.segmentation import watershed

OLD_DIST, OLD_AREA = 3.0, 50
RATIO, MIN_DIST, SMOOTH = 2.0, 0.9, 1.0


def old_markers(dist):
    n, cc, st, _ = cv2.connectedComponentsWithStats((dist >= OLD_DIST).astype(np.uint8), connectivity=8)
    keep = np.zeros(n, bool); keep[1:] = st[1:, cv2.CC_STAT_AREA] >= OLD_AREA
    lut = np.cumsum(keep) * keep
    return lut[cc].astype(np.int32)


def new_markers(dist):
    d = cv2.GaussianBlur(dist.astype(np.float32), (0, 0), SMOOTH) if SMOOTH > 0 else dist.astype(np.float32)
    f = np.log1p(np.maximum(d, 0)).astype(np.float64)
    m = h_maxima(f, np.log(RATIO)).astype(bool) & (d >= MIN_DIST)
    return cv2.connectedComponents(m.astype(np.uint8), connectivity=8)[1].astype(np.int32)


def hybrid_markers(dist):
    """Old markers, plus every h-maxima seed component that touches no old marker (regions the old rule
    leaves unseeded, whether by the 3 px distance or the 50 px area threshold). Added after the pure
    h-maxima rule over-split large units on 05016 (large-instance recall 0.976 -> 0.805): a wide unit keeps
    its single connected old seed instead of many maxima. v1 (added only maxima with peak < 3 px) missed the
    area-threshold failures, the larger share; this v2 is the corrected rule (one fix, no parameter change)."""
    old = old_markers(dist); hm = new_markers(dist)
    nh = int(hm.max()); touch = np.zeros(nh + 1, bool); touch[hm[old > 0]] = True; touch[0] = True
    out = old.copy(); add = ~touch[hm]
    out[add] = hm[add] + int(old.max())
    u, inv = np.unique(out, return_inverse=True)                     # u[0] == 0 (background always present)
    return inv.reshape(out.shape).astype(np.int32)


def segment(dist, markers):
    return watershed(-dist.astype(np.float32), markers)
