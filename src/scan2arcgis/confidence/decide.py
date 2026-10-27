"""R1 decision policy (r1_poc_uncalibrated_v0).

Because no calibrator exists yet, AUTO_ACCEPT is NEVER emitted (D0 rule V3).
Uncalibrated signals only order the work: AUTO_RETRY (re-run with another
recognizer variant), HUMAN_REVIEW (riskiest), NONE (no action proposed yet,
pending calibration). Thresholds below are ranking cut-offs, not accuracy claims.
"""
from __future__ import annotations


def _hard_fail(hard):
    return any(h["status"] == "FAIL" for h in hard)


def decide_region(sig: dict, hard: list[dict]) -> str:
    if _hard_fail(hard):
        return "BLOCKED"
    if sig["mean_margin"] < 0.25 or sig["low_margin_frac"] > 0.6:
        return "HUMAN_REVIEW"
    if sig["mean_margin"] < 0.5:
        return "AUTO_RETRY"
    return "NONE"


def decide_line(sig: dict, hard: list[dict], kind: str) -> str:
    if _hard_fail(hard):
        return "BLOCKED"
    if kind == "contact":
        return "HUMAN_REVIEW" if min(sig["side_margins"]) < 0.25 else "NONE"
    return "HUMAN_REVIEW" if sig["ink_score"] < 0.3 else "NONE"
