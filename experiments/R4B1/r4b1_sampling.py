"""R4-B1 sampling anchors for small instances (200 <= area < 20000 px).

frozen_anchors   what r4a2_train.load_sheet does: np.unique(..., return_index=True) -> the FIRST pixel of each
                 instance in row-major order (top row, leftmost pixel). Named "small_instance_centre" in the code,
                 but it is an extreme point on the instance outline, not a centre.
interior_anchors proposed fix: the pixel of maximum own-mask inscribed distance (DIST_L2 mask 5 on the padded
                 instance mask; first in raster order on ties), i.e. the centre of the largest inscribed disc.
                 Uses only the instance mask (training labels); no validation sheet, no model output.
simulate_crop    exact replica of r4a2_train.crop() placement: y0 = clip(y - 256 + U{-128..128}, 0, H - 512).
"""
import numpy as np, cv2
from scipy import ndimage as ndi

TILE = 512


def small_ids(inst):
    i1 = inst.ravel() + 1
    area = np.bincount(i1)
    ids = np.flatnonzero((area >= 200) & (area < 20000)); ids = ids[ids > 0]
    return ids, area


def frozen_anchors(inst):
    """Flat indices exactly as r4a2_train.load_sheet computes them (before its random subsampling)."""
    ids, first, cnt = np.unique(inst[inst >= 0], return_index=True, return_counts=True)
    pos = np.flatnonzero(inst >= 0)[first]
    keep = (cnt >= 200) & (cnt < 20000)
    return ids[keep] + 1, pos[keep]                       # instance id (1-based) and flat index


def interior_anchors(inst):
    i1 = inst + 1; objs = ndi.find_objects(i1); W = inst.shape[1]
    ids, _ = small_ids(inst); out = np.zeros(len(ids), np.int64)
    for j, k in enumerate(ids):
        sl = objs[k - 1]; m = np.pad((i1[sl] == k).astype(np.uint8), 1)
        d = cv2.distanceTransform(m, cv2.DIST_L2, 5)[1:-1, 1:-1]
        y, x = np.unravel_index(int(np.argmax(d)), d.shape)
        out[j] = (sl[0].start + y) * W + sl[1].start + x
    return ids, out


def simulate_crop(y, x, H, W, rng):
    y0 = int(np.clip(y - TILE // 2 + rng.integers(-TILE // 4, TILE // 4 + 1), 0, H - TILE))
    x0 = int(np.clip(x - TILE // 2 + rng.integers(-TILE // 4, TILE // 4 + 1), 0, W - TILE))
    return y0, x0
