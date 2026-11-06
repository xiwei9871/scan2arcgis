"""V0.3 gates: P0 no-silent-geology-loss, P1 red-face real repair, P2 OCR review workflow.
Synthetic GPKGs only - no protected U2 files required."""
import sys
from pathlib import Path
import numpy as np, pandas as pd, geopandas as gpd, pytest, shapely
from shapely.geometry import LineString, Point, Polygon

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.stitchvector_editor.core import Document, EditError, TEXT_COLS, LINE_SUSPECT_KIND, LINE_KEPT_KIND  # noqa: E402
from tools.stitchvector_editor import red_face_repair as RF  # noqa: E402
from tools.stitchvector_studio import exports as EXP  # noqa: E402

W, H = 200, 120


def rect(x0, y0, x1, y1): return Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


def make_doc(tmp_path, texts=None, line_kinds=None, enclosed_frag=True, residue=False):
    """Synthetic map: left face = host with an interior ring whose hole holds one small enclosed
    fragment (the red-face case); right half two plain faces. Suspect lines flagged as the pipeline
    leaves them; a real geological line crosses the text box region."""
    hole = [(40, 20), (52, 20), (52, 30), (40, 30)]           # 12x10 = 96 px2 < max_area(120)
    faces = [Polygon([(0, 0), (100, 0), (100, 60), (100, 120), (0, 120), (0, 0)], [hole]),
             rect(100, 0, 200, 60), rect(100, 60, 200, 120)]
    geoms = list(faces); rgb = ["#c0392b", "#bbbbbb", "#cccccc"]; lab = ["red_unit", None, None]
    src = ["test", "test", "test"]
    if enclosed_frag:
        geoms.append(Polygon(hole)); rgb.append("#e07060"); lab.append(None); src.append("test")
    F = gpd.GeoDataFrame({"face_id": [f"F{i}" for i in range(len(geoms))], "rgb": rgb,
                          "label": lab, "source": src}, geometry=geoms)
    kinds = line_kinds if line_kinds is not None else ["contact", LINE_SUSPECT_KIND, LINE_SUSPECT_KIND]
    L = gpd.GeoDataFrame({"line_id": ["L0", "rev-L7", "rev-L9"], "logical_id": ["G0", "G7", "G9"],
                          "kind": kinds, "width_px": [2.0, 1.5, 1.5], "rgb": ["#000000"] * 3,
                          "source": ["test"] * 3, "draw_order": [0, 1, 2]},
                         geometry=[LineString([(0, 90), (200, 90)]),        # plain contact, away from text
                                   LineString([(10, 40), (170, 44)]),      # suspect: crosses text box below
                                   LineString([(150, 10), (180, 30)])])    # suspect: short stroke
    p = tmp_path / "in.gpkg"
    F.to_file(p, layer="colour_faces", driver="GPKG", engine="pyogrio")
    L.to_file(p, layer="visual_lines", driver="GPKG", engine="pyogrio")
    T = gpd.GeoDataFrame([{**{c: None for c in TEXT_COLS},
                          "label_id": f"T{i}", "text": t["text"], "ocr_text": t.get("ocr_text", ""),
                          "ocr_score": t.get("score", 0.0), "font_px": t.get("font_px", 15.0),
                          "angle_deg": t.get("angle_deg", 0.0), "anchor": "center", "rgb": "#000000",
                          "box_x0": t["x"] - 30, "box_y0": t["y"] - 8, "box_x1": t["x"] + 30, "box_y1": t["y"] + 8,
                          "source": "test", "review_status": t.get("review_status", "OCR_CANDIDATE")}
                         for i, t in enumerate(texts or [])], geometry=[Point(t["x"], t["y"]) for t in (texts or [])])
    if len(T): T.to_file(p, layer="text_labels", driver="GPKG", engine="pyogrio")
    if residue:
        Q = gpd.GeoDataFrame({"res_id": ["residue-0"], "src_line_id": ["L63"], "src_logical_id": ["G50"],
                              "kind": ["ocr_glyph_residue"], "width_px": [1.0], "rgb": ["#000000"],
                              "restore_hint": ["isolated suspect glyph stroke"]},
                             geometry=[LineString([(20, 100), (30, 105)])])
        Q.to_file(p, layer="text_residue_lines", driver="GPKG", engine="pyogrio")
    img = np.full((H, W, 3), 255, np.uint8)
    return Document(p, (W, H), img), p, tmp_path


