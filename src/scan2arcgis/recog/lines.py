"""Line candidates for the new route.

contacts : derived from area labels (shared boundaries) -- not detected separately.
faults   : dark-ink skeleton that is NOT explained by a contact, filtered by
           length and elongation (removes text and point symbols).
Scores are UNCALIBRATED.
"""
from __future__ import annotations

import cv2
import numpy as np
from skimage.morphology import skeletonize

from ..eval.raster_metrics import class_boundaries
from .legend_classifier import to_lab


def contacts_from_labels(labels: np.ndarray, valid: np.ndarray) -> np.ndarray:
    return class_boundaries(labels, valid)


def fault_candidates(rgb: np.ndarray, labels: np.ndarray, valid: np.ndarray, *,
                     contact_buffer_px: int = 3, min_len_px: int = 60, min_elong: float = 4.0):
    L = to_lab(rgb)[..., 0]
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11))
    bh = cv2.morphologyEx(L, cv2.MORPH_BLACKHAT, k)
    # chroma check: faults are printed in near-black; coloured graticule/roads excluded
    lab = to_lab(rgb)
    chroma = np.hypot(lab[..., 1] - 128, lab[..., 2] - 128)
    dark = ((bh > 40) | (L < 70)) & (chroma < 25) & valid
    # thick-line emphasis: faults are drawn wider than contacts on most maps
    opened = cv2.morphologyEx(dark.astype(np.uint8), cv2.MORPH_OPEN, np.ones((2, 2), np.uint8)) > 0
    sk = skeletonize(opened)
    contact = contacts_from_labels(labels, valid)
    near_contact = cv2.dilate(contact.astype(np.uint8), np.ones((2 * contact_buffer_px + 1,) * 2, np.uint8)) > 0
    # keep skeleton pixels not explained by a contact, but bridge the gaps where faults cross contacts
    cand = sk & ~near_contact
    n, cc, st, _ = cv2.connectedComponentsWithStats(cand.astype(np.uint8), connectivity=8)
    keep = np.zeros(n, bool)
    scores = np.zeros(n, np.float32)
    for i in range(1, n):
        w, h, a = st[i, cv2.CC_STAT_WIDTH], st[i, cv2.CC_STAT_HEIGHT], st[i, cv2.CC_STAT_AREA]
        span = float(np.hypot(w, h))
        elong = span / max(1.0, np.sqrt(a))
        if a >= min_len_px and elong >= min_elong:
            keep[i] = True
            scores[i] = min(1.0, a / 400.0) * min(1.0, elong / 12.0)   # UNCALIBRATED
    mask = keep[cc]
    return mask, cc * mask, scores
