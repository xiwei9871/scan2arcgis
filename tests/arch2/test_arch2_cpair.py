import sys
from pathlib import Path
import cv2, numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "experiments" / "ARCH2"))
import arch2_cpair as C  # noqa: E402


def _scene(width=5, gap=False, colour=True):
    """Two vertical boundary lines (strength 0.9) enclosing a strip; RGB strip colour differs from both sides."""
    H, W = 120, 80; b = np.zeros((H, W), np.float32); x0 = 35
    b[10:110, x0] = 0.9; b[10:110, x0 + width + 1] = 0.9
    if gap: b[55:58, x0] = 0.0
    lab = np.zeros((H, W, 3), np.float32); lab[..., 0] = 70
    if colour: lab[:, x0 + 1:x0 + width + 1, 1] = 40
    ink = np.zeros((H, W), bool)
    return b, lab, ink, x0


def test_strip_between_two_lines_is_one_candidate():
    b, lab, ink, x0 = _scene(5)
    g = C.generate(b, lab, ink)
    assert g["K"] == 1
    m = g["cand"] == 1; ys, xs = np.nonzero(m)
    assert xs.min() >= x0 + 1 and xs.max() <= x0 + 5 and ys.max() - ys.min() > 80
    f = g["feats"]; assert abs(f["s_width"][0] - 6) <= 1 and f["s_edge"][0] > 0.8 and f["s_colour"][0] > 30


def test_short_gap_is_bridged():
    b, lab, ink, x0 = _scene(5, gap=True)
    g = C.generate(b, lab, ink)
    assert g["K"] == 1 and g["feats"]["bridged_share"][0] > 0


def test_missing_colour_gives_uncertain():
    b, lab, ink, x0 = _scene(5)
    ink[:, x0 - 4:x0 + 10] = True                                    # all centre and side pixels on ink
    g = C.generate(b, lab, ink)
    assert np.isnan(g["feats"]["s_colour"][0])
    thr = {"protect": {"s_edge": 0.1, "s_colour": 1.0, "s_width": 1.0}, "ink": {"s_colour": 99, "s_width": 99}}
    assert C.states(g["feats"], thr)[0] == "UNCERTAIN"


def test_states_protect_merge_conflict():
    f = {"s_edge": np.array([0.9, 0.9, 0.9]), "s_colour": np.array([30.0, 2.0, 30.0]), "s_width": np.array([6.0, 2.5, 2.5])}
    thr = {"protect": {"s_edge": 0.5, "s_colour": 10.0, "s_width": 3.0}, "ink": {"s_colour": 5.0, "s_width": 4.0}}
    assert list(C.states(f, thr)) == ["PROTECT_SOFT", "MERGE", "UNCERTAIN"]


def test_soft_protection_raises_merge_cost():
    import r4c0_rag as R
    lab = np.zeros((30, 30), np.int32); lab[:, :10] = 1; lab[:, 10:13] = 2; lab[:, 13:] = 3
    sr = np.zeros((30, 30), np.float32); sd = np.zeros((30, 30), np.float32); sr[:, 9] = 0.4; sr[:, 12] = 0.4
    rag = R.build_rag(lab, sr, sd)
    none = C.merge_protected(rag, np.zeros(4), 0.0, 0.45)
    prot = C.merge_protected(rag, np.array([0, 0, 7, 0]), 0.2, 0.45)
    assert len(none) == 2 and len(prot) == 0