# ---------------- P0: NO_SILENT_GEOLOGY_LOSS ----------------

def test_suspect_lines_queued_with_region_and_source(tmp_path):
    d, _, _ = make_doc(tmp_path, residue=True)
    q = d.line_review_queue(); c = d.line_review_counters()
    assert c["suspect_pending"] == 2 and c["residue_pending"] == 1
    sus = [r for r in q if r["layer"] == "visual_lines"]
    assert len(sus) == 2 and all(r["status"] == "PENDING" for r in sus)
    assert {r["src_line_id"] for r in sus} == {"L7", "L9"}          # baseline source id preserved
    assert all(r["region"] and r["reason"] == "possible_real_geology_REVIEW" for r in sus)
    res = [r for r in q if r["layer"] == "text_residue_lines"]
    assert res[0]["src_line_id"] == "L63"


def test_suspect_line_batch_keep_and_cleanup_undoable(tmp_path):
    d, _, _ = make_doc(tmp_path)
    q = d.line_review_queue(); sus = [r["id"] for r in q if r["layer"] == "visual_lines"]
    nL, nQ = len(d.L), len(d.Q)
    d.line_review_decide([sus[0]], "keep")                        # batch API, one id here
    keep = d.L.loc[d.L["_eid"] == sus[0]].iloc[0]
    assert keep["kind"] == LINE_KEPT_KIND                          # stays in visual_lines, geometry untouched
    d.line_review_decide([sus[1]], "cleanup")
    assert sus[1] not in set(d.L["_eid"]) and len(d.Q) == nQ + 1   # isolated, never deleted
    moved = d.Q.iloc[-1]
    assert str(moved["src_line_id"]) == str(moved["line_id"]).removeprefix("rev-") and "cleanup" in str(moved["restore_hint"])
    d.undo_op(); assert len(d.L) == nL and sus[1] in set(d.L["_eid"])   # one op = one undo
    d.undo_op(); assert d.L.loc[d.L["_eid"] == sus[0], "kind"].iloc[0] == LINE_SUSPECT_KIND


def test_residue_line_restore_returns_to_visual_lines(tmp_path):
    d, _, _ = make_doc(tmp_path, residue=True)
    rid = int(d.Q["_eid"].iloc[0]); nL = len(d.L)
    d.line_review_decide([rid], "restore")
    assert len(d.Q) == 0 and len(d.L) == nL + 1
    assert d.L.iloc[-1]["kind"] == LINE_KEPT_KIND
    d.undo_op(); assert len(d.Q) == 1 and len(d.L) == nL


def test_crossing_geological_line_never_auto_suggested(tmp_path):
    """a real geological line crossing an OCR box region keeps inside_share<1 -> flagged, never suggested."""
    d, _, _ = make_doc(tmp_path)
    cross = d.L.loc[d.L["line_id"] == "rev-L7", "geometry"].iloc[0]
    box = [90, 20, 200, 60]                                # covers ~half the crossing line
    r = d.text_preview(box, ocr=False)
    hit = [c for c in r["line_info"] if c["inside_share"] < 0.9]
    assert hit and all("partially_outside" in c["risks"] and not c["suggested"] for c in hit)
    assert cross.equals(d.L.loc[d.L["line_id"] == "rev-L7", "geometry"].iloc[0])   # untouched


def test_export_gate_blocks_unresolved_suspect_lines(tmp_path):
    d, p, tp = make_doc(tmp_path)
    doc = {"coordinate_mode": "PIXEL_SPACE"}
    with pytest.raises(EXP.ExportError, match="suspect geological lines"):
        EXP.export(p, doc, "GPKG", ["geological_lines"], tp / "e1")
    meta = EXP.export(p, doc, "GPKG", ["geological_lines"], tp / "e2", draft=True)
    assert meta["unresolved_suspect_lines"] == 2 and meta["export_mode"] == "draft"
    q = d.line_review_queue(); ids = [r["id"] for r in q if r["layer"] == "visual_lines"]
    d.line_review_decide(ids, "keep")                             # batch resolve all
    d.save_as(tp / "resolved.gpkg", draft=True)
    meta = EXP.export(tp / "resolved.gpkg", doc, "GPKG", ["geological_lines"], tp / "e3")
    assert meta["unresolved_suspect_lines"] == 0 and meta["export_mode"] == "formal"


