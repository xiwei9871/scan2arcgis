import sys
from pathlib import Path
import cv2, numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "experiments" / "R4B1T"))
import r4b1t_labels as L  # noqa: E402


def _unit(strip_w):
    u = np.zeros((60, 80), np.int32); u[:, 40:] = 1; u[:, 20:20 + strip_w] = 2
    return u


def _ub(u):
    b = np.zeros(u.shape, bool); h = u[:, 1:] != u[:, :-1]; b[:, 1:] |= h; b[:, :-1] |= h
    v = u[1:] != u[:-1]; b[1:] |= v; b[:-1] |= v
    return b


def test_B_one_edge_per_transition_and_no_area():
    u = _unit(4); er, ed = L.edges_B(u, np.ones(u.shape, bool))
    assert er.sum() == 3 * 60 and ed.sum() == 0                  # transitions 0|2, 2|0, 0|1, each once per row
    lab, n = L.reconstruct_B(er, ed, np.ones(u.shape, bool))
    assert n == 4                                                # left 0, 4 px strip, middle 0, right 1
    assert len(np.unique(lab[:, 20:24])) == 1 and lab[0, 21] != lab[0, 10]


def test_B_reconstruction_matches_4conn_instances():
    rng = np.random.default_rng(0); u = rng.integers(0, 3, (40, 40)).astype(np.int32)
    u = cv2.resize(u.astype(np.uint8), (120, 120), interpolation=cv2.INTER_NEAREST).astype(np.int32)
    er, ed = L.edges_B(u, np.ones(u.shape, bool)); lab, n = L.reconstruct_B(er, ed, np.ones(u.shape, bool))
    k = 0
    for j in np.unique(u): k += cv2.connectedComponents((u == j).astype(np.uint8), connectivity=4)[0] - 1
    assert n == k
    pairs = np.unique(np.stack([lab.ravel(), u.ravel()], 1), axis=0)
    assert len(pairs) == n                                       # every reconstructed region has one unit


def test_B_ignores_invalid_neighbours():
    u = _unit(4); u[:, :10] = -1
    er, _ = L.edges_B(u, np.ones(u.shape, bool))
    assert not er[:, :10].any()                                  # no edge against unlabelled area


def test_A_optimum_keeps_only_ub_pixels():
    for w in (4, 6):
        u = _unit(w); ub = _ub(u); d = cv2.distanceTransform((~ub).astype(np.uint8), cv2.DIST_L2, 3)
        assert ((L.pstar(L.target_A(d)) > 0.5) == ub).all()
    u = _unit(4); ub = _ub(u); d = cv2.distanceTransform((~ub).astype(np.uint8), cv2.DIST_L2, 3)
    pv2 = L.pstar(L.target_v2(d)) > 0.5; pA = L.pstar(L.target_A(d)) > 0.5
    assert pv2[:, 20:24].all() and not pA[:, 21:23].any()        # v2 floods a 4 px strip, A keeps its 2 px interior
    u = _unit(6); ub = _ub(u); d = cv2.distanceTransform((~ub).astype(np.uint8), cv2.DIST_L2, 3)
    assert not (L.pstar(L.target_v2(d)) > 0.5)[:, 22:24].any()   # 6 px: centre at d = 1.91 > 1.79, not flooded by v2


def test_dist_to_edge_half_pixel_at_edge():
    u = _unit(6); er, ed = L.edges_B(u, np.ones(u.shape, bool)); D = L.dist_to_edge(er, ed)
    assert abs(D[30, 19] - 0.5) < 1e-6 and abs(D[30, 20] - 0.5) < 1e-6 and abs(D[30, 22] - 2.5) < 1e-6


def test_segments_pixel_coordinates():
    er = np.zeros((3, 3), bool); er[1, 0] = True; ed = np.zeros((3, 3), bool); ed[0, 2] = True
    s = L.segments_B(er, ed)
    assert ((1, -1), (1, -2)) in s and ((2, -1), (3, -1)) in s
