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


# ---------- T12: narrow-face restoration + wrong-merge splitting ----------

def test_draw_snaps_to_line_midsegment(tmp_path):
    """T-junction boundary snapping: a drawn endpoint near the middle of an existing line snaps onto it."""
    d, _ = make_frag_doc(tmp_path)
    lid = d.add_line([(50, 5), (49.4, 40.8)], width=2, rgb="#000000")   # end near L0 (y=40) mid-segment
    g = d.L.loc[d.L["_eid"] == lid, "geometry"].iloc[0]
    x, y = list(g.coords)[-1]
    assert abs(y - 40.0) < 1e-6 and abs(x - 49.4) < 1e-6, "endpoint snapped onto the line's mid-segment"


def test_narrow_face_restored_by_draw_and_l2f(tmp_path):
    """A05: draw the missing narrow band's axis, line_to_face -> labelled narrow face, coverage stays valid,
    neighbours keep their ids."""
    d, _ = make_frag_doc(tmp_path)
    n0, ids0 = len(d.F), set(d.F["face_id"])
    lid = d.add_line([(25, 42), (25, 118)], width=4, rgb="#aaaaaa")
    r = d.line_to_face([lid], width=4, rgb="#aaaaaa", label="K1")
    assert r["area_px2"] > 0
    new = d.F.loc[d.F["source"] == "edited_line_to_face"]
    assert len(new) == 1 and new["label"].iloc[0] == "K1", "the narrow band becomes a labelled face"
    assert set(d.F["face_id"]) >= ids0 - {"F1"}, "existing faces survive (pieces keep original ids)"
    rep = __import__("tools.stitchvector_editor.core", fromlist=["coverage_report"]).coverage_report(d.F, W, H)
    assert rep["accepted"], rep
    d.undo_op(); assert len(d.F) == n0 and len(d.L) == 2, "one undo restores the drawn line"
    d.undo_op(); assert len(d.L) == 1, "a second undo removes it"


def test_wrong_merge_split_along_drawn_line(tmp_path):
    """A06: a wrongly merged face is cut along a user-drawn SPLIT line; preview first, neighbours untouched."""
    d, _ = make_frag_doc(tmp_path)
    d.merge_components([0, 1, 2], allow_mixed_labels=True)          # pretend B2c wrongly merged the left block
    assert len(d.F) == 2
    lid = d.add_line([(50, -0.5), (50, 120.5)], width=2, rgb="#000000")
    d.set_role([lid], "SPLIT")
    pv = d.split_face_preview(lid)
    assert pv["pieces"] == 2 and pv["faces_cut"] == 1
    r = d.split_face_apply(pv["preview_id"])
    assert len(d.F) == 3, "merged face is back to two pieces"
    f3 = d.F.loc[d.F["face_id"] == "F3"].iloc[0]
    assert f3.geometry.area > 0, "the untouched face is not harmed"
    d.undo_op(); assert len(d.F) == 2


# ---------------- T13: join broken lines + line grouping ----------------

def make_broken_doc(tmp_path):
    """A15/A20/A24: L0+L1 collinear with a 5px endpoint gap; L2 a 10px further segment; L3 an isolated stroke."""
    F = gpd.GeoDataFrame({"face_id": ["F0"], "rgb": ["#aaaaaa"], "label": ["K1"], "source": ["test"]},
                         geometry=[rect(0, 0, 200, 120)])
    L = gpd.GeoDataFrame({"line_id": ["L0", "L1", "L2", "L3"], "logical_id": ["G0", "G0", "G1", "G9"],
                          "kind": ["contact"] * 4, "width_px": [2.0] * 4, "rgb": ["#000000"] * 4,
                          "source": ["test"] * 4, "draw_order": [0, 1, 2, 3]},
                         geometry=[LineString([(10, 10), (40, 10)]),
                                   LineString([(45, 10), (80, 10)]),
                                   LineString([(90, 10), (120, 10)]),
                                   LineString([(150, 50), (165, 50)])])
    p = tmp_path / "in.gpkg"
    F.to_file(p, layer="colour_faces", driver="GPKG", engine="pyogrio")
    L.to_file(p, layer="visual_lines", driver="GPKG", engine="pyogrio")
    return Document(p, (W, H), np.full((H, W, 3), 170, np.uint8)), p


def test_join_preview_orders_and_reports_gaps(tmp_path):
    d, _ = make_broken_doc(tmp_path)
    pv = d.join_preview([0, 1, 2])
    assert pv["order"] == [0, 1, 2]
    assert [g["gap"] for g in pv["gaps"]] == [5.0, 10.0], "each junction's endpoint gap is reported"
    assert len(pv["connectors"]) == 2 and pv["dash_protected"] is False


