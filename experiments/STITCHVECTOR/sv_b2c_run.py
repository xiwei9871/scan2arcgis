"""B2c Phase C run: B0 / B2a / B2c on sv_synth test tiles and counterexample test scenes. Rules: sv_b2c_prereg.json.
Usage: sv_b2c_run.py <json_dir> <img_dir> <dev|test>   (.venv-sv)"""
import json, sys, collections
from pathlib import Path
import numpy as np, shapely
from shapely.geometry import LineString, Polygon
from PIL import Image, ImageDraw
import sv_synth as S, sv_autoline as AL, sv_ld_fix as F, sv_ld_stages as LS, sv_ld_compare as CMP, sv_b2b as BB, sv_b2c as C, sv_b2c_scenes as SC

HERE = Path(__file__).resolve().parent
PRE = json.load(open(HERE / "sv_b2c_prereg.json"))


def run3(img):
    base, add = BB.added(img); L = AL.lab(img); kept, dls = [], []
    for o in add:
        dl, st = C.seg_dL(L, o["geom"], o["width"]); ok = (st < C.Q["min_stable"]) or (dl <= C.Q["dL_max"]); dls.append((dl, st, ok))
        if ok: kept.append(o)
    return {"B0": base, "B2a": base + add, "B2c": base + kept}, add, dls


def false_split(objs, truth_lines, faces, bands):
    T = shapely.union_all([LineString(a) for a in truth_lines]).buffer(3) if truth_lines else None
    E = shapely.union_all([Polygon(f).exterior for f in faces]).buffer(2.5) if faces else None
    Bd = shapely.union_all([LineString(b["axis"]).buffer(b["width"] / 2 + 2) for b in bands]) if bands else None
    out = {"fill_edge": 0.0, "band": 0.0, "other": 0.0}
    for o in objs:
        r = shapely.difference(o["geom"], T) if T is not None else o["geom"]
        if E is not None: out["fill_edge"] += shapely.intersection(r, E).length; r = shapely.difference(r, E)
        if Bd is not None: out["band"] += shapely.intersection(r, Bd).length; r = shapely.difference(r, Bd)
        out["other"] += r.length
    return out


def synth(seeds):
    res = {}
    for s in seeds:
        img, truth, faces = S.generate(s); own, _ = LS.owner_map(truth, img.shape[:2]); M, add, dls = run3(img); tile = {}
        for k, objs in M.items():
            sc = CMP.score(objs, img, truth, own); sc["false_split"] = false_split(objs, [t["axis"] for t in truth["lines"]], list(faces.values()), truth["bands"])
            U = shapely.union_all([o["geom"] for o in objs]).buffer(1.5)
            sc["b0_length_not_in_output"] = float(sum(shapely.difference(o["geom"], U).length for o in M["B0"])); tile[k] = sc
        segs = []
        for o, (dl, st, ok) in zip(add, dls):
            lab, parts = BB.label(o["geom"], truth, list(faces.values()), truth["bands"])
            segs.append({"label": lab, "purity": max(parts.values()), "length": o["geom"].length, "dL": dl, "stable": st, "kept": ok})
        tile["added_segments"] = segs; res[str(s)] = tile
    return res


def scenes(seeds):
    res = {}
    for s in seeds:
        for kind in SC.KINDS:
            img, t = SC.scene(kind, s); M, add, dls = run3(img); tile = {}
            for k, objs in M.items():
                U = shapely.union_all([o["geom"] for o in objs]) if objs else None; per = {}
                for x in t["ink"]:
                    g = LineString(x["axis"]); pts = shapely.line_interpolate_point(g, np.linspace(0, g.length, int(g.length) + 1))
                    per[x["id"]] = {"sub": x["sub"], "samples": len(pts), "hit": int((shapely.distance(pts, U) <= 2.0).sum()) if U is not None else 0}
                faces = []
                fs = false_split(objs, [x["axis"] for x in t["ink"]], [], t["bands"])
                Eo = [LineString(x["axis"]).buffer(2.5) for x in t["edges"] if not x["covered_by_ink"]]
                if Eo and objs:
                    T = shapely.union_all([LineString(x["axis"]) for x in t["ink"]]).buffer(3) if t["ink"] else None
                    edge_len = sum(shapely.intersection(shapely.difference(o["geom"], T) if T is not None else o["geom"], shapely.union_all(Eo)).length for o in objs)
                    fs["fill_edge"] = edge_len; fs["other"] = max(fs["other"] - edge_len, 0.0)
                Bd = {b["id"]: float((shapely.distance(shapely.line_interpolate_point(LineString(b["axis"]), np.linspace(0, LineString(b["axis"]).length, int(LineString(b["axis"]).length) + 1)), U) <= 0.5).mean()) if U is not None else 0.0 for b in t["bands"]}
                tile[k] = {"ink": per, "false_split": fs, "band_axis_share": Bd, "objects": len(objs)}
            tile["added"] = [{"label": C.label_scene(o["geom"], t)[0], "sub": C.label_scene(o["geom"], t)[2], "length": o["geom"].length, "dL": dl, "kept": ok} for o, (dl, st, ok) in zip(add, dls)]
            res[f"{s}_{kind}"] = tile
    return res


