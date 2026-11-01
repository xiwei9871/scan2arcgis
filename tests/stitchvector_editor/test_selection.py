import shutil, sys
from pathlib import Path
import numpy as np, pytest, shapely
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.stitchvector_editor.core import Document, EditError, FACE, LINE, coverage_report  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
INP = None
for base in (ROOT, ROOT.parents[2]):
    p = base / "runs/stitchvector/editor_v01/inputs"
    if (p / "u2_B2c.gpkg").exists(): INP = p; break
pytestmark = pytest.mark.skipif(INP is None, reason="local editor inputs not available")


@pytest.fixture
def doc(tmp_path):
    src = tmp_path / "in.gpkg"; shutil.copyfile(INP / "u2_B2c.gpkg", src)
    img = np.asarray(Image.open(INP / "u2_original.png").convert("RGB")); return Document(src, (300, 300), img)


def test_gesture_and_select_do_not_modify(doc):
    F0 = doc.F.copy(); g = doc.gesture("brush", [[10, 10], [40, 40]], 3)
    ids = doc.select_region(g, FACE, "touch")
    assert ids and len(doc.log) == 0 and doc.F.equals(F0)
    lasso = doc.gesture("lasso", [[0, 0], [50, 0], [50, 50], [0, 50]])
    assert set(doc.select_region(lasso, FACE, "centre")) <= set(doc.select_region(lasso, FACE, "touch"))
    with pytest.raises(EditError): doc.gesture("lasso", [[0, 0], [1, 1]])


def test_grow_shrink(doc):
    big = int(doc.F["_eid"].iloc[int(np.argmax(doc.F.geometry.area))])
    g1 = doc.grow([big]); assert big in g1 and len(g1) > 1
    assert set(doc.shrink(g1)) <= set(g1)


def test_merge_preview_then_merge_components_valid(doc):
    lasso = doc.gesture("lasso", [[5, 5], [60, 5], [60, 60], [5, 60]]); ids = doc.select_region(lasso, FACE, "centre")
    pv = doc.merge_preview(ids); assert pv["groups"] and all("outline" in g for g in pv["groups"])
    n0 = len(doc.F); r = doc.merge_components(ids)
    assert len(doc.F) < n0 and coverage_report(doc.F, 300, 300)["accepted"]
    doc.undo_op(); assert len(doc.F) == n0


def test_heal_preview_and_apply(doc):
    v = doc.L.iloc[0].geometry; stroke = [list(v.coords[0]), list(v.coords[-1])]
    region = doc.gesture("brush", stroke, 4); pv = doc.heal_preview(region)
    assert "candidates" in pv and all(c["decision"] in ("merge", "keep", "uncertain") for c in pv["candidates"])
    if pv["counts"]["merge"]:
        n0 = len(doc.F); doc.heal_apply(pv["preview_id"]); assert len(doc.F) < n0 and coverage_report(doc.F, 300, 300)["accepted"]
        doc.undo_op(); assert len(doc.F) == n0