def test_join_lines_bridges_small_gaps_undoable(tmp_path):
    d, _ = make_broken_doc(tmp_path)
    r = d.join_lines([0, 1])
    assert r["id"] == 0 and len(d.L) == 3, "two segments become one line"
    g = d.L.loc[d.L["_eid"] == 0, "geometry"].iloc[0]
    assert list(g.coords)[0] == (10, 10) and list(g.coords)[-1] == (80, 10) and len(g.coords) == 4, \
        "the 5px gap becomes a straight connector edge between the two endpoint vertices"
    d.undo_op(); assert len(d.L) == 4 and d.L.geometry.loc[d.L["_eid"] == 0].iloc[0].length == 30


def test_join_refuses_gap_too_large(tmp_path):
    d, _ = make_broken_doc(tmp_path)
    with pytest.raises(EditError, match="too large"):
        d.join_lines([0, 1, 2], max_gap=7)          # L1->L2 gap is 10px
    assert len(d.L) == 4, "a refused join changes nothing"


def test_join_reverses_far_end_first(tmp_path):
    """a segment picked backwards is reversed so its nearest end connects."""
    d, _ = make_broken_doc(tmp_path)
    pv = d.join_preview([2, 1])                      # 1 sits before 2 on the axis
    assert pv["order"] == [1, 2] and pv["gaps"][0]["gap"] == 10.0


def test_dash_join_refused_use_logical_group(tmp_path):
    """A20: a dashed line's gaps are semantic - geometry join is refused; logical grouping keeps them dash."""
    d, _ = make_broken_doc(tmp_path)
    d.apply_legend("visual_lines", [1], "L_DASH_RED")
    with pytest.raises(EditError, match="dashed"):
        d.join_lines([0, 1])
    lid = d.new_group([0, 1])
    assert set(d.L.loc[d.L["_eid"].isin([0, 1]), "logical_id"]) == {lid}
    assert len(d.L) == 4, "grouping changes membership only, never geometry"


def test_ungroup_lines_gives_individual_groups(tmp_path):
    d, _ = make_broken_doc(tmp_path)
    assert len(set(d.L["logical_id"])) == 3
    d.ungroup_lines([0, 1])
    lids = d.L.loc[d.L["_eid"].isin([0, 1]), "logical_id"].tolist()
    assert len(set(lids)) == 2 and "G0" not in lids, "each ungrouped line gets its own fresh logical_id"
    d.undo_op(); assert set(d.L.loc[d.L["_eid"].isin([0, 1]), "logical_id"]) == {"G0"}


def test_isolate_lines_moves_to_residue_restorable(tmp_path):
    """A24: a text stroke wrongly grouped as a geological line is moved out - never deleted, restorable."""
    d, _ = make_broken_doc(tmp_path)
    q0 = len(d.Q)
    d.isolate_lines([3], reason="misgrouped")
    assert len(d.L) == 3 and len(d.Q) == q0 + 1
    row = d.Q.iloc[-1]
    assert row["residue_of"] == "manual_isolate" and row["source"] == "isolated_misgrouped"
    d.undo_op(); assert len(d.L) == 4 and len(d.Q) == q0


def test_join_persists_through_save(tmp_path):
    d, p = make_broken_doc(tmp_path)
    d.join_lines([0, 1, 2])
    out = tmp_path / "out.gpkg"; d.save_as(out)
    d2 = Document(out, (W, H))
    assert len(d2.L) == 2 and d2.L.loc[d2.L["_eid"] == 0, "geometry"].iloc[0].length == 110


def test_text_apply_default_isolates_only_suggested_lines(tmp_path):
    """P2.1: a caller that passes no line_ids must isolate only risk-free (suggested) residue lines;
    boundary-risk lines stay in visual_lines unless explicitly opted in."""
    d, _ = make_residue_doc(tmp_path)
    t = d.text_residue([0])["texts"][0]
    sug = {l["id"] for l in t["line_info"] if l["suggested"]}
    r = d.text_apply(t["preview_id"], "怀道")                       # no line_ids at all
    assert set(d.Q["line_id"]) == {"L0"} and r["moved_lines"] == len(sug) == 1, \
        "only the suggested glyph stroke is isolated by default"
    assert "L1" in set(d.L["line_id"]), "the SPLIT-role line is never default-isolated"
    (tmp_path / "b").mkdir(); d2 = make_residue_doc(tmp_path / "b")[0]
    t2 = d2.text_residue([0])["texts"][0]
    r2 = d2.text_apply(t2["preview_id"], "怀道", line_ids=list(t2["lines"]))   # explicit opt-in still moves all
    assert r2["moved_lines"] == 2


# ---------- P2.1 T14 hardening: ROI persistence / undo / clip export ----------

