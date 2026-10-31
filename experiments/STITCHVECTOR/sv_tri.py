"""Line-error triage (rules: sv_tri_rules.json). Read-only diagnosis of the frozen M0 (B2c) and M2 (sv_pa, 1fee542) on
already-viewed data. Nothing is tuned; no method is changed. Usage: sv_tri.py <json_out> <img_dir> [--smoke]   (.venv-sv)"""
import json, sys, collections
from pathlib import Path
import numpy as np, shapely, geopandas as gpd
from shapely.geometry import LineString, Polygon, box
from scipy import ndimage as ndi
from scipy.spatial import cKDTree
from skimage.filters import apply_hysteresis_threshold
from PIL import Image, ImageDraw
import sv_synth as S, sv_b2c_scenes as SC, sv_autoline as AL, sv_ld_fix as F, sv_ld_stages as LS, sv_ld_compare as CMP
import sv_pa as PA, sv_b2b as BB, sv_b2c as C, sv_v3 as V, sv_g3 as G, sv_lf as LF, sv_oracle as O, sv_oracle_v2 as O2, sv_common as Cm

HERE = Path(__file__).resolve().parent
RULES = json.load(open(HERE / "sv_tri_rules.json"))
TOL = 2.0
MISS_CLASSES = ["found_off_or_not_credited", "no_candidate", "luminance_removed", "protected_no_grey", "skeleton_join_minlen",
                "drawn_cut_by_overlap", "other"]


def U(gs): gs = [g for g in gs if g is not None and not g.is_empty]; return shapely.union_all(gs) if gs else None


def dist(pts, u): return shapely.distance(pts, u) if u is not None else np.full(len(pts), 1e9)


def ds(dt, xy):
    x = np.clip(xy[:, 0].astype(int), 0, dt.shape[1] - 1); y = np.clip(xy[:, 1].astype(int), 0, dt.shape[0] - 1); return dt[y, x]


def stage_masks(a):
    edt = lambda m: ndi.distance_transform_edt(~m) if m.any() else np.full(m.shape, 1e9)
    lab_c = AL.contrast(a, PA.Q["bg_median"]); grey_c = PA.grey_contrast(a, PA.Q["bg_median"]); prot = PA.protected(a)
    lab = apply_hysteresis_threshold(lab_c, PA.Q["lab_lo"], PA.Q["lab_hi"]); grey = apply_hysteresis_threshold(grey_c, PA.Q["grey_lo"], PA.Q["grey_hi"])
    return {"d_lab": edt(lab), "d_lab_unprot": edt(lab & ~prot), "d_grey": edt(grey)}


def methods(a):
    base = C.b2c(a)[0]; m2, info = PA.run(a, "M2"); grey_drawn, _ = F._pipeline(a, PA.candidates(a, "M2"), AL.P)
    return {"base": base, "m2": m2, "info": info, "grey_drawn": grey_drawn,
            "rej": [s["geom"] for s in info["segments"] if not s["kept"]], "acc": [s["geom"] for s in info["segments"] if s["kept"]]}


