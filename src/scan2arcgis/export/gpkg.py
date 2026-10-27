"""Write R1 PoC results to GeoPackage with D0 feature-record fields.

No CRS is written. Every feature carries coord_space=image_px_unreferenced and
geo_referenced=false. Scores are stored as raw_score with UNCALIBRATED status.
"""
from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd

from ..d0.validate import validate_records

D0_JSON_FIELDS = ("class_candidates", "calibration_ref", "derived_from", "hard_checks", "quality_signals")


def d0_record(fid, map_id, feature_class, legend_code, legend_entry_id, raw_score, raw_sem,
              producer, version, run_id, decision, hard_checks, signals, derived=()):
    return {
        "feature_id": fid, "map_id": map_id, "record_kind": "prediction", "feature_class": feature_class,
        "legend_code": legend_code, "legend_entry_id": legend_entry_id, "class_candidates": [],
        "calibration_status": "UNCALIBRATED", "raw_score": raw_score, "raw_score_semantics": raw_sem,
        "calibrated_p_correct": None, "p_error": None, "calibration_ref": None,
        "producer_kind": producer[0], "producer_name": producer[1], "producer_version": version,
        "model_version_id": producer[2] if len(producer) > 2 else None, "run_id": run_id,
        "derived_from": list(derived), "review_status": "UNREVIEWED", "reviewer_role": None,
        "reviewed_at": None, "supersedes": None, "review_sampling": None,
        "hard_checks": hard_checks, "geometry_score": None, "quality_signals": signals,
        "decision": decision, "decision_policy_id": "r1_poc_uncalibrated_v0",
    }


def write_layers(path: Path, layers: dict[str, list[tuple]]) -> dict:
    """layers: name -> list of (geometry, d0_record). Validates records before writing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    summary = {}
    for name, items in layers.items():
        recs = [r for _, r in items]
        issues = validate_records(recs)
        if issues:
            raise ValueError(f"D0 validation failed for layer {name}: {issues[:5]}")
        rows = []
        for g, r in items:
            row = {k: (json.dumps(v, ensure_ascii=False) if k in D0_JSON_FIELDS else v) for k, v in r.items()}
            row["coord_space"] = "image_px_unreferenced"; row["geo_referenced"] = False
            rows.append(row)
        gdf = gpd.GeoDataFrame(rows, geometry=[g for g, _ in items], crs=None)
        gdf.to_file(path, layer=name, driver="GPKG", engine="pyogrio")
        summary[name] = len(rows)
    return summary
