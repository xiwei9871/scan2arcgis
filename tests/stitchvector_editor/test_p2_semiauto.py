"""P2 semi-automatic repair tests (2026-11-05): T10 merge_suggest + face LOGICAL_GROUP + ROI.
Synthetic GPKGs only - no protected data."""
import sys
from pathlib import Path
import numpy as np, pandas as pd, geopandas as gpd, pytest
from shapely.geometry import LineString, Polygon

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.stitchvector_editor.core import Document, EditError  # noqa: E402

W, H = 200, 120


def rect(x0, y0, x1, y1): return Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


def make_frag_doc(tmp_path, labels=None):
    """fragmented left half: F0 (main) + F1/F2 small fragments, same colour; F3 distinct colour right."""
    faces = [Polygon([(0, 0), (100, 0), (100, 40), (50, 40), (0, 40)]),  # F0 bottom edge noded at (50,40)
             rect(0, 40, 50, 120), rect(50, 40, 100, 120),
             Polygon([(100, 0), (200, 0), (200, 120), (100, 120), (100, 40), (100, 0)])]
    F = gpd.GeoDataFrame({"face_id": ["F0", "F1", "F2", "F3"],
                          "rgb": ["#aaaaaa", "#aaaaaa", "#aaaaaa", "#66cc66"],
                          "label": labels or ["K1", None, None, "J"], "source": ["test"] * 4},
                         geometry=faces)
    L = gpd.GeoDataFrame({"line_id": ["L0"], "logical_id": ["G0"], "kind": ["contact"], "width_px": [2.0],
                          "rgb": ["#000000"], "source": ["test"], "draw_order": [0],
                          "line_role": ["SPLIT"]},
                         geometry=[LineString([(0, 40), (100, 40)])])
    p = tmp_path / "in.gpkg"
    F.to_file(p, layer="colour_faces", driver="GPKG", engine="pyogrio")
    L.to_file(p, layer="visual_lines", driver="GPKG", engine="pyogrio")
    return Document(p, (W, H), np.full((H, W, 3), 170, np.uint8)), p


def test_merge_suggest_grows_same_colour(tmp_path):
    d, _ = make_frag_doc(tmp_path)
    r = d.merge_suggest([0], de=15)
    assert set(r["candidates_eid"] if "candidates_eid" in r else [c["eid"] for c in r["candidates"]]) == {0, 1, 2}
    assert 3 not in [c["eid"] for c in r["candidates"]], "different colour must not be suggested"


def test_merge_suggest_roi_flags_outside(tmp_path):
    d, _ = make_frag_doc(tmp_path)
    r = d.merge_suggest([0], de=15, roi=[0, 0, 100, 60])   # F1/F2 centres (y=80) are outside this ROI
    byid = {c["eid"]: c for c in r["candidates"]}
    for e in (1, 2):
        assert "outside_roi" in byid[e]["risks"] and byid[e]["suggested"] is False, \
            "centre-outside candidate is flagged outside_roi, never auto-suggested"
    r2 = d.merge_suggest([0], de=15, roi=[0, 0, 100, 120])
    assert all("outside_roi" not in c["risks"] for c in r2["candidates"]), "all-inside ROI adds no outside flag"
    r3 = d.merge_suggest([0], de=15, roi=[0, 0, 100, 20])
    assert all(c["suggested"] is False or c["eid"] == 0 for c in r3["candidates"]), \
        "tight ROI leaves nothing safe besides the seed"


def test_merge_suggest_risks(tmp_path):
    d, _ = make_frag_doc(tmp_path, labels=["K1", "J2", None, "X"])
    r = d.merge_suggest([0], de=15)
    byid = {c["eid"]: c for c in r["candidates"]}
    assert "crosses_split_line" in byid[1]["risks"], \
        "face bounded by a SPLIT line must flag the risk"
    assert "crosses_split_line" in byid[2]["risks"], "F2 also borders the SPLIT line"
    assert "mixed_label" in byid[1]["risks"], "different label must flag mixed_label"
    assert byid[1]["suggested"] is False and byid[2]["suggested"] is False, \
        "line-bounded candidates stay out of the auto-suggested set"
    assert r["suggested"] == [0], "only the seed is safe to auto-include here"


