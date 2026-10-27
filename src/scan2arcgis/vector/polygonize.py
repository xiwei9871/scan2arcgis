"""Raster labels -> topologically consistent pixel-space vectors (R1 PoC).

Polygons: rasterio.features.shapes on the label raster (a partition, so no
overlaps/gaps by construction), then topology-preserving simplification.
Contacts: shared edges between adjacent polygons of different classes,
computed from the polygon set (so lines and areas always agree).
Faults: skeleton pixel components traced into polylines.

Coordinates: original image pixels, y down. Exported layers carry NO CRS and a
`coord_space=image_px_unreferenced` field; they are not georeferenced GIS data.
"""
from __future__ import annotations

import numpy as np
import rasterio.features
from shapely.geometry import shape, LineString, MultiLineString, Polygon
from shapely.ops import linemerge, unary_union
try:  # shapely >= 2.1
    from shapely import coverage_simplify
except ImportError:  # shapely 2.0.x (pinned for legacy compatibility): no coverage-safe simplification
    coverage_simplify = None

COORD_SPACE = "image_px_unreferenced"


def polygons_from_labels(labels: np.ndarray, valid: np.ndarray, *, min_area_px=50, simplify_px=1.0):
    lab = np.where(valid, labels, -1).astype(np.int32)
    geoms, cls = [], []
    for g, v in rasterio.features.shapes(lab, mask=lab >= 0, connectivity=4):
        p = shape(g)
        if p.area >= min_area_px:
            geoms.append(p); cls.append(int(v))
    if simplify_px > 0 and geoms and coverage_simplify is not None:
        # coverage-aware simplification keeps shared edges identical (no slivers)
        geoms = list(coverage_simplify(np.array(geoms, dtype=object), simplify_px))
    return [(g, c) for g, c in zip(geoms, cls) if not g.is_empty]


def contacts_from_polygons(polys):
    """Shared boundaries between neighbouring polygons with different class ids."""
    from shapely.strtree import STRtree
    geoms = [p for p, _ in polys]
    tree = STRtree(geoms)
    out = []
    for i, (gi, ci) in enumerate(polys):
        for j in tree.query(gi):
            if j <= i or polys[j][1] == ci:
                continue
            inter = gi.boundary.intersection(polys[j][0].boundary)
            if inter.is_empty:
                continue
            lines = [g for g in getattr(inter, "geoms", [inter]) if g.geom_type in ("LineString", "MultiLineString")]
            if not lines:
                continue
            u = unary_union(lines)
            merged = linemerge(u) if u.geom_type == "MultiLineString" else u
            for ln in getattr(merged, "geoms", [merged]):
                if ln.length >= 2:
                    out.append((ln, ci, polys[j][1], i, int(j)))
    return out


def trace_skeleton(component_labels: np.ndarray, scores: np.ndarray, min_len=20):
    """Very small skeleton tracer: order pixels of each component by a greedy walk.
    Adequate for PoC; production should use a graph-based tracer (e.g. sknw)."""
    out = []
    ids = np.unique(component_labels[component_labels > 0])
    nb = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
    for i in ids:
        ys, xs = np.nonzero(component_labels == i)
        pts = set(zip(xs.tolist(), ys.tolist()))
        deg = {p: sum((p[0] + dx, p[1] + dy) in pts for dy, dx in nb) for p in pts}
        start = min(pts, key=lambda p: (deg[p], p))
        seen, path, cur = {start}, [start], start
        while True:
            nxt = [(cur[0] + dx, cur[1] + dy) for dy, dx in nb if (cur[0] + dx, cur[1] + dy) in pts and (cur[0] + dx, cur[1] + dy) not in seen]
            if not nxt:
                break
            cur = nxt[0]; seen.add(cur); path.append(cur)
        if len(path) >= min_len:
            ln = LineString([(x + 0.5, y + 0.5) for x, y in path]).simplify(1.0)
            out.append((ln, float(scores[i]) if i < len(scores) else 0.0))
    return out


def topology_report(polys, valid_area_px: float) -> dict:
    geoms = [p for p, _ in polys]
    invalid = sum(not g.is_valid for g in geoms)
    union = unary_union(geoms)
    overlap = float(sum(g.area for g in geoms) - union.area)
    return {"n_polygons": len(geoms), "invalid": int(invalid), "overlap_area_px": overlap,
            "coverage_ratio": float(union.area / max(1.0, valid_area_px))}
