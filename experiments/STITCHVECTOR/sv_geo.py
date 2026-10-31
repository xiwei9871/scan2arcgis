"""Near-miss geometry attribution (rules: sv_geo_rules.json). Read-only diagnosis of the frozen M2 (sv_pa, 1fee542) on
already-viewed data. Re-derives the sv_tri (1823cb9) per-sample miss classes exactly, then splits
  'found_off_or_not_credited' (an M2 line within 4 px, not credited)  into A-E, and
  'skeleton_join_minlen'                                            into pipeline sub-stages.
Nothing is tuned; no method is changed. Usage: sv_geo.py <json_out> <img_dir> [--smoke]   (.venv-sv)"""
import json, sys, collections
from pathlib import Path
import numpy as np, shapely, cv2
from shapely.geometry import LineString, Polygon
from scipy import ndimage as ndi
from scipy.spatial import cKDTree
from skimage.morphology import skeletonize
from PIL import Image, ImageDraw
import sv_tri as T, sv_autoline as AL, sv_ld_fix as F, sv_ld_stages as LS, sv_ld_compare as CMP, sv_pa as PA, sv_d71 as D
import sv_g3 as G, sv_common as Cm, sv_oracle as O, sv_oracle_v2 as O2

HERE = Path(__file__).resolve().parent
RULES = json.load(open(HERE / "sv_geo_rules.json"))
COS = np.cos(np.radians(30.0)); D_CROSS = 3.0
NEAR_CLASSES = ["D_crossing_or_overlap", "A_scoring_attribution", "B_offset_2_3px", "B_offset_3_4px",
                "C_other_ink_line", "C_band", "C_fill_edge", "C_other_object", "E_uncertain"]
SKEL_CLASSES = ["lab_only_signal", "isolated_candidate_pixels", "no_skeleton_nearby", "spur_removed", "min_len_removed", "smoothing_or_simplify_shift"]


def tangents(g, s):
    L = g.length; a = shapely.get_coordinates(shapely.line_interpolate_point(g, np.clip(s - 0.75, 0, L)))
    b = shapely.get_coordinates(shapely.line_interpolate_point(g, np.clip(s + 0.75, 0, L))); t = b - a
    return t / np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-9)


def out_samples(objs):
    P, Tg, oid = [], [], []
    for i, o in enumerate(objs):
        for part in shapely.get_parts(o["geom"]):
            if part.geom_type != "LineString" or part.length == 0: continue
            p, t = G._s(part, 0.5); P.append(p); Tg.append(t); oid.append(np.full(len(p), i))
    if not P: return np.zeros((0, 2)), np.zeros((0, 2)), np.zeros(0, int)
    return np.vstack(P), np.vstack(Tg), np.concatenate(oid)


def pipeline_parts(a):
    """grey M2 candidate mask -> skeleton, chains kept after spur removal, and the short groups 2.0 drops (< min_len)."""
    ink = PA.candidates(a, "M2"); p = AL.P; sk = skeletonize(ink)
    chains, _ = D.skeleton_chains(sk); chains = [np.array(c, float) for c in chains if len(c) >= 2]
    deg = {}
    for c in chains:
        for e in (tuple(c[0]), tuple(c[-1])): deg[e] = deg.get(e, 0) + 1
    kept = [c for c in chains if not ((deg[tuple(c[0])] == 1) != (deg[tuple(c[-1])] == 1) and len(c) < p["spur"])]
    drawn, short = F._pipeline(a, ink, p)
    km = np.zeros(ink.shape, bool)
    for c in kept: km[c[:, 0].astype(int), c[:, 1].astype(int)] = True
    lab, n = ndi.label(ink, np.ones((3, 3))); sizes = np.bincount(lab.ravel())
    edt = lambda m: ndi.distance_transform_edt(~m) if m.any() else np.full(m.shape, 1e9)
    return {"cand": ink, "comp": lab, "comp_size": sizes, "d_skel": edt(sk), "d_kept": edt(km), "short": T.U([s["geom"] for s in short])}


