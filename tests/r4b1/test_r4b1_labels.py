import sys
from pathlib import Path
import cv2, numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "experiments" / "R4B1"))
import r4b1_labels as L  # noqa: E402


def _map(strip_w):
    u = np.zeros((120, 200), np.int32); u[:, 100:] = 1; u[:, 40:40 + strip_w] = 2
    inst = np.full(u.shape, -1, np.int32); k0 = 0
    for j in np.unique(u):
        n, cc = cv2.connectedComponents((u == j).astype(np.uint8), connectivity=4); inst[cc > 0] = cc[cc > 0] - 1 + k0; k0 += n - 1
    ub = np.zeros(u.shape, bool); h = u[:, 1:] != u[:, :-1]; ub[:, 1:] |= h; ub[:, :-1] |= h
    d = cv2.distanceTransform((~ub).astype(np.uint8), cv2.DIST_L2, 3)
    return inst, ub, d


def test_safe_respects_priority_and_hard_hits_soft_positives():
    inst, ub, d = _map(8)
    ign = np.zeros(ub.shape, bool); ink1 = np.zeros(ub.shape, bool); ink1[:, 44] = True
    w = L.own_width(inst); narrow, cand, hard, safe = L.rule_sets(inst, ub, d, ign, ink1, w)
    assert not (safe & (ub | (d <= 2) | ink1 | ign)).any()
    assert (hard & (d <= 2)).any()                       # the HARD rule overwrites soft positives


def test_no_safe_pixels_in_a_5px_strip():
    inst, ub, d = _map(5)
    z = np.zeros(ub.shape, bool); w = L.own_width(inst)
    _, _, hard, safe = L.rule_sets(inst, ub, d, z, z, w)
    assert hard.any() and not safe.any()                 # interior lies entirely within d <= 2


def test_safe_weight_only_changes_safe_pixels():
    w_v2 = np.full((10, 10), 0.1, np.float32); safe = np.zeros((10, 10), bool); safe[3, 3] = True
    w = L.safe_weight(w_v2, safe)
    assert w[3, 3] == 1.0 and (w[~safe] == w_v2[~safe]).all()