def test_group_faces_logical_no_geometry_change(tmp_path):
    d, _ = make_frag_doc(tmp_path)
    g0 = [g.wkb for g in d.F.geometry]
    gid = d.group_faces([0, 1, 2])
    assert gid.startswith("FG")
    assert [g.wkb for g in d.F.geometry] == g0, "LOGICAL_GROUP must not touch geometry"
    assert set(d.F.loc[d.F["face_group"] == gid, "_eid"]) == {0, 1, 2}
    d.undo_op()
    assert (d.F["face_group"] == "").all(), "undo must clear the group tag"


def test_group_persists_and_ungroup(tmp_path):
    d, p = make_frag_doc(tmp_path)
    gid = d.group_faces([0, 1])
    out = tmp_path / "out.gpkg"
    d.save_as(out)
    d2 = Document(out, (W, H))
    assert "face_group" in d2.F.columns
    assert set(d2.F.loc[d2.F["face_group"] == gid, "face_id"]) == {"F0", "F1"}
    d2.ungroup_faces([0, 1])
    assert (d2.F["face_group"] == "").all()


def test_set_roi_state(tmp_path):
    d, _ = make_frag_doc(tmp_path)
    r = d.set_roi([10, 10, 90, 90])
    assert r["roi"] == [10, 10, 90, 90]
    sug = d.merge_suggest([0], de=15)  # doc-level ROI applied
    assert all(c["eid"] in (0, 1, 2) for c in sug["candidates"])
    d.set_roi(None)
    assert d.roi is None


# ---------- T11: text residue semi-automatic cleanup ----------

def make_residue_doc(tmp_path):
    """ground face + tiny residue face inside a text box; lines: glyph stroke inside, SPLIT-role line inside
    (must flag boundary_risk), long line crossing the box edge (never a residue candidate)."""
    faces = [Polygon([(0, 0), (200, 0), (200, 120), (0, 120)], holes=[[(61, 41), (68, 41), (68, 48), (61, 48)]]),  # F0 ground with hole
             rect(61, 41, 68, 48)]                                          # F1 tiny fragment tiling the hole (<60px)
    F = gpd.GeoDataFrame({"face_id": ["F0", "F1"], "rgb": ["#aaaaaa", "#aaaaaa"], "label": [None, None], "source": ["test"] * 2},
                         geometry=faces)
    L = gpd.GeoDataFrame({"line_id": ["L0", "L1", "L2"], "logical_id": ["G0", "G1", "G2"],
                          "kind": ["contact"] * 3, "width_px": [2.0] * 3, "rgb": ["#000000"] * 3,
                          "source": ["test"] * 3, "draw_order": [0] * 3,
                          "line_role": ["COVER", "SPLIT", "SPLIT"]},
                         geometry=[LineString([(52, 42), (58, 46)]),        # L0 glyph stroke, fully inside box
                                   LineString([(62, 43), (68, 47)]),        # L1 SPLIT-role, fully inside -> boundary_risk
                                   LineString([(0, 45), (200, 45)])])       # L2 real contact through the box -> kept
    T = gpd.GeoDataFrame([{"label_id": "T0", "text": "怀道", "ocr_text": "怀道", "ocr_score": 0.9, "font_px": 12.0,
                           "angle_deg": 0.0, "anchor": "center", "rgb": "#000000",
                           "box_x0": 50.0, "box_y0": 38.0, "box_x1": 72.0, "box_y1": 52.0,
                           "source": "test", "review_status": "OCR_CONFIRMED"}],
                        geometry=[__import__("shapely").geometry.Point(61, 45)])
    p = tmp_path / "in.gpkg"
    F.to_file(p, layer="colour_faces", driver="GPKG", engine="pyogrio")
    L.to_file(p, layer="visual_lines", driver="GPKG", engine="pyogrio")
    T.to_file(p, layer="text_labels", driver="GPKG", engine="pyogrio")
    return Document(p, (W, H), np.full((H, W, 3), 170, np.uint8)), p


