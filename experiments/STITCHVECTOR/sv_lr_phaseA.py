"""Line recovery Phase A: visual vs data failure attribution on the FROZEN P1 test tiles (seeds 2001-2005, code 32e8a41).
Descriptive only; the P1 pre-registered scores are not changed. Usage: sv_lr_phaseA.py <img_dir> <json_out>   (.venv-sv)
Coordinates: detections are pixel-edge coordinates (centre = index + 0.5); truth axes are used exactly as P1 scored them."""
import json, sys
from pathlib import Path
import numpy as np, shapely
from shapely.geometry import LineString, Point
from PIL import Image, ImageDraw
import sv_synth as S, sv_autoline as AL, sv_autoline_eval as EV

HERE = Path(__file__).resolve().parent
TOL = 2.0
SEEDS = json.load(open(HERE / "autoline/autoline_test.json"))["seeds"]
PALETTE = [(230, 25, 75), (60, 180, 75), (0, 130, 200), (245, 130, 48), (145, 30, 180), (70, 240, 240), (240, 50, 230), (210, 245, 60),
           (0, 128, 128), (170, 110, 40), (128, 0, 0), (0, 0, 128), (128, 128, 0), (255, 215, 0), (0, 191, 255), (199, 21, 133)]
CASES = [("black_1_fragmented", 2005, "black_1"), ("red_2px_breaks", 2004, "red_aa_2"), ("pale_1_missed", 2001, "pale_1"),
         ("red_var_2to5", 2001, "red_var_2to5"), ("red_touch_fill", 2001, "red_touch_fill"), ("band_drawn_as_line", 2001, "band_yellow")]


def samples(axis):
    g = LineString(axis); n = max(int(g.length), 1); d = np.linspace(0, g.length, n + 1)
    return g, d, shapely.line_interpolate_point(g, d)


def occluded(truth, li, pts):
    """A sample of line li is hidden if a line drawn LATER passes within its half width + 0.5 px (sv_synth draws in list order)."""
    occ = np.zeros(len(pts), bool)
    for t in truth["lines"][li + 1:]:
        occ |= shapely.distance(pts, LineString(t["axis"])) <= np.median(t["width"]) / 2 + 0.5
    return occ


def runs(mask):
    m = np.r_[0, mask.astype(int), 0]; d = np.diff(m); return list(zip(np.nonzero(d == 1)[0], np.nonzero(d == -1)[0]))


def end_tangent(g, at_start, k=5.0):
    L = g.length; k = min(k, L)
    a, b = (g.interpolate(0), g.interpolate(k)) if at_start else (g.interpolate(L), g.interpolate(L - k))
    v = np.array([a.x - b.x, a.y - b.y]); n = np.hypot(*v); return v / n if n else v


