import shutil, sys
from pathlib import Path
import numpy as np, pytest, shapely
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.stitchvector_editor.core import Document, EditError, FACE, LINE, sha256, coverage_report  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SRC = None
for base in (ROOT, ROOT.parents[2]):                       # worktree or main checkout (runs/ is local only)
    p = base / "runs/stitchvector/v3_u2_real/gpkg/u2_B2c.gpkg"
    if p.exists(): SRC = p; break
pytestmark = pytest.mark.skipif(SRC is None, reason="local u2_B2c.gpkg not available")


@pytest.fixture
def doc(tmp_path):
    src = tmp_path / "in.gpkg"; shutil.copyfile(SRC, src); return Document(src, (300, 300)), src, tmp_path


def test_open_and_coverage(doc):
    d, src, _ = doc
    assert len(d.F) == 665 and len(d.L) == 35 and coverage_report(d.F, 300, 300)["accepted"]


def test_recolour_face_no_geometry_change_and_undo_redo(doc):
    d, _, _ = doc; e = int(d.F["_eid"].iloc[0]); g0 = d.F.geometry.iloc[0]
    d.recolour(FACE, [e], "#123456"); assert d.F.loc[d.F["_eid"] == e, "rgb"].iloc[0] == "#123456" and d.F.geometry.iloc[0].equals(g0)
    d.undo_op(); assert d.F.loc[d.F["_eid"] == e, "rgb"].iloc[0] != "#123456"
    d.redo_op(); assert d.F.loc[d.F["_eid"] == e, "rgb"].iloc[0] == "#123456"


def test_group_rewidth_recolour_lines(doc):
    d, _, _ = doc; e = int(d.L["_eid"].iloc[0]); grp = d.group(e)
    d.rewidth(grp, 4); d.recolour(LINE, grp, "#9a9c8c")
    assert (d.L.loc[d.L["_eid"].isin(grp), "width_px"] == 4).all()


def test_merge_adjacent_and_refuse_disconnected(doc):
    d, _, _ = doc
    big = int(d.F["_eid"].iloc[int(np.argmax(d.F.geometry.area))]); gb = d.F.loc[d.F["_eid"] == big, "geometry"].iloc[0]
    direct = [int(e) for e, g in zip(d.F["_eid"], d.F.geometry) if e != big and shapely.length(shapely.intersection(g, gb)) > 0]
    pair = [big, direct[0]]; n0 = len(d.F); d.merge_faces(pair)
    assert len(d.F) == n0 - 1 and coverage_report(d.F, 300, 300)["accepted"]
    g = list(zip(d.F["_eid"], d.F.geometry)); a = g[0]
    b = next((e, x) for e, x in g[1:] if x.distance(a[1]) > 5)          # two faces that do not touch
    with pytest.raises(EditError): d.merge_faces([int(a[0]), int(b[0])])


def test_split_draw_delete(doc):
    d, _, _ = doc; e = int(d.L.loc[d.L.geometry.length.idxmax(), "_eid"]); g = d.L.loc[d.L["_eid"] == e, "geometry"].iloc[0]
    p = g.interpolate(0.5, normalized=True); a, b = d.split_line(e, p.x, p.y)
    assert len(d.L) == 36 and abs(sum(d.L.loc[d.L["_eid"].isin([a, b]), "geometry"].length) - g.length) < 1e-6
    n = d.add_line([[10, 10], [20, 12]], 2, "#000000"); d.delete_lines([n]); assert len(d.L) == 36


def test_save_as_new_file_readback_and_source_unchanged(doc):
    d, src, tmp = doc; h0 = sha256(src); d.recolour(FACE, [int(d.F["_eid"].iloc[5])], "#abcdef")
    with pytest.raises(EditError): d.save_as(src)
    r = d.save_as(tmp / "out.gpkg")
    assert r["accepted"] and r["readback_matches_memory"] and r["input_sha256_unchanged"] and sha256(src) == h0
    assert r["face_columns_kept"] and r["line_columns_kept"] and Path(r["edit_log"]).exists()
    assert d.diff()[FACE]["attribute_changed"] == 1 and d.diff()[FACE]["geometry_changed"] == 0


def test_line_to_face_valid_or_rolled_back(doc):
    d, _, _ = doc; e = int(d.L["_eid"].iloc[0]); grp = d.group(e); F0 = d.F.copy()
    try:
        d.line_to_face(grp, 4, "#9a9c8c"); assert coverage_report(d.F, 300, 300)["accepted"]
    except EditError as x:
        assert "EXPERIMENTAL_NOT_ACCEPTED" in str(x) and len(d.F) == len(F0)
