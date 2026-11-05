"""P0 UAT remediation tests (2026-11-05): E22 hit-sync, E04 duplicate text, E31 merge provenance,
E09 OCR font/angle from quad, E12 ocr_box status/reuse. Synthetic GPKGs only - no protected data."""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd, geopandas as gpd, pytest, shapely
from shapely.geometry import LineString, Point, Polygon

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.stitchvector_editor.core import Document, EditError, TEXT_COLS  # noqa: E402
from tools.stitchvector_studio.projects import _quad_metrics  # noqa: E402

W, H = 200, 120


def rect(x0, y0, x1, y1): return Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


def make_doc(tmp_path, texts=None, labels=None):
    """faces tile the 200x120 window exactly (valid coverage); optional labels per face."""
    faces = [Polygon([(0, 0), (100, 0), (100, 60), (100, 120), (0, 120)]),   # left half, vertex shared at (100,60)
             rect(100, 0, 200, 60), rect(100, 60, 200, 120)]
    lab = labels or [None, None, None]
    F = gpd.GeoDataFrame({"face_id": ["F0", "F1", "F2"], "rgb": ["#aaaaaa", "#bbbbbb", "#cccccc"],
                          "label": lab, "source": ["test"] * 3}, geometry=faces)
    L = gpd.GeoDataFrame({"line_id": ["L0"], "logical_id": ["G0"], "kind": ["contact"], "width_px": [2.0],
                          "rgb": ["#000000"], "source": ["test"], "draw_order": [0]}, geometry=[LineString([(0, 60), (200, 60)])])
    T = gpd.GeoDataFrame([{**{c: None for c in TEXT_COLS},
                          "label_id": f"T{i}", "text": t["text"], "ocr_text": t.get("ocr_text", ""), "ocr_score": t.get("score", 0.0),
                          "font_px": t.get("font_px", 15.0), "angle_deg": t.get("angle_deg", 0.0), "anchor": "center", "rgb": "#000000",
                          "box_x0": t["x"] - 10, "box_y0": t["y"] - 8, "box_x1": t["x"] + 10, "box_y1": t["y"] + 8,
                          "source": "test", "review_status": t.get("review_status", "OCR_DRAFT")}
                         for i, t in enumerate(texts or [])], geometry=[Point(t["x"], t["y"]) for t in (texts or [])])
    p = tmp_path / "in.gpkg"
    F.to_file(p, layer="colour_faces", driver="GPKG", engine="pyogrio")
    L.to_file(p, layer="visual_lines", driver="GPKG", engine="pyogrio")
    if len(T): T.to_file(p, layer="text_labels", driver="GPKG", engine="pyogrio")
    img = np.full((H, W, 3), 255, np.uint8)
    return Document(p, (W, H), img), p, tmp_path


# ---------- T01 / E22: position/font/angle -> display box -> hit region ----------

def test_move_text_syncs_hit_region(tmp_path):
    d, _, _ = make_doc(tmp_path, texts=[{"x": 50, "y": 50, "text": "芽"}])
    tid = int(d.T["_eid"].iloc[0])
    assert d.pick_text(50, 50) == [tid]
    d.edit_text(tid, x=80.0, y=80.0)
    assert d.pick_text(80, 80) == [tid], "new position must be clickable"
    assert d.pick_text(50, 50) == [], "old position must no longer hit"
    row = d.T.loc[d.T["_eid"] == tid].iloc[0]
    assert row["box_x0"] <= 80 <= row["box_x1"] and row["box_y0"] <= 80 <= row["box_y1"], "display box must follow the point"


def test_font_and_angle_sync_hit_region(tmp_path):
    d, _, _ = make_doc(tmp_path, texts=[{"x": 100, "y": 60, "text": "测试文字", "font_px": 20.0}])
    tid = int(d.T["_eid"].iloc[0])
    w0 = d.T.loc[d.T["_eid"] == tid, "box_x1"].iloc[0] - d.T.loc[d.T["_eid"] == tid, "box_x0"].iloc[0]
    d.edit_text(tid, font_px=40.0)
    row = d.T.loc[d.T["_eid"] == tid].iloc[0]
    assert (row["box_x1"] - row["box_x0"]) > w0 * 1.8, "bigger font must grow the display box"
    assert d.pick_text(100 + 20 * 4 / 2 - 3, 60) == [tid]          # just inside the right rendered edge
    d.edit_text(tid, angle_deg=90.0)                              # now the text stands vertical
    assert d.pick_text(100, 60 + 20 * 4 / 2 - 3) == [tid], "rotated extent must hit along the vertical axis"
    assert d.pick_text(100 + 20 * 4 / 2 - 3, 60) == [], "old horizontal extent must not hit any more"


