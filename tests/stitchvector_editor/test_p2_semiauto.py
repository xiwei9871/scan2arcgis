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


def test_merge_suggest_roi_clips(tmp_path):
    d, _ = make_frag_doc(tmp_path)
    r = d.merge_suggest([0], de=15, roi=[0, 0, 100, 60])
    eids = {c["eid"] for c in r["candidates"]}
    assert 0 in eids and eids <= {0, 1, 2}, "ROI centre-rule may drop lower fragments"
    r2 = d.merge_suggest([0], de=15, roi=[0, 0, 100, 30])
    assert {c["eid"] for c in r2["candidates"]} == {0}, "tight ROI must stop the flood"


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
