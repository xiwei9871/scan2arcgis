import sys
from pathlib import Path
import numpy as np
import vtracer

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "experiments/STITCHVECTOR"))
import sv_common as C  # noqa: E402
import sv_svg as S  # noqa: E402


def _trace(a, **kw):
    h, w = a.shape[:2]
    rgba = np.dstack([a, np.full((h, w), 255, np.uint8)]).ravel().tolist()
    cfg = vtracer.Config(**kw)
    return vtracer.convert_pixels(rgba, w, h, cfg)


def test_parse_relative_and_cubic():
    rings = S.parse_d("M0,0l4,0l0,4l-4,0Z")
    assert len(rings) == 1 and np.allclose(rings[0][2], [4, 4])
    rings = S.parse_d("M0,0C0,1,0,3,0,4L4,4L4,0Z")
    assert len(rings[0]) == 1 + S.NSEG + 2


def test_pixel_mode_cutout_roundtrip_exact():
    rng = np.random.default_rng(1)
    pal = np.array([[200, 40, 40], [40, 200, 40], [40, 40, 200], [240, 240, 240]], np.uint8)
    lab = np.zeros((48, 48), int)
    for _ in range(12):
        y, x = rng.integers(0, 40, 2); lab[y:y + rng.integers(2, 9), x:x + rng.integers(2, 9)] = rng.integers(0, 4)
    a = pal[lab]
    svg = _trace(a, mode="pixel", hierarchical="cutout", filter_speckle=0, color_precision=8)
    f = S.svg_features(svg)
    rec = C.key_rgb(C.render(f, 48, 48))
    assert (rec == a).all(-1).mean() == 1.0
