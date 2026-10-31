"""Protection ablation run: M0-M3 on sv_synth tiles and counterexample scenes. Rules: sv_pa_prereg.json.
Usage: sv_pa_run.py <json_dir> <img_dir> <dev|test>   (.venv-sv)"""
import json, sys, collections
from pathlib import Path
import numpy as np, shapely
from shapely.geometry import LineString
from PIL import Image, ImageDraw
import sv_synth as S, sv_b2c_scenes as SC, sv_b2c as C, sv_b2c_run as BR, sv_ld_stages as LS, sv_ld_compare as CMP, sv_pa as PA

HERE = Path(__file__).resolve().parent
PRE = json.load(open(HERE / "sv_pa_prereg.json"))
TYPE = lambda t: {"pale": "pale", "var_width": "var_width", "touch_fill": "touch_fill"}.get(t, "red_black")


def gaps(objs, axis, tol=2.0, n=10):
    g = LineString(axis); pts = shapely.line_interpolate_point(g, np.linspace(0, g.length, int(g.length) + 1))
    U = shapely.union_all([o["geom"] for o in objs]) if objs else None
    miss = (shapely.distance(pts, U) > tol) if U is not None else np.ones(len(pts), bool)
    m = np.r_[0, miss.astype(int), 0]; d = np.diff(m); r = np.nonzero(d == -1)[0] - np.nonzero(d == 1)[0]
    return [int(x) for x in r if x >= n]


def synth_one(s):
    a, truth, faces = S.generate(s); own, _ = LS.owner_map(truth, a.shape[:2]); out = {}
    for m in PA.METHODS:
        objs, info = PA.run(a, m); sc = CMP.score(objs, a, truth, own)
        fs = BR.false_split(objs, [t["axis"] for t in truth["lines"]], list(faces.values()), truth["bands"])
        lab = collections.Counter(); kept = collections.Counter()
        for g in info["segments"]:
            l, _ = __import__("sv_b2b").label(g["geom"], truth, list(faces.values()), truth["bands"]); lab[l] += 1; kept[l] += g["kept"]
        out[m] = {"recall_by_type": {k: [0, 0] for k in ("pale", "red_black", "var_width", "touch_fill")}, "false_split": fs,
                  "false_length": sum(fs.values()), "detected_length": sc["detected_length"], "objects": sc["objects"], "mixed_objects": sc["mixed_objects"],
                  "bands": {b: {"width": v["width"], "axis_share_with_line": v["axis_share_with_line"]} for b, v in sc["bands"].items()},
                  "gaps_ge10": {t["id"]: gaps(objs, t["axis"]) for t in truth["lines"]},
                  "candidates": info["candidates"], "kept": info["kept"], "candidates_by_label": dict(lab), "kept_by_label": dict(kept)}
        for v in sc["lines"].values():
            r = out[m]["recall_by_type"][TYPE(v["type"])]; r[0] += v["hit"]; r[1] += v["visible"]
    return out, a, truth


