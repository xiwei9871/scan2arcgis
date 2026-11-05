"""P1.1 gate-hardening tests (2026-11 review): unified deliverable gate shared by editor save + studio export,
human-confirmation semantics (no auto-confirm on style edits / same-text resubmits), era-code English guard."""
import json, sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.stitchvector_editor.test_p0_fixes import make_doc  # noqa: E402
from tools.stitchvector_editor.core import Document, EditError, _era_like, review_pending  # noqa: E402

T = [{"x": 20, "y": 20, "text": "怀道", "score": 0.98}, {"x": 60, "y": 20, "text": "低分", "score": 0.5}]


def _confirm_all(d):
    ids = [int(i) for i in d.T.loc[d.T["review_status"].isin(("REVIEW_REQUIRED", "REVIEW_SKIPPED", "AUTO_ACCEPTED_UNVERIFIED")), "_eid"]]
    if ids: d.review_decide(ids, "confirm")


# ---------- unified gate: every incomplete state blocks a formal save ----------

def test_all_skipped_still_blocks_formal_export(tmp_path):
    """skipping leaves the queue but is NOT a deliverable state: all-skipped -> formal save refused, draft allowed."""
    d, _, _ = make_doc(tmp_path, texts=T)
    d.classify_review(0.90)
    q = [x["id"] for x in d.review_queue()]
    d.review_decide(q, "skip")
    st = set(d.T["review_status"])
    assert all(x["status"] == "REVIEW_SKIPPED" for x in d.review_queue()) and st == {"REVIEW_SKIPPED", "AUTO_ACCEPTED_UNVERIFIED"}
    with pytest.raises(EditError, match="deliverable state"):
        d.save_as(tmp_path / "formal.gpkg")
    r = d.save_as(tmp_path / "draft.gpkg", draft=True)
    assert r["export_mode"] == "draft" and r["unreviewed"] == 1


def test_pipeline_states_are_not_confirmations(tmp_path):
    """TEXT_VECTOR_CREATED / BACKGROUND_CLEAR_PENDING / OCR_CANDIDATE all block a formal save."""
    for st in ("TEXT_VECTOR_CREATED", "BACKGROUND_CLEAR_PENDING", "OCR_CANDIDATE", "OCR_DRAFT"):
        d, _, _ = make_doc(tmp_path, texts=[{"x": 20, "y": 20, "text": "字", "review_status": st}])
        assert review_pending(d.T) == 1, st
        with pytest.raises(EditError, match="deliverable state"): d.save_as(tmp_path / f"f_{st}.gpkg")
    for st in ("OCR_CONFIRMED", "HUMAN_EDITED", "AUTO_ACCEPTED_UNVERIFIED", "TEXT_LAYER_COMPLETE"):
        d, _, _ = make_doc(tmp_path, texts=[{"x": 20, "y": 20, "text": "字", "review_status": st}])
        assert review_pending(d.T) == 0, st
        d.save_as(tmp_path / f"ok_{st}.gpkg")


# ---------- human confirmation requires a real content action ----------

def test_font_angle_only_edit_does_not_confirm(tmp_path):
    d, _, _ = make_doc(tmp_path, texts=[{"x": 20, "y": 20, "text": "低分", "score": 0.5}])
    d.classify_review(0.90)
    tid = int(d.T["_eid"].iloc[0])
    d.edit_text(tid, font_px=30.0, angle_deg=15.0)
    assert d.T["review_status"].iloc[0] == "REVIEW_REQUIRED", "typography edits must not confirm"
    d.edit_text(tid, text="低分")
    assert d.T["review_status"].iloc[0] == "REVIEW_REQUIRED", "re-submitting the same text is not a confirmation"
    d.edit_text(tid, text="低分改正")
    r = d.T.iloc[0]
    assert r["review_status"] == "HUMAN_EDITED" and r["reviewed_at"] and r["review_actor"] == "human:edit_text"


