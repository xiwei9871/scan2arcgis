"""Automatic line test on synthetic tiles with truth. Rules: sv_autoline_prereg.json. Usage: sv_autoline_run.py <out_dir> [dev|test]"""
import json, sys, time, csv
from pathlib import Path
import numpy as np, shapely
from shapely.geometry import LineString
import sv_common as C, sv_d71 as D, sv_synth as S, sv_autoline as AL, sv_autoline_eval as EV

HERE = Path(__file__).resolve().parent
PRE = json.load(open(HERE / "sv_autoline_prereg.json"))


def d71_recall(img, truth, tol=2.0):
    lab, pal = C.quantize(img, 32); r = D.run_one(lab, pal, D.P0); Lm = r["Lm"]
    ys, xs = np.nonzero(Lm); U = shapely.union_all(shapely.points(xs + 0.5, ys + 0.5)) if len(xs) else None
    out = {}
    for t in truth["lines"]:
        g = LineString(t["axis"]); pts = shapely.line_interpolate_point(g, np.linspace(0, g.length, max(int(g.length), 1) + 1))
        out[t["id"]] = float((shapely.distance(pts, U) <= tol).mean()) if U is not None else 0.0
    return out, int(Lm.sum())


def verdict(m):
    if m["recall"] >= PRE["criteria"]["found_recall"] and m["objects_covering"] <= PRE["criteria"]["continuous_max_objects"]: return "continuous"
    if m["recall"] >= PRE["criteria"]["found_recall"]: return "found_fragmented"
    return "missed"


def main(out_dir, split):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True); seeds = PRE["seeds"][split]; rows = []; res = {"split": split, "seeds": seeds, "tiles": {}}
    for s in seeds:
        img, truth, faces = S.generate(s); t = time.time(); L, info = AL.extract(img, AL.P); sec = time.time() - t
        sc = EV.score(L, truth, img.shape[:2]); base, base_px = d71_recall(img, truth)
        res["tiles"][str(s)] = {"seconds": round(sec, 2), "score": sc, "d71_baseline_recall": base, "d71_L_px": base_px,
                                "fills_found": len(info["fills"]), "protected_share": float(info["protected"].mean()),
                                "vertices": int(sum(len(l["geom"].coords) if l["geom"].geom_type == "LineString" else shapely.get_num_coordinates(l["geom"]) for l in L))}
        for lid, m in sc["lines"].items():
            rows.append([s, lid, round(m["recall"], 3), m["gaps_ge3px"], m["objects_covering"], m["width_true"], m["width_est_median"], verdict(m), round(base[lid], 3)])
    agg = {}
    for lid in {r[1] for r in rows}:
        rr = [r for r in rows if r[1] == lid]
        agg[lid] = {"recall_mean": float(np.mean([r[2] for r in rr])), "objects_mean": float(np.mean([r[4] for r in rr])),
                    "gaps_mean": float(np.mean([r[3] for r in rr])), "verdicts": {v: sum(r[7] == v for r in rr) for v in ("continuous", "found_fragmented", "missed")},
                    "width_abs_err_mean": float(np.mean([abs(r[6] - r[5]) for r in rr if r[6] is not None])) if any(r[6] is not None for r in rr) else None,
                    "d71_recall_mean": float(np.mean([r[8] for r in rr]))}
    bands = [b for t in res["tiles"].values() for b in t["score"]["bands"].values()]
    res["aggregate"] = {"lines": agg, "bands": {"n": len(bands), "max_axis_share_with_line": max(b["axis_share_with_a_line_on_it"] for b in bands),
                                                "mean_axis_share_with_line": float(np.mean([b["axis_share_with_a_line_on_it"] for b in bands])),
                                                "protected_ok": sum(b["axis_share_with_a_line_on_it"] <= PRE["criteria"]["band_max_axis_share"] for b in bands)},
                        "false_length_share_mean": float(np.mean([t["score"]["false_length_share"] for t in res["tiles"].values()]))}
    json.dump(res, open(out / f"autoline_{split}.json", "w"), indent=1, default=float)
    with open(out / f"autoline_{split}.csv", "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["seed", "line", "recall", "gaps_ge3px", "objects", "width_true", "width_est", "verdict", "d71_recall"]); w.writerows(rows)
    print(json.dumps(res["aggregate"], indent=1, default=float))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "dev")
