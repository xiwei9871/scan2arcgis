"""B2c: B2a + luminance check on the segments B2a adds (rules: sv_b2c_phaseA_rules.json, sv_b2c_prereg.json).

B0 (frozen 2.0) objects are never touched; B2a only proposes extra segments. For each added segment the feature is the
one already computed by sv_b2b.features (unchanged): dL = median over samples of
  L*(centre pixel) - min(L*(left side), L*(right side)),   sides at w/2+2 and w/2+3 px along the normal.
Negative dL = the centre is darker than both sides (an ink stroke). A fill edge has its centre between the two sides
(dL near 0 or positive). JPEG 4:2:0 mainly blurs chroma, so L* is expected to survive better than the colour test of B2b.
Rule: keep an added segment if dL <= dL_max, or if its sides cannot be measured (stable share < min_stable: keep, do
not delete what cannot be judged). Known limit by construction: ink brighter than one of its sides is deleted.
"""
import numpy as np, shapely
from shapely.geometry import LineString
import sv_autoline as AL, sv_b2b as BB

Q = {"dL_max": -3.0, "min_stable": 0.3}


def seg_dL(L, g, w):
    f = BB.features(L, g, w); return f["centre_vs_sides_dL"], f["stable_share"]


def b2c(a, p=AL.P, q=Q):
    base, add = BB.added(a, p); L = AL.lab(a); keep, info = [], []
    for o in add:
        dl, st = seg_dL(L, o["geom"], o["width"]); ok = (st < q["min_stable"]) or (dl <= q["dL_max"])
        info.append({"dL": dl, "stable_share": st, "kept": bool(ok), "length": float(o["geom"].length)})
        if ok: keep.append(o)
    return base + keep, {"added": len(add), "kept": len(keep), "segments": info}


def label_scene(g, t, tol=2.0):
    """Ground truth for a counterexample-scene segment (evaluation only). Ink beats edge where ink is drawn on it."""
    L = g.length; parts = {}
    I = shapely.union_all([LineString(x["axis"]).buffer(tol + x["width"] / 2) for x in t["ink"]]) if t["ink"] else None
    E = shapely.union_all([LineString(x["axis"]).buffer(2.5) for x in t["edges"] if not x["covered_by_ink"]]) if any(not x["covered_by_ink"] for x in t["edges"]) else None
    Bd = shapely.union_all([LineString(x["axis"]).buffer(x["width"] / 2 + 2) for x in t["bands"]]) if t["bands"] else None
    rest = g
    for k, G in (("true_line", I), ("fill_edge", E), ("band_edge", Bd)):
        if G is None: parts[k] = 0.0; continue
        parts[k] = shapely.intersection(rest, G).length; rest = shapely.difference(rest, G)
    parts["other"] = rest.length
    lab = max(parts, key=parts.get)
    sub = None
    if lab == "true_line":
        best = max(t["ink"], key=lambda x: shapely.intersection(g, LineString(x["axis"]).buffer(tol + x["width"] / 2)).length); sub = best["sub"]
    return lab, {k: v / max(L, 1e-9) for k, v in parts.items()}, sub
