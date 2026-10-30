import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "experiments/STITCHVECTOR"))
import sv_r2 as R  # noqa: E402


def _scene():
    rng = np.random.default_rng(0)
    a = np.zeros((96, 96), np.int32); a[:, 48:] = 1
    a[20:60, 10:13] = 2                       # 3 px strip
    a[70, 5:90] = 3                           # 1 px line
    a[30:50, 60:80] = 2; a[38:42, 68:72] = 0  # ring with hole
    a[rng.integers(0, 96, 40), rng.integers(0, 96, 40)] = 4   # speckle
    return a


def test_progressive_exact_and_planar_every_stage():
    a = _scene(); f, log = R.progressive(a, check=True)
    assert log[-1]["final_residual_px"] == 0
    for rec in log[1:-1]:
        if "trace_ok" in rec:
            assert rec["trace_ok"] and rec["area_sum_equals_window"] and rec["coverage_valid_no_overlap"]


def test_no_small_block_discarded():
    a = np.zeros((40, 40), np.int32); a[20, 20] = 1   # single-pixel feature must survive
    f, log = R.progressive(a)
    assert (R.render(f, 40, 40) == a).all()


def test_transparent_layer_not_drawn():
    a = np.full((30, 30), R.TR, np.int32); a[10:12, :] = 5
    f, _ = R.progressive(a)
    r = R.render(f, 30, 30)
    assert (r[10:12] == 5).all() and (r[:10] == -1).all()


def test_fill_completion_flags_inferred():
    lab = np.zeros((20, 20), np.int32); lab[:, 10:] = 1; lab[:, 9:11] = 2
    L, it, left = R.fill_complete(lab, lab == 2)
    assert left == 0 and set(np.unique(L[:, 9:11])) <= {0, 1}
