import sys
from pathlib import Path
import cv2, numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "experiments" / "R4B1"))
import r4b1_sampling as SA  # noqa: E402


def _diag_strip():
    inst = np.zeros((300, 300), np.int32)                    # background instance 0 (large)
    m = np.zeros((300, 300), np.uint8)
    cv2.line(m, (20, 20), (280, 280), 1, 6)                  # diagonal strip ~6 px wide, area < 20000
    inst[m > 0] = 1
    return inst


def test_frozen_anchor_is_first_raster_pixel_on_the_outline():
    inst = _diag_strip()
    ids, pos = SA.frozen_anchors(inst)
    k = list(ids).index(2)                                   # instance 1 -> id 2 (1-based)
    y, x = divmod(int(pos[k]), inst.shape[1])
    ys, xs = np.nonzero(inst == 1)
    assert y == ys.min() and x == xs[ys == ys.min()].min()   # top row, leftmost pixel
    assert y < 40 and x < 40                                 # at the upper-left END of the strip


def test_interior_anchor_is_inside_and_deepest():
    inst = _diag_strip()
    ids, pos = SA.interior_anchors(inst)
    k = list(ids).index(2); y, x = divmod(int(pos[k]), inst.shape[1])
    assert inst[y, x] == 1
    d = cv2.distanceTransform(np.pad((inst == 1).astype(np.uint8), 1), cv2.DIST_L2, 5)[1:-1, 1:-1]
    assert d[y, x] == d.max()


def test_simulated_crop_matches_frozen_placement_bounds():
    rng = np.random.default_rng(0)
    for _ in range(200):
        y0, x0 = SA.simulate_crop(int(rng.integers(0, 2911)), int(rng.integers(0, 3550)), 2911, 3550, rng)
        assert 0 <= y0 <= 2911 - 512 and 0 <= x0 <= 3550 - 512
