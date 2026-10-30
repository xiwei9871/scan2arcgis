import sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "experiments/STITCHVECTOR"))
import sv_common as C  # noqa: E402
import sv_r0 as R0  # noqa: E402


def test_r0_random_8_colour_roundtrip():
    rng = np.random.default_rng(0); pal = rng.integers(0, 256, (8, 3), dtype=np.uint8)
    a = pal[rng.integers(0, 8, (64, 64))]
    f = R0.r0_features(a)
    assert (C.key_rgb(C.render(f, 64, 64)) == a).all()


def test_ring_with_hole_and_nesting():
    a = np.zeros((40, 40, 3), np.uint8); a[5:35, 5:35] = (200, 0, 0); a[12:28, 12:28] = (0, 200, 0); a[18:22, 18:22] = (0, 0, 200)
    f = R0.r0_features(a)
    assert any(len(g.interiors) > 0 for g, _, _ in f)
    assert (C.key_rgb(C.render(f, 40, 40)) == a).all()


def test_gpkg_roundtrip_equals_memory(tmp_path):
    rng = np.random.default_rng(1); pal = rng.integers(0, 256, (5, 3), dtype=np.uint8)
    a = pal[rng.integers(0, 5, (32, 48))]
    f = R0.r0_features(a); p = tmp_path / "t.gpkg"
    R0.write_gpkg(f, p)
    assert (R0.read_render(p, 32, 48) == C.key_rgb(C.render(f, 32, 48))).all()
    assert (R0.read_render(p, 32, 48) == a).all()
