"""Line repair + Legend acceptance scenarios on copies of existing GPKGs (DATA_LEVEL_VERIFIED; same core the UI calls).

S_COVER  u2 fault F3: B2c misses a 21.6 px stretch. Draw it, role COVER (ASSUMED for the test, geology not verified),
         heal-brush along it, apply the teeth legend, save, reopen.
S_SPLIT  u2 line B (red line on a green edge, missed by B2c). Draw it across the face it should separate, role SPLIT
         (ASSUMED), preview + apply split, save, reopen.
S_NEG    negative checks: stale preview after an edit / undo, SPLIT refused for UNKNOWN, heal under UNKNOWN never merged.
The Oracle traces are used only to place the drawn line (standing in for the user's clicks) and to score afterwards.
"""
import json, shutil, sys, hashlib
from pathlib import Path
import numpy as np, shapely, pyogrio
from shapely.geometry import LineString
from PIL import Image
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from tools.stitchvector_editor.core import Document, EditError, FACE, LINE, coverage_report  # noqa: E402

INP = Path.home() / "geomap2arcgis/runs/stitchvector/editor_v01/inputs"
OUT = Path.home() / "geomap2arcgis/runs/stitchvector/editor_lr/uat"
ORA = json.load(open(ROOT / "experiments/STITCHVECTOR/oracle/u2_300_oracle.json"))


def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()


def trace(lid):
    l = next(x for x in ORA["lines"] if x["id"] == lid); return LineString(l.get("raw") or l.get("points") or l.get("waypoints"))


def fresh(tag):
    d = OUT / tag; d.mkdir(parents=True, exist_ok=True); src = d / "input_copy.gpkg"
    if src.exists(): src.unlink()
    shutil.copyfile(INP / "u2_B2c.gpkg", src); img = np.asarray(Image.open(INP / "u2_original.png").convert("RGB"))
    return Document(src, (300, 300), img), d


def small_near(doc, geom, r=3.0, max_area=5.0):
    g = np.asarray(doc.F.geometry.values, object); m = shapely.intersects(g, geom.buffer(r)) & (shapely.area(g) <= max_area)
    return int(m.sum())


def missing_piece(lid, doc):
    U = shapely.union_all([g.buffer(2) for g in doc.L.geometry]); t = trace(lid)
    parts = sorted([p for p in shapely.get_parts(t.difference(U)) if p.geom_type == "LineString"], key=lambda p: -p.length)
    return t, parts[0]


def continuity(lid, doc, tol=2.0):
    t = trace(lid); U = shapely.union_all([g.buffer(tol) for g in doc.L.geometry])
    pts = [t.interpolate(d) for d in np.arange(0, t.length, 1.0)]
    hit = np.array([U.contains(p) for p in pts]); gaps, run = [], 0
    for h in hit:
        if not h: run += 1
        elif run: gaps.append(run); run = 0
    if run: gaps.append(run)
    return {"axis_px": len(pts), "covered_share": round(float(hit.mean()), 3), "gaps_px": gaps}


def changed_outside(doc, F0, L0, zone):
    """faces/lines changed whose geometry is not near the working zone (should be 0)."""
    a, b = F0.set_index("_eid"), doc.F.set_index("_eid"); n = 0
    for i in a.index:
        g = a.at[i, "geometry"]
        if g.intersects(zone): continue
        if i not in b.index or not g.equals_exact(b.at[i, "geometry"], 1e-9) or a.at[i, "rgb"] != b.at[i, "rgb"]: n += 1
    la, lb = L0.set_index("_eid"), doc.L.set_index("_eid")
    for i in la.index:
        g = la.at[i, "geometry"]
        if g.intersects(zone): continue
        if i not in lb.index or not g.equals_exact(lb.at[i, "geometry"], 1e-9): n += 1
    return n


