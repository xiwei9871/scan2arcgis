"""POC 1 data-level check (DATA_LEVEL_VERIFIED: drives the editor core, same code the UI calls).
Case A: synthetic 7001 B2c green region (37 faces, V0.1 needed 37 shift-clicks). User-like gestures are placed with the
truth polygon (marked TRUTH_ASSISTED for the gesture shape only); every selection rule runs without truth. Truth scores.
Case B: u2 B2c heal brush along two strokes: one over a recognised line, one over unrecognised ink (POC 0 red zone).
Usage: sv_poc1_check.py <inputs_dir> <out_dir> <json_out>   (.venv-sv)"""
import json, sys, shutil
from pathlib import Path
import numpy as np, shapely
from shapely.geometry import Polygon, LineString
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[2])); sys.path.insert(0, str(Path(__file__).resolve().parent))
from tools.stitchvector_editor.core import Document, EditError, FACE, LINE, sha256, coverage_report  # noqa: E402
import sv_synth as S  # noqa: E402


def score(d, sel, region):
    if not sel: return {"faces": 0, "precision_area": 0.0, "recall_area": 0.0}
    U = shapely.union_all([d.F.loc[d.F["_eid"] == e, "geometry"].iloc[0] for e in sel])
    return {"faces": len(sel), "precision_area": round(float(shapely.intersection(U, region).area / U.area), 4),
            "recall_area": round(float(shapely.intersection(U, region).area / region.area), 4)}


def case_a(inp, out):
    src = inp / "synth_7001_B2c.gpkg"; img = np.asarray(Image.open(inp / "synth_7001.png").convert("RGB"))
    a, truth, faces = S.generate(7001); order = ["green", "yellow", "redfill"]; r = shapely.make_valid(Polygon(faces["green"]))
    for m in order[1:]: r = shapely.difference(r, shapely.make_valid(Polygon(faces[m])))
    region = max(shapely.get_parts(r), key=lambda p: p.area) if r.geom_type != "Polygon" else r
    res = {"region_area": round(region.area, 1), "routes": {}}
    d = Document(src, (256, 256), img)
    inreg = [int(e) for e, g in zip(d.F["_eid"], d.F.geometry) if shapely.intersection(g, region).area >= 0.5 * g.area]
    res["faces_mostly_in_region"] = len(inreg)
    # R1: lasso = the region outline shrunk 2 px, simplified to ~12 points (what a user draws by hand)
    lasso_pts = list(region.buffer(-2).simplify(3).exterior.coords)
    g = d.gesture("lasso", lasso_pts); res["routes"]["lasso_centre_rule"] = {**score(d, d.select_region(g, FACE, "centre"), region), "gestures": 1, "lasso_points": len(lasso_pts)}
    res["routes"]["lasso_cover50_rule"] = {**score(d, d.select_region(g, FACE, "cover50"), region), "gestures": 1}
    # R2: two brush strokes across the region (medial-ish lines through the region), radius 6
    minx, miny, maxx, maxy = region.bounds; cy = (miny + maxy) / 2; cx = (minx + maxx) / 2
    s1 = shapely.intersection(LineString([(minx, cy), (maxx, cy)]), region.buffer(-3)); s2 = shapely.intersection(LineString([(cx, miny), (cx, maxy)]), region.buffer(-3))
    strokes = [list(max(shapely.get_parts(s), key=lambda p: p.length).coords) for s in (s1, s2) if not s.is_empty]
    sel = []
    for st in strokes: sel = sorted(set(sel) | set(d.select_region(d.gesture("brush", st, 6), FACE, "touch")))
    res["routes"]["brush_2_strokes_touch"] = {**score(d, sel, region), "gestures": len(strokes)}
    # R3: lasso then grow one ring, then subtract with a lasso outside the region? keep simple: lasso + grow + shrink
    las = d.select_region(g, FACE, "centre"); grown = d.grow(las); res["routes"]["lasso_then_grow1"] = {**score(d, grown, region), "gestures": 2}
    # merge with preview on the lasso route
    pv = d.merge_preview(las)
    res["merge_preview"] = [{"faces": len(x["faces"]), "area": round(x["area"], 1), "single_polygon": x["single_polygon"],
                             "colour_conflict_share": round(x.get("colour_conflict_share", 0), 3)} for x in pv["groups"]]
    n0 = len(d.F); r_ = d.merge_components(las); merged = max((d.F.loc[d.F["source"] == "edited_merge", "geometry"]), key=lambda x: x.area)
    res["merge"] = {"faces_before_after": [n0, len(d.F)], "groups_merged": r_["groups"], "largest_merged_area": round(merged.area, 1),
                    "largest_merged_outside_region_px2": round(float(shapely.difference(merged, region).area), 1),
                    "coverage_valid": coverage_report(d.F, 256, 256)["accepted"]}
    sv = d.save_as(out / "synth_7001_lasso_merge.gpkg"); res["save"] = {k: sv[k] for k in ("accepted", "readback_matches_memory", "input_sha256_unchanged")}
    res["v01_baseline"] = {"shift_clicks": 37, "merged_outside_region_px2": 275.7}
    return res