def analyse(a, tl, key_of, bands, fill_lines, tag):
    """returns per-sample records for all visible truth samples, reproducing sv_tri.attribute exactly."""
    M = T.methods(a); mk = T.stage_masks(a); own = T.owner(tl, a.shape[:2]); pp = pipeline_parts(a)
    Ub, Um, Ug, Ur = T.U([o["geom"] for o in M["base"]]), T.U([o["geom"] for o in M["m2"]]), T.U([o["geom"] for o in M["grey_drawn"]]), T.U(M["rej"])
    OP, OT, OI = out_samples(M["m2"]); tree = cKDTree(OP) if len(OP) else None
    axes = [LineString(t["axis"]) for t in tl["lines"]]
    od = np.stack([shapely.distance(shapely.points(OP), g) for g in axes], 1) if len(OP) else np.zeros((0, len(axes)))
    o_near = od.argmin(1) if len(OP) else np.zeros(0, int); o_near_d = od.min(1) if len(OP) else np.zeros(0)
    Bz = T.U([b["axis"].buffer(b["width"] / 2 + 2) for b in bands]); Ez = T.U([g.buffer(2.5) for g in fill_lines])
    o_band = shapely.contains_xy(Bz, OP[:, 0], OP[:, 1]) if (Bz is not None and len(OP)) else np.zeros(len(OP), bool)
    o_edge = shapely.contains_xy(Ez, OP[:, 0], OP[:, 1]) if (Ez is not None and len(OP)) else np.zeros(len(OP), bool)
    recs = []
    for li, t in enumerate(tl["lines"]):
        g = axes[li]; s = np.linspace(0, g.length, int(g.length) + 1); pts = shapely.line_interpolate_point(g, s); xy = shapely.get_coordinates(pts); tt = tangents(g, s)
        vis = ~LS.occluded(tl, li, pts); h2 = CMP.visible_recall(M["m2"], tl, own, li, pts, vis)
        w = float(np.median(t["width"])); r = w / 2 + 1.0
        dl, dg, dlu = T.ds(mk["d_lab"], xy) <= r, T.ds(mk["d_grey"], xy) <= r, T.ds(mk["d_lab_unprot"], xy) <= r
        near4, rej2, gdr, bdr = T.dist(pts, Um) <= 4, T.dist(pts, Ur) <= T.TOL, T.dist(pts, Ug) <= T.TOL, T.dist(pts, Ub) <= T.TOL
        cls = np.select([near4, ~dl & ~dg, rej2, dl & ~dlu & ~dg, (dg & ~gdr) | (dlu & ~bdr & ~dg), gdr], T.MISS_CLASSES[:-1], "other")
        others = [axes[j] for j in range(len(axes)) if j != li]
        d_other = np.min(np.stack([shapely.distance(pts, x) for x in others]), 0) if others else np.full(len(pts), 1e9)
        best = {2: np.zeros(len(pts), bool), 3: np.zeros(len(pts), bool), 4: np.zeros(len(pts), bool)}
        for k in range(len(pts)):
            sub = None
            if tree is not None:
                nb = tree.query_ball_point(xy[k], 4.0)
                if nb:
                    nb = np.array(nb); d = np.linalg.norm(OP[nb] - xy[k], axis=1); al = np.abs(OT[nb] @ tt[k]) >= COS
                    same = (o_near[nb] == li) & al
                    if same.any():
                        dm = d[same].min()
                        for c in (2, 3, 4): best[c][k] = dm <= c
            rec = {"tag": tag, "line": t["id"], "type": key_of(t), "i": k, "xy": xy[k], "visible": bool(vis[k]), "hit": bool(h2[k]), "cls": str(cls[k]),
                   "d_other_axis": float(d_other[k])}
            if vis[k] and not h2[k] and cls[k] == "found_off_or_not_credited":
                nb = np.array(tree.query_ball_point(xy[k], 4.0)) if tree is not None else np.array([], int)
                if len(nb) == 0: sub = "E_uncertain"
                else:
                    d = np.linalg.norm(OP[nb] - xy[k], axis=1); al = np.abs(OT[nb] @ tt[k]) >= COS; same = (o_near[nb] == li) & al
                    if d_other[k] <= D_CROSS: sub = "D_crossing_or_overlap"
                    elif same.any():
                        dm = d[same].min(); sub = "A_scoring_attribution" if dm <= 2.0 else ("B_offset_2_3px" if dm <= 3.0 else "B_offset_3_4px")
                    else:
                        q = nb[np.argmin(d)]
                        if o_near[q] != li and o_near_d[q] <= 3.0: sub = "C_other_ink_line"
                        elif o_band[q]: sub = "C_band"
                        elif o_edge[q]: sub = "C_fill_edge"
                        elif o_near[q] == li: sub = "E_uncertain"
                        else: sub = "C_other_object"
                rec["near_sub"] = sub
            if vis[k] and not h2[k] and cls[k] == "skeleton_join_minlen":
                x, y = int(np.clip(xy[k][0], 0, a.shape[1] - 1)), int(np.clip(xy[k][1], 0, a.shape[0] - 1))
                if not dg[k]: sub = "lab_only_signal"
                else:
                    R = int(np.ceil(r)); win = pp["comp"][max(0, y - R):y + R + 1, max(0, x - R):x + R + 1]; ids = np.unique(win[win > 0])
                    big = int(pp["comp_size"][ids].max()) if len(ids) else 0; rec["cand_component_px"] = big
                    if big < 10: sub = "isolated_candidate_pixels"
                    elif pp["d_skel"][y, x] > 2.0: sub = "no_skeleton_nearby"
                    elif pp["d_kept"][y, x] > 2.0: sub = "spur_removed"
                    elif pp["short"] is not None and shapely.distance(pts[k], pp["short"]) <= 2.0: sub = "min_len_removed"
                    else: sub = "smoothing_or_simplify_shift"
                rec["skel_sub"] = sub
            recs.append(rec)
        for k in range(len(pts)):
            recs[-len(pts) + k]["same_line_aligned_within"] = {c: bool(best[c][k]) for c in (2, 3, 4)}
    return recs, M


