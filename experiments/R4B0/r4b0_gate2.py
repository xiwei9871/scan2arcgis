"""R4-B0 Gate 2: fair comparison of M1 / M2 post-processing (rules: preregistration.json gate2).
Same evaluation code (r4a2_2_eval instance_metrics / boundary_metrics) and valid area for every method.
M1, M2_oldseed, M2_hybrid must reproduce the saved R4-A2.2 region maps exactly (consistency check).
Usage: r4b0_gate2.py <out_dir>   (.venv-ml)
"""
import json, sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import r4b0_common as C  # noqa: E402

G2 = C.PR["gate2"]
SAVED = {"M1": "M1/regions_M1.npy", "M2_oldseed": "M2/regions_M2_oldseed.npy", "M2_hybrid": "M2/regions_M2_hybrid.npy"}


def main(out_dir):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True); res = {"methods": G2["methods"], "sheets": {}}
    for code in ("15023", "15041"):
        S, P = C.load_sheet(code); res["sheets"][code] = {}
        for m in G2["methods"]:
            M = C.run_method(m, S, P)
            same = None
            if m in SAVED: same = bool((np.load(C.PRED / code / SAVED[m]) == M["regions"]).all())
            inst, _ = C.E.instance_metrics(M["regions"].astype(np.int64), S["R"]); bnd = C.E.boundary_metrics(M["regions"], S["R"])
            rows, extra = C.analyze(S, M)
            r = {"postprocess_seconds": M["seconds"], "dist_source": M["dist_source"], "reproduces_r4a2_2": same,
                 "small": inst["small"], "large": inst["large"], "tiny": inst["tiny"], "all": inst["all"], "regions": inst["regions"],
                 "oracle_majority_unit_miou": inst["oracle_majority_unit_miou"], "hungarian_instance_mean_iou": inst["hungarian_instance_mean_iou_area_ge200"],
                 "boundary_F1": {t: bnd[t]["F1"] for t in ("tol1", "tol2", "tol3")}, "false_boundary_share": bnd["false_boundary_share_near_neg_ink_1px"],
                 "recall_by_width_own": {b: v["recall"] for b, v in C.summarize(rows, "width_bin_own").items()},
                 "n_by_width_own": {b: v["n"] for b, v in C.summarize(rows, "width_bin_own").items()},
                 "recall_by_width_old": {b: v["recall"] for b, v in C.summarize(rows, "width_bin_old").items()},
                 "regions_credited_to_more_than_one_instance": extra["regions_credited_to_more_than_one_instance"]}
            res["sheets"][code][m] = r
            print(code, m, "small", round(r["small"]["recall_iou50"], 4), "over", round(r["small"]["over_seg"], 4), "regions", r["regions"]["n_pred"],
                  "w", r["recall_by_width_own"], "t", r["postprocess_seconds"], "same", same, flush=True)
    # pre-registered decision
    rec = lambda c, m: res["sheets"][c][m]["small"]["recall_iou50"]; ov = lambda c, m: res["sheets"][c][m]["small"]["over_seg"]
    guard = {m: all(ov(c, m) <= ov(c, "M2_hybrid") + 0.03 for c in ("15023", "15041")) for m in G2["methods"]}
    head = all(rec(c, "M2_hybrid") - max(rec(c, "M1_DD_hybrid") if guard["M1_DD_hybrid"] else -1, rec(c, "M2_PD_hybrid") if guard["M2_PD_hybrid"] else -1) >= 0.02
               for c in ("15023", "15041"))
    m1ok = all(max(rec(c, "M1") if guard["M1"] else -1, rec(c, "M1_DD_hybrid") if guard["M1_DD_hybrid"] else -1) >= rec(c, "M2_hybrid") - 0.01 for c in ("15023", "15041"))
    res["decision"] = {"topology_guard_pass": guard, "m2_head_has_independent_value": head, "m1_matches_or_exceeds_m2": m1ok,
                       "verdict": "PREFER_M1" if m1ok else ("M2_HEAD_HAS_VALUE" if head else "INCONCLUSIVE"),
                       "differences": {c: {"M2_hybrid_minus_M1_DD_hybrid": round(rec(c, "M2_hybrid") - rec(c, "M1_DD_hybrid"), 4),
                                           "M2_hybrid_minus_M2_PD_hybrid": round(rec(c, "M2_hybrid") - rec(c, "M2_PD_hybrid"), 4),
                                           "M2_hybrid_minus_M1": round(rec(c, "M2_hybrid") - rec(c, "M1"), 4)} for c in ("15023", "15041")}}
    json.dump(res, open(out / "gate2_comparison.json", "w"), indent=1, default=float)
    print(json.dumps(res["decision"], indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
