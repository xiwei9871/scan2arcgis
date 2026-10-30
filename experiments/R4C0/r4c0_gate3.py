"""R4-C0 Gate 3: frozen RAG variants vs M2_hybrid on dev sheets 15023 / 15041 (retrospective: 14030, 13015).
Rules: r4c0_preregistration.json gate3, parameters from gate2/gate2_freeze.json. One run per sheet.
Prediction: B2 edge probabilities (existing R4-B2 predictions) + RGB image only. Labels read only for scoring.
Usage: r4c0_gate3.py <sheet> <status> <B2_pred_dir> <M2_hybrid_regions.npy> <out_json> <local_dir>   (.venv-ml)
"""
import json, sys, time
from pathlib import Path
import cv2, numpy as np

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "R4A"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "R4B1T"))
import r4c0_rag as R  # noqa: E402
import r4a2_2_eval as EV  # noqa: E402
import r4b1t_width as W  # noqa: E402
from r4b1t_labels import ink_masks, lab_image  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
FZ = json.load(open(ROOT / "experiments/R4C0/gate2/gate2_freeze.json"))
assert FZ["candidate"] == "B2"


def per_instance(reg, i1, V, ids, area):
    C = R.overlaps(reg, i1, V); ra = np.bincount(reg[V].ravel(), minlength=int(reg.max()) + 1)
    s, g, x = C.row, C.col, C.data
    iou = x / (ra[s] + area[g] - x); best = np.zeros(int(i1.max()) + 1); np.maximum.at(best, g, iou)
    o = np.lexsort((-x, g)); f = np.unique(g[o], return_index=True)[1]
    br = np.zeros(int(i1.max()) + 1, np.int64); br[g[o][f]] = s[o][f]
    hold = x / area[g] >= 0.5; holders = np.bincount(s[hold], minlength=int(reg.max()) + 1)
    held = np.zeros(int(i1.max()) + 1, bool); held[g[hold]] = True
    return best[ids], br[ids], holders, held[ids]


def classify(oa, best, br, holders, held):
    out = np.full(len(oa), "SUCCESS", object)
    fail = best < 0.5
    out[fail & (oa < 0.5)] = "INITIAL_MIXED"
    mg = fail & (oa >= 0.5) & (holders[br] >= 2)
    out[mg] = "MERGE_ERROR"
    fr = fail & (oa >= 0.5) & ~mg & ~held
    out[fr] = "UNDER_MERGE_FRAGMENTS"
    out[fail & (oa >= 0.5) & ~mg & ~fr] = "OTHER"
    return out


def method(name, reg, Rref, S, oa):
    inst, _ = EV.instance_metrics(reg.astype(np.int64), Rref); bnd = EV.boundary_metrics(reg, Rref)
    best, br, holders, held = per_instance(reg, S["i1"], S["V"], S["ids"], S["area"])
    cls = classify(oa, best, br, holders, held)
    bins = {}
    for b, lo, hi in W.BINS:
        m = (S["wid"] >= lo) & (S["wid"] < hi)
        if m.any(): bins[b] = {"n": int(m.sum()), "recall": float((best[m] >= 0.5).mean())}
    ra = np.bincount(reg[S["V"]].ravel())
    fails = cls != "SUCCESS"
    return {"method": name, "small": inst["small"], "large": inst["large"], "all": inst["all"], "regions": inst["regions"],
            "by_width": bins, "boundary_F1": {t: bnd[t]["F1"] for t in ("tol1", "tol2", "tol3")},
            "false_boundary_share": bnd["false_boundary_share_near_neg_ink_1px"],
            "regions_holding_ge2_instances": int((holders >= 2).sum()),
            "largest_region_px": int(ra.max()), "largest_official_instance_px": int(S["area"][1:].max()),
            "catastrophic_merge": bool(ra.max() > 1.5 * S["area"][1:].max()),
            "failure_decomposition": {k: int((cls == k).sum()) for k in ("INITIAL_MIXED", "MERGE_ERROR", "UNDER_MERGE_FRAGMENTS", "OTHER")},
            "failure_share": {k: round(float((cls == k).sum() / max(fails.sum(), 1)), 4) for k in ("INITIAL_MIXED", "MERGE_ERROR", "UNDER_MERGE_FRAGMENTS", "OTHER")}}, best, cls