def runs_of(recs, key, val):
    """lengths of consecutive runs (per line) of samples whose recs[key] == val."""
    out = []; cur = 0; prev = None
    for r in recs:
        if prev is not None and (r["tag"], r["line"]) != prev: out += [cur] if cur else []; cur = 0
        if r.get(key) == val: cur += 1
        else:
            if cur: out.append(cur)
            cur = 0
        prev = (r["tag"], r["line"])
    if cur: out.append(cur)
    return out


def summarise(recs):
    by = collections.defaultdict(list)
    for r in recs:
        if r["visible"]: by[r["type"]].append(r)
    by["ALL"] = [r for r in recs if r["visible"]]; res = {}
    for k, v in by.items():
        n = len(v); hit = sum(r["hit"] for r in v); near = [r for r in v if not r["hit"] and r["cls"] == "found_off_or_not_credited"]
        skel = [r for r in v if not r["hit"] and r["cls"] == "skeleton_join_minlen"]
        nc = collections.Counter(r["near_sub"] for r in near); sc = collections.Counter(r["skel_sub"] for r in skel)
        A = nc["A_scoring_attribution"]
        res[k] = {"visible": n, "recall_owner_credited_2px": hit / max(n, 1), "recall_attribution_corrected_2px": (hit + A) / max(n, 1),
                  "recall_same_line_aligned": {f"{c}px": sum(r["same_line_aligned_within"][c] for r in v) / max(n, 1) for c in (2, 3, 4)},
                  "recall_owner_or_same_line_aligned": {f"{c}px": sum(r["hit"] or r["same_line_aligned_within"][c] for r in v) / max(n, 1) for c in (2, 3, 4)},
                  "missed": n - hit, "near_missed": len(near), "near_by_class": {c: nc[c] for c in NEAR_CLASSES},
                  "skeleton_missed": len(skel), "skeleton_by_class": {c: sc[c] for c in SKEL_CLASSES},
                  "miss_by_tri_class": dict(collections.Counter(r["cls"] for r in v if not r["hit"]))}
    return res