def aggregate(sy, sc):
    A = {}
    for k in ("B0", "B2a", "B2c"):
        hits = collections.defaultdict(lambda: [0, 0]); fs = collections.Counter(); bands = {}; obj = mixed = lost = 0
        for s, t in sy.items():
            x = t[k]; obj += x["objects"]; mixed += x["mixed_objects"]; lost += x["b0_length_not_in_output"]
            for v in x["lines"].values(): hits[v["type"]][0] += v["hit"]; hits[v["type"]][1] += v["visible"]
            for kk, v in x["false_split"].items(): fs[kk] += v
            for b, v in x["bands"].items(): bands[f"{s}:{b}:{int(v['width'])}px"] = v["axis_share_with_line"]
        A[k] = {"hits": {t: h for t, h in hits.items()}, "false_split": dict(fs), "false_total": sum(fs.values()), "objects": obj, "mixed_objects": mixed,
                "b0_length_lost": lost, "band_axis_share": bands}
    def gain(t):
        g_a = A["B2a"]["hits"][t][0] - A["B0"]["hits"][t][0]; g_c = A["B2c"]["hits"][t][0] - A["B0"]["hits"][t][0]
        return {"B2a_added_hits": g_a, "B2c_added_hits": g_c, "retained_share": g_c / g_a if g_a > 0 else None}
    red = {kk: {"B2a_added": A["B2a"]["false_split"][kk] - A["B0"]["false_split"][kk], "B2c_added": A["B2c"]["false_split"][kk] - A["B0"]["false_split"][kk]} for kk in ("fill_edge", "band", "other")}
    for kk, v in red.items(): v["removed_share"] = 1 - v["B2c_added"] / v["B2a_added"] if v["B2a_added"] > 0 else None
    ta = A["B2a"]["false_total"] - A["B0"]["false_total"]; tc = A["B2c"]["false_total"] - A["B0"]["false_total"]
    segs = [g for t in sy.values() for g in t["added_segments"]]
    sub = collections.defaultdict(lambda: {"B0": [0, 0], "B2a": [0, 0], "B2c": [0, 0]})
    for key, t in sc.items():
        for k in ("B0", "B2a", "B2c"):
            for x in t[k]["ink"].values(): sub[x["sub"]][k][0] += x["hit"]; sub[x["sub"]][k][1] += x["samples"]
    scf = {k: dict(sum((collections.Counter(t[k]["false_split"]) for t in sc.values()), collections.Counter())) for k in ("B0", "B2a", "B2c")}
    return {"synth": A, "gain_by_type": {t: gain(t) for t in A["B0"]["hits"]}, "added_false_by_place": red,
            "added_false_total": {"B2a": ta, "B2c": tc, "removed_share": 1 - tc / ta if ta > 0 else None},
            "added_segments": {"B2a": len(segs), "B2c_kept": sum(g["kept"] for g in segs), "impure_lt_0.8": sum(g["purity"] < 0.8 for g in segs),
                               "by_label": {lab: {"n": sum(g["label"] == lab for g in segs), "kept": sum(g["kept"] and g["label"] == lab for g in segs),
                                                  "length": sum(g["length"] for g in segs if g["label"] == lab), "kept_length": sum(g["length"] for g in segs if g["label"] == lab and g["kept"])}
                                            for lab in sorted({g["label"] for g in segs})}},
            "scenes_ink_recall_by_sub": {s_: {k: v[k][0] / max(v[k][1], 1) for k in v} for s_, v in sub.items()},
            "scenes_false_by_place": scf}


def draw(img, objs, k, col, base=None, w=2):
    im = Image.fromarray(np.kron(img, np.ones((k, k, 1), np.uint8)) if base is None else base); d = ImageDraw.Draw(im)
    for o in objs:
        for q in shapely.get_parts(o["geom"]): d.line([(x * k, y * k) for x, y in q.coords], fill=col, width=w)
    return im


