"""D0 feature-record validation: JSON Schema + semantic rules V1-V8.

See docs/design/D0_dataset_spec.md section 6. The key invariant is that an
uncalibrated score is never presented as a probability.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping

from jsonschema import Draft202012Validator

SCHEMA_PATH = Path(__file__).resolve().parents[3] / "schemas" / "d0" / "feature_record.schema.json"


@dataclass(frozen=True)
class ValidationIssue:
    feature_id: str
    rule: str
    message: str


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    return Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))


def _semantic_rules(r: Mapping[str, Any], holdout_maps: frozenset[str]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    cal = r.get("calibration_status")
    kind = r.get("producer_kind")
    ref = r.get("calibration_ref")

    if cal == "UNCALIBRATED":  # V1
        for key in ("calibrated_p_correct", "p_error", "calibration_ref"):
            if r.get(key) is not None:
                out.append(("V1", f"UNCALIBRATED record must not carry {key}"))
    if cal == "CALIBRATED":  # V2
        if not isinstance(ref, Mapping):
            out.append(("V2", "CALIBRATED record requires calibration_ref"))
        elif ref.get("calib_dataset_version", "") in holdout_maps:
            out.append(("V2", "calibration_ref references holdout data"))
        if r.get("calibrated_p_correct") is None and r.get("p_error") is None:
            out.append(("V2", "CALIBRATED record must provide calibrated_p_correct or p_error"))
    if r.get("decision") == "AUTO_ACCEPT":  # V3
        if cal != "CALIBRATED":
            out.append(("V3", "AUTO_ACCEPT requires CALIBRATED confidence"))
        checks = r.get("hard_checks") or []
        if not checks or any(c.get("status") != "PASS" for c in checks):
            out.append(("V3", "AUTO_ACCEPT requires all hard_checks PASS (and at least one)"))
    if kind == "legacy_rule" and cal != "UNCALIBRATED":  # V4
        out.append(("V4", "legacy_rule output must be UNCALIBRATED"))
    if r.get("record_kind") == "ground_truth":  # V5
        if cal != "NOT_APPLICABLE":
            out.append(("V5", "ground_truth must use calibration_status NOT_APPLICABLE"))
        if kind not in ("human", "import"):
            out.append(("V5", "ground_truth producer_kind must be human or import"))
    elif cal == "NOT_APPLICABLE":
        out.append(("V5", "NOT_APPLICABLE is reserved for ground_truth"))
    if r.get("review_status") == "AUTO_ACCEPTED" and r.get("decision") != "AUTO_ACCEPT":  # V6
        out.append(("V6", "AUTO_ACCEPTED review_status requires decision AUTO_ACCEPT"))
    has_model = r.get("model_version_id") not in (None, "")
    if has_model != (kind in ("model", "hybrid")):  # V7
        out.append(("V7", "model_version_id must be set iff producer_kind is model/hybrid"))
    return out  # V8 (score ranges) is enforced by the JSON Schema


def validate_record(record: Mapping[str, Any], holdout_dataset_versions: Iterable[str] = ()) -> list[ValidationIssue]:
    fid = str(record.get("feature_id", "<missing>"))
    issues = [ValidationIssue(fid, "SCHEMA", f"{'/'.join(map(str, e.path)) or '<root>'}: {e.message}")
              for e in sorted(_validator().iter_errors(record), key=lambda e: list(e.path))]
    issues += [ValidationIssue(fid, rule, msg)
               for rule, msg in _semantic_rules(record, frozenset(holdout_dataset_versions))]
    return issues


def validate_records(records: Iterable[Mapping[str, Any]], holdout_dataset_versions: Iterable[str] = ()) -> list[ValidationIssue]:
    holdout = tuple(holdout_dataset_versions)
    seen: set[str] = set()
    issues: list[ValidationIssue] = []
    for r in records:
        fid = str(r.get("feature_id"))
        if fid in seen:
            issues.append(ValidationIssue(fid, "UNIQUE", "duplicate feature_id"))
        seen.add(fid)
        issues += validate_record(r, holdout)
    return issues
