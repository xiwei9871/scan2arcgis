"""R4-B2 Stage 4 evaluation (rules: r4b2_preregistration.json stage4_metrics + r4b2_stage1_amendment.json).

Per sheet, for each method region map (B2 = frozen full-image reconstruction; M2_hybrid baseline):
  instance   experiments/R4A/r4a2_2_eval.instance_metrics (unchanged) + recall per canonical width bin
  edges      region-implied pair edges vs official edges (strict / 1-pair tolerance), both methods;
             B2 also raw edge probabilities > 0.5
  thin       3-6 / 6-10 px instances: share whose best-overlap region holds >= 50% of no other instance
  merges     regions holding >= 50% of >= 2 instances; small instances inside them; share of small-instance
             failures whose best-overlap region also holds >= 50% of another instance (decision C)
  shared     share of 4-adjacent instance pairs (valid area) whose best-overlap regions differ
  boundary   r4a2_2_eval.boundary_metrics (unchanged)
B2 only, separately marked:
  ORACLE_DOMAIN   the same B2 probabilities reconstructed inside D_gt (label-derived) - diagnostic, NOT a score
  invalid_link    small instances lost by the full-image rule but recovered on D_gt (attributable to links
                  through D_gt-invalid pixels) and regions crossing invalid pixels that hold >= 2 instances
Usage: r4b2_eval.py <sheet> <status> <B2_pred_dir> <M2_hybrid_regions.npy> <out.json>   (.venv-ml)
"""
import json, sys
from pathlib import Path
import numpy as np
from scipy.sparse import coo_matrix

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "R4A"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "R4B1T"))
import r4b2_edges as E  # noqa: E402
import r4a2_2_eval as EV  # noqa: E402
import r4b1t_width as W  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def overlap_stats(i1, reg, V, area):
    m = V & (i1 > 0) & (reg > 0)
    C = coo_matrix((np.ones(int(m.sum())), (i1[m], reg[m])), shape=(int(i1.max()) + 1, int(reg.max()) + 1)).tocsr().tocoo()
    r_, c_, n_ = C.row, C.col, C.data
    ra = np.bincount(np.where(V, reg, 0).ravel(), minlength=int(reg.max()) + 1)
    iou = n_ / (area[r_] + ra[c_] - n_)
    best_iou = np.zeros(int(i1.max()) + 1); np.maximum.at(best_iou, r_, iou)
    o = np.lexsort((-n_, r_)); f = np.unique(r_[o], return_index=True)[1]
    best_r = np.zeros(int(i1.max()) + 1, np.int64); best_r[r_[o][f]] = c_[o][f]
    hold = n_ / area[r_] >= 0.5
    holders = np.bincount(c_[hold], minlength=int(reg.max()) + 1)               # instances held (>= 50%) per region
    held_by = np.zeros(int(i1.max()) + 1, np.int64); held_by[r_[hold]] = c_[hold]
    return best_iou, best_r, holders, held_by


def method_metrics(name, reg, S, extra_edges=None):
    R, V, i1, area, ids, wid = S["R"], S["V"], S["i1"], S["area"], S["ids"], S["wid"]
    inst, _ = EV.instance_metrics(reg.astype(np.int64), R); bnd = EV.boundary_metrics(reg, R)
    best_iou, best_r, holders, held_by = overlap_stats(i1, reg, V, area)
    hit = best_iou[ids] >= 0.5
    bins = {}
    for b, _, _ in W.BINS:
        m = np.array([W.width_bin(w) == b for w in wid])
        if m.any():
            sep = holders[best_r[ids[m]]] <= 1
            bins[b] = {"n": int(m.sum()), "recall": float(hit[m].mean()), "kept_separate": float(sep.mean())}
    multi = holders >= 2
    fail = ids[~hit]
    caused = [k for k in fail if best_r[k] > 0 and holders[best_r[k]] >= (2 if held_by[k] == best_r[k] else 1)]
    small_in_multi = int(sum(multi[held_by[k]] for k in ids if held_by[k] > 0))
    pairs = EV.adjacency(i1, V); und = {(a, b) for a, b in pairs if a < b}
    sepd = float(np.mean([best_r[a] != best_r[b] for a, b in und])) if und else None
    pr, pd = E.region_edges(reg)
    out = {"method": name, "small": inst["small"], "large": inst["large"], "all": inst["all"], "regions": inst["regions"],
           "small_recall_canonical": float(hit.mean()), "n_small_canonical": int(len(ids)), "by_width": bins,
           "region_edges": E.edge_metrics(pr, pd, *S["edges"]),
           "merges": {"regions_holding_ge2_instances": int(multi.sum()), "small_instances_in_such_regions": small_in_multi,
                      "small_failures": int(len(fail)), "small_failures_caused_by_multi_instance_merge": int(len(caused)),
                      "share_failures_caused_by_merge": round(len(caused) / max(len(fail), 1), 4)},
           "shared_boundary_pairs_separated": sepd, "boundary_F1": {t: bnd[t]["F1"] for t in ("tol1", "tol2", "tol3")},
           "false_boundary_share": bnd["false_boundary_share_near_neg_ink_1px"]}
    if extra_edges is not None: out["prob_edges_p_gt_0.5"] = E.edge_metrics(*extra_edges, *S["edges"])
    return out, hit, best_r, holders


