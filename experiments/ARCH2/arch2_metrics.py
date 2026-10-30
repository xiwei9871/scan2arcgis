"""ARCH-2 metric definitions (pre-registered; labels are read only here, never by C-PAIR).

Candidate classes (evaluation only), for each candidate c from C-PAIR:
  TRUE_NARROW  c is matched one-to-one to an official instance g of canonical width < 10 px (rule below)
  INK_BAND     not TRUE_NARROW, and >= 80% of c's pixels lie within 1.5 px of UNIT_BOUNDARY and >= 60% on image ink
               (the ARCH-0 D1 proxy; NOT an independent ink-band annotation)
  INCIDENTAL   neither
One-to-one matching (Gate 1 and 2): IoU(c, g) >= 0.3 is a possible match (narrow units are thin, so IoU 0.5 is too
strict for a candidate strip); among possible pairs, greedy by descending IoU, each candidate and each instance used
at most once. Duplicates of an already matched instance become INCIDENTAL, never a second success.
Per width group (canonical width of the instance for detection; predicted width of the candidate for candidate counts):
  detection_rate   matched narrow instances / narrow instances
  candidate_counts number of candidates per class (base rates)
For a protection decision P (PROTECT_SOFT) over candidates:
  precision        TRUE_NARROW among protected / protected
  recall           protected TRUE_NARROW / TRUE_NARROW candidates
  fpr              protected non-TRUE_NARROW / non-TRUE_NARROW candidates
  fdr              1 - precision
  false_protection_ink_band_share   INK_BAND among protected / protected   (gate: <= 0.30)
Survival (Gate 3): a protected TRUE_NARROW candidate SURVIVES if its matched instance is recovered (IoU >= 0.5) in the
final partition.
Uncertainty: Wilson 95% interval for every proportion; per-sheet values always reported next to pooled values.
"""
import numpy as np
from scipy.sparse import coo_matrix


def wilson(k, n, z=1.96):
    if n == 0: return [None, None]
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n); h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    lo = 0.0 if k == 0 else min(max((c - h) / d, 0.0), 1.0); hi = 1.0 if k == n else min(max((c + h) / d, 0.0), 1.0)
    return [float(lo), float(hi)]


def prop(k, n):
    return {"k": int(k), "n": int(n), "value": float(k / n) if n else None, "ci95": wilson(k, n)}


def match_one_to_one(cand, inst, narrow_ids, thr=0.3):
    """cand: int map (0 = none, 1..nc); inst: int map of official instances (0 = none); narrow_ids: ids allowed.
    Returns dict cand_id -> inst_id for matched pairs."""
    m = (cand > 0) & (inst > 0)
    C = coo_matrix((np.ones(int(m.sum())), (cand[m], inst[m])), shape=(int(cand.max()) + 1, int(inst.max()) + 1)).tocsr().tocoo()
    ca = np.bincount(cand.ravel(), minlength=int(cand.max()) + 1); ia = np.bincount(inst.ravel(), minlength=int(inst.max()) + 1)
    iou = C.data / (ca[C.row] + ia[C.col] - C.data)
    ok = (iou >= thr) & np.isin(C.col, narrow_ids)
    order = np.argsort(-iou[ok]); used_c, used_g, out = set(), set(), {}
    for c, g in zip(C.row[ok][order], C.col[ok][order]):
        if c in used_c or g in used_g: continue
        used_c.add(c); used_g.add(g); out[int(c)] = int(g)
    return out


def classify(cand, inst, narrow_ids, near_contact_15, ink1, thr=0.3):
    """Return (class per candidate id as dict, matching dict)."""
    mt = match_one_to_one(cand, inst, narrow_ids, thr)
    n = int(cand.max()); sz = np.bincount(cand.ravel(), minlength=n + 1)
    nc = np.bincount(cand.ravel(), weights=near_contact_15.ravel(), minlength=n + 1) / np.maximum(sz, 1)
    ik = np.bincount(cand.ravel(), weights=ink1.ravel(), minlength=n + 1) / np.maximum(sz, 1)
    cls = {}
    for c in range(1, n + 1):
        if sz[c] == 0: continue
        cls[c] = "TRUE_NARROW" if c in mt else ("INK_BAND" if nc[c] >= 0.8 and ik[c] >= 0.6 else "INCIDENTAL")
    return cls, mt


def protection_metrics(cls, protected):
    ids = list(cls); P = set(protected)
    tn = [c for c in ids if cls[c] == "TRUE_NARROW"]; other = [c for c in ids if cls[c] != "TRUE_NARROW"]
    pt = sum(c in P for c in tn); po = sum(c in P for c in other); pi = sum(c in P and cls[c] == "INK_BAND" for c in ids)
    npro = pt + po
    return {"protected": npro, "base_rates": {k: sum(cls[c] == k for c in ids) for k in ("TRUE_NARROW", "INK_BAND", "INCIDENTAL")},
            "precision": prop(pt, npro), "recall": prop(pt, len(tn)), "fpr": prop(po, len(other)),
            "fdr": prop(po, npro), "false_protection_ink_band_share": prop(pi, npro)}
