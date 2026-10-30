import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "experiments" / "ARCH1"))
import arch1_linewidth as LW  # noqa: E402


def _median_width(img):
    m = LW.measure(img); k = m["reliable"] & (m["y"] > 20) & (m["y"] < 180) & (m["x"] > 20) & (m["x"] < 180)
    return float(np.median(m["width"][k]))


def test_widths_from_1_5_px_are_accurate():
    for w in (1.5, 2.0, 3.0, 5.0):
        assert abs(_median_width(LW.synthetic(w, 30)) - w) <= max(0.35, 0.12 * w)


def test_crossing_is_flagged_unreliable():
    m = LW.measure(LW.synthetic(2.0, 0, "cross"))
    near = np.hypot(m["y"] - 100, m["x"] - 100) <= 3
    assert near.any() and not m["reliable"][near].any()


def test_known_limit_one_pixel_line_overestimated():
    # documented failure (Gate 3): 1 px lines are overestimated at every angle (1.23-1.80 px, pooled median 1.39)
    assert all(_median_width(LW.synthetic(1.0, a)) > 1.2 for a in (0, 30, 45, 90))


def test_repeatable():
    img = LW.synthetic(2.5, 45)
    a, b = LW.measure(img), LW.measure(img)
    assert all(np.array_equal(a[k], b[k]) for k in a)
