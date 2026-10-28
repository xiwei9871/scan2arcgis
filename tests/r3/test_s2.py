import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "experiments" / "R3"))
from s2_lines import a1_regions, fill_from_nearest  # noqa: E402


def test_a1_splits_along_line_and_votes():
    pred = np.zeros((20, 20), np.int32); pred[:, 12:] = 1           # R1 boundary at x=12
    mm = np.ones_like(pred, bool)
    line = np.zeros_like(mm); line[:, 10] = True                     # ink line at x=10
    out, n = a1_regions(pred, mm, line)
    assert n == 2
    assert (out[:, :9] == 0).all() and (out[:, 12:] == 1).all()      # right face: majority class 1


def test_fill_from_nearest_fills_holes_only():
    lab = np.array([[0, 0, -1, 1, 1]]); holes = lab < 0; valid = np.ones_like(holes)
    out = fill_from_nearest(lab, holes, valid)
    assert out[0, 2] in (0, 1) and (out[0, [0, 1, 3, 4]] == [0, 0, 1, 1]).all()