def attribute(a, truthL, key_of, M, mk):
    """per truth visible sample: hit by M0 / M2 (owner-credited), and for M2 misses the first failing stage."""
    own = owner(truthL, a.shape[:2]); out = collections.defaultdict(collections.Counter); gaps = collections.defaultdict(list)
    Ub, Um, Ug, Ur = U([o["geom"] for o in M["base"]]), U([o["geom"] for o in M["m2"]]), U([o["geom"] for o in M["grey_drawn"]]), U(M["rej"])
    for li, t in enumerate(truthL["lines"]):
        g = LineString(t["axis"]); pts = shapely.line_interpolate_point(g, np.linspace(0, g.length, int(g.length) + 1)); xy = shapely.get_coordinates(pts)
        vis = ~LS.occluded(truthL, li, pts); h2 = CMP.visible_recall(M["m2"], truthL, own, li, pts, vis); h0 = CMP.visible_recall(M["base"], truthL, own, li, pts, vis)
        w = float(np.median(t["width"])); r = w / 2 + 1.0; k = key_of(t); c = out[k]
        c["visible"] += int(vis.sum()); c["hit_M0"] += int((h0 & vis).sum()); c["hit_M2"] += int((h2 & vis).sum())
        dl, dg, dlu = ds(mk["d_lab"], xy) <= r, ds(mk["d_grey"], xy) <= r, ds(mk["d_lab_unprot"], xy) <= r
        near4, rej2, gdr, bdr = dist(pts, Um) <= 4, dist(pts, Ur) <= TOL, dist(pts, Ug) <= TOL, dist(pts, Ub) <= TOL
        cls = np.select([near4, ~dl & ~dg, rej2, dl & ~dlu & ~dg, (dg & ~gdr) | (dlu & ~bdr & ~dg), gdr], MISS_CLASSES[:-1], "other")
        miss = vis & ~h2
        for cl in cls[miss]: c[cl] += 1
        m = np.r_[0, miss.astype(int), 0]; d = np.diff(m); runs = np.nonzero(d == -1)[0] - np.nonzero(d == 1)[0]; gaps[k] += [int(x) for x in runs if x >= 10]
    res = {}
    for k, c in out.items():
        miss = c["visible"] - c["hit_M2"]
        res[k] = {"visible": c["visible"], "recall_M0": c["hit_M0"] / max(c["visible"], 1), "recall_M2": c["hit_M2"] / max(c["visible"], 1), "missed_M2": miss,
                  "miss_by_stage": {cl: c[cl] for cl in MISS_CLASSES}, "miss_share_by_stage": {cl: c[cl] / max(miss, 1) for cl in MISS_CLASSES},
                  "gaps_ge10_M2": len(gaps[k]), "gap_px_ge10_M2": int(sum(gaps[k]))}
    return res


def owner(truthL, shape):
    """sv_ld_stages.owner_map, with a single-line fallback (that helper needs >= 2 lines)."""
    if len(truthL["lines"]) >= 2: return LS.owner_map(truthL, shape)[0]
    return np.zeros(shape, np.int64)


def face_cache(a):
    X, _ = LF.labels(a); fc = O.faces(X, 0); Fg = gpd.GeoDataFrame(geometry=fc["polys"]); H, W = a.shape[:2]
    FI, _ = G.out_geometry(Fg, None, box(0, 0, W, H).boundary.buffer(0.6)); return FI, G.face_id_raster(Fg, (H, W)), Fg


def band_decomp(a, bands, inks, objs, fcache):
    """line length inside each band zone (band + 1.5 px), legal ink (truth ink + 2 px) excluded, split into centreline /
    side edge / crossing / other; reusable axis share; whether F0 face edges still outline the band; groups leaving the band."""
    ink_zone = U([LineString(x["axis"]).buffer(float(np.median(x["width"])) / 2 + 2) for x in inks]); groups = V.group(a, objs)[0] if objs else []
    LP, LT = G.sample([o["geom"] for o in objs], 0.5) if objs else (np.zeros((0, 2)), np.zeros((0, 2))); LI = G.Index(LP, LT)
    FI, fid, Fg = fcache; empty = G.Index(np.zeros((0, 2)), np.zeros((0, 2))); res = {}
    for b in bands:
        g, w = b["axis"], b["width"]; zone = g.buffer(w / 2 + 1.5); AP, AT = G._s(g, 0.5); tree = cKDTree(AP); cnt = collections.Counter()
        for o in objs:
            part = shapely.intersection(o["geom"], zone)
            if ink_zone is not None: part = shapely.difference(part, ink_zone)
            if part.is_empty or part.length < 0.5: continue
            P, T = G.sample([part], 0.5)
            if not len(P): continue
            d, idx = tree.query(P); ok = np.abs((AT[idx] * T).sum(1)) >= G.COS
            centre = (d <= 1.5) & ok; side = ~centre & (np.abs(d - w / 2) <= 1.0) & ok; cross = ~ok
            cnt["centreline"] += centre.sum() * 0.5; cnt["side_edge"] += side.sum() * 0.5; cnt["crossing_non_ink"] += cross.sum() * 0.5
            cnt["other"] += (~centre & ~side & ~cross).sum() * 0.5
        P, T = G.truth_samples(g); vis = np.ones(len(P), bool); reuse = float(G.runs_ok(LI.match(P, T), vis).mean())
        bf = G.band_faces(Fg, g, w); _, fcl, _ = G.classify_band(g, w, vis, FI, empty, fid, bf)
        span = mixink = 0
        for gr in groups:
            if shapely.intersection(gr["geom"], zone).length < 10: continue
            outside = shapely.difference(gr["geom"], zone.buffer(1.0))
            span += outside.length >= 10
            if ink_zone is not None and shapely.intersection(outside, ink_zone).length >= 10: mixink += 1
        res[b["id"]] = {"width": w, "axis_length": float(g.length), "line_px_in_band_by_class": {k: float(v) for k, v in cnt.items()},
                        "line_px_in_band": float(sum(cnt.values())), "axis_reusable_centreline_share": reuse,
                        "F0_face_outline_share": float((fcl == "face_ok").mean()), "F0_band_faces": len(bf),
                        "groups_in_band_extending_outside": int(span), "groups_in_band_also_running_along_ink": int(mixink)}
    return res