def test_text_residue_suggests_from_text_box(tmp_path):
    d, _ = make_residue_doc(tmp_path)
    L0, F0 = d.L.copy(), d.F.copy()
    r = d.text_residue([0])
    assert d.L.equals(L0) and d.F.equals(F0) and not d.log, "suggestion must not modify anything"
    t = r["texts"][0]
    assert t["text_id"] == 0 and t["counts"]["residue_faces"] >= 1
    info = {x["id"]: x for x in t["line_info"]}
    assert 0 in info and 1 in info and 2 not in info, "only fully-inside lines are candidates"
    assert "boundary_risk" in info[1]["risks"] and info[1]["suggested"] is False, \
        "a SPLIT-role line inside the box must be flagged, not suggested"
    assert info[0]["suggested"] is True


def test_text_apply_line_subset_keeps_risky_line(tmp_path):
    d, _ = make_residue_doc(tmp_path)
    t = d.text_residue([0])["texts"][0]
    r = d.text_apply(t["preview_id"], "怀道", line_ids=[0])          # isolate only the glyph stroke, keep the SPLIT line
    assert r["mode"] == "edited_existing" and r["moved_lines"] == 1
    assert set(d.L["line_id"]) == {"L1", "L2"}, "the flagged line and the crossing contact stay in visual_lines"
    assert list(d.Q["line_id"]) == ["L0"] and d.Q["residue_of"].iloc[0] == "text#0"
    d.restore_residue_lines([int(d.Q["_eid"].iloc[0])])
    assert set(d.L["line_id"]) == {"L0", "L1", "L2"} and len(d.Q) == 0


def test_residue_cleanup_undo_and_save(tmp_path):
    d, _ = make_residue_doc(tmp_path)
    t = d.text_residue([0])["texts"][0]
    d.text_apply(t["preview_id"], "怀道", line_ids=[0, 1])
    assert len(d.Q) == 2 and len(d.L) == 1
    d.undo_op()
    assert len(d.L) == 3 and len(d.Q) == 0
    d.redo_op(); assert len(d.Q) == 2
    out = tmp_path / "out.gpkg"; d.save_as(out)
    d2 = Document(out, (W, H))
    assert len(d2.Q) == 2 and d2.Q["residue_of"].iloc[0] == "text#0"


# ---------- T14: ROI / background protection ----------

def test_roi_report_counts(tmp_path):
    d, _ = make_frag_doc(tmp_path)
    d.set_roi([0, 0, 100, 60])
    r = d.roi_report()
    assert r["roi"] == [0, 0, 100, 60]
    assert r["faces"]["inside"] == 1 and r["faces"]["crossing"] == 3 and r["faces"]["outside"] == 0, \
        "edge-touching neighbours count as crossing, not outside"
    d.set_roi([0, 0, 99, 120])
    assert d.roi_report()["faces"]["outside"] == 1, "F3 (x>=100) is fully outside the tighter ROI"
    assert d.roi_report()["roi"] is not None and Document(d.src, (W, H)).roi_report()["roi"] is None


def test_save_blocked_by_outside_roi_objects(tmp_path):
    d, _ = make_frag_doc(tmp_path)
    d.set_roi([0, 0, 99, 120])           # F3 (x>=100) is now fully outside the processing region
    with pytest.raises(EditError, match="outside"):
        d.save_as(tmp_path / "formal.gpkg")
    d.set_roi(None)
    out = tmp_path / "ok.gpkg"; r = d.save_as(out)
    assert r["roi"]["roi"] is None


def test_legit_multi_region_not_forced(tmp_path):
    """two disjoint same-colour faces may share a logical group; a geometric merge never joins them
    (components merge only within connectivity) - legitimate multi-region units are preserved."""
    d, _ = make_frag_doc(tmp_path)
    gid = d.group_faces([1, 3])          # F1 (x<=50) and F3 (x>=100) are disjoint: logical group is fine
    assert gid and (d.F["face_group"] == gid).sum() == 2
    with pytest.raises(EditError, match="share an edge"):
        d.merge_components([1, 3], allow_mixed_labels=True)   # no shared edge -> can never union into one face