def scenario_cover():
    doc, d = fresh("cover"); F0, L0 = doc.F.copy(), doc.L.copy(); ops = {}
    t, miss = missing_piece("F3", doc); zone = miss.buffer(8)
    before = {"small_faces_near_gap": small_near(doc, miss), "continuity": continuity("F3", doc)}
    near_f3 = [int(e) for e, g in zip(doc.L["_eid"], doc.L.geometry) if g.distance(t) < 2]
    # 1 draw the missing stretch (endpoints snap to existing F3 ends), joined to the F3 group
    lid = str(doc.L.loc[doc.L["_eid"] == near_f3[0], "logical_id"].iloc[0]) if near_f3 else None
    new = doc.add_line([list(c) for c in miss.coords], 1.8, "#c0392b", lid); ops["draw"] = 1
    group = doc.group(new); ops["select_group"] = 1
    # 2 role COVER (assumed) for the whole fault group
    doc.set_role(group, "COVER"); ops["set_role"] = 1
    # 3 heal brush along the drawn line
    pv = doc.heal_preview(doc.gesture("brush", [list(c) for c in miss.coords], 4.0), 6.0); ops["heal_preview"] = 1
    counts = pv["counts"]; r = doc.heal_apply(pv["preview_id"]); ops["heal_apply"] = 1
    # 4 legend: teeth on the left, spacing 10
    doc.apply_legend(LINE, group, "L_TEETH_RED"); ops["apply_legend"] = 1
    geom_before_legend = [g.wkb for g in doc.L.loc[doc.L["_eid"].isin(group)].geometry]
    doc.set_style("L_TEETH_RED", {"tooth_spacing": 8.0, "tooth_side": "right"}); ops["edit_style"] = 1
    geom_after_legend = [g.wkb for g in doc.L.loc[doc.L["_eid"].isin(group)].geometry]
    teeth = sum(len(x["teeth"]) for x in doc.render_lines() if x["id"] in group)
    after = {"small_faces_near_gap": small_near(doc, miss), "continuity": continuity("F3", doc)}
    out = d / "u2_F3_cover_repair.gpkg"
    if out.exists(): out.unlink()
    sv = doc.save_as(out); ops["save"] = 1
    re = Document(out, (300, 300))
    rl = re.L.loc[re.L["legend_id"] == "L_TEETH_RED"]
    return {"role_assumption": "F3 treated as COVER for the test; geology not verified", "drawn_px": round(miss.length, 1),
            "group_size": len(group), "heal_counts": counts, "heal_merged": r["merged"], "before": before, "after": after,
            "legend_geometry_unchanged": geom_before_legend == geom_after_legend, "teeth_rendered": teeth,
            "objects_changed_outside_zone": changed_outside(doc, F0, L0, zone.union(t.buffer(8))),
            "save": {k: sv[k] for k in ("accepted", "readback_matches_memory", "input_sha256_unchanged")},
            "reopen": {"styles": sorted(re.styles), "teeth_style": re.styles["L_TEETH_RED"], "lines_with_teeth_legend": int(len(rl)),
                       "roles": sorted(set(re.L["line_role"])), "teeth_rendered": sum(len(x["teeth"]) for x in re.render_lines())},
            "ops": ops, "output": str(out), "output_sha256": sha(out)}


