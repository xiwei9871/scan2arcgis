"""Tests for D0 record validation rules V1-V8 (docs/design/D0_dataset_spec.md §6)."""
import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from scan2arcgis.d0 import validate_record, validate_records  # noqa: E402

LEGACY = {
    "feature_id": "f1", "map_id": "gm1", "record_kind": "prediction",
    "feature_class": "contact", "legend_code": None, "class_candidates": [],
    "calibration_status": "UNCALIBRATED", "raw_score": 0.83,
    "raw_score_semantics": "legacy_heuristic:boundary.confidence",
    "calibrated_p_correct": None, "p_error": None, "calibration_ref": None,
    "producer_kind": "legacy_rule", "producer_name": "legacy.boundary",
    "producer_version": "7aad0c1", "model_version_id": None, "run_id": "r1",
    "derived_from": [], "review_status": "UNREVIEWED", "hard_checks": [],
    "quality_signals": {}, "decision": "NONE",
}
CAL_REF = {"calibrator_id": "c1", "method": "isotonic", "calib_dataset_version": "d0-v1-calib", "fitted_at": "2026-10-27T00:00:00Z"}


def rules(record, holdout=()):
    return {i.rule for i in validate_record(record, holdout)}


def mutate(**kw):
    r = copy.deepcopy(LEGACY)
    r.update(kw)
    return r


def model_record(**kw):
    base = dict(producer_kind="model", model_version_id="m1", calibration_status="CALIBRATED",
                calibration_ref=CAL_REF, calibrated_p_correct=0.97, p_error=0.03)
    base.update(kw)
    return mutate(**base)


def test_valid_legacy_record_has_no_issues():
    assert validate_record(LEGACY) == []


def test_v1_uncalibrated_cannot_carry_probability():
    assert "V1" in rules(mutate(calibrated_p_correct=0.95))
    assert "V1" in rules(mutate(p_error=0.05))


def test_v4_legacy_cannot_claim_calibration():
    r = mutate(calibration_status="CALIBRATED", calibration_ref=CAL_REF, calibrated_p_correct=0.9)
    assert "V4" in rules(r)


def test_v2_calibrated_requires_reference_and_value():
    assert "V2" in rules(model_record(calibration_ref=None))
    assert "V2" in rules(model_record(calibrated_p_correct=None, p_error=None))
    assert "V2" in rules(model_record(), holdout=("d0-v1-calib",))
    assert validate_record(model_record()) == []


def test_v3_auto_accept_requires_calibration_and_hard_checks():
    assert "V3" in rules(mutate(decision="AUTO_ACCEPT", hard_checks=[{"check_id": "topo", "status": "PASS"}]))
    assert "V3" in rules(model_record(decision="AUTO_ACCEPT", hard_checks=[]))
    assert "V3" in rules(model_record(decision="AUTO_ACCEPT", hard_checks=[{"check_id": "topo", "status": "FAIL"}]))
    ok = model_record(decision="AUTO_ACCEPT", review_status="AUTO_ACCEPTED",
                      hard_checks=[{"check_id": "topo", "status": "PASS"}])
    assert validate_record(ok) == []


def test_v5_ground_truth_constraints():
    gt = mutate(record_kind="ground_truth", calibration_status="NOT_APPLICABLE", raw_score=None,
                producer_kind="human", producer_name="annotation", producer_version="d0-v1",
                label_status="draft", label_method="from_scratch")
    assert validate_record(gt) == []
    assert "V5" in rules({**gt, "producer_kind": "model", "model_version_id": "m1"})
    assert "V5" in rules(mutate(calibration_status="NOT_APPLICABLE"))


def test_v6_auto_accepted_status_requires_decision():
    assert "V6" in rules(mutate(review_status="AUTO_ACCEPTED"))


def test_v7_model_version_consistency():
    assert "V7" in rules(mutate(model_version_id="m1"))
    assert "V7" in rules(model_record(model_version_id=None))


def test_v8_score_range_enforced_by_schema():
    assert "SCHEMA" in rules(model_record(calibrated_p_correct=1.5))


def test_schema_rejects_unknown_fields_and_enums():
    assert "SCHEMA" in rules(mutate(confidence=0.9))
    assert "SCHEMA" in rules(mutate(calibration_status="MAYBE"))


def test_duplicate_feature_ids_are_reported():
    assert any(i.rule == "UNIQUE" for i in validate_records([LEGACY, LEGACY]))