def test_text_apply_same_text_does_not_confirm(tmp_path):
    d, _, _ = make_doc(tmp_path, texts=[{"x": 60, "y": 60, "text": "怀道", "score": 0.6, "review_status": "REVIEW_REQUIRED"}])
    pv = d.text_preview([50, 50, 76, 74])
    r = d.text_apply(pv["preview_id"], "怀道", font_px=18.4)
    assert r["mode"] == "edited_existing" and d.T["review_status"].iloc[0] == "REVIEW_REQUIRED"
    r2 = d.text_apply(d.text_preview([50, 50, 76, 74])["preview_id"], "怀道镇")
    assert d.T["review_status"].iloc[0] == "HUMAN_EDITED" and d.T["reviewed_at"].iloc[0]


def test_review_decide_can_confirm_pipeline_state(tmp_path):
    """a TEXT_VECTOR_CREATED text can be explicitly confirmed -> then a formal save passes."""
    d, _, _ = make_doc(tmp_path, texts=[{"x": 20, "y": 20, "text": "字", "review_status": "TEXT_VECTOR_CREATED"}])
    tid = int(d.T["_eid"].iloc[0])
    d.review_decide([tid], "confirm")
    assert d.T["review_status"].iloc[0] == "OCR_CONFIRMED"
    d.save_as(tmp_path / "formal.gpkg")


def test_already_confirmed_cannot_be_decided_again(tmp_path):
    d, _, _ = make_doc(tmp_path, texts=[{"x": 20, "y": 20, "text": "字", "review_status": "OCR_CONFIRMED"}])
    with pytest.raises(EditError): d.review_decide([int(d.T["_eid"].iloc[0])], "skip")


# ---------- era-code rule: ordinary English must not be flagged ----------

def test_era_like_rejects_english_words():
    for word in ("North", "Tertiary", "Ordovician", "Carboniferous", "Jurassic", "Neogene"):
        assert not _era_like(word), word
    for code in ("Є2", "Pt3", "Ar", "O1", "J3t", "N-Q", "C-P", "AreJ", "PuiL", "K1", "S3", "γδ"):
        assert _era_like(code), code


def test_english_word_goes_to_auto_not_review(tmp_path):
    d, _, _ = make_doc(tmp_path, texts=[{"x": 20, "y": 20, "text": "North", "score": 0.98},
                                       {"x": 60, "y": 20, "text": "Ordovician", "score": 0.98}])
    d.classify_review(0.90)
    rr = d.T["review_reason"].apply(lambda s: json.loads(s or "[]"))
    assert all("stratigraphic_or_lithology_code" not in x for x in rr)


# ---------- studio export shares the same gate ----------

def test_studio_export_gate_and_draft(tmp_path):
    from tools.stitchvector_studio import exports as EXP
    d, _, _ = make_doc(tmp_path, texts=T)
    d.classify_review(0.90)
    g = tmp_path / "w.gpkg"; d.save_as(g, draft=True)
    doc = {"coordinate_mode": "PIXEL_SPACE"}
    with pytest.raises(EXP.ExportError, match="deliverable state"):
        EXP.export(g, doc, "GPKG", list(EXP.DEFAULT_LAYERS), tmp_path / "e1")
    meta = EXP.export(g, doc, "GPKG", list(EXP.DEFAULT_LAYERS), tmp_path / "e2", draft=True)
    assert meta["export_mode"] == "draft" and meta["unreviewed"] == 1
    assert "text_unconfirmed" in meta["layers"], "draft export must carry the unreviewed texts with their states"
    _confirm_all(d); g2 = tmp_path / "w2.gpkg"; d.save_as(g2)
    meta2 = EXP.export(g2, doc, "GPKG", list(EXP.DEFAULT_LAYERS), tmp_path / "e3")
    assert meta2["export_mode"] == "formal" and meta2["unreviewed"] == 0