def main(sheet, status, b2_dir, m2_regions, out_json, local_dir):
    loc = Path(local_dir); loc.mkdir(parents=True, exist_ok=True); t0 = time.time()
    d = Path(b2_dir); P = {"pr": np.load(d / "prob_right.npy"), "pd": np.load(d / "prob_down.npy")}
    b, sr, sd = R.strengths("B2", P); lab = R.overseg(b); rag = R.build_rag(lab, sr, sd)
    bgr = cv2.imread(str(ROOT / "runs/r4a2" / sheet / "geotiff_rgb.png")); _, ink1, _ = ink_masks(bgr)
    cs, cc = R.region_colour(lab, lab_image(bgr), ink1)
    fb, fa = FZ["RAG_BOUNDARY_ONLY"], FZ["RAG_BOUNDARY_APPEARANCE"]
    reg_b = R.partitions(rag["n"], R.merge(rag, stop=fb["tau"]), [np.inf])[np.inf][lab]
    reg_a = R.partitions(rag["n"], R.merge(rag, cs, cc, lam=fa["lambda"], stop=fa["tau"]), [np.inf])[np.inf][lab]
    t_pred = time.time() - t0
    np.save(loc / f"{sheet}_RAG_BOUNDARY_ONLY.npy", reg_b.astype(np.int32)); np.save(loc / f"{sheet}_RAG_BOUNDARY_APPEARANCE.npy", reg_a.astype(np.int32))
    # ---- scoring (reads labels) ----
    Rref = EV.load_ref(sheet); unit = np.load(ROOT / "runs/r4a2" / sheet / "unit.npy")
    V = (Rref["ignore"] == 0) & (unit >= 0); i1, area, ids, wid = W.canonical_widths(Rref["instance"], V)
    S = {"V": V, "i1": i1, "area": area, "ids": ids, "wid": wid}
    oa = R.oracle_A(lab, i1, V, ids)
    m2 = np.load(m2_regions)
    res = {"sheet": sheet, "status": status, "frozen": FZ, "initial_regions": int(lab.max()), "prediction_seconds": round(t_pred, 1),
           "initial_oracle_A_small_recall": float((oa >= 0.5).mean())}
    res["M2_hybrid"], best_m, _ = method("M2_hybrid", m2, Rref, S, oa)
    res["RAG_BOUNDARY_ONLY"], best_b, cls_b = method("RAG_BOUNDARY_ONLY", reg_b, Rref, S, oa)
    res["RAG_BOUNDARY_APPEARANCE"], best_a, cls_a = method("RAG_BOUNDARY_APPEARANCE", reg_a, Rref, S, oa)
    res["appearance_effect"] = {"PREVENTED_MERGE": int(((best_a >= 0.5) & (cls_b == "MERGE_ERROR")).sum()),
                                "CAUSED_SPLIT": int(((best_b >= 0.5) & (cls_a == "UNDER_MERGE_FRAGMENTS")).sum()),
                                "recovered_only_by_appearance": int(((best_a >= 0.5) & (best_b < 0.5)).sum()),
                                "recovered_only_by_boundary_only": int(((best_b >= 0.5) & (best_a < 0.5)).sum())}
    base = res["M2_hybrid"]
    for k in ("RAG_BOUNDARY_ONLY", "RAG_BOUNDARY_APPEARANCE"):
        r = res[k]
        r["vs_M2_hybrid"] = {"small_recall": r["small"]["recall_iou50"] - base["small"]["recall_iou50"],
                             "small_over_seg": r["small"]["over_seg"] - base["small"]["over_seg"],
                             "large_recall": r["large"]["recall_iou50"] - base["large"]["recall_iou50"]}
        v = r["vs_M2_hybrid"]
        r["gate3_criteria"] = {"recall_gain_ge_0.03": v["small_recall"] >= 0.03, "over_seg_increase_le_0.03": v["small_over_seg"] <= 0.03,
                               "large_drop_le_0.05": v["large_recall"] >= -0.05, "no_catastrophic_merge": not r["catastrophic_merge"]}
        r["gate3_pass_on_sheet"] = all(r["gate3_criteria"].values())
    json.dump(res, open(out_json, "w"), indent=1, default=float)
    f = lambda k: (round(res[k]["small"]["recall_iou50"], 4), round(res[k]["small"]["over_seg"], 4), {b: round(v["recall"], 3) for b, v in res[k]["by_width"].items()})
    print(sheet, status, "M2h", f("M2_hybrid"), "RAG_B", f("RAG_BOUNDARY_ONLY"), "RAG_A", f("RAG_BOUNDARY_APPEARANCE"),
          "pass", res["RAG_BOUNDARY_ONLY"]["gate3_pass_on_sheet"], res["RAG_BOUNDARY_APPEARANCE"]["gate3_pass_on_sheet"], flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:7])