def test_roi_persists_through_save_and_undo(tmp_path):
    d, _ = make_frag_doc(tmp_path)
    d.set_roi([0, 0, 60, 120]); assert d.dirty, "declaring an ROI is project state and must be saved"
    d.undo_op(); assert d.roi is None, "undo restores the previous ROI"
    d.redo_op(); assert d.roi is not None and list(d.roi.bounds) == [0, 0, 60, 120]
    out = tmp_path / "r.gpkg"; d.save_as(out, roi_mode="keep")
    d2 = Document(out, (W, H))
    assert d2.roi is not None and list(d2.roi.bounds) == [0, 0, 60, 120], "project_roi layer restores the ROI on reopen"


def test_roi_clip_preview_lists_every_layer(tmp_path):
    d, _ = make_frag_doc(tmp_path)
    d.set_roi([0, 0, 60, 120])
    pv = d.roi_clip_preview()
    L = pv["layers"]
    assert L["faces"]["inside"] == [1] and set(L["faces"]["crossing"]) == {0, 2}, "F1 inside; F0/F2 cross the edge"
    assert L["faces"]["outside"] == [3], "F3 is fully outside this ROI"
    assert L["lines"]["crossing"] == [0], "the contact crosses the ROI edge"
    assert len(d.F) == 4 and len(d.L) == 1, "preview changes nothing"


def test_roi_export_clip_tiles_roi_and_drops_outside(tmp_path):
    d, _ = make_frag_doc(tmp_path)
    d.set_roi([0, 0, 60, 120])
    out = tmp_path / "clip.gpkg"; r = d.save_as(out, roi_mode="clip")
    assert r["export_mode"] == "roi_clip" and r["accepted"]
    import pyogrio
    F = pyogrio.read_dataframe(out, layer="colour_faces")
    assert len(F) == 3, "F0/F2 clipped at the edge, F1 kept, F3 dropped"
    u = __import__("shapely").union_all(list(F.geometry))
    assert abs(u.area - 60 * 120) < 1e-6, "clipped faces tile the ROI exactly"
    L = pyogrio.read_dataframe(out, layer="visual_lines")
    assert abs(L.geometry.iloc[0].length - 60) < 1e-6, "the crossing contact is cut at the ROI edge"
    assert len(d.F) == 4, "the document itself is unchanged by a scoped export"


def test_roi_export_keep_preserves_crossing_wholes(tmp_path):
    d, _ = make_frag_doc(tmp_path)
    d.set_roi([0, 0, 60, 120])
    out = tmp_path / "keep.gpkg"; r = d.save_as(out, roi_mode="keep")
    assert r["export_mode"] == "roi_keep" and r["accepted"]
    import pyogrio
    F = pyogrio.read_dataframe(out, layer="colour_faces")
    assert len(F) == 3, "crossing faces kept whole, only fully-outside F3 dropped"
    u = __import__("shapely").union_all(list(F.geometry))
    assert u.area > 60 * 120, "kept crossing faces extend past the ROI - union covers it"
    with pytest.raises(EditError):
        d.save_as(tmp_path / "formal.gpkg"), "formal save still refuses while F3 is outside the ROI"


def test_dash_wrongly_joined_split_regap_regroup(tmp_path):
    """A20 recovery path: B2c connected separate dashes into one solid line. Manual repair = split at each
    gap boundary, delete the wrong connector segments, re-assign the dash legend, regroup logically.
    The dash interval semantics are restored; render still comes from the legend."""
    d, _ = make_broken_doc(tmp_path)
    # pretend L0+L1 were wrongly auto-joined in the input: one solid line with a wrong connector 40-45
    d.join_lines([0, 1])                                    # now one solid 10->80 line (the "wrong" state)
    solid = int(d.L.loc[d.L["line_id"] == "L0", "_eid"].iloc[0])
    d.split_line(solid, 45, 10)                             # cut at gap end -> [10-45,45-80]
    d.split_line(solid, 40, 10)                             # cut at gap start -> [10-40,40-45,45-80]
    pieces = list(d.L.loc[d.L.geometry.bounds.minx.between(9, 81) & d.L.geometry.bounds.miny.between(9, 11), "_eid"])
    conn = [e for e in pieces if abs(d.L.loc[d.L["_eid"] == e, "geometry"].iloc[0].length - 5) < 1e-6]
    assert len(conn) == 1, "the wrongly-drawn 40-45 connector is isolated"
    d.isolate_lines(conn, reason="dash_gap")                # remove the false connector - isolated, restorable
    dash = [e for e in pieces if e != conn[0]]
    for e in dash: d.apply_legend("visual_lines", [e], "L_DASH_RED")
    lid = d.new_group(dash)
    assert set(d.L.loc[d.L["_eid"].isin(dash), "logical_id"]) == {lid} and len(d.L) == 4
    render = {r["id"]: r for r in d.render_lines()}
    assert all(render[e]["line_type"] == "dash" for e in dash), "the two segments render dashed again"
    total = sum(d.L.loc[d.L["_eid"].isin(dash), "geometry"].iloc[i].length for i in range(2))
    assert total == 65.0, "two dash segments, 30+35 visible length, the 5px interval is preserved as a gap"
