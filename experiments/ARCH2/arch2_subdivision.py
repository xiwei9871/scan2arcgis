"""ARCH-2 graded common subdivision (corrects experiments/ARCH1/arch1_gate4.graded, kept unchanged as history).

Defect of the ARCH-1 version: the partition key used the candidate label wherever cand_lab > 0, so candidate
interior labels cut the base partition even when every candidate boundary pixel had been removed by the 1-px
dedup (a 1-px-offset duplicate still produced a new region while reporting 0 added boundary pixels).

Corrected rule (pixel-pair level, 4-connectivity):
  base separations   pair (p, q) separated in the base partition: base[p] != base[q]
  candidate pairs    pair separated in the candidate map: cand[p] != cand[q] (cand 0 = no candidate)
  dedup              a candidate pair is DROPPED if a base separation of the SAME orientation exists within its
                     3x3 pair neighbourhood (covers coincident and 1-px-offset duplicates; perpendicular base
                     boundaries at T-junctions do not drop it, so a candidate stays closed where it meets them)
  partition          4-connected components of all pixels over pairs that are neither base- nor kept-candidate-
                     separated (exact 2x lattice, r4b2_edges.components)
Guarantees (unit-tested): every base separation survives; no separation appears outside base | kept candidate pairs.
Kept pairs that end up inside one component (open boundary fragments left after dedup) cannot cut a partition;
they are counted as dangling_kept_pairs and reported, never silently treated as cuts.
"""
import sys
from pathlib import Path
import numpy as np
from scipy import ndimage as ndi

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "R4B2"))
import r4b2_edges as E  # noqa: E402

K3 = np.ones((3, 3), bool)


def separations(lab):
    sr = np.zeros(lab.shape, bool); sd = np.zeros(lab.shape, bool)
    sr[:, :-1] = lab[:, :-1] != lab[:, 1:]; sd[:-1] = lab[:-1] != lab[1:]
    return sr, sd


def graded(base, cand):
    """Return (partition int32 labels 1..n, info dict)."""
    br, bd = separations(base); cr, cd = separations(cand)
    near_r = ndi.binary_dilation(br, K3); near_d = ndi.binary_dilation(bd, K3)
    kr = cr & ~near_r; kd = cd & ~near_d
    lab = E.components(br | kr, bd | kd)
    lr, ld = separations(lab)
    info = {"dangling_kept_pairs": int((kr & ~lr).sum() + (kd & ~ld).sum()), "candidate_pairs": int(cr.sum() + cd.sum()), "kept_pairs": int(kr.sum() + kd.sum()),
            "dropped_as_duplicate": int((cr & near_r).sum() + (cd & near_d).sum())}
    return lab, info, (kr, kd)


def graded_region(base, cand, cover=0.9, size=1.5):
    """Region-level dedup (closure-preserving alternative to the pair-level rule).
    A candidate region c is SKIPPED if one base region already holds >= cover of c and is <= size x |c| (c is already
    separated); otherwise c's full boundary is added (intersection of base and the kept candidates).
    Returns (partition, info, kept candidate ids)."""
    base = base.astype(np.int64); cand = cand.astype(np.int64)
    m = cand > 0; nb = int(base.max()) + 1
    key = cand[m] * nb + base[m]; uk, cnt = np.unique(key, return_counts=True)
    cid, bid = uk // nb, uk % nb
    csz = np.bincount(cand[m], minlength=int(cand.max()) + 1); bsz = np.bincount(base.ravel(), minlength=nb)
    o = np.lexsort((-cnt, cid)); f = np.unique(cid[o], return_index=True)[1]
    c0, b0, n0 = cid[o][f], bid[o][f], cnt[o][f]
    covered = (n0 >= cover * csz[c0]) & (bsz[b0] <= size * csz[c0])
    keep = c0[~covered]
    lut = np.zeros(int(cand.max()) + 1, np.int64); lut[keep] = keep
    c2 = lut[cand]
    k2 = base * (int(c2.max()) + 1) + c2
    br, bd = separations(base); sr, sd = separations(k2)
    lab = E.components(sr, sd)
    info = {"candidates": int(len(c0)), "skipped_already_separated": int(covered.sum()), "kept_candidates": int(len(keep))}
    return lab, info, keep