def scenario_split():
    doc, d = fresh("split"); F0, L0 = doc.F.copy(), doc.L.copy(); ops = {}
    t = trace("C"); ends = list(t.coords)
    # extend each end 2 px so the cut fully crosses the face it separates
    def ext(p, q, k=2.0):
        v = np.subtract(p, q); v = v / max(np.hypot(*v), 1e-9); return list(np.add(p, v * k))
    pts = [ext(ends[0], ends[1])] + [list(c) for c in ends] + [ext(ends[-1], ends[-2])]
    hit_before = int(shapely.intersects(np.asarray(doc.F.geometry.values, object), LineString(pts)).sum())
    new = doc.add_line(pts, 1.5, "#c0392b"); ops["draw"] = 1
    doc.set_role([new], "SPLIT"); ops["set_role"] = 1
    pv = doc.split_face_preview(new); ops["split_preview"] = 1
    r = doc.split_face_apply(pv["preview_id"]); ops["split_apply"] = 1
    doc.apply_legend(LINE, [new], "L_SOLID_BLACK"); ops["apply_legend"] = 1
    # the split's new shared edge: fraction of the drawn line that lies on a face boundary
    B = shapely.union_all([p.boundary for p in doc.F.geometry if p.intersects(LineString(pts).buffer(1))])
    Lc = LineString(pts); samp = [Lc.interpolate(d) for d in np.arange(0, Lc.length, 1.0)]
    on_edge = float(np.mean([B.distance(q) <= 0.75 for q in samp]))   # share of 1 px samples of the drawn line lying on a face edge
    rep = coverage_report(doc.F, doc.W, doc.H)
    out = d / "u2_C_split_repair.gpkg"
    if out.exists(): out.unlink()
    sv = doc.save_as(out); ops["save"] = 1; re = Document(out, (300, 300))
    return {"role_assumption": "C treated as SPLIT for the test; geology not verified", "faces_crossed": hit_before, "faces_cut": r["faces_cut"],
            "pieces": r["pieces"], "faces_before_after": [len(F0), len(doc.F)], "coverage": rep, "new_edge_along_line_share": round(on_edge, 2),
            "continuity": continuity("C", doc), "objects_changed_outside_zone": changed_outside(doc, F0, L0, LineString(pts).buffer(8)),
            "save": {k: sv[k] for k in ("accepted", "readback_matches_memory", "input_sha256_unchanged")},
            "reopen_roles": sorted(set(re.L["line_role"])), "ops": ops, "output": str(out), "output_sha256": sha(out)}


def scenario_negative():
    doc, _ = fresh("neg"); res = {}
    pv = doc.heal_preview(doc.gesture("brush", [[40, 33], [53, 13]], 4), 6.0)
    doc.rewidth([0], 2.0)
    try: doc.heal_apply(pv["preview_id"]); res["stale_after_edit"] = "ACCEPTED (bad)"
    except EditError as e: res["stale_after_edit"] = "rejected: " + str(e)
    pv = doc.heal_preview(doc.gesture("brush", [[40, 33], [53, 13]], 4), 6.0); doc.undo_op()
    try: doc.heal_apply(pv["preview_id"]); res["stale_after_undo"] = "ACCEPTED (bad)"
    except EditError as e: res["stale_after_undo"] = "rejected: " + str(e)
    try: doc.split_face_preview(0); res["split_on_unknown"] = "ACCEPTED (bad)"
    except EditError as e: res["split_on_unknown"] = "rejected: " + str(e)
    t = doc.L.geometry.iloc[0]; pv = doc.heal_preview(doc.gesture("brush", [list(c) for c in t.coords], 3), 6.0)
    under = [c for c in pv["candidates"] if c.get("under_split_or_unknown_share", 0) >= 0.5]
    res["under_unknown_candidates"] = len(under); res["under_unknown_proposed_merge"] = sum(c["decision"] == "merge" for c in under)
    return res


if __name__ == "__main__":
    src_sha = sha(INP / "u2_B2c.gpkg")
    R = {"S_COVER": scenario_cover(), "S_SPLIT": scenario_split(), "S_NEG": scenario_negative(),
         "inputs_unchanged": sha(INP / "u2_B2c.gpkg") == src_sha, "verification": "DATA_LEVEL_VERIFIED"}
    o = ROOT / "experiments/STITCHVECTOR/line_repair/lr_result.json"; o.parent.mkdir(parents=True, exist_ok=True)
    json.dump(R, open(o, "w"), indent=1, default=str); print(json.dumps(R, indent=1, default=str)[:3000])