def analyse_line(truth, li, det, tree, faces):
    t = truth["lines"][li]; g, dist, pts = samples(t["axis"]); occ = occluded(truth, li, pts)
    if t["id"] == "red_touch_fill": occ |= np.zeros(len(pts), bool)
    dd = np.full((len(pts), len(det)), np.inf)
    for j in tree.query(g.buffer(TOL)): dd[:, j] = shapely.distance(pts, det[j])
    near = dd.min(1) if len(det) else np.full(len(pts), np.inf); hit = near <= TOL
    owner = np.where(hit, dd.argmin(1) if len(det) else -1, -1)
    vis = ~occ; miss_vis = ~hit & vis
    gaps = [(int(s), int(e)) for s, e in runs(miss_vis)]
    seq = []                                                     # owner runs along the truth line (visible or hit samples)
    for i, o in enumerate(owner):
        if o < 0: continue
        if seq and seq[-1][0] == o: seq[-1][2] = i
        else: seq.append([int(o), i, i])
    splits = []
    for (o1, s1, e1), (o2, s2, e2) in zip(seq[:-1], seq[1:]):
        if o1 == o2: continue
        between = np.arange(e1 + 1, s2); vis_miss = int(miss_vis[between].sum()) if len(between) else 0; occ_n = int(occ[between].sum()) if len(between) else 0
        p1, p2 = Point(pts[e1].x, pts[e1].y), Point(pts[s2].x, pts[s2].y)
        g1, g2 = det[o1], det[o2]
        ends1 = [Point(g1.coords[0]), Point(g1.coords[-1])]; ends2 = [Point(g2.coords[0]), Point(g2.coords[-1])]
        i1 = int(np.argmin([q.distance(p1) for q in ends1])); i2 = int(np.argmin([q.distance(p2) for q in ends2]))
        endp = ends1[i1].distance(ends2[i2]); e_at_end1 = ends1[i1].distance(p1) <= TOL + 1; e_at_end2 = ends2[i2].distance(p2) <= TOL + 1
        t1 = end_tangent(g1, i1 == 0); t2 = end_tangent(g2, i2 == 0); ang = float(np.degrees(np.arccos(np.clip(-t1 @ t2, -1, 1))))
        kind = "seamless" if s2 - e1 <= 2 else ("occluded_crossing" if occ_n >= (s2 - e1 - 1) * 0.5 else "visual_gap")
        splits.append({"from": o1, "to": o2, "truth_gap_px": int(s2 - e1 - 1), "visible_missing_px": vis_miss, "occluded_px": occ_n, "kind": kind,
                       "endpoint_dist": float(endp), "both_at_object_ends": bool(e_at_end1 and e_at_end2), "turn_deg": ang,
                       "at": [round(p1.x, 1), round(p1.y, 1)], "end1": [round(ends1[i1].x, 2), round(ends1[i1].y, 2), i1], "end2": [round(ends2[i2].x, 2), round(ends2[i2].y, 2), i2]})
    objs = sorted({o for o in owner if o >= 0})
    return {"id": t["id"], "ink": t["ink"], "width": float(np.median(t["width"])), "samples": int(len(pts)), "occluded_share": float(occ.mean()),
            "recall_all": float(hit.mean()), "recall_visible": float(hit[vis].mean()) if vis.any() else None,
            "visual_gaps": [{"start": s, "len": e - s} for s, e in gaps], "objects_on_line": objs, "owner_runs": len(seq), "splits": splits,
            "_hit": hit, "_occ": occ, "_owner": owner, "_pts": pts}


def objects_spanning(per, det):
    span = {}
    for r in per:
        for o in set(r["_owner"][r["_owner"] >= 0].tolist()):
            n = int((r["_owner"] == o).sum())
            if n >= 10: span.setdefault(o, []).append((r["id"], n))
    return {int(o): v for o, v in span.items() if len(v) >= 2}


def draw_lines(im, geoms, k, cols, width=1):
    d = ImageDraw.Draw(im)
    for g, c in zip(geoms, cols):
        for part in shapely.get_parts(g):
            c_ = np.asarray(part.coords) * k; d.line([tuple(p) for p in c_], fill=c, width=width)


