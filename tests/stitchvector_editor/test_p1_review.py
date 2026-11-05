"""P1 OCR confidence review tests (2026-11-05): T06 classify/risk rules, T07 queue semantics,
T08 persistence, T09 save gate + draft export. Synthetic fixtures only."""
import json, sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.stitchvector_editor.test_p0_fixes import make_doc  # noqa: E402
from tools.stitchvector_editor.core import Document, EditError  # noqa: E402

TEXTS = [
    {"x": 20, "y": 20, "text": "怀道", "score": 0.98},                    # clean high conf -> auto
    {"x": 60, "y": 20, "text": "Є2", "score": 0.99},                     # stratigraphic code -> review despite score
    {"x": 100, "y": 20, "text": "17", "score": 0.97},                    # numeric short -> review
    {"x": 150, "y": 20, "text": "低分字", "score": 0.60},                  # below threshold -> review
    {"x": 20, "y": 60, "text": "倾斜字", "score": 0.95, "angle_deg": 45},  # rotated -> review
    {"x": 60, "y": 60, "text": "竖排文字", "score": 0.95, "angle_deg": 90},# vertical -> review
    {"x": 100, "y": 100, "text": "普通词", "score": 0.95},                 # clean, off the y=60 test line -> auto
    {"x": 150, "y": 60, "text": "无分字", "score": None},                  # no evidence -> review
]


def test_classify_routes_by_score_and_risk(tmp_path):
    d, _, _ = make_doc(tmp_path, texts=TEXTS)
    c = d.classify_review(0.90)
    st = dict(zip(d.T["text"], d.T["review_status"]))
    assert st["怀道"] == "AUTO_ACCEPTED_UNVERIFIED" and st["普通词"] == "AUTO_ACCEPTED_UNVERIFIED"
    for t in ("Є2", "17", "低分字", "倾斜字", "竖排文字", "无分字"):
        assert st[t] == "REVIEW_REQUIRED", t
    assert c["required"] == 6 and c["auto_accepted"] == 2
    rr = dict(zip(d.T["text"], d.T["review_reason"]))
    assert "stratigraphic_or_lithology_code" in json.loads(rr["Є2"]) and "numeric_or_short" in json.loads(rr["17"])
    assert "rotated_or_vertical" in json.loads(rr["竖排文字"]) and "no_ocr_evidence" in json.loads(rr["无分字"])
    assert json.loads(rr["怀道"]) == [], "clean text must carry no fabricated risk"


def test_auto_accepted_never_masquerades_as_confirmed(tmp_path):
    d, _, _ = make_doc(tmp_path, texts=TEXTS[:1])
    d.classify_review(0.90)
    assert d.T["review_status"].iloc[0] == "AUTO_ACCEPTED_UNVERIFIED"
    assert "auto:classify" in d.T["review_actor"].iloc[0]
    assert not (d.T["review_status"] == "OCR_CONFIRMED").any()


def test_queue_order_and_skip(tmp_path):
    d, _, _ = make_doc(tmp_path, texts=TEXTS)
    d.classify_review(0.90)
    q = d.review_queue()
    assert len(q) == 6 and all(x["status"] == "REVIEW_REQUIRED" for x in q)
    ys = [(x["y"], x["x"]) for x in q]; assert ys == sorted(ys), "queue sorted top-to-bottom, left-to-right"
    d.review_decide([q[0]["id"]], "skip")
    q2 = d.review_queue()
    assert len(q2) == 6 and q2[-1]["status"] == "REVIEW_SKIPPED", "skipped item leaves the active queue, goes last"


def test_confirm_and_edit_leave_queue(tmp_path):
    d, _, _ = make_doc(tmp_path, texts=TEXTS)
    d.classify_review(0.90)
    q = d.review_queue(); tgt = q[0]["id"]
    c = d.review_decide([tgt], "confirm")
    row = d.T.loc[d.T["_eid"] == tgt].iloc[0]
    assert row["review_status"] == "OCR_CONFIRMED" and row["review_actor"] == "human" and row["reviewed_at"]
    assert c["confirmed"] == 1 and c["required"] == 5
    other = d.review_queue()[0]["id"]
    d.edit_text(other, text="人工改")
    assert d.T.loc[d.T["_eid"] == other, "review_status"].iloc[0] == "HUMAN_EDITED"
    assert other not in [x["id"] for x in d.review_queue()], "human edit is a terminal review state"


def test_classify_does_not_touch_human_states(tmp_path):
    d, _, _ = make_doc(tmp_path, texts=[{**TEXTS[0], "review_status": "HUMAN_EDITED"}, TEXTS[4]])
    d.classify_review(0.90)
    assert d.T.loc[d.T["text"] == "怀道", "review_status"].iloc[0] == "HUMAN_EDITED"


def test_review_state_survives_save_reopen(tmp_path):
    d, _, _ = make_doc(tmp_path, texts=TEXTS)
    d.classify_review(0.90)
    q = d.review_queue(); d.review_decide([q[0]["id"]], "confirm")
    out = tmp_path / "v1.gpkg"; d.save_as(out, draft=True)
    d2 = Document(out, (200, 120))
    row = d2.T.loc[d2.T["text"] == "怀道"].iloc[0]
    assert row["review_status"] == "AUTO_ACCEPTED_UNVERIFIED" and row["review_actor"].startswith("auto:classify")
    assert (d2.T["review_status"] == "REVIEW_REQUIRED").sum() == 5
    assert d2.review_queue() and all("reasons" in x for x in d2.review_queue())


def test_save_gate_blocks_unreviewed_and_draft_records_manifest(tmp_path):
    d, _, _ = make_doc(tmp_path, texts=TEXTS)
    d.classify_review(0.90)
    with pytest.raises(EditError, match="deliverable state"):
        d.save_as(tmp_path / "formal.gpkg")
    r = d.save_as(tmp_path / "draft.gpkg", draft=True)
    assert r["export_mode"] == "draft" and r["unreviewed"] == 6
    man = json.load(open(tmp_path / "draft.edits.json"))
    assert man["export_mode"] == "draft" and man["unreviewed"] == 6 and man["review"]["required"] == 6
    d2 = Document(tmp_path / "draft.gpkg", (200, 120))
    assert (d2.T["review_status"] == "REVIEW_REQUIRED").sum() == 6, "draft keeps pending flags; nothing silently confirmed"


def test_undo_redo_classify_and_decide(tmp_path):
    d, _, _ = make_doc(tmp_path, texts=TEXTS[:2])
    d.classify_review(0.90)
    st1 = list(d.T["review_status"])
    d.undo_op(); assert (d.T["review_status"] == "OCR_DRAFT").all()
    d.redo_op(); assert list(d.T["review_status"]) == st1
    q = d.review_queue(); d.review_decide([q[0]["id"]], "confirm")
    d.undo_op(); assert d.T.loc[d.T["_eid"] == q[0]["id"], "review_status"].iloc[0] == "REVIEW_REQUIRED"