def test_move_undo_redo_restores_hit(tmp_path):
    d, _, _ = make_doc(tmp_path, texts=[{"x": 50, "y": 50, "text": "芽"}])
    tid = int(d.T["_eid"].iloc[0])
    d.edit_text(tid, x=90.0, y=90.0)
    d.undo_op(); assert d.pick_text(50, 50) == [tid] and d.pick_text(90, 90) == []
    d.redo_op(); assert d.pick_text(90, 90) == [tid] and d.pick_text(50, 50) == []


def test_box_sync_survives_save_reopen(tmp_path):
    d, p, _ = make_doc(tmp_path, texts=[{"x": 50, "y": 50, "text": "芽"}])
    tid = int(d.T["_eid"].iloc[0]); d.edit_text(tid, x=80.0, y=80.0)
    out = tmp_path / "v1.gpkg"; d.save_as(out)
    d2 = Document(out, (W, H))
    assert d2.pick_text(80, 80) == [tid] and d2.pick_text(50, 50) == []


# ---------- T02 / E04: no duplicate text on repeated box-confirm ----------

def test_box_over_existing_text_reuses_and_edits_not_duplicates(tmp_path):
    d, _, _ = make_doc(tmp_path, texts=[{"x": 60, "y": 60, "text": "怀道", "score": 0.9}])
    n0 = len(d.T); tid = int(d.T["_eid"].iloc[0])
    pv = d.text_preview([50, 50, 76, 74])
    assert pv["existing"] and pv["existing"][0]["id"] == tid and pv["ocr"]["status"] == "reused"
    r = d.text_apply(pv["preview_id"], "怀道", font_px=18.4)
    assert r["mode"] == "edited_existing" and r["text_id"] == tid and len(d.T) == n0, "must edit the existing text, not create a second one"
    assert float(d.T.loc[d.T["_eid"] == tid, "font_px"].iloc[0]) == 18.4
    pv2 = d.text_preview([50, 50, 76, 74]); r2 = d.text_apply(pv2["preview_id"], "怀道")
    assert r2["mode"] == "edited_existing" and len(d.T) == n0, "repeating the confirm must not accumulate duplicates"


def test_box_over_existing_force_new_still_possible(tmp_path):
    d, _, _ = make_doc(tmp_path, texts=[{"x": 60, "y": 60, "text": "怀道"}])
    n0 = len(d.T)
    pv = d.text_preview([50, 50, 76, 74])
    r = d.text_apply(pv["preview_id"], "怀道", existing_mode="create")
    assert r["mode"] == "created" and len(d.T) == n0 + 1, "explicit opt-in may still create a second text"


def test_empty_box_still_creates(tmp_path):
    d, _, _ = make_doc(tmp_path)
    pv = d.text_preview([40, 40, 60, 60])
    assert pv["existing"] == []
    r = d.text_apply(pv["preview_id"], "新字", existing_mode="create")
    assert r["mode"] == "created" and len(d.T) == 1


# ---------- T03 / E31: merge provenance ----------

def test_merge_keeps_source_provenance(tmp_path):
    d, _, _ = make_doc(tmp_path)
    keep = d.merge_faces([1, 2])
    row = d.F.loc[d.F["_eid"] == keep].iloc[0]
    src = json.loads(row["merged_from"])
    assert {e["eid"] for e in src} == {1, 2} and sum(1 for e in src if e["kept"]) == 1
    assert {e["rgb"] for e in src} == {"#bbbbbb", "#cccccc"} and all("area" in e and "op" in e for e in src)
    hist = d.merge_history(); assert len(hist) == 1 and hist[0]["eid"] == keep


def test_mixed_label_merge_needs_opt_in(tmp_path):
    d, _, _ = make_doc(tmp_path, labels=[0, 1, 9])
    with pytest.raises(EditError, match="different labels"):
        d.merge_faces([1, 2])
    keep = d.merge_faces([1, 2], allow_mixed_labels=True)
    src = json.loads(d.F.loc[d.F["_eid"] == keep, "merged_from"].iloc[0])
    assert {e["label"] for e in src} == {1, 9}


def test_merge_components_provenance_and_chain(tmp_path):
    d, _, _ = make_doc(tmp_path)
    d.merge_components([0, 1])
    keep = d.merge_history()[0]["eid"]
    src0 = json.loads(d.F.loc[d.F["_eid"] == keep, "merged_from"].iloc[0])
    assert {e["eid"] for e in src0} == {0, 1}
    d.merge_faces([keep, 2])                       # merge the merged face once more
    row = d.F.loc[d.F["_eid"] == keep].iloc[0]
    src = json.loads(row["merged_from"])
    assert {e["eid"] for e in src} >= {0, 1, 2}, "chained merge keeps the full lineage"
    assert any(e.get("via") == keep for e in src), "earlier sources marked as coming via the merged face"