def main(sheet, status, b2_dir, m2_regions, out_json):
    R = EV.load_ref(sheet); unit = np.load(ROOT / "runs/r4a2" / sheet / "unit.npy").astype(np.int32)
    V = (R["ignore"] == 0) & (unit >= 0)
    i1, area, ids, wid = W.canonical_widths(R["instance"], V)
    S = {"R": R, "V": V, "i1": i1, "area": area, "ids": ids, "wid": wid, "edges": E.edges_from_labels(unit, V)}
    d = Path(b2_dir); pr = np.load(d / "prob_right.npy").astype(np.float32); pd = np.load(d / "prob_down.npy").astype(np.float32)
    b2 = np.load(d / "regions_B2.npy"); m2 = np.load(m2_regions)
    res = {"sheet": sheet, "status": status, "valid_px": int(V.sum()), "invalid_px_share_D_gt": round(float((~V).mean()), 5)}
    res["B2"], hit_b2, br_b2, hold_b2 = method_metrics("B2", b2, S, (pr, pd))
    res["M2_hybrid"], hit_m2, _, _ = method_metrics("M2_hybrid", m2, S)
    od, _ = E.regions_from_probs(pr, pd, domain=V)
    res["B2_ORACLE_DOMAIN"], hit_od, _, _ = method_metrics("B2_ORACLE_DOMAIN (label-derived D_gt; diagnostic, NOT a score)", od, S)
    inv = ~V
    cross = np.bincount(b2[inv].ravel(), minlength=int(b2.max()) + 1) > 0
    res["invalid_link_diagnostic"] = {"small_lost_full_image_recovered_on_D_gt": int((~hit_b2 & hit_od).sum()),
                                      "small_recovered_full_image_lost_on_D_gt": int((hit_b2 & ~hit_od).sum()),
                                      "regions_crossing_invalid_px_holding_ge2_instances": int((cross & (hold_b2 >= 2)).sum())}
    res["difference_B2_minus_M2_hybrid"] = {"small_recall": res["B2"]["small"]["recall_iou50"] - res["M2_hybrid"]["small"]["recall_iou50"],
                                            "small_over_seg": res["B2"]["small"]["over_seg"] - res["M2_hybrid"]["small"]["over_seg"],
                                            "by_width": {b: res["B2"]["by_width"][b]["recall"] - res["M2_hybrid"]["by_width"][b]["recall"]
                                                         for b in res["B2"]["by_width"] if b in res["M2_hybrid"]["by_width"]}}
    json.dump(res, open(out_json, "w"), indent=1, default=float)
    s = lambda m: (round(res[m]["small"]["recall_iou50"], 4), {b: round(v["recall"], 3) for b, v in res[m]["by_width"].items()})
    print(sheet, status, "B2", s("B2"), "M2_hybrid", s("M2_hybrid"), "ORACLE_DOMAIN", s("B2_ORACLE_DOMAIN"),
          "edgesF1 strict/tol1", round(res["B2"]["prob_edges_p_gt_0.5"]["strict"]["F1"], 3), round(res["B2"]["prob_edges_p_gt_0.5"]["tol1"]["F1"], 3),
          "merge-share", res["B2"]["merges"]["share_failures_caused_by_merge"], res["invalid_link_diagnostic"], flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:6])
