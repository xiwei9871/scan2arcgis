"""Line recovery Phase C run. Rules: sv_lr_prereg.json. Usage: sv_lr_run.py <out_dir> <dev|test>   (.venv-sv)"""
import json, sys, time, csv
from pathlib import Path
import numpy as np
import sv_lr_bench as B, sv_linker as LK

HERE = Path(__file__).resolve().parent
PRE = json.load(open(HERE / "sv_lr_prereg.json"))


def main(out_dir, split):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True); assert PRE["params"] == LK.P, "params differ from frozen code"
    res = {"split": split, "L1": {}, "L2": {}}; rows = []
    for s in PRE["seeds"][split]["L1"]:
        img, lines, bands, rng = B.scene(s); frags, tp = B.cut(img, lines, bands, rng)
        t = time.time(); r = LK.link(frags, img); sec = time.time() - t; sc = B.score_l1(frags, tp, r)
        sc["seconds"] = round(sec, 3); sc["links_by_status"] = {k: sum(x["status"] == k for x in r["links"]) for k in ("CONFIRMED", "INFERRED", "INFERRED_OCCLUDED")}
        sc["true_pairs_non_band"] = sum(1 for x in tp if x["kind"] != "band"); res["L1"][str(s)] = sc
        rows.append(["L1", s, sc["true_pairs_non_band"], sc["predicted"], sc["correct"], sc["wrong"], sc["uncertain"], sc["band_band_links"], sc["impure_components"]])
    for s in PRE["seeds"][split]["L2"]:
        r = B.run_l2(s); res["L2"][str(s)] = r
        rows.append(["L2", s, "", r["links"], r["links_same_owner"], r["links_different_owner"], r["uncertain"], "", r["links_unassignable"]])
    L1 = list(res["L1"].values()); L2 = list(res["L2"].values())
    tp = sum(x["true_pairs_non_band"] for x in L1); pr = sum(x["predicted"] for x in L1); ok = sum(x["correct"] for x in L1)
    def by(key):
        d = {}
        for x in L1:
            for k, v in x[key].items(): d[k] = d.get(k, 0) + v
        return d
    tb, cb = by("true_by_gap"), by("correct_by_gap"); tb.pop("band", None)
    wk = by("wrong_by_kind")
    comp = {}
    for x in L1:
        for k, v in x["components_per_line"].items(): comp.setdefault(k, []).append(v)
    def l2sum(k): return sum(x[k] for x in L2)
    def rec(x, which): return float(np.mean([v["recall"] for v in x[which]["lines"].values()]))
    def objs(x, which): return float(np.mean([v["objects_covering"] for v in x[which]["lines"].values()]))
    res["aggregate"] = {
        "L1": {"true_pairs": tp, "predicted": pr, "correct": ok, "wrong": pr - ok, "precision": ok / max(pr, 1), "recall": ok / max(tp, 1),
               "recall_by_gap": {k: [cb.get(k, 0), v] for k, v in sorted(tb.items())}, "wrong_by_kind": wk,
               "uncertain": sum(x["uncertain"] for x in L1), "uncertain_on_true_pair": sum(x["uncertain_on_true_pair"] for x in L1),
               "band_band_links": sum(x["band_band_links"] for x in L1), "impure_components": sum(x["impure_components"] for x in L1),
               "fragments": sum(x["fragments"] for x in L1), "components_mean_by_line": {k: float(np.mean(v)) for k, v in sorted(comp.items())},
               "false_merges_must_not": {k: wk.get(k, 0) for k in ("parallel->parallel", "true_termination->true_termination", "line->true_termination", "true_termination->line", "band_to_line")}},
        "L2": {"fragments": l2sum("fragments"), "logical": l2sum("logical"), "links": l2sum("links"), "links_same_owner": l2sum("links_same_owner"),
               "links_different_owner": l2sum("links_different_owner"), "links_unassignable": l2sum("links_unassignable"), "uncertain": l2sum("uncertain"),
               "recall_mean_before": float(np.mean([rec(x, "before") for x in L2])), "recall_mean_after": float(np.mean([rec(x, "after") for x in L2])),
               "objects_covering_mean_before": float(np.mean([objs(x, "before") for x in L2])), "objects_covering_mean_after": float(np.mean([objs(x, "after") for x in L2]))}}
    json.dump(res, open(out / f"lr_{split}.json", "w"), indent=1, default=float)
    with open(out / f"lr_{split}.csv", "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["level", "seed", "true_pairs", "predicted_links", "correct_or_same_owner", "wrong_or_different_owner", "uncertain", "band_band", "impure_or_unassignable"]); w.writerows(rows)
    print(json.dumps(res["aggregate"], indent=1, default=float))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
