import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "experiments" / "R2_real_map"))
from gsj_metrics3 import adjacency, norm_sym  # noqa: E402
from gsj_oracle import direct_scores  # noqa: E402
from gsj_sensitivity import perturb  # noqa: E402


def test_norm_sym():
    assert norm_sym(" t 1 ") == "t1" and norm_sym(float("nan")) is None and norm_sym(None) is None


def test_direct_scores_do_not_remap_labels():
    gt = np.zeros((10, 10), np.int32); gt[:, 5:] = 1
    swapped = 1 - gt                     # perfect segmentation, wrong names
    r = direct_scores(swapped, gt, np.ones_like(gt, bool), 2)
    assert r["pixel_acc"] == 0.0 and r["miou"] == 0.0


def test_adjacency_symmetric_and_ignores_invalid():
    lab = np.array([[0, 0, 1], [2, 2, 1]]); valid = np.ones_like(lab, bool)
    assert adjacency(lab, valid) == {(0, 1), (0, 2), (1, 2)}
    valid[:, 2] = False
    assert adjacency(lab, valid) == {(0, 2)}


def test_perturb_shift_and_identity():
    H = np.eye(3)
    assert np.allclose(perturb(H, "none", 0, (0, 0)), H)
    p = perturb(H, "shift_diag", np.sqrt(2), (0, 0)) @ np.array([0, 0, 1.0])
    assert np.allclose(p[:2], [1, 1])
