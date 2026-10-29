"""R4-B1 narrow-unit interior supervision: candidate rules and their pixel sets (training labels only).

Notation (per sheet, GeoTIFF grid, all from r4a2_labels.py outputs):
  UB      unit_boundary.npy (both sides of every unit transition)
  d       dist.npy, DIST_L2 mask 3 distance to UB (clipped 32)
  w_v2    v2 weight (r4a2_1_labels.sup_weight: 1 for d<=2, 0.1 for 2<d<=4, 0.3 for 4<d<=8, 1 beyond, 0 on IGNORE_EVAL)
  t_v2    soft target train_boundary.npy (exp(-d^2/2) for d<=2, else 0)
  narrow  instances whose own-mask inscribed width 2*(max EDT - 0.5) < 10 px
  ink     gray black-hat (ellipse 9 px, as the label builder) > 40;  ink1 / ink2 = ink dilated to 1 / 2 px

Rules audited:
  HARD   (R4-B0.1 proposal) every narrow-instance pixel not in UB -> target 0, weight 1
  SAFE   priority IGNORE_EVAL > boundary protection > reliable interior negative > original:
           boundary protection = UB, d <= 2 (soft positive band), and ink1
           reliable interior   = narrow-instance pixel, d > 2, not ink1, not IGNORE_EVAL -> target 0 (unchanged), weight 1
         t_v2 is never changed; only weights of pixels whose v2 target is already 0 are raised.
"""
import cv2, numpy as np
from scipy import ndimage as ndi

NARROW_MAX = 10.0


def own_width(inst):
    """Per instance id (1-based, index 0 unused): 2 * (max own-mask DIST_L2-mask-5 distance - 0.5)."""
    i1 = inst + 1; n = int(i1.max()); objs = ndi.find_objects(i1); w = np.zeros(n + 1, np.float32)
    for k in range(1, n + 1):
        sl = objs[k - 1]
        if sl is None: continue
        m = np.pad((i1[sl] == k).astype(np.uint8), 1)
        w[k] = 2 * (cv2.distanceTransform(m, cv2.DIST_L2, 5).max() - 0.5)
    return w


def ink_masks(rgb_bgr):
    g = cv2.cvtColor(rgb_bgr, cv2.COLOR_BGR2GRAY)
    ink = cv2.morphologyEx(g, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))) > 40
    return ink, cv2.dilate(ink.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0, cv2.dilate(ink.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0


def rule_sets(inst, ub, d, ign_eval, ink1, width):
    i1 = inst + 1; narrow_px = (width[i1] < NARROW_MAX) & (inst >= 0)
    cand = narrow_px & ~ub & ~ign_eval
    hard = cand
    safe = cand & (d > 2) & ~ink1
    return narrow_px, cand, hard, safe


def safe_weight(w_v2, safe):
    w = w_v2.copy(); w[safe] = 1.0
    return w
