import sys
from pathlib import Path
import cv2, numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "experiments" / "R4B0"))
import r4b0_1_common as C  # noqa: E402


def test_a1_terrain_direction_high_prob_is_barrier():
    # two units separated by a vertical high-probability boundary; seeds come from a distance map
    prob = np.zeros((80, 120), np.float32); prob[:, 58:62] = 0.95
    dist = cv2.distanceTransform((prob < 0.5).astype(np.uint8), cv2.DIST_L2, 3).astype(np.float32)
    reg, mk = C.a1_regions(prob, dist)
    assert mk.max() == 2
    left, right = np.unique(reg[:, :55]), np.unique(reg[:, 65:])
    assert len(left) == 1 and len(right) == 1 and left[0] != right[0]


def _lines(width, angle_deg, up=8, size=600):
    """White page with dark parallel lines of the given width (px at final scale), drawn at 8x then area-averaged."""
    S = size * up; img = np.full((S, S), 235, np.uint8)
    t = np.radians(angle_deg); d = np.array([np.cos(t), np.sin(t)]); nrm = np.array([-d[1], d[0]])
    for off in range(-S, S, 40 * up):
        c = np.array([S / 2, S / 2]) + nrm * off
        p0, p1 = (c - d * S).astype(int), (c + d * S).astype(int)
        cv2.line(img, tuple(int(v) for v in p0), tuple(int(v) for v in p1), 40, max(1, int(round(width * up))), cv2.LINE_8)
    img = cv2.resize(img, (size, size), interpolation=cv2.INTER_AREA)
    return np.dstack([img] * 3)


def test_estimator_tracks_subpixel_width_and_is_direction_neutral():
    est = {w: C.line_width(_lines(w, 0))["median_width_px"] for w in (0.75, 1.5, 3.0)}
    assert abs(est[0.75] / est[1.5] - 0.5) <= 0.15 * 0.5 and abs(est[3.0] / est[1.5] - 2.0) <= 0.15 * 2.0
    a = C.line_width(_lines(1.5, 0))["median_width_px"]; g = C.line_width(_lines(1.5, 45))["median_width_px"]
    assert 0.85 <= g / a <= 1.18


def test_estimator_rejects_text_like_blobs():
    img = np.full((400, 400, 3), 235, np.uint8)
    rng = np.random.default_rng(0)
    for _ in range(300):
        x, y = rng.integers(10, 390, 2); cv2.putText(img, "A8", (int(x), int(y)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (40, 40, 40), 1)
    assert C.line_width(img)["accepted_components"] == 0


def test_estimator_repeatable():
    im = _lines(1.2, 30)
    assert C.line_width(im) == C.line_width(im)
