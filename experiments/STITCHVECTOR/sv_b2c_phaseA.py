"""B2c Phase A on NEW dev data (rules: sv_b2c_phaseA_rules.json, pushed d6f67ce before this data existed).
Usage: sv_b2c_phaseA.py <json_out> <img_out>   (.venv-sv)"""
import json, sys, collections
import numpy as np, shapely
from shapely.geometry import LineString
from PIL import Image, ImageDraw
import sv_synth as S, sv_autoline as AL, sv_b2b as BB, sv_b2c as C, sv_b2c_scenes as SC

R = json.load(open("sv_b2c_phaseA_rules.json"))
TH = [-1, -2, -3, -4, -5]


def kept_share(rows, key="label"):
    by = collections.defaultdict(list)
    for r in rows: by[r[key]].append(r)
    out = {}
    for lab, v in sorted(by.items()):
        tot = sum(r["length"] for r in v)
        out[lab] = {"segments": len(v), "length": tot, "dL_pct_10_50_90": np.percentile([r["dL"] for r in v], [10, 50, 90]).tolist(),
                    "kept_share": {str(t): sum(r["length"] for r in v if r["stable"] < 0.3 or r["dL"] <= t) / max(tot, 1e-9) for t in TH}}
    return out


def a1():
    rows, crops = [], []
    for s in R["dev_data"]["sv_synth"]:
        img, truth, faces = S.generate(s); L = AL.lab(img); _, add = BB.added(img)
        for o in add:
            lab, parts = BB.label(o["geom"], truth, list(faces.values()), truth["bands"]); dl, st = C.seg_dL(L, o["geom"], o["width"])
            rows.append({"seed": s, "label": lab, "purity": max(parts.values()), "length": o["geom"].length, "dL": dl, "stable": st}); crops.append((img, o["geom"], rows[-1]))
    return rows, crops


def a2_a3():
    rows, axes, crops = [], [], []
    for s in R["dev_data"]["counterexample_scenes"]:
        for k in SC.KINDS:
            img, t = SC.scene(k, s); L = AL.lab(img); _, add = BB.added(img)
            for o in add:
                lab, parts, sub = C.label_scene(o["geom"], t); dl, st = C.seg_dL(L, o["geom"], o["width"])
                rows.append({"seed": s, "kind": k, "label": lab, "sub": sub or lab, "purity": max(parts.values()), "length": o["geom"].length, "dL": dl, "stable": st})
                crops.append((img, o["geom"], rows[-1]))
            for x in t["ink"]:
                g = LineString(x["axis"]); dl, st = C.seg_dL(L, g, x["width"]); axes.append({"seed": s, "kind": k, "class": "ink:" + x["sub"], "dL": dl, "stable": st})
            for x in t["edges"]:
                if x["covered_by_ink"]: continue
                g = LineString(x["axis"]); dl, st = C.seg_dL(L, g, 1.0); axes.append({"seed": s, "kind": k, "class": "edge_only", "dL": dl, "stable": st})
            for x in t["bands"]:
                g = LineString(x["axis"]); n = np.array([-(np.asarray(x["axis"][-1]) - np.asarray(x["axis"][0]))[1], (np.asarray(x["axis"][-1]) - np.asarray(x["axis"][0]))[0]]); n /= np.linalg.norm(n)
                for sgn in (-1, 1):
                    e = shapely.affinity.translate(g, *(n * sgn * x["width"] / 2)); dl, st = C.seg_dL(L, e, 1.0)
                    axes.append({"seed": s, "kind": k, "class": f"band_edge_{int(x['width'])}px", "dL": dl, "stable": st})
    return rows, axes, crops


def sheet(crops, path, k=6, win=28, per=6):
    by = collections.defaultdict(list)
    for c in crops: by[c[2].get("sub", c[2]["label"])].append(c)
    tiles = []
    for lab in sorted(by):
        for img, g, r in sorted(by[lab], key=lambda c: -c[2]["length"])[:per]:
            cx, cy = np.asarray(g.interpolate(0.5, normalized=True).coords[0]); x0 = int(np.clip(cx - win / 2, 0, 256 - win)); y0 = int(np.clip(cy - win / 2, 0, 256 - win))
            im = Image.fromarray(np.kron(img[y0:y0 + win, x0:x0 + win], np.ones((k, k, 1), np.uint8))); d = ImageDraw.Draw(im)
            for part in shapely.get_parts(g): d.line([((x - x0) * k, (y - y0) * k) for x, y in part.coords], fill=(0, 90, 255), width=2)
            d.rectangle([0, 0, win * k, 26], fill=(255, 255, 255)); d.text((2, 1), lab[:30], fill="black"); d.text((2, 13), f"dL {r['dL']:.1f}  seed {r['seed']}", fill="black")
            tiles.append(np.asarray(im))
    cols = 6; rows = [np.hstack(tiles[i:i + cols] + [np.full_like(tiles[0], 255)] * (cols - len(tiles[i:i + cols]))) for i in range(0, len(tiles), cols)]
    Image.fromarray(np.vstack(rows)).save(path)


def main(json_out, img_out):
    r1, c1 = a1(); r2, axes, c2 = a2_a3()
    A1 = kept_share(r1); A2 = kept_share(r2, "sub")
    ax = collections.defaultdict(list)
    for a in axes: ax[a["class"]].append(a["dL"])
    A3 = {k: {"n": len(v), "dL_min_median_max": [float(np.min(v)), float(np.median(v)), float(np.max(v))]} for k, v in sorted(ax.items())}
    tl, fe = A1.get("true_line"), A1.get("fill_edge")
    s1 = [t for t in TH if tl and fe and tl["kept_share"][str(t)] >= 0.8 and 1 - fe["kept_share"][str(t)] >= 0.5]
    pale = [x for k in ("ink:pale_darker", "ink:boundary_pale") for x in ax.get(k, [])]; edge = ax.get("edge_only", [])
    s2 = bool(pale and edge and max(pale) < min(edge))
    res = {"rules": "sv_b2c_phaseA_rules.json", "A1_pipeline_sv_synth": A1, "A2_pipeline_scenes": A2, "A3_truth_axes": A3,
           "stop_check": {"A1_thresholds_meeting_80_50": s1, "A3_pale_ink_max_below_edge_only_min": s2,
                          "pale_ink_max": max(pale) if pale else None, "edge_only_min": min(edge) if edge else None,
                          "decision": "CONTINUE" if (s1 and s2) else "STOP"},
           "impure_segments": {"A1": sum(1 for r in r1 if r["purity"] < 0.8), "A2": sum(1 for r in r2 if r["purity"] < 0.8)},
           "segments_A1": r1, "segments_A2": r2, "axes_A3": axes}
    json.dump(res, open(json_out, "w"), indent=1, default=float); sheet(c1 + c2, img_out)
    print("A1", {k: (v["segments"], round(v["length"]), np.round(v["dL_pct_10_50_90"], 1).tolist(), {t: round(x, 2) for t, x in v["kept_share"].items()}) for k, v in A1.items()})
    print("A2", {k: (v["segments"], round(v["length"]), {t: round(x, 2) for t, x in v["kept_share"].items()}) for k, v in A2.items()})
    for k, v in A3.items(): print("A3", k.ljust(40), v["n"], np.round(v["dL_min_median_max"], 1).tolist())
    print("stop_check", res["stop_check"], "impure", res["impure_segments"])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
