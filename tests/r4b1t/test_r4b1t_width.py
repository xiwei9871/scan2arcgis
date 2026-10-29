import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "experiments" / "R4B1T"))
import r4b1t_width as W  # noqa: E402


def _strip(k, length=120):
    inst = np.zeros((length, 60), np.int32); inst[:, 20:20 + k] = 1; inst[:, 20 + k:] = 2
    return inst


def test_strip_width_quantisation():
    # documented: odd k reads k, even k reads k - 1
    for k in (3, 4, 5, 6, 7, 8, 12):
        inst = _strip(k, length=max(120, 2 * (200 // k + 1)))
        _, _, ids, w = W.canonical_widths(inst, np.ones(inst.shape, bool))
        j = list(ids).index(2)                                  # instance value 1 -> id 2
        assert abs(w[j] - (k if k % 2 else k - 1)) < 0.05, (k, w[j])


def test_bins_edges():
    assert W.width_bin(2.99) == "lt3" and W.width_bin(3.0) == "3-6" and W.width_bin(6.0) == "6-10"
    assert W.width_bin(10.0) == "10-20" and W.width_bin(20.0) == "ge20"


def test_valid_mask_restricts_area():
    inst = _strip(5); valid = np.ones(inst.shape, bool); valid[:80] = False
    _, area, ids, _ = W.canonical_widths(inst, valid)
    assert area[2] == 40 * 5 and 2 in ids                     # 200 px left inside the valid area
