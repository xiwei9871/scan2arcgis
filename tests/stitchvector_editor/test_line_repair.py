import shutil, sys
from pathlib import Path
import numpy as np, pytest, shapely
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.stitchvector_editor import core  # noqa: E402
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


def _heal_stroke(doc):
    g = doc.L.geometry.iloc[0]; pts = [list(g.interpolate(t, normalized=True).coords[0]) for t in (0.2, 0.5, 0.8)]
    return doc.gesture("brush", pts, 4)


def test_lines_default_unknown_and_never_auto_merged(doc):
    assert set(doc.L["line_role"]) == {"UNKNOWN"}
    pv = doc.heal_preview(_heal_stroke(doc))
    assert all(c["reason"] != "under a COVER line" for c in pv["candidates"])
    assert all(c["decision"] != "merge" or c["reason"] != "under a SPLIT/UNKNOWN line" for c in pv["candidates"])


def test_stale_preview_rejected_after_edit_undo_redo(doc):
    pv = doc.heal_preview(_heal_stroke(doc))
    doc.recolour(LINE, [int(doc.L["_eid"].iloc[0])], "#123456")
    with pytest.raises(EditError): doc.heal_apply(pv["preview_id"])
    pv = doc.heal_preview(_heal_stroke(doc)); doc.undo_op()
    with pytest.raises(EditError): doc.heal_apply(pv["preview_id"])
    pv = doc.heal_preview(_heal_stroke(doc)); doc.redo_op()
    with pytest.raises(EditError): doc.heal_apply(pv["preview_id"])
    with pytest.raises(EditError): doc.heal_apply("heal-does-not-exist")


def test_heal_rechecks_adjacency(doc):
    pv = doc.heal_preview(_heal_stroke(doc))
    rec = next((c for c in pv["candidates"] if c["decision"] == "merge"), None)
    if rec is None: pytest.skip("no merge candidate near this line")
    far = [int(e) for e in doc.F["_eid"] if e != rec["target"] and e not in doc._edge_neighbours(rec["id"])][0]
    doc.previews[pv["preview_id"]]["candidates"] = [{**rec, "target": far}]
    n0 = len(doc.F)
    with pytest.raises(EditError): doc.heal_apply(pv["preview_id"])
    assert len(doc.F) == n0


def test_non_adjacent_merge_refused(doc):
    a = int(doc.F["_eid"].iloc[0]); nb = set(doc._edge_neighbours(a))
    b = next(int(e) for e in doc.F["_eid"] if int(e) != a and int(e) not in nb and not (set(doc._edge_neighbours(int(e))) & nb))
    n0 = len(doc.F)
    with pytest.raises(EditError): doc.merge_faces([a, b])
    assert len(doc.F) == n0


def test_failed_save_leaves_nothing_and_stays_dirty(doc, tmp_path, monkeypatch):
    doc.recolour(LINE, [int(doc.L["_eid"].iloc[0])], "#123456")
    real = doc.verify
    monkeypatch.setattr(doc, "verify", lambda p, **kw: {**real(p), "accepted": False})
    out = tmp_path / "out.gpkg"
    with pytest.raises(EditError): doc.save_as(out)
    assert not out.exists() and not list(tmp_path.glob(".out.*")) and doc.dirty
    monkeypatch.setattr(doc, "verify", real)
    r = doc.save_as(out); assert out.exists() and r["accepted"] and not doc.dirty


def test_legend_changes_style_not_geometry_and_round_trips(doc, tmp_path):
    e = int(doc.L["_eid"].iloc[0]); g0 = doc.L.loc[doc.L["_eid"] == e, "geometry"].iloc[0]
    f = int(doc.F["_eid"].iloc[0]); fg0 = doc.F.loc[doc.F["_eid"] == f, "geometry"].iloc[0]
    doc.apply_legend(LINE, [e], "L_TEETH_RED"); doc.apply_legend(FACE, [f], "F_PINK")
    doc.set_style("L_TEETH_RED", {"tooth_spacing": 6.0, "tooth_side": "right"})
    r = {x["id"]: x for x in doc.render_lines()}[e]
    assert r["line_type"] == "teeth" and len(r["teeth"]) >= 1
    assert doc.L.loc[doc.L["_eid"] == e, "geometry"].iloc[0].equals_exact(g0, 0)
    assert doc.F.loc[doc.F["_eid"] == f, "geometry"].iloc[0].equals_exact(fg0, 0)
    with pytest.raises(EditError): doc.apply_legend(LINE, [e], "F_PINK")
    with pytest.raises(EditError): doc.set_style("L_TEETH_RED", {"tooth_spacing": 0.5})
    out = tmp_path / "leg.gpkg"; doc.save_as(out)
    d2 = Document(out, (300, 300))
    assert d2.styles["L_TEETH_RED"]["tooth_spacing"] == 6.0 and d2.styles["L_TEETH_RED"]["tooth_side"] == "right"
    assert d2.L.loc[d2.L["_eid"] == e, "legend_id"].iloc[0] == "L_TEETH_RED"
    assert d2.L.geometry.iloc[0].equals_exact(doc.L.geometry.iloc[0], 1e-9)


def test_split_needs_split_role_and_keeps_coverage(doc):
    big = doc.F.iloc[int(np.argmax(doc.F.geometry.area))]; c = big.geometry.representative_point(); x0, y0, x1, y1 = big.geometry.bounds
    e = doc.add_line([[x0 - 1, c.y + 0.3], [x1 + 1, c.y + 0.3]], 1.0, "#000000")
    with pytest.raises(EditError): doc.split_face_preview(e)
    doc.set_role([e], "SPLIT"); pv = doc.split_face_preview(e)
    assert pv["faces_cut"] >= 1; n0 = len(doc.F)
    doc.split_face_apply(pv["preview_id"]); assert len(doc.F) > n0 and coverage_report(doc.F, 300, 300)["accepted"]
    with pytest.raises(EditError): doc.split_face_apply(pv["preview_id"])


def test_drawn_line_defaults_unknown(doc):
    e = doc.add_line([[5, 5], [30, 30]], 1.5, "#202020")
    r = doc.L.loc[doc.L["_eid"] == e].iloc[0]
    assert r["line_role"] == "UNKNOWN" and r["legend_id"] == ""
