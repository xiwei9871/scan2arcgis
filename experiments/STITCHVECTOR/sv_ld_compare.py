"""Score B0 / B1 / B2 line outputs on synthetic tiles with the Phase A attribution rule (visible samples, credited only
to the owning line). Usage: sv_ld_compare.py <json_out> <seed> [...]   (.venv-sv)"""
import json, sys, collections
import numpy as np, shapely
from shapely.geometry import LineString
import sv_synth as S, sv_ld_stages as L, sv_ld_fix as F, sv_v3_eval as E


def visible_recall(objs, truth, own, li, pts, vis):
    parts = [q for o in objs for q in shapely.get_parts(o["geom"])]
    if not parts: return np.zeros(len(pts), bool)
    sp = np.vstack([shapely.get_coordinates(shapely.line_interpolate_point(q, np.arange(0, q.length + 0.5, 0.5))) for q in parts])
    xi, yi = np.clip(sp[:, 0].astype(int), 0, 255), np.clip(sp[:, 1].astype(int), 0, 255); sp = sp[own[yi, xi] == li]
    return (shapely.distance(pts, shapely.multipoints(sp)) <= 2.0) if len(sp) else np.zeros(len(pts), bool)


def score(objs, img, truth, own):
    per = {}
    for li, t in enumerate(truth["lines"]):
        g = LineString(t["axis"]); pts = shapely.line_interpolate_point(g, np.linspace(0, g.length, int(g.length) + 1))
        vis = ~L.occluded(truth, li, pts); hit = visible_recall(objs, truth, own, li, pts, vis)
        m = np.r_[0, (vis & ~hit).astype(int), 0]; d = np.diff(m); runs = np.nonzero(d == -1)[0] - np.nonzero(d == 1)[0]
        per[t["id"]] = {"type": L.TYPES.get(t["id"], "red_black"), "visible": int(vis.sum()), "hit": int((hit & vis).sum()),
                        "gaps_ge10": int((runs >= 10).sum())}
    Tu = shapely.union_all([LineString(t["axis"]) for t in truth["lines"]]).buffer(3)
    tot = sum(o["geom"].length for o in objs); fal = sum(shapely.difference(o["geom"], Tu).length for o in objs)
    U = shapely.union_all([o["geom"] for o in objs]) if objs else None; bands = {}
    for b in truth["bands"]:
        bg = LineString(b["axis"]); bp = shapely.line_interpolate_point(bg, np.linspace(0, bg.length, int(bg.length) + 1))
        bands[b["id"]] = {"width": b["width"], "axis_share_with_line": float((shapely.distance(bp, U) <= 0.5).mean()) if U is not None else 0.0}
    mixed = E.score([{"geom": o["geom"]} for o in objs], truth)["mixed_objects"]
    return {"lines": per, "false_length": fal, "detected_length": tot, "objects": len(objs), "mixed_objects": mixed, "bands": bands}


ALL = {"B0": lambda a: (F.b0(a), {}), "B1": F.b1, "B2": F.b2, "B2a": F.b2a}
METHODS = dict(ALL)


def main(out, seeds):
    res = {"seeds": seeds, "tiles": {}, "aggregate": {}}
    for s in seeds:
        img, truth, _ = S.generate(s); own, _ = L.owner_map(truth, img.shape[:2]); tile = {}
        base = None
        for k, fn in METHODS.items():
            objs, info = fn(img); sc = score(objs, img, truth, own); sc["info"] = info
            if k == "B0": base = objs
            else:                                               # non-degradation: B0 drawing still present?
                U = shapely.union_all([o["geom"] for o in objs]).buffer(1.5) if objs else None
                sc["b0_length_not_in_new"] = float(sum(shapely.difference(o["geom"], U).length for o in base)) if U is not None else float(sum(o["geom"].length for o in base))
            tile[k] = sc
        res["tiles"][str(s)] = tile
    for k in METHODS:
        a = collections.defaultdict(lambda: [0, 0]); g10 = collections.Counter(); fl = dl = ob = mx = lost = 0; bmax = 0.0; bok = 0; nb = 0
        for t in res["tiles"].values():
            x = t[k]; fl += x["false_length"]; dl += x["detected_length"]; ob += x["objects"]; mx += x["mixed_objects"]; lost += x.get("b0_length_not_in_new", 0.0)
            for v in x["lines"].values(): a[v["type"]][0] += v["hit"]; a[v["type"]][1] += v["visible"]; g10[v["type"]] += v["gaps_ge10"]
            for b in x["bands"].values(): nb += 1; bmax = max(bmax, b["axis_share_with_line"]); bok += b["axis_share_with_line"] <= 0.1
        res["aggregate"][k] = {"visible_recall": {t: h / max(v, 1) for t, (h, v) in a.items()}, "gaps_ge10": dict(g10),
                               "false_length_share": fl / max(dl, 1e-9), "objects": ob, "mixed_objects": mx,
                               "bands_protected": f"{bok}/{nb}", "band_axis_share_max": bmax, "b0_length_lost_px": lost}
    json.dump(res, open(out, "w"), indent=1, default=float)
    for k, v in res["aggregate"].items():
        print(k, {t: round(r, 3) for t, r in sorted(v["visible_recall"].items())}, "gaps>=10", dict(sorted(v["gaps_ge10"].items())),
              "false", round(v["false_length_share"], 3), "obj", v["objects"], "mixed", v["mixed_objects"], "bands", v["bands_protected"],
              "bmax", round(v["band_axis_share_max"], 2), "B0 lost px", round(v["b0_length_lost_px"], 1))


if __name__ == "__main__":
    main(sys.argv[1], [int(x) for x in sys.argv[2:]])