def scene_one(s, kind):
    a, t = SC.scene(kind, s); out = {}
    for m in PA.METHODS:
        objs, info = PA.run(a, m); U = shapely.union_all([o["geom"] for o in objs]) if objs else None; per = {}
        for x in t["ink"]:
            g = LineString(x["axis"]); pts = shapely.line_interpolate_point(g, np.linspace(0, g.length, int(g.length) + 1))
            per[x["id"]] = {"sub": x["sub"], "samples": len(pts), "hit": int((shapely.distance(pts, U) <= 2.0).sum()) if U is not None else 0, "gaps_ge10": gaps(objs, x["axis"])}
        fs = BR.false_split(objs, [x["axis"] for x in t["ink"]], [], t["bands"])
        Eo = [LineString(x["axis"]).buffer(2.5) for x in t["edges"] if not x["covered_by_ink"]]
        if Eo and objs:
            T = shapely.union_all([LineString(x["axis"]) for x in t["ink"]]).buffer(3) if t["ink"] else None
            el = sum(shapely.intersection(shapely.difference(o["geom"], T) if T is not None else o["geom"], shapely.union_all(Eo)).length for o in objs)
            fs["fill_edge"] = el; fs["other"] = max(fs["other"] - el, 0.0)
        bands = {}
        for b in t["bands"]:
            g = LineString(b["axis"]); pts = shapely.line_interpolate_point(g, np.linspace(0, g.length, int(g.length) + 1))
            bands[b["id"]] = {"width": b["width"], "axis_share_with_line": float((shapely.distance(pts, U) <= 0.5).mean()) if U is not None else 0.0}
        segs = [{"label": C.label_scene(g["geom"], t)[0], "sub": C.label_scene(g["geom"], t)[2], "length": g["geom"].length, "kept": g["kept"], "dL": g["dL"]} for g in info["segments"]]
        out[m] = {"ink": per, "false_split": fs, "false_length": sum(fs.values()), "detected_length": float(sum(o["geom"].length for o in objs)),
                  "bands": bands, "objects": len(objs), "candidates": info["candidates"], "kept": info["kept"], "added_segments": segs}
    return out, a, t


def aggregate(sy, sc):
    A = {}
    for m in PA.METHODS:
        rec = collections.defaultdict(lambda: [0, 0]); fs = collections.Counter(); det = 0.0; obj = mix = cand = kept = 0; worst = {}
        for s, t in sy.items():
            x = t[m]; det += x["detected_length"]; obj += x["objects"]; mix += x["mixed_objects"]; cand += x["candidates"]; kept += x["kept"]; fs.update(x["false_split"])
            for k, (h, v) in x["recall_by_type"].items(): rec[k][0] += h; rec[k][1] += v
            hit = sum(h for h, v in x["recall_by_type"].values()); vis = sum(v for h, v in x["recall_by_type"].values())
            worst[s] = {"recall_all": hit / max(vis, 1), "pale": x["recall_by_type"]["pale"][0] / max(x["recall_by_type"]["pale"][1], 1),
                        "precision": 1 - x["false_length"] / max(x["detected_length"], 1e-9), "gaps_ge10": sum(len(v) for v in x["gaps_ge10"].values())}
        hit = sum(h for h, v in rec.values()); vis = sum(v for h, v in rec.values())
        bands = {f"{s}:{b}": v["axis_share_with_line"] for s, t in sy.items() for b, v in t[m]["bands"].items()}
        srec = collections.defaultdict(lambda: [0, 0]); sfs = collections.Counter(); sdet = 0.0; sbands = {}; sub_c = collections.Counter(); sub_k = collections.Counter()
        for key, t in sc.items():
            x = t[m]; sdet += x["detected_length"]; sfs.update(x["false_split"])
            for v in x["ink"].values(): srec[v["sub"]][0] += v["hit"]; srec[v["sub"]][1] += v["samples"]
            for b, v in x["bands"].items(): sbands[f"{key}:{b}"] = v["axis_share_with_line"]
            for g in x["added_segments"]:
                k = g["sub"] or g["label"]; sub_c[k] += 1; sub_k[k] += g["kept"]
        A[m] = {"synthetic": {"recall_all": hit / max(vis, 1), "recall_by_type": {k: h / max(v, 1) for k, (h, v) in rec.items()},
                              "precision_length": 1 - sum(fs.values()) / max(det, 1e-9), "false_by_place": dict(fs), "objects": obj, "mixed_objects": mix,
                              "candidates_added": cand, "kept_after_luminance": kept, "band_axis_share": bands,
                              "bands_over_0.1": sum(v > 0.1 for v in bands.values()), "per_seed": worst,
                              "worst_seed_by_recall": min(worst, key=lambda s: worst[s]["recall_all"]), "worst_seed_by_precision": min(worst, key=lambda s: worst[s]["precision"])},
                "scenes": {"recall_by_sub": {k: h / max(v, 1) for k, (h, v) in srec.items()}, "precision_length": 1 - sum(sfs.values()) / max(sdet, 1e-9),
                           "false_by_place": dict(sfs), "band_axis_share_mean": float(np.mean(list(sbands.values()))) if sbands else None,
                           "band_axis_share_max": float(max(sbands.values())) if sbands else None, "added_candidates_by_sub": dict(sub_c), "added_kept_by_sub": dict(sub_k)}}
    return A


