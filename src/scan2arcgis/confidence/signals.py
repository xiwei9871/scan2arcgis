"""Uncalibrated reliability signals and review-region ranking (R1 PoC).

Nothing here is a probability. Outputs are ranking signals; the D0 record must
carry calibration_status=UNCALIBRATED until a calibrator is fitted on an
independent calib split (docs/design/evaluation_framework.md §4).
"""
from __future__ import annotations

import numpy as np


def region_confidence(labels, margin, valid, pred_inst) -> dict[int, float]:
    """Per predicted region: mean classifier margin inside the region."""
    ids = pred_inst[valid & (pred_inst > 0)]
    m = margin[valid & (pred_inst > 0)]
    sums = np.bincount(ids, weights=m); cnt = np.bincount(ids)
    return {int(i): float(sums[i] / cnt[i]) for i in np.nonzero(cnt)[0]}


def review_tiles(margin, valid, tile=64):
    """Tile grid with risk score = 1 - mean margin (higher = review first)."""
    H, W = margin.shape
    out = []
    for y in range(0, H, tile):
        for x in range(0, W, tile):
            v = valid[y:y + tile, x:x + tile]
            if v.mean() < 0.5:
                continue
            mm = margin[y:y + tile, x:x + tile][v]
            # low-margin pixel fraction emphasises small confused areas inside a tile
            risk = 0.5 * (1 - mm.mean()) + 0.5 * float((mm < 0.3).mean())
            out.append((risk, x, y, tile))
    out.sort(reverse=True)
    return out


def error_capture(tiles, err, fractions=(0.1, 0.2)):
    """Fraction of all erroneous pixels contained in the top-k% riskiest tiles,
    compared with a random ordering (expected = k%)."""
    total = err.sum()
    res = {"n_tiles": len(tiles), "total_error_px": int(total)}
    if total == 0 or not tiles:
        return res
    per = np.array([err[y:y + t, x:x + t].sum() for _, x, y, t in tiles], float)
    for f in fractions:
        k = max(1, int(round(f * len(tiles))))
        res[f"top{int(f*100)}pct_tiles_error_capture"] = float(per[:k].sum() / total)
    return res
