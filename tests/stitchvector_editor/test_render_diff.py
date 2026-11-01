"""Deterministic render + residual checks (task D 1-4) on the small u2 B2c input."""
import shutil, sys
from pathlib import Path
import numpy as np, pyogrio, pytest
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.stitchvector_editor import render as R  # noqa: E402

INP = None
for base in (Path(__file__).resolve().parents[2], Path.home() / "geomap2arcgis"):
    p = base / "runs/stitchvector/editor_v01/inputs"
    if (p / "u2_B2c.gpkg").exists(): INP = p; break
pytestmark = pytest.mark.skipif(INP is None, reason="local editor inputs not available")


@pytest.fixture
def frames():
    F = pyogrio.read_dataframe(INP / "u2_B2c.gpkg", layer=R.FACE); L = pyogrio.read_dataframe(INP / "u2_B2c.gpkg", layer=R.LINE)
    return F, L


def test_scan_vs_itself_is_zero():
    a = np.asarray(Image.open(INP / "u2_original.png").convert("RGB"))
    assert R.residual(a, a)[1].max() == 0


def test_repeat_render_identical_and_fully_covered():
    a, fid, _ = R.render(INP / "u2_B2c.gpkg", (300, 300)); b, _, _ = R.render(INP / "u2_B2c.gpkg", (300, 300))
    assert (a == b).all() and (fid >= 0).all() and R.png_bytes(a) == R.png_bytes(b)


def test_deleted_line_is_located(frames):
    F, L = frames; base = R.render_frames(F, L, None, (300, 300))[0]
    i = int(np.argmax(L.geometry.length)); cut = R.render_frames(F, L.drop(L.index[i]), None, (300, 300))[0]
    d = R.residual(base, cut)[1] > 0; ys, xs = np.nonzero(d)
    assert d.any()
    near = L.geometry.iloc[i].buffer(float(L["width_px"].iloc[i]) / 2 + 2)
    import shapely
    assert all(near.contains(shapely.Point(x + 0.5, y + 0.5)) for x, y in zip(xs, ys))


def test_recoloured_face_is_located(frames):
    F, L = frames; base, fid, _ = R.render_frames(F, L, None, (300, 300))
    j = int(np.argmax(F.geometry.area)); G = F.copy(); G.loc[G.index[j], "rgb"] = "#00ff00"
    d = R.residual(base, R.render_frames(G, L, None, (300, 300))[0])[1] > 0
    assert d.any() and (fid[d] == j).all()


def test_shape_mismatch_refused():
    with pytest.raises(ValueError): R.residual(np.zeros((3, 3, 3), np.uint8), np.zeros((3, 4, 3), np.uint8))