def test_provenance_survives_save_reopen_and_undo(tmp_path):
    d, _, _ = make_doc(tmp_path)
    keep = d.merge_faces([1, 2])
    out = tmp_path / "v1.gpkg"; d.save_as(out)
    d2 = Document(out, (W, H))
    src = json.loads(d2.F.loc[d2.F["_eid"] == keep, "merged_from"].iloc[0])
    assert {e["eid"] for e in src} == {1, 2}
    d.undo_op()
    row = d.F.loc[d.F["_eid"] == keep].iloc[0] if (d.F["_eid"] == keep).any() else None
    assert row is None or not row["merged_from"], "undo must restore the pre-merge provenance state"


# ---------- T04 / E09: font_px/angle from the quad, not the bounding box ----------

def test_quad_metrics_horizontal():
    h, a = _quad_metrics([[0, 0], [40, 0], [40, 10], [0, 10]])
    assert h == pytest.approx(10.0) and a == 0.0


def test_quad_metrics_rotated45_keeps_glyph_height():
    import math
    s, L = 10.0, 40.0
    q = [[0, 0], [L * math.cos(math.pi / 4), L * math.sin(math.pi / 4)],
         [L * math.cos(math.pi / 4) - s * math.sin(math.pi / 4), L * math.sin(math.pi / 4) + s * math.cos(math.pi / 4)],
         [-s * math.sin(math.pi / 4), s * math.cos(math.pi / 4)]]
    h, a = _quad_metrics(q)
    assert h == pytest.approx(10.0, abs=0.5), "rotated text: height = short edge, not the AABB"
    assert a == pytest.approx(-45.0, abs=0.5)


def test_quad_metrics_vertical():
    h, a = _quad_metrics([[0, 0], [10, 0], [10, 80], [0, 80]])
    assert h == pytest.approx(10.0) and abs(abs(a) - 90.0) < 0.5


def test_drafts_font_capped_by_glyph_height(tmp_path):
    from tools.stitchvector_studio.projects import add_text_drafts
    ocj = tmp_path / "ocr.json"
    json.dump({"schema": "ocr_candidates.v1", "engine": "test", "model": "m",
               "items": [{"id": "O0", "quad": [[0, 0], [8, 0], [8, 80], [0, 80]], "text": "竖", "score": 0.9,
                          "status": "OCR_CANDIDATE", "suggested_text": "竖", "candidate_texts": ["竖"], "rule_reasons": []}]},
              open(ocj, "w"))
    import pyogrio
    gpkg = tmp_path / "w.gpkg"; make_doc(tmp_path)[1].rename(gpkg)   # reuse the fixture's GPKG
    r = add_text_drafts(gpkg, ocj, "run-x")
    T = pyogrio.read_dataframe(gpkg, layer="text_labels")
    assert r["drafts"] == 1 and float(T["font_px"].iloc[0]) <= 8.0, "vertical text: font_px must follow the short edge, not the AABB"
    assert abs(abs(float(T["angle_deg"].iloc[0])) - 90.0) < 0.5


# ---------- T05 / E12: ocr_box status + reuse ----------

def test_ocr_python_resolves_existing_venv():
    from tools.stitchvector_editor.core import _ocr_python
    py, where = _ocr_python()
    assert py is not None and py.exists(), f"expected a usable interpreter, got {where}"


def test_ocr_box_reports_status_not_silent_none(monkeypatch, tmp_path):
    d, _, _ = make_doc(tmp_path)
    import tools.stitchvector_editor.core as C
    monkeypatch.setattr(C, "_ocr_python", lambda: (None, "no .venv-ocr interpreter found (set STITCHVECTOR_OCR_PY)"))
    r = d.ocr_box([40, 40, 60, 60])
    assert r["status"] == "engine_unavailable" and "venv" in r["reason"] and r["engine"] == "none"
    d.img = None
    monkeypatch.undo()
    r = d.ocr_box([40, 40, 60, 60])
    assert r["status"] == "engine_unavailable" and r["reason"] == "no scan image loaded"


def test_text_preview_reuses_existing_text_without_ocr(tmp_path):
    d, _, _ = make_doc(tmp_path, texts=[{"x": 60, "y": 60, "text": "已有字"}])
    pv = d.text_preview([50, 50, 76, 74])
    assert pv["ocr"]["engine"] == "existing" and pv["ocr"]["status"] == "reused"