def added_classes(segments, labeller):
    out = collections.defaultdict(float)
    for s in segments:
        if s["kept"]: out[labeller(s["geom"])] += s["geom"].length
    return dict(out)


def synth_case(seed):
    a, truth, faces = S.generate(seed); tl = {"lines": [{"id": t["id"], "axis": t["axis"], "width": t["width"]} for t in truth["lines"]]}
    bands = [{"id": b["id"], "axis": LineString(b["axis"]), "width": b["width"]} for b in truth["bands"]]
    return a, tl, bands, list(faces.values()), truth, lambda t: LS.TYPES.get(t["id"], "red_black")


def scene_case(seed, kind):
    a, t = SC.scene(kind, seed); tl = {"lines": [{"id": x["id"], "axis": x["axis"], "width": [x["width"]], "sub": x["sub"]} for x in t["ink"]]}
    bands = [{"id": b["id"], "axis": LineString(b["axis"]), "width": b["width"]} for b in t["bands"]]
    return a, tl, bands, t, (lambda x: x["sub"])


def merge_attr(acc, r):
    for k, v in r.items():
        x = acc.setdefault(k, {"visible": 0, "hit_M0": 0, "hit_M2": 0, "missed_M2": 0, "miss_by_stage": collections.Counter(), "gaps_ge10_M2": 0, "gap_px_ge10_M2": 0})
        x["visible"] += v["visible"]; x["hit_M0"] += round(v["recall_M0"] * v["visible"]); x["hit_M2"] += round(v["recall_M2"] * v["visible"]); x["missed_M2"] += v["missed_M2"]
        x["miss_by_stage"].update(v["miss_by_stage"]); x["gaps_ge10_M2"] += v["gaps_ge10_M2"]; x["gap_px_ge10_M2"] += v["gap_px_ge10_M2"]


def finish_attr(acc):
    return {k: {"visible": x["visible"], "recall_M0": x["hit_M0"] / max(x["visible"], 1), "recall_M2": x["hit_M2"] / max(x["visible"], 1), "missed_M2": x["missed_M2"],
                "miss_share_by_stage": {cl: x["miss_by_stage"][cl] / max(x["missed_M2"], 1) for cl in MISS_CLASSES}, "miss_px_by_stage": dict(x["miss_by_stage"]),
                "gaps_ge10_M2": x["gaps_ge10_M2"], "gap_px_ge10_M2": x["gap_px_ge10_M2"]} for k, x in sorted(acc.items())}


