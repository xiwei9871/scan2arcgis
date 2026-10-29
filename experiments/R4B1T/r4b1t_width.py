"""R4-B1T canonical instance / width definitions (single implementation from here on; history unchanged).

Instance   official instance.npy (4-connected component of one geo_A unit on the GeoTIFF grid), id = value + 1.
Valid      evaluation valid mask: ignore.npy == 0 and unit.npy >= 0 (same as experiments/R4A/r4a2_2_eval.load_ref).
Area       number of instance pixels inside Valid.
Small      200 <= Area < 20000.
Width      inscribed edge-to-edge width of the instance's own mask restricted to Valid:
           2 * (max DIST_L2-mask-5 distance inside the 1-px-padded mask - 0.5).
           Quantisation (unit-tested): an axis-aligned strip k px wide reads k for odd k and k - 1 for even k
           (the ridge of an even strip is two pixels at distance k/2). So bin [3, 6) holds true 3-6 px strips,
           [6, 10) true 7-10 px, [10, 20) true 11-20 px. Kept as is: it is the formula of R4-B0 Gates 1-3,
           so all earlier per-width results stay comparable.
Bins       [3, 6), [6, 10), [10, 20); lt3 and ge20 kept as extra rows.

Historical definitions reconciled in Gate 0 (not used further):
  H1 pre-check (R4-B0 discussion):      2 * max EDT (no -0.5), full grid       -> +1 px vs canonical
  H2 R4-A2.2 width_old:                  2 * max(official dist to UB) + 1, valid area
  H3 R4-B0 Gate 1/2/3 width_own:         canonical formula, valid area            -> identical to canonical
  H4 R4-B1 Gate 1/2 width_own:           canonical formula, FULL grid (no valid mask)
"""
import cv2, numpy as np
from scipy import ndimage as ndi

BINS = [("lt3", 0, 3), ("3-6", 3, 6), ("6-10", 6, 10), ("10-20", 10, 20), ("ge20", 20, 1e9)]


def width_bin(w):
    return next(n for n, lo, hi in BINS if lo <= w < hi)


def instances(inst, valid=None):
    """Return inst1 (0 = none) restricted to valid, area per id, find_objects slices."""
    i1 = (inst + 1).astype(np.int32)
    if valid is not None: i1 = np.where(valid, i1, 0)
    n = int(i1.max()); area = np.bincount(i1.ravel(), minlength=n + 1)
    return i1, area, ndi.find_objects(i1, max_label=n)


def max_edt(i1, objs, ids):
    out = np.zeros(len(ids), np.float32)
    for j, k in enumerate(ids):
        sl = objs[k - 1]
        if sl is None: continue
        m = np.pad((i1[sl] == k).astype(np.uint8), 1)
        out[j] = cv2.distanceTransform(m, cv2.DIST_L2, 5).max()
    return out


def canonical_widths(inst, valid):
    i1, area, objs = instances(inst, valid)
    ids = np.flatnonzero((area >= 200) & (area < 20000)); ids = ids[ids > 0]
    e = max_edt(i1, objs, ids)
    return i1, area, ids, 2 * (e - 0.5)
