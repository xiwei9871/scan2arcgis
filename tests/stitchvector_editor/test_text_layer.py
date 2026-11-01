import shutil, sys
from pathlib import Path
import numpy as np, pyogrio, pytest, shapely
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.stitchvector_editor.core import Document, EditError, TEXT, RESIDUE, coverage_report  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
INP = None
for base in (ROOT, ROOT.parents[2]):
    p = base / "runs/stitchvector/editor_v01/inputs"
    if (p / "u2_B2c.gpkg").exists(): INP = p; break
pytestmark = pytest.mark.skipif(INP is None, reason="local editor inputs not available")
EO, YUN, AR = (3, 25, 35, 42), (24, 59, 41, 76), (0, 196, 52, 225)


@pytest.fixture
def doc(tmp_path):
    src = tmp_path / "in.gpkg"; shutil.copyfile(INP / "u2_B2c.gpkg", src)
    return Document(src, (300, 300), np.asarray(Image.open(INP / "u2_original.png").convert("RGB")))


def test_preview_changes_nothing(doc):
    F0, L0 = doc.F.copy(), doc.L.copy(); pv = doc.text_preview(EO, ocr=False)
    assert pv["counts"]["residue_faces"] > 0 and doc.F.equals(F0) and doc.L.equals(L0) and not doc.log


def test_apply_cleans_box_keeps_outside_and_round_trips(doc, tmp_path):
    F0 = doc.F.set_index("_eid"); B = shapely.box(*EO)
    pv = doc.text_preview(EO, ocr=False); r = doc.text_apply(pv["preview_id"], "Є-O")
    assert r["merged_faces"] == pv["counts"]["merge_faces"] and coverage_report(doc.F, 300, 300)["accepted"]
    g = np.asarray(doc.F.geometry.values, object); small = (shapely.area(g) <= 60) & (shapely.area(shapely.intersection(g, B)) >= 0.5 * shapely.area(g))
    assert int(small.sum()) == 0
    out = tmp_path / "t.gpkg"; sv = doc.save_as(out); assert sv["accepted"] and sv["text_matches_memory"]
    T = pyogrio.read_dataframe(out, layer=TEXT); assert list(T["text"]) == ["Є-O"]
    assert len(pyogrio.read_dataframe(out, layer=RESIDUE)) == r["moved_lines"]
    re = Document(out, (300, 300)); assert list(re.T["text"]) == ["Є-O"]


def test_box_on_contact_left_uncertain_and_assign_checked(doc):
    pv = doc.text_preview(AR, ocr=False); unc = [i for i, g in enumerate(pv["groups"]) if g["decision"] == "uncertain"]
    assert unc and all(len(pv["groups"][i]["grounds"]) >= 2 for i in unc)
    with pytest.raises(EditError): doc.text_apply(pv["preview_id"], "Ar₂E", assign={unc[0]: 999999})
    with pytest.raises(EditError): doc.text_apply(pv["preview_id"], "Ar₂E", assign={len(pv["groups"]) + 5: 7})
    n = len(doc.F); doc.text_apply(pv["preview_id"], "Ar₂E")
    assert len(doc.F) == n - pv["counts"]["merge_faces"]   # uncertain groups untouched by default


def test_stale_text_preview_and_empty_text_rejected(doc):
    pv = doc.text_preview(YUN, ocr=False)
    with pytest.raises(EditError): doc.text_apply(pv["preview_id"], "   ")
    doc.rewidth([0], 2.0)
    with pytest.raises(EditError): doc.text_apply(pv["preview_id"], "云")


def test_undo_restores_faces_lines_text_and_residue_lines_restorable(doc):
    F0n, L0n = len(doc.F), len(doc.L); pv = doc.text_preview(YUN, ocr=False); r = doc.text_apply(pv["preview_id"], "云")
    assert len(doc.T) == 1 and len(doc.Q) == r["moved_lines"]
    doc.undo_op(); assert len(doc.F) == F0n and len(doc.L) == L0n and len(doc.T) == 0 and len(doc.Q) == 0
    doc.redo_op(); ids = list(doc.Q["_eid"]); doc.restore_residue_lines(ids); assert len(doc.L) == L0n and len(doc.Q) == 0


def test_edit_text_validates(doc):
    pv = doc.text_preview(YUN, ocr=False); r = doc.text_apply(pv["preview_id"], "云"); tid = r["text_id"]
    doc.edit_text(tid, text="雲", font_px=12, angle_deg=15); t = doc.T.loc[doc.T["_eid"] == tid].iloc[0]
    assert t["text"] == "雲" and t["font_px"] == 12 and t["angle_deg"] == 15
    with pytest.raises(EditError): doc.edit_text(tid, font_px=0)
    with pytest.raises(EditError): doc.edit_text(tid, x=-5, y=10)


AR2E = (0, 196, 52, 225)


def test_uncertain_groups_carry_before_after_options_and_default_no_merge(doc):
    pv = doc.text_preview(AR2E, ocr=False); unc = [g for g in pv["groups"] if g["decision"] == "uncertain"]
    assert unc and all(len(g["options"]) == len(g["grounds"]) for g in unc)
    assert all(o["before"] and o["after"] for g in unc for o in g["options"])
    n0 = len(doc.F); before = {e for g in unc for e in g["faces"]}
    doc.text_apply(pv["preview_id"], "Ar₂E")          # no assignment: uncertain faces stay
    live = set(int(e) for e in doc.F["_eid"]); assert before <= live and len(doc.F) < n0


def test_assign_one_group_only_merges_that_group(doc):
    pv = doc.text_preview(AR2E, ocr=False); idx = [i for i, g in enumerate(pv["groups"]) if g["decision"] == "uncertain"]
    k = idx[0]; g = pv["groups"][k]; t = g["grounds"][0]
    others = {e for i in idx[1:] for e in pv["groups"][i]["faces"]}
    doc.text_apply(pv["preview_id"], "Ar₂E", assign={k: t})
    live = set(int(e) for e in doc.F["_eid"])
    assert not (set(g["faces"]) & live) and others <= live


def test_residue_listed_and_restore_one_line(doc):
    pv = doc.text_preview(AR2E, ocr=False); doc.text_apply(pv["preview_id"], "Ar₂E")
    st = doc.state(); assert st["residue"] and all(r["coords"] for r in st["residue"])
    nL, nQ = len(doc.L), len(doc.Q); rid = st["residue"][0]["id"]
    doc.restore_residue_lines([rid]); assert len(doc.L) == nL + 1 and len(doc.Q) == nQ - 1
    doc.undo_op(); assert len(doc.L) == nL and len(doc.Q) == nQ