def draw(a, objs, k=3):
    im = Image.fromarray(np.kron(a, np.ones((k, k, 1), np.uint8))); d = ImageDraw.Draw(im)
    for o in objs:
        for q in shapely.get_parts(o["geom"]): d.line([(x * k, y * k) for x, y in q.coords], fill=(0, 90, 255), width=2)
    return im


def sheet(ims, names):
    w, h = ims[0].size; out = Image.new("RGB", (len(ims) * (w + 8), h + 20), "white"); d = ImageDraw.Draw(out)
    for i, (im, n) in enumerate(zip(ims, names)): out.paste(im, (i * (w + 8), 20)); d.text((i * (w + 8) + 2, 4), n, fill="black")
    return out


def main(json_dir, img_dir, split):
    jd, idr = Path(json_dir), Path(img_dir); jd.mkdir(parents=True, exist_ok=True); idr.mkdir(parents=True, exist_ok=True)
    assert PRE["params"] == PA.Q, "params differ from frozen code"
    sy, sc = {}, {}
    for s in PRE["seeds"][split]["sv_synth"]:
        r, a, _ = synth_one(s); sy[str(s)] = r
        sheet([Image.fromarray(np.kron(a, np.ones((3, 3, 1), np.uint8)))] + [draw(a, PA.run(a, m)[0]) for m in PA.METHODS], ["original"] + PA.METHODS).save(idr / f"pa_{split}_synth_{s}_x3.png")
    for s in PRE["seeds"][split]["scenes"]:
        rows = []
        for k in PRE["scene_kinds"]:
            r, a, _ = scene_one(s, k); sc[f"{s}_{k}"] = r
            rows.append(sheet([Image.fromarray(np.kron(a, np.ones((2, 2, 1), np.uint8)))] + [draw(a, PA.run(a, m)[0], 2) for m in PA.METHODS], [k] + PA.METHODS))
        W = max(x.size[0] for x in rows); out = Image.new("RGB", (W, sum(x.size[1] for x in rows)), "white"); y = 0
        for x in rows: out.paste(x, (0, y)); y += x.size[1]
        out.save(idr / f"pa_{split}_scenes_{s}_x2.png")
    for t in list(sy.values()) + list(sc.values()):
        for m in t.values():
            for g in m.get("added_segments", []): g.pop("geom", None)
    res = {"split": split, "synthetic": sy, "scenes": sc, "aggregate": aggregate(sy, sc)}
    json.dump(res, open(jd / f"pa_{split}.json", "w"), indent=1, default=float)
    for m, x in res["aggregate"].items():
        s_ = x["synthetic"]; c_ = x["scenes"]
        print(m, "synth recall", round(s_["recall_all"], 3), {k: round(v, 3) for k, v in s_["recall_by_type"].items()}, "precision", round(s_["precision_length"], 3),
              "false", {k: round(v) for k, v in s_["false_by_place"].items()}, "bands>0.1", s_["bands_over_0.1"], "cand/kept", s_["candidates_added"], s_["kept_after_luminance"],
              "| scenes", {k: round(v, 2) for k, v in c_["recall_by_sub"].items()}, "prec", round(c_["precision_length"], 3), "band mean/max", round(c_["band_axis_share_mean"] or 0, 3), round(c_["band_axis_share_max"] or 0, 3))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