def panels(img, truth, det, case_line, rec, fp_mask_geoms, k, box=None):
    H, W = img.shape[:2]; base = Image.fromarray(np.kron(img, np.ones((k, k, 1), np.uint8)))
    faded = Image.fromarray((np.kron(img, np.ones((k, k, 1), np.uint8)) * 0.35 + 255 * 0.65).astype(np.uint8))
    A = base.copy()
    B = faded.copy(); draw_lines(B, [LineString(t["axis"]) for t in truth["lines"]], k, [(150, 150, 150)] * len(truth["lines"]), 1)
    if case_line is not None:
        draw_lines(B, [LineString(case_line["axis"])], k, [(0, 160, 0)], 2)
    C = Image.new("RGB", base.size, "white"); draw_lines(C, det, k, [(0, 0, 0)] * len(det), max(1, k // 3))
    D = base.copy(); draw_lines(D, det, k, [(0, 90, 255)] * len(det), max(1, k // 3))
    E = faded.copy(); dE = ImageDraw.Draw(E)
    draw_lines(E, fp_mask_geoms, k, [(230, 0, 230)] * len(fp_mask_geoms), max(1, k // 2))
    if rec is not None:
        for p, h, o in zip(rec["_pts"], rec["_hit"], rec["_occ"]):
            c = (0, 170, 0) if h else ((255, 150, 0) if o else (230, 0, 0)); r = max(1, k // 3)
            dE.ellipse([p.x * k - r, p.y * k - r, p.x * k + r, p.y * k + r], fill=c)
    F = faded.copy(); cols = [PALETTE[i % len(PALETTE)] for i in range(len(det))]; draw_lines(F, det, k, cols, max(1, k // 2)); dF = ImageDraw.Draw(F)
    for g, c in zip(det, cols):
        for part in shapely.get_parts(g):
            for q in (part.coords[0], part.coords[-1]):
                r = max(2, k // 2); dF.ellipse([q[0] * k - r, q[1] * k - r, q[0] * k + r, q[1] * k + r], outline=(0, 0, 0), fill=c)
    out = [A, B, C, D, E, F]
    if box is not None: out = [im.crop(tuple(int(v * k) for v in box)) for im in out]
    w, h = out[0].size; sheet = Image.new("RGB", (6 * w + 50, h + 22), "white"); dd = ImageDraw.Draw(sheet)
    for i, (im, name) in enumerate(zip(out, ["A original", "B truth (green = this line)", "C AutoLine output", "D output on original",
                                               "E green hit / red missed / orange hidden / magenta false", "F objects + endpoints"])):
        sheet.paste(im, (i * (w + 10), 22)); dd.text((i * (w + 10) + 2, 4), name, fill="black")
    return sheet


def main(img_dir, json_out):
    out = Path(img_dir); out.mkdir(parents=True, exist_ok=True); res = {"source": "frozen P1 (32e8a41) on test seeds", "tol_px": TOL, "tiles": {}}
    for s in SEEDS:
        img, truth, faces = S.generate(s); L, info = AL.extract(img); det = [l["geom"] for l in L]
        tree = shapely.STRtree(np.asarray(det, object)); Tu = shapely.union_all([LineString(t["axis"]) for t in truth["lines"]])
        per = [analyse_line(truth, i, det, tree, faces) for i in range(len(truth["lines"]))]
        false_parts = [shapely.difference(g, Tu.buffer(3.0)) for g in det]; false_parts = [g for g in false_parts if not g.is_empty and g.length >= 3]
        fl = float(sum(g.length for g in false_parts)); band_px = {}
        for b in truth["bands"]:
            on = shapely.intersection(shapely.union_all(det), LineString(b["axis"]).buffer(b["width"] / 2)) if det else None
            band_px[b["id"]] = {"width": b["width"], "detected_length_inside_band": float(on.length) if on is not None else 0.0, "band_length": float(LineString(b["axis"]).length)}
        span = objects_spanning(per, det)
        ends = [(j, q) for j, g in enumerate(det) for q in (g.coords[0], g.coords[-1])]
        res["tiles"][str(s)] = {"detected_objects": len(det), "false_length_px": fl, "detected_length_px": float(sum(g.length for g in det)),
                                "objects_spanning_2plus_truth_lines": span, "bands": band_px, "endpoints": len(ends),
                                "lines": [{k: v for k, v in r.items() if not k.startswith("_")} for r in per]}
        panels(img, truth, det, None, None, false_parts, 2).save(out / f"tile_{s}_x2.png")
        for name, seed, lid in CASES:
            if seed != s: continue
            if lid.startswith("band"):
                b = [x for x in truth["bands"] if x["id"] == lid][0]; case = {"axis": b["axis"]}; rec = None
                rr = analyse_line({"lines": [{"id": lid, "ink": "band", "width": [b["width"]], "axis": b["axis"]}]}, 0, det, tree, faces); rec = rr
            else:
                li = [i for i, t in enumerate(truth["lines"]) if t["id"] == lid][0]; case = truth["lines"][li]; rec = per[li]
            panels(img, truth, det, case, rec, false_parts, 3).save(out / f"case_{name}_x3.png")
            ax = np.asarray(case["axis"]); bad = np.nonzero(~rec["_hit"] & ~rec["_occ"])[0]
            cx, cy = (rec["_pts"][bad[len(bad) // 2]].x, rec["_pts"][bad[len(bad) // 2]].y) if len(bad) else ax.mean(0)
            box = (max(0, cx - 24), max(0, cy - 24), min(256, cx + 24), min(256, cy + 24))
            panels(img, truth, det, case, rec, false_parts, 8, box).save(out / f"case_{name}_zoom_x8.png")
            res.setdefault("cases", {})[name] = {"seed": seed, "line": lid, "zoom_box": [round(v, 1) for v in box]}
    json.dump(res, open(json_out, "w"), indent=1, default=float)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