def case_b(inp, out, poc0):
    src = inp / "u2_B2c.gpkg"; img = np.asarray(Image.open(inp / "u2_original.png").convert("RGB")); res = {}
    p0 = json.load(open(poc0)); red = [r for r in p0["faces_detail"] if r["class"] == "on_unrecognised_ink"]
    d0 = Document(src, (300, 300), img)
    L = d0.L.iloc[int(np.argmax(d0.L.geometry.length))].geometry; known = [list(L.interpolate(t, normalized=True).coords[0]) for t in np.linspace(0.2, 0.8, 8)]
    pts = np.array([r["xy"] for r in red]); ymid = np.median(pts[:, 1]); band = pts[np.abs(pts[:, 1] - ymid) < 25]
    o = np.argsort(band[:, 0]); unrec = band[o][:: max(len(band) // 8, 1)].tolist()
    for name, stroke in (("over_recognised_line", known), ("over_unrecognised_ink", unrec)):
        d = Document(src, (300, 300), img); reg = d.gesture("brush", stroke, 4); pv = d.heal_preview(reg)
        rec = {"stroke_points": len(stroke), "candidates": len(pv["candidates"]), "counts": pv.get("counts", {}),
               "reasons": {k: sum(1 for c in pv["candidates"] if c["reason"] == k) for k in {c["reason"] for c in pv["candidates"]}}}
        if pv.get("counts", {}).get("merge"):
            n0 = len(d.F); d.heal_apply(pv["candidates"]); rec["faces_before_after"] = [n0, len(d.F)]; rec["coverage_valid"] = coverage_report(d.F, 300, 300)["accepted"]
            d.undo_op(); rec["undo_restores"] = len(d.F) == n0; d.redo_op()
            sv = d.save_as(out / f"u2_heal_{name}.gpkg"); rec["save"] = {k: sv[k] for k in ("accepted", "readback_matches_memory", "input_sha256_unchanged")}
        res[name] = rec
    return res


def main(inp, out, js):
    inp, out = Path(inp), Path(out); out.mkdir(parents=True, exist_ok=True)
    for f in out.glob("*"): f.unlink()
    h0 = {f.name: sha256(f) for f in inp.glob("*.gpkg")}
    res = {"mode": "DATA_LEVEL_VERIFIED", "A_fragments_7001": case_a(inp, out),
           "B_heal_u2": case_b(inp, out, Path(__file__).with_name("editor_poc") / "poc0_u2_B2c.json")}
    res["inputs_unchanged"] = all(sha256(inp / k) == v for k, v in h0.items()); res["outputs_sha256"] = {f.name: sha256(f) for f in sorted(out.glob("*.gpkg"))}
    json.dump(res, open(js, "w"), indent=1, default=str); print(json.dumps(res, indent=1, default=str)[:4000])


if __name__ == "__main__":
    main(*sys.argv[1:4])