def faded(img, k): return Image.fromarray((np.kron(img, np.ones((k, k, 1), np.uint8)) * 0.35 + 255 * 0.65).astype(np.uint8))


def sheet(ims, names):
    w, h = ims[0].size; out = Image.new("RGB", (len(ims) * (w + 8), h + 20), "white"); d = ImageDraw.Draw(out)
    for i, (im, n) in enumerate(zip(ims, names)): out.paste(im, (i * (w + 8), 20)); d.text((i * (w + 8) + 2, 4), n, fill="black")
    return out


def images(idr, synth_seeds, scene_seeds, split):
    k = 3
    for s in synth_seeds:
        img, truth, faces = S.generate(s); M, add, dls = run3(img)
        lab = [BB.label(o["geom"], truth, list(faces.values()), truth["bands"])[0] for o in add]
        corr = [o for o, l in zip(add, lab) if l == "true_line"]; wrong = [o for o, l in zip(add, lab) if l != "true_line"]
        kept = [o for o, d in zip(add, dls) if d[2]]; dele = [o for o, d in zip(add, dls) if not d[2]]
        p5 = draw(img, corr, k, (0, 90, 255), np.asarray(faded(img, k)), 3); p5 = draw(img, wrong, k, (230, 0, 230), np.asarray(p5), 3)
        p6 = draw(img, kept, k, (0, 160, 0), np.asarray(faded(img, k)), 3); p6 = draw(img, dele, k, (230, 0, 0), np.asarray(p6), 3)
        sheet([Image.fromarray(np.kron(img, np.ones((k, k, 1), np.uint8))), draw(img, M["B0"], k, (0, 90, 255)), draw(img, M["B2a"], k, (0, 90, 255)), draw(img, M["B2c"], k, (0, 90, 255)), p5, p6],
              ["original", "B0", "B2a", "B2c", "B2a added: blue = on a true line, magenta = false", "B2c on B2a added: green = kept, red = deleted"]).save(Path(idr) / f"b2c_{split}_synth_{s}_x3.png")
    for s in scene_seeds:
        rows = []
        for kind in SC.KINDS:
            img, t = SC.scene(kind, s); M, add, dls = run3(img); kept = [o for o, d in zip(add, dls) if d[2]]; dele = [o for o, d in zip(add, dls) if not d[2]]
            p = draw(img, kept, 2, (0, 160, 0), np.asarray(faded(img, 2)), 3); p = draw(img, dele, 2, (230, 0, 0), np.asarray(p), 3)
            rows.append(sheet([Image.fromarray(np.kron(img, np.ones((2, 2, 1), np.uint8))), draw(img, M["B0"], 2, (0, 90, 255)), draw(img, M["B2a"], 2, (0, 90, 255)), draw(img, M["B2c"], 2, (0, 90, 255)), p],
                              [f"{kind}", "B0", "B2a", "B2c", "B2a added: green kept / red deleted by B2c"]))
        W_ = max(r.size[0] for r in rows); out = Image.new("RGB", (W_, sum(r.size[1] for r in rows)), "white"); y = 0
        for r in rows: out.paste(r, (0, y)); y += r.size[1]
        out.save(Path(idr) / f"b2c_{split}_scenes_{s}_x2.png")


def main(json_dir, img_dir, split):
    jd, idr = Path(json_dir), Path(img_dir); jd.mkdir(parents=True, exist_ok=True); idr.mkdir(parents=True, exist_ok=True)
    assert PRE["params"] == C.Q, "params differ from frozen code"
    ss, cs = PRE["seeds"][split]["sv_synth"], PRE["seeds"][split]["scenes"]
    sy = synth(ss); sc = scenes(cs); agg = aggregate(sy, sc)
    json.dump({"split": split, "synth": sy, "scenes": sc, "aggregate": agg}, open(jd / f"b2c_{split}.json", "w"), indent=1, default=float)
    images(idr, ss, cs, split)
    print(json.dumps({k: agg[k] for k in ("gain_by_type", "added_false_by_place", "added_false_total", "added_segments", "scenes_ink_recall_by_sub")}, indent=0, default=float))
    for k in ("B0", "B2a", "B2c"): print(k, "false", round(agg["synth"][k]["false_total"], 1), agg["synth"][k]["false_split"], "objects", agg["synth"][k]["objects"], "mixed", agg["synth"][k]["mixed_objects"], "B0 lost", round(agg["synth"][k]["b0_length_lost"], 1))
    print("bands", {b: [round(agg["synth"][k]["band_axis_share"][b], 3) for k in ("B0", "B2a", "B2c")] for b in agg["synth"]["B0"]["band_axis_share"]})


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
