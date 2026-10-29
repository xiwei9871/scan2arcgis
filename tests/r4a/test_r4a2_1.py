import sys
from pathlib import Path
import cv2, numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "experiments" / "R4A"))
from r4a2_1_labels import sup_weight, pstar  # noqa: E402
from r4a2_1_seeds import old_markers, new_markers, hybrid_markers, segment  # noqa: E402


def test_sup_weight_zones():
    d = np.array([0, 1, 2, 2.01, 4, 4.01, 8, 8.01, 32], np.float32)
    w = sup_weight(d, np.zeros_like(d, np.uint8), 0.1, 0.3)
    assert np.allclose(w, [1, 1, 1, 0.1, 0.1, 0.3, 0.3, 1, 1])


def test_sup_weight_ignore_eval_wins():
    d = np.array([0, 3, 6, 20], np.float32)
    assert (sup_weight(d, np.ones(4, np.uint8), 0.1, 0.3) == 0).all()


def test_pstar_threshold_matches_1px():
    t = lambda d: np.exp(-d * d / 2)
    assert pstar(t(0.955), 4) > 0.8 > pstar(t(1.3693), 4)      # axial in, diagonal out at thr 0.8
    assert abs(pstar(0.5, 4) - 0.8) < 1e-12
    assert pstar(0.0, 4) == 0                                   # every d > 2 px negative has optimum 0


def _dist(lab):
    b = np.zeros(lab.shape, bool)
    h = lab[:, 1:] != lab[:, :-1]; b[:, 1:] |= h; b[:, :-1] |= h
    v = lab[1:] != lab[:-1]; b[1:] |= v; b[:-1] |= v
    return cv2.distanceTransform((~b).astype(np.uint8), cv2.DIST_L2, 3)


def _strip(w):
    lab = np.zeros((120, 200), np.int32); lab[:, 100:] = 2; lab[:, 60:60 + w] = 1
    return _dist(lab)


def test_old_rule_misses_thin_strip_hybrid_seeds_it():
    d = _strip(8)                                               # 8 px strip: interior dist < 3 px
    assert (old_markers(d)[:, 60:68] == 0).all()
    hy = hybrid_markers(d)
    assert (hy[:, 60:68] > 0).any()
    reg = segment(d, hy)
    strip = reg[10:110, 61:67]; vals, cnt = np.unique(strip, return_counts=True)
    assert cnt.max() / strip.size > 0.9 and vals[cnt.argmax()] not in np.unique(reg[:, :55])


def test_documented_width_limit():
    # recorded limitation of the frozen parameters (SMOOTH 1, RATIO 2): seeded from 7 px, not below
    assert all((hybrid_markers(_strip(w))[:, 60:60 + w] > 0).any() for w in (7, 9, 12))
    assert not any((hybrid_markers(_strip(w))[:, 60:60 + w] > 0).any() for w in (3, 4, 5, 6))


def test_hybrid_keeps_one_seed_for_wide_unit():
    lab = np.zeros((200, 200), np.int32); lab[:, 100:] = 1
    d = _dist(lab)
    assert old_markers(d).max() == 2 and hybrid_markers(d).max() == 2
    assert new_markers(d).max() >= 2


def test_hybrid_labels_are_contiguous():
    lab = np.zeros((120, 200), np.int32); lab[:, 100:] = 2; lab[:, 60:65] = 1; lab[:, 150:154] = 3
    hy = hybrid_markers(_dist(lab))
    assert set(np.unique(hy)) == set(range(int(hy.max()) + 1))
