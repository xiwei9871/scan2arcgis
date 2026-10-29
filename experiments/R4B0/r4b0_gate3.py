"""R4-B0 Gate 3: ORACLE counterfactuals (rules: preregistration.json gate3). Diagnostics only.
Methods prefixed O_ read official labels (official dist.npy or ideal seeds = one pixel per official instance
at its maximum official distance). They are upper bounds, NOT model results, and never inference inputs.
Usage: r4b0_gate3.py <out_dir>   (.venv-ml)
"""
import csv, json, sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import r4b0_common as C  # noqa: E402

METHODS = ["O_GTD_old", "O_GTD_hybrid", "O_GTD_ideal", "O_M2D_ideal", "O_M1DD_ideal", "O_M1P_ideal", "M2_hybrid", "M1_DD_hybrid", "M1"]
BINS = ("3-6", "6-10", "10-20")


def main(out_dir):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    res = {"label": "ORACLE - diagnostic upper bound, not a model result", "sheets": {}, "split": {}}
    succ = {}; widths = {}
    for code in ("15023", "15041"):
        S, P = C.load_sheet(code); res["sheets"][code] = {}
        for m in METHODS:
            M = C.run_method(m, S, P)
            inst, _ = C.E.instance_metrics(M["regions"].astype(np.int64), S["R"])
            rows, extra = C.analyze(S, M)
            for r in rows:
                succ[(code, m, r["instance"])] = r["success"]; widths[(code, r["instance"])] = r["width_bin_own"]
            res["sheets"][code][m] = {"oracle": M["oracle"], "dist_source": M["dist_source"], "small_recall": inst["small"]["recall_iou50"],
                                      "small_over_seg": inst["small"]["over_seg"], "large_recall": inst["large"]["recall_iou50"],
                                      "regions": inst["regions"]["n_pred"], "recall_by_width_own": {b: v["recall"] for b, v in C.summarize(rows, "width_bin_own").items()},
                                      "regions_credited_to_more_than_one_instance": extra["regions_credited_to_more_than_one_instance"]}
            print(code, m, "ORACLE" if M["oracle"] else "model", round(inst["small"]["recall_iou50"], 4), res["sheets"][code][m]["recall_by_width_own"], flush=True)
    # pre-registered split of model failures
    split_rows = []
    for code in ("15023", "15041", "pooled"):
        for model, ideal in (("M2_hybrid", "O_M2D_ideal"), ("M1_DD_hybrid", "O_M1DD_ideal"), ("M1", "O_M1P_ideal")):
            for b in BINS + ("all_small",):
                keys = [k for k in widths if (code == "pooled" or k[0] == code) and (b == "all_small" or widths[k] == b)]
                fails = [k for k in keys if not succ[(k[0], model, k[1])]]
                fix = [k for k in fails if succ[(k[0], ideal, k[1])]]
                need = [k for k in fails if not succ[(k[0], ideal, k[1])]]
                field = [k for k in need if succ[(k[0], "O_GTD_ideal", k[1])]]
                beyond = [k for k in need if not succ[(k[0], "O_GTD_ideal", k[1])]]
                d = {"n": len(keys), "model_failures": len(fails),
                     "postprocess_fixable": len(fix), "boundary_or_field_required": len(need),
                     "of_which_field_limited": len(field), "of_which_beyond_watershed_or_eval_limit": len(beyond),
                     "share_postprocess_fixable": round(len(fix) / max(len(fails), 1), 4),
                     "share_boundary_required": round(len(need) / max(len(fails), 1), 4)}
                res["split"][f"{code}|{model}|{b}"] = d
                split_rows.append({"sheet": code, "model": model, "ideal_seed_oracle": ideal, "width_bin_own": b, **d})
    with open(out / "gate3_split.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(split_rows[0])); w.writeheader(); w.writerows(split_rows)
    json.dump(res, open(out / "gate3_oracle.json", "w"), indent=1, default=float)
    for b in BINS + ("all_small",): print("pooled M2_hybrid", b, res["split"][f"pooled|M2_hybrid|{b}"])


if __name__ == "__main__":
    main(sys.argv[1])
