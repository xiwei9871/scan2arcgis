"""ARCH-2 shared runner: C-PAIR on one sheet, candidate classes (evaluation), graded subdivision, protection ids.
Prediction part (generate, subdivision, merge) reads only B2 probabilities and the RGB image.
Labels are read only in label_part() for classes, Oracle A / B and scoring.
"""
import json, sys
from pathlib import Path
import cv2, numpy as np

ROOT = Path(__file__).resolve().parents[2]
for p in ("ARCH2", "ARCH1", "R4C0", "R4A", "R4B1T"): sys.path.insert(0, str(ROOT / "experiments" / p))
import arch2_cpair as C  # noqa: E402
import arch2_subdivision as S  # noqa: E402
import arch2_metrics as M  # noqa: E402
import arch1_feats as F  # noqa: E402
import r4c0_rag as R  # noqa: E402
import r4c0_gate3 as G3  # noqa: E402

PR = json.load(open(ROOT / "experiments/ARCH2/arch2_preregistration.json"))
AM = json.load(open(ROOT / "experiments/ARCH2/arch2_prereg_amendment1.json"))
SUB = PR["parameters_fixed_now"]["subdivision"]
LOCAL = ROOT / "runs/arch2"
WG = [("3-6", 3, 6), ("6-10", 6, 10), ("10-20", 10, 20), ("gt20", 20, 1e9)]


def prediction_part(code):
    X = F.load_inputs(code)
    g = C.generate(X["b"], X["lab"], X["ink1"])
    base = F.compact(F.initial_regions(code, X)).astype(np.int32)
    return X, g, base


def subdivide(base, cand, keep_ids=None):
    c = cand.astype(np.int64)
    if keep_ids is not None:
        lut = np.zeros(int(c.max()) + 1, np.int64); lut[np.asarray(keep_ids, int)] = np.asarray(keep_ids, int); c = lut[c]
    lab, info, kept = S.graded_region(base, c, SUB["cover"], SUB["size"])
    return lab.astype(np.int32), info, kept


def protection_ids(lab, cand, ids):
    """Initial region -> protecting candidate id (majority overlap >= 0.5 of the region with a protected candidate)."""
    n = int(lab.max()); pc = np.zeros(n + 1, np.int64)
    if len(ids) == 0: return pc
    lut = np.zeros(int(cand.max()) + 1, np.int64); lut[np.asarray(ids, int)] = np.asarray(ids, int)
    c = lut[cand]; m = c > 0
    key = lab[m].astype(np.int64) * (int(c.max()) + 1) + c[m]; uk, cnt = np.unique(key, return_counts=True)
    r, k = uk // (int(c.max()) + 1), uk % (int(c.max()) + 1); sz = np.bincount(lab.ravel(), minlength=n + 1)
    ok = cnt >= 0.5 * sz[r]; pc[r[ok]] = k[ok]
    return pc


def label_part(code, X, g):
    Rr, V, i1, ia, ids, wid = F.label_ref(code)
    ub = (Rr["unit_boundary"] > 0) & V
    near15 = cv2.distanceTransform((~ub).astype(np.uint8), cv2.DIST_L2, 3) <= 1.5
    narrow = ids[wid < 10]
    cls, mt = M.classify(g["cand"].astype(np.int64), i1, narrow, near15, X["ink1"])
    return {"Rr": Rr, "V": V, "i1": i1, "ia": ia, "ids": ids, "wid": wid, "cls": cls, "match": mt}


def width_bins(wid, vals, ids_mask=None):
    out = {}
    for n, lo, hi in WG:
        m = (wid >= lo) & (wid < hi)
        if m.any(): out[n] = {"n": int(m.sum()), "hits": int(vals[m].sum())}
    return out