def test_dedupe_never_merges_different_text(tmp_path):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "experiments" / "STITCHVECTOR"))
    import sv_u2_ocr_protected_build as B
    quads = [{"quad": [[10, 10], [60, 10], [60, 30], [10, 30]], "text": "J2y", "score": 0.9},
             {"quad": [[12, 12], [62, 12], [62, 32], [12, 32]], "text": "J2x", "score": 0.8},   # IoU>0.5, different text
             {"quad": [[11, 11], [61, 11], [61, 31], [11, 31]], "text": "J2y", "score": 0.85}]  # duplicate of first
    m = B.dedupe_quads(quads)
    assert len(m) == 2, "different text at overlapping boxes must NOT merge"
    j2y = next(q for q in m if q["text"] == "J2y")
    assert len(j2y["src"]) == 2 and "J2x" in j2y.get("conflicts", [])     # provenance + conflict kept


# ---------------- P1: RED_FACE_REAL_REPAIR_VERIFIED ----------------

def test_enclosed_frag_triage_then_real_geometric_merge(tmp_path):
    """the hole-filling fragment is batch_safe; a labelled unit would be review; merge is REAL union into
    the host (one undo record) - not a face_group tag."""
    d, _, _ = make_doc(tmp_path)
    sc, cand = RF.candidates(d, [0, 0, 100, 120], 0)
    safe = cand["batch_safe"]
    assert len(safe) == 1 and safe[0]["host_eid"] == 0            # frag inside the host ring -> host 0
    host_area = d.F.loc[d.F["_eid"] == 0, "geometry"].iloc[0].area
    n0 = len(d.F)
    merged, skipped = RF.apply_safe(d, safe)
    assert not skipped and len(merged) == 1 and merged[0]["host"] == 0
    assert len(d.F) == n0 - 1
    g = d.F.loc[d.F["_eid"] == 0, "geometry"].iloc[0]
    assert abs(g.area - host_area - 12 * 10) < 1e-6 and len(g.interiors) == 0    # hole filled by real union
    mf = d.F.loc[d.F["_eid"] == 0, "merged_from"].iloc[0]
    assert mf and str(safe[0]["eid"]) in str(mf)                               # provenance, not grouping
    d.undo_op(); assert len(d.F) == n0                                          # ONE undo restores everything


def test_heterochromatic_frag_merges_to_specified_host(tmp_path):
    """mixed-label/colour fragments merge only through the explicit confirmed path (apply_safe = the
    batch the user confirmed); review-classified candidates stay untouched."""
    d, _, _ = make_doc(tmp_path)
    sc, cand = RF.candidates(d, [0, 0, 100, 120], 0)
    safe = cand["batch_safe"]
    # make the frag clearly heterochromatic: still merges because the operator confirmed the batch
    assert d.F.loc[d.F["_eid"] == safe[0]["eid"], "rgb"].iloc[0] != d.F.loc[d.F["_eid"] == 0, "rgb"].iloc[0]
    merged, _ = RF.apply_safe(d, safe)
    assert merged[0]["host"] == 0
    # anything the scan put in review is NOT in batch_safe and cannot be merged by apply_safe silently
    for r in cand["review"]:
        assert r["eid"] in set(d.F["_eid"])


# ---------------- P2: STUDIO_OWNER_WORKFLOW_READY ----------------

def test_all_ocr_candidates_reach_review_queue(tmp_path):
    texts = [{"x": 60 + 12 * i, "y": 42, "text": f"W{i}", "score": s}
             for i, s in enumerate([0.99, 0.95, 0.7, 0.4, 0.0])]
    d, _, _ = make_doc(tmp_path, texts=texts)
    assert (d.T["review_status"] == "OCR_CANDIDATE").all()
    d.classify_review(0.90)
    q = d.review_queue()
    assert len(q) >= 3 and all(r["status"] in ("REVIEW_REQUIRED", "REVIEW_SKIPPED") for r in q)
    # low-score / risk texts are the queue; high-score become AUTO_ACCEPTED_UNVERIFIED, still countable
    cnt = d.review_counters()
    assert cnt["total"] == 5 and cnt["required"] >= 3
    ids = [r["id"] for r in q]
    d.review_decide(ids, "confirm")
    assert d.review_counters()["confirmed"] == len(ids)