def sum_bands(per):
    tot = collections.Counter(); n = 0; reuse = []; face = []; span = mix = 0
    for v in per.values():
        tot.update(v["line_px_in_band_by_class"]); n += 1; reuse.append(v["axis_reusable_centreline_share"]); face.append(v["F0_face_outline_share"])
        span += v["groups_in_band_extending_outside"]; mix += v["groups_in_band_also_running_along_ink"]
    return {"bands": n, "line_px_in_band_by_class": dict(tot), "line_px_in_band": float(sum(tot.values())), "mean_axis_reusable_centreline_share": float(np.mean(reuse)) if reuse else None,
            "mean_F0_face_outline_share": float(np.mean(face)) if face else None, "groups_extending_outside": span, "groups_also_along_ink": mix}


def u2_part(img_dir):
    a, _ = Cm.centre_crop(Cm.load("u2"), 300, 300); P = dict(O.P); P.update(O2.PRE["params"]); ol, _ = O2.build(a, P)
    tl = {"lines": [{"id": f["id"], "axis": f["raw"], "width": [f["width"]], "kind": f["kind"]} for f in ol if len(f["raw"]) >= 2]}
    bands = [{"id": q["id"], "axis": LineString(q["axis"]), "width": 2 * q["radius"]} for q in O2.ORA["protected"]]
    M = methods(a); mk = stage_masks(a); fcache = face_cache(a)
    key = lambda t: t["id"] if t["id"] in ("G1", "G2", "G3") else ("red_tooth" if t["kind"] == "red_tooth" else "red_other")
    res = {"miss_attribution": attribute(a, tl, key, M, mk), "bands_M0": band_decomp(a, bands, tl["lines"], M["base"], fcache),
           "bands_M2": band_decomp(a, bands, tl["lines"], M["m2"], fcache)}
    T = U([LineString(x["axis"]) for x in tl["lines"]]).buffer(3.0); Lstar = AL.lab(a)[..., 0]; comp, _ = ndi.label(Lstar < 50); sizes = np.bincount(comp.ravel())
    FI = fcache[0]; far = []; added = M["m2"][len(M["base"]):]
    for o in added:
        part = shapely.difference(o["geom"], T)
        for q in shapely.get_parts(part):
            if q.geom_type != "LineString" or q.length < 2: continue
            m = O.rmask(q.buffer(2.0), a.shape[:2]); ids = np.unique(comp[m]); ids = ids[ids > 0]; big = int(sizes[ids].max()) if len(ids) else 0
            Pq, Tq = G.sample([q], 0.5); along = float(FI.match(Pq, Tq).mean()) if len(Pq) else 0.0
            cx, cy = np.asarray(q.interpolate(0.5, normalized=True).coords[0])
            far.append({"length": float(q.length), "centre_xy": [round(float(cx), 1), round(float(cy), 1)], "in_map": bool(cx < 94),
                        "dark_component_px_within_2px": big, "F0_face_edge_match_share": along,
                        "class": "near_dark_ink" if big >= 10 else ("along_face_boundary" if along >= 0.6 else "unexplained"), "_geom": q})
    tiles = []
    for f in far:
        cx, cy = f["centre_xy"]; x0, y0 = int(np.clip(cx - 15, 0, 270)), int(np.clip(cy - 15, 0, 270)); k = 8
        im = Image.fromarray(np.kron(a[y0:y0 + 30, x0:x0 + 30], np.ones((k, k, 1), np.uint8))); d = ImageDraw.Draw(im)
        for x in tl["lines"]:
            c = np.asarray(x["axis"]); d.line([((p[0] - x0) * k, (p[1] - y0) * k) for p in c], fill=(0, 170, 0), width=1)
        d.line([((p[0] - x0) * k, (p[1] - y0) * k) for p in f["_geom"].coords], fill=(230, 0, 230), width=3)
        d.rectangle([0, 0, 240, 14], fill="white"); d.text((2, 1), f"{f['class']} {f['length']:.0f}px", fill="black"); tiles.append(np.asarray(im))
    if tiles:
        cols = 6; rows = [np.hstack(tiles[i:i + cols] + [np.full_like(tiles[0], 255)] * (cols - len(tiles[i:i + cols]))) for i in range(0, len(tiles), cols)]
        Image.fromarray(np.vstack(rows)).save(Path(img_dir) / "u2_M2_far_segments_x8.png")
    for f in far: f.pop("_geom")
    cls = collections.defaultdict(float)
    for f in far:
        if f["in_map"]: cls[f["class"]] += f["length"]
    res["M2_added_far_from_oracle"] = {"segments": far, "length_in_map_by_class": dict(cls)}
    return res