def per_seed(recs):
    out = {}
    for tag in sorted({r["tag"] for r in recs}):
        v = [r for r in recs if r["tag"] == tag and r["visible"]]; n = len(v); hit = sum(r["hit"] for r in v)
        A = sum(1 for r in v if r.get("near_sub") == "A_scoring_attribution")
        out[tag] = {"visible": n, "recall_owner_credited_2px": hit / max(n, 1), "recall_attribution_corrected_2px": (hit + A) / max(n, 1),
                    "near_by_class": dict(collections.Counter(r["near_sub"] for r in v if r.get("near_sub"))),
                    "skeleton_by_class": dict(collections.Counter(r["skel_sub"] for r in v if r.get("skel_sub")))}
    return out


def skel_runs(recs):
    g = collections.defaultdict(list)
    for sub in SKEL_CLASSES:
        rs = runs_of(recs, "skel_sub", sub); g[sub] = {"runs": len(rs), "runs_ge5px": sum(x >= 5 for x in rs), "px_in_runs_ge5": int(sum(x for x in rs if x >= 5)), "max_run": max(rs) if rs else 0}
    return dict(g)


COL = {"A_scoring_attribution": (0, 170, 0), "B_offset_2_3px": (255, 150, 0), "B_offset_3_4px": (230, 90, 0), "C_other_ink_line": (230, 0, 0),
       "C_band": (150, 0, 200), "C_fill_edge": (230, 0, 230), "C_other_object": (120, 60, 0), "D_crossing_or_overlap": (0, 150, 220), "E_uncertain": (90, 90, 90)}


def evidence(a, recs, M, axes, tag, img_dir, per_class=3):
    tiles = []; seen = collections.Counter()
    for r in recs:
        sub = r.get("near_sub")
        if not sub or seen[sub] >= per_class or r["i"] % 7: continue
        seen[sub] += 1; cx, cy = r["xy"]; x0, y0 = int(np.clip(cx - 20, 0, a.shape[1] - 40)), int(np.clip(cy - 20, 0, a.shape[0] - 40)); k = 6
        im = Image.fromarray(np.kron(a[y0:y0 + 40, x0:x0 + 40], np.ones((k, k, 1), np.uint8))); d = ImageDraw.Draw(im)
        for g in axes: d.line([((p[0] - x0) * k, (p[1] - y0) * k) for p in g.coords], fill=(0, 200, 0), width=1)
        for o in M["m2"]:
            for q in shapely.get_parts(o["geom"]): d.line([((p[0] - x0) * k, (p[1] - y0) * k) for p in q.coords], fill=(0, 90, 255), width=2)
        for rr in recs:
            if rr["tag"] == r["tag"] and rr.get("near_sub") and x0 <= rr["xy"][0] < x0 + 40 and y0 <= rr["xy"][1] < y0 + 40:
                px, py = (rr["xy"][0] - x0) * k, (rr["xy"][1] - y0) * k; d.ellipse([px - 3, py - 3, px + 3, py + 3], fill=COL[rr["near_sub"]])
        d.rectangle([0, 0, 240, 14], fill="white"); d.text((2, 1), f"{tag} {r['line']} {sub}", fill="black"); tiles.append(np.asarray(im))
    return tiles


def save_sheet(tiles, path, cols=6):
    if not tiles: return
    rows = [np.hstack(tiles[i:i + cols] + [np.full_like(tiles[0], 255)] * (cols - len(tiles[i:i + cols]))) for i in range(0, len(tiles), cols)]
    Image.fromarray(np.vstack(rows)).save(path)


