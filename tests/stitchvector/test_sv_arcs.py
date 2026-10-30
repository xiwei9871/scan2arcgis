import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "experiments/STITCHVECTOR"))
import sv_arcs as A  # noqa: E402


def _scene(seed=0):
    rng = np.random.default_rng(seed); lab = np.zeros((64, 64), np.int64)
    lab[10:40, 5:30] = 1; lab[20:25, 0:64] = 2          # thin band crossing
    lab[45:60, 40:60] = 3; lab[50:55, 47:53] = 4         # hole inside 3
    lab[30, 30] = 5                                      # single pixel
    lab[rng.integers(0, 64, 30), rng.integers(0, 64, 30)] = 6
    return lab


def test_exact_single_pass_is_lossless_and_strict_valid():
    lab = _scene(); p, v, lines, _ = A.single_pass(lab, 0)
    assert (A.render(p, v, *lab.shape) == lab).all()
    t = A.topology(p, *lab.shape); assert all(t.values())


def test_arcs_shared_once():
    lab = _scene(); arcs = A.arcs_from_labels(lab)
    edges = set()
    for a in arcs:
        for p, q in zip(a[:-1], a[1:]):
            k = tuple(sorted([tuple(p), tuple(q)])); assert k not in edges; edges.add(k)
    hz, vt = A.boundary_edges(lab); assert len(edges) == int(hz.sum() + vt.sum())


def test_progressive_ends_exact_and_strict_valid():
    for s in range(3):
        lab = _scene(s); p, v, lines, log = A.progressive(lab)
        assert log[-1]["mismatch_px"] == 0
        assert (A.render(p, v, *lab.shape) == lab).all()
        assert all(A.topology(p, *lab.shape).values())


def test_coarse_tolerance_stays_planar():
    lab = _scene(); p, v, lines, n0 = A.single_pass(lab, 4)
    t = A.topology(p, *lab.shape); assert t["area_sum_equals_window"] and t["union_area_equals_window"]
    assert t["coverage_is_valid_strict"]