def main(out, img_dir, smoke=False):
    Path(img_dir).mkdir(parents=True, exist_ok=True); seeds = RULES["data"]["dev_smoke" if smoke else "target"]
    res = {"rules": "sv_tri_rules.json", "smoke": smoke}; A_syn, A_scn = {}, {}; band_syn = {"M0": {}, "M2": {}}; band_scn = {"M0": {}, "M2": {}}
    add_syn = collections.Counter(); add_scn = collections.Counter(); pale_add = collections.Counter()
    for s in seeds["sv_synth"]:
        a, tl, bands, polys, truth, key = synth_case(s); M = methods(a); mk = stage_masks(a); fc = face_cache(a)
        merge_attr(A_syn, attribute(a, tl, key, M, mk))
        for m, objs in (("M0", M["base"]), ("M2", M["m2"])):
            for bid, v in band_decomp(a, bands, tl["lines"], objs, fc).items(): band_syn[m][f"{s}:{bid}"] = v
        pale = LineString([t for t in truth["lines"] if t["id"] == "pale_1"][0]["axis"]).buffer(TOL)
        for sg in M["info"]["segments"]:
            if not sg["kept"]: continue
            lab, _ = BB.label(sg["geom"], truth, polys, truth["bands"]); add_syn[lab] += sg["geom"].length; pale_add["synthetic_pale_px"] += shapely.intersection(sg["geom"], pale).length
    for s in seeds["scenes"]:
        for kind in RULES["scene_kinds"]:
            a, tl, bands, t, key = scene_case(s, kind); M = methods(a); mk = stage_masks(a)
            if tl["lines"]: merge_attr(A_scn, attribute(a, tl, key, M, mk))
            if bands:
                fc = face_cache(a)
                for m, objs in (("M0", M["base"]), ("M2", M["m2"])):
                    for bid, v in band_decomp(a, bands, tl["lines"], objs, fc).items(): band_scn[m][f"{s}_{kind}:{bid}"] = v
            for sg in M["info"]["segments"]:
                if not sg["kept"]: continue
                lab, _, sub = C.label_scene(sg["geom"], t); add_scn[f"{lab}:{sub}" if sub else lab] += sg["geom"].length
    res["miss_attribution"] = {"synthetic": finish_attr(A_syn), "scenes": finish_attr(A_scn)}
    res["bands"] = {"synthetic": {m: {"per_band": v, "total": sum_bands(v)} for m, v in band_syn.items()},
                    "scenes": {m: {"per_band": v, "total": sum_bands(v)} for m, v in band_scn.items()}}
    res["M2_added_kept_length_by_truth_label"] = {"synthetic": dict(add_syn), "scenes": dict(add_scn), "synthetic_pale_effective_px": pale_add["synthetic_pale_px"]}
    if not smoke: res["u2"] = u2_part(img_dir)
    json.dump(res, open(out, "w"), indent=1, default=float)
    for part in ("synthetic", "scenes"):
        for k, v in res["miss_attribution"][part].items():
            print(part, k.ljust(30), "vis", v["visible"], "M0 %.3f M2 %.3f" % (v["recall_M0"], v["recall_M2"]), {c: round(x, 2) for c, x in v["miss_share_by_stage"].items() if x > 0})
        for m in ("M0", "M2"): print(part, "bands", m, {k: (round(v, 1) if isinstance(v, float) else v) for k, v in res["bands"][part][m]["total"].items()})
    print("added", {k: {a_: round(b, 1) for a_, b in v.items()} if isinstance(v, dict) else round(v, 1) for k, v in res["M2_added_kept_length_by_truth_label"].items()})


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], "--smoke" in sys.argv)