def main(out, img_dir, smoke=False):
    Path(img_dir).mkdir(parents=True, exist_ok=True); sel = RULES["data"]["dev_smoke" if smoke else "target"]
    res = {"rules": "sv_geo_rules.json", "smoke": smoke}; syn, scn = [], []; tiles_syn, tiles_scn = [], []
    for s in sel["sv_synth"]:
        a, tl, bands, polys, truth, key = T.synth_case(s)
        recs, M = analyse(a, tl, key, bands, [Polygon(p).exterior for p in polys], str(s)); syn += recs
        tiles_syn += evidence(a, recs, M, [LineString(x["axis"]) for x in tl["lines"]], str(s), img_dir)
    for s in sel["scenes"]:
        for kind in RULES["scene_kinds"]:
            a, tl, bands, t, key = T.scene_case(s, kind)
            if not tl["lines"]: continue
            edges = [LineString(e["axis"]) for e in t["edges"] if not e["covered_by_ink"]]
            recs, M = analyse(a, tl, key, bands, edges, f"{s}_{kind}"); scn += recs
            tiles_scn += evidence(a, recs, M, [LineString(x["axis"]) for x in tl["lines"]], f"{s}_{kind}", img_dir, per_class=1)
    res["synthetic"] = {"summary": summarise(syn), "per_seed": per_seed(syn), "skeleton_runs": skel_runs(syn)}
    res["scenes"] = {"summary": summarise(scn), "per_seed": per_seed(scn), "skeleton_runs": skel_runs(scn)}
    save_sheet(tiles_syn, Path(img_dir) / ("geo_smoke_synthetic.png" if smoke else "geo_synthetic_evidence_x6.png"))
    save_sheet(tiles_scn, Path(img_dir) / ("geo_smoke_scenes.png" if smoke else "geo_scenes_evidence_x6.png"))
    if not smoke:
        tri = json.load(open(HERE / "protabl_triage/tri_result.json"))
        res["reproduces_sv_tri"] = {part: {k: {"tri_missed": v["missed_M2"], "here_missed": res[part]["summary"].get(k, {}).get("missed"),
                                               "tri_found_off": v["miss_px_by_stage"].get("found_off_or_not_credited", 0), "here_found_off": res[part]["summary"].get(k, {}).get("near_missed"),
                                               "tri_skeleton": v["miss_px_by_stage"].get("skeleton_join_minlen", 0), "here_skeleton": res[part]["summary"].get(k, {}).get("skeleton_missed")}
                                           for k, v in tri["miss_attribution"][part].items()} for part in ("synthetic", "scenes")}
        a, _ = Cm.centre_crop(Cm.load("u2"), 300, 300); P = dict(O.P); P.update(O2.PRE["params"]); ol, _ = O2.build(a, P)
        tl = {"lines": [{"id": f["id"], "axis": f["raw"], "width": [f["width"]], "kind": f["kind"]} for f in ol if len(f["raw"]) >= 2]}
        bands = [{"id": q["id"], "axis": LineString(q["axis"]), "width": 2 * q["radius"]} for q in O2.ORA["protected"]]
        key = lambda t: t["id"] if t["id"] in ("G1", "G2", "G3") else ("red_tooth" if t["kind"] == "red_tooth" else ("red_curve" if t["id"] == "LOOP" else "red_fault_or_line"))
        recs, M = analyse(a, tl, key, bands, [], "u2")
        res["u2"] = {"summary": summarise(recs), "skeleton_runs": skel_runs(recs),
                     "near_misses_close_to_PN1_PN2": sum(1 for r in recs if r.get("near_sub") and min(shapely.distance(shapely.Point(r["xy"]), b["axis"]) for b in bands) <= 4)}
        save_sheet(evidence(a, recs, M, [LineString(x["axis"]) for x in tl["lines"]], "u2", img_dir, per_class=4), Path(img_dir) / "geo_u2_evidence_x6.png")
    json.dump(res, open(out, "w"), indent=1, default=float)
    for part in ("synthetic", "scenes", "u2"):
        if part not in res: continue
        for k, v in res[part]["summary"].items():
            print(part[:3], k[:24].ljust(24), "vis", v["visible"], "own2 %.3f corr2 %.3f same2/3/4 %s" % (v["recall_owner_credited_2px"], v["recall_attribution_corrected_2px"],
                  "/".join(f"{x:.3f}" for x in v["recall_same_line_aligned"].values())), "near", v["near_missed"], {c[:6]: n for c, n in v["near_by_class"].items() if n},
                  "skel", v["skeleton_missed"], {c[:8]: n for c, n in v["skeleton_by_class"].items() if n})


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], "--smoke" in sys.argv)
