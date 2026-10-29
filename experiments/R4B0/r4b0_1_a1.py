"""R4-B0.1 Gate A1: M2_DISTANCE_SEEDS_BOUNDARY_TERRAIN vs M2_hybrid (rules: r4b0_1_preregistration.json a1).
Both methods use the same float16 M2 files and the same hybrid markers; only the watershed terrain differs.
Valid-polygon fraction: regions exported through experiments/R4A/r4a2_2_export.py rules is a .venv (geopandas)
step; here the region maps are saved locally and the export/validation is run by the companion shell lines in
the Gate A1 report.
Usage: r4b0_1_a1.py <out_dir> <local_dir>   (.venv-ml)
"""
import json, sys, time
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import r4b0_common as C  # noqa: E402
import r4b0_1_common as C1  # noqa: E402

NAME = "M2_DISTANCE_SEEDS_BOUNDARY_TERRAIN"


def evaluate(S, M):
    inst, _ = C.E.instance_metrics(M["regions"].astype(np.int64), S["R"]); bnd = C.E.boundary_metrics(M["regions"], S["R"])
    rows, extra = C.analyze(S, M)
    return {"postprocess_seconds": M["seconds"], "small": inst["small"], "large": inst["large"], "tiny": inst["tiny"], "all": inst["all"],
            "regions": inst["regions"], "oracle_majority_unit_miou": inst["oracle_majority_unit_miou"],
            "hungarian_instance_mean_iou": inst["hungarian_instance_mean_iou_area_ge200"],
            "boundary_F1": {t: bnd[t]["F1"] for t in ("tol1", "tol2", "tol3")}, "false_boundary_share": bnd["false_boundary_share_near_neg_ink_1px"],
            "recall_by_width_own": {b: v["recall"] for b, v in C.summarize(rows, "width_bin_own").items()},
            "n_by_width_own": {b: v["n"] for b, v in C.summarize(rows, "width_bin_own").items()},
            "recall_by_width_old": {b: v["recall"] for b, v in C.summarize(rows, "width_bin_old").items()},
            "primary_failure_by_width_own": {b: v["primary_share_of_failures"] for b, v in C.summarize(rows, "width_bin_own").items()},
            "regions_credited_to_more_than_one_instance": extra["regions_credited_to_more_than_one_instance"]}, rows


def main(out_dir, local_dir):
    out, loc = Path(out_dir), Path(local_dir).resolve(); out.mkdir(parents=True, exist_ok=True); loc.mkdir(parents=True, exist_ok=True)
    res = {"method": NAME, "baseline": "M2_hybrid (same float16 files, same markers)", "sheets": {}}
    for code in ("15023", "15041"):
        S, P = C.load_sheet(code)
        base = C.run_method("M2_hybrid", S, P)
        t0 = time.time(); reg, mk = C1.a1_regions(P["prob2"], P["dist2"]); dt = round(time.time() - t0, 2)
        assert (mk == base["markers"]).all(), "seeds must be identical to M2_hybrid"
        new = {"name": NAME, "regions": reg, "markers": mk, "dist": P["dist2"], "dist_source": "M2_PRED_DIST", "prob": P["prob2"], "oracle": False, "seconds": dt}
        rb, _ = evaluate(S, base); rn, rows = evaluate(S, new)
        np.save(loc / f"{code}_regions_{NAME}.npy", reg); np.save(loc / f"{code}_regions_M2_hybrid_rerun.npy", base["regions"])
        d = {"small_recall": rn["small"]["recall_iou50"] - rb["small"]["recall_iou50"], "small_over_seg": rn["small"]["over_seg"] - rb["small"]["over_seg"],
             "small_under_seg": rn["small"]["under_seg"] - rb["small"]["under_seg"],
             "small_absorbed": rn["small"]["absorbed_by_larger_neighbour"] - rb["small"]["absorbed_by_larger_neighbour"],
             "large_recall": rn["large"]["recall_iou50"] - rb["large"]["recall_iou50"], "regions": rn["regions"]["n_pred"] - rb["regions"]["n_pred"],
             "recall_by_width_own": {b: round(rn["recall_by_width_own"][b] - rb["recall_by_width_own"][b], 4) for b in rn["recall_by_width_own"]}}
        res["sheets"][code] = {"M2_hybrid": rb, NAME: rn, "difference_new_minus_old": d, "seeds_identical": True}
        print(code, "recall", round(rb["small"]["recall_iou50"], 4), "->", round(rn["small"]["recall_iou50"], 4),
              "over", round(rb["small"]["over_seg"], 4), "->", round(rn["small"]["over_seg"], 4), "w", d["recall_by_width_own"], "t", dt, flush=True)
    crit = {c: {"recall_gain_ge_0.02": res["sheets"][c]["difference_new_minus_old"]["small_recall"] >= 0.02,
                "over_seg_increase_le_0.03": res["sheets"][c]["difference_new_minus_old"]["small_over_seg"] <= 0.03} for c in ("15023", "15041")}
    res["criteria"] = crit; res["verdict"] = "PASS" if all(all(v.values()) for v in crit.values()) else "FAIL"
    json.dump(res, open(out / "a1_comparison.json", "w"), indent=1, default=float)
    print("A1", res["verdict"], json.dumps(crit))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
