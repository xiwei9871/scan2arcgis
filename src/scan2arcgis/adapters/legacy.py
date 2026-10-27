"""Adapter: run legacy (GitLab dev 7aad0c1) stratigraphy and boundary pipelines
and convert their output to label rasters / line masks for evaluation.

Legacy code is used read-only from a git worktree (./legacy). Facts verified
while building this adapter (see docs/research/auto_vectorization_r1/legacy_algorithm_review.md):
  * input images must be OpenCV BGR; passing RGB silently yields ~0 polygons;
  * legend entries are dicts with map_fill_color as RGB;
  * outputs carry an uncalibrated heuristic `confidence`.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import cv2
import numpy as np

LEGACY_COMMIT = "7aad0c1"


def _import_legacy(legacy_backend: Path):
    p = str(legacy_backend)
    if p not in sys.path:
        sys.path.insert(0, p)
    from core.recognition.stratigraphy.pipeline import StratigraphyPipeline  # noqa
    from core.recognition.boundary.pipeline import BoundaryPipeline  # noqa
    return StratigraphyPipeline, BoundaryPipeline


def legend_dicts(legend: list[dict]) -> list[dict]:
    return [{"feature_type": "stratigraphy", "legend_entry_id": e["legend_entry_id"],
             "stratigraphy_symbol": e["legend_code"], "stratigraphy_name": e["legend_code"],
             "map_fill_color": [int(v) for v in e["fill_rgb"]]} for e in legend]


def _fill_geometry(mask, geom, value):
    def ring(c):
        return np.round(np.asarray(c)).astype(np.int32).reshape(-1, 1, 2)
    polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"] if geom["type"] == "MultiPolygon" else []
    for poly in polys:
        cv2.fillPoly(mask, [ring(poly[0])], value)
        for hole in poly[1:]:
            cv2.fillPoly(mask, [ring(hole)], -1 if mask.dtype != np.uint8 else 0)


def run_stratigraphy(legacy_backend: Path, rgb: np.ndarray, legend: list[dict]):
    Strat, _ = _import_legacy(legacy_backend)
    bgr = np.ascontiguousarray(rgb[..., ::-1])
    t = time.perf_counter()
    out = Strat().run(bgr, legend_entries=legend_dicts(legend), return_geojson=True)
    secs = time.perf_counter() - t
    code_to_id = {e["legend_code"]: e["class_id"] for e in legend}
    lab = np.full(rgb.shape[:2], -1, np.int32)
    feats = []
    # paint larger polygons first so small ones (lenses) stay on top
    def area(f):
        g = f["geometry"]; c = g["coordinates"][0][0] if g["type"] == "MultiPolygon" else g["coordinates"][0]
        a = np.asarray(c); return 0.5 * abs(np.dot(a[:, 0], np.roll(a[:, 1], 1)) - np.dot(a[:, 1], np.roll(a[:, 0], 1)))
    for f in sorted(out["features"], key=area, reverse=True):
        code = f["properties"].get("stratigraphy_symbol")
        cid = code_to_id.get(code, -1)
        _fill_geometry(lab, f["geometry"], cid)
        feats.append({"legend_code": code, "class_id": cid, "raw_score": f["properties"].get("confidence")})
    return lab.astype(np.int16), feats, secs


def run_boundary(legacy_backend: Path, rgb: np.ndarray):
    _, Bnd = _import_legacy(legacy_backend)
    bgr = np.ascontiguousarray(rgb[..., ::-1])
    t = time.perf_counter()
    out = Bnd().run(bgr, legend_entries=None, contour_legend_provided=False, boundary_legend_provided=False)
    secs = time.perf_counter() - t
    lines, meta = [], []
    for f in out["features"]:
        g = f["geometry"]
        parts = [g["coordinates"]] if g["type"] == "LineString" else g["coordinates"] if g["type"] == "MultiLineString" else []
        for p in parts:
            lines.append(p)
            meta.append({"kind": f["properties"].get("boundary_kind"), "raw_score": f["properties"].get("confidence")})
    return lines, meta, secs
