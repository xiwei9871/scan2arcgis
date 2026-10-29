"""R4-A2.2 unified evaluation (freeze_config.json "metrics", unchanged) for M0/M1/M2 region maps.

Same grid (each sheet's GeoTIFF grid), same valid area (ignore.npy == 0), same reference labels
(instance.npy, unit.npy, unit_boundary.npy, printed_contact.npy, low_ink_boundary.npy, neg_candidate.npy).
Region map convention: int, 0 = no region; IoU and boundaries are computed inside the valid area only.

Instances: small 200 <= area < 20000 px (primary: class-agnostic IoU >= 0.5 recall), tiny < 200, large >= 20000.
  under_seg   best-overlap region covers >= 50% of the instance, IoU < 0.5, region > 2x instance
  over_seg    no single region covers >= 50% of the instance
  absorbed    best-overlap region's majority instance is a different, larger instance adjacent to this one
Thin units: estimated width = 2 * max(dist to UNIT_BOUNDARY inside the instance) + 1, bins <3, 3-6, 6-10, >=10 px.
Boundary: region boundary (both sides of each region change, like UNIT_BOUNDARY) P/R/F1 at 1/2/3 px;
  recall vs PRINTED_CONTACT and LOW_INK_BOUNDARY; false-boundary share = predicted px within 1 px of neg_candidate ink.
Upper bounds (evaluation only): oracle majority-unit mIoU (each region gets its majority geo_A unit) and
  Hungarian 1:1 region-instance mean IoU.
Probability diagnostics (optional prob.npy): P/R/F1 of p > thr vs UNIT_BOUNDARY for thr 0.1..0.9 - diagnostic
  curve only; headline thresholds are the frozen 0.5 (v1) and 0.8 (v2 gate).
Usage: r4a2_2_eval.py <code> <regions.npy> <out.json> [prob.npy]
"""
import json, sys
from pathlib import Path
import cv2, numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.sparse import coo_matrix

ROOT = Path(__file__).resolve().parents[2]


def load_ref(code):
    d = ROOT / "runs/r4a2" / code
    R = {k: np.load(d / f"{k}.npy") for k in ("instance", "unit", "unit_boundary", "printed_contact", "low_ink_boundary", "neg_candidate", "ignore", "dist")}
    R["valid"] = (R["ignore"] == 0) & (R["unit"] >= 0)
    return R


def both_side_boundary(lab, valid):
    b = np.zeros(lab.shape, bool)
    h = (lab[:, 1:] != lab[:, :-1]) & valid[:, 1:] & valid[:, :-1]; b[:, 1:] |= h; b[:, :-1] |= h
    v = (lab[1:] != lab[:-1]) & valid[1:] & valid[:-1]; b[1:] |= v; b[:-1] |= v
    return b & valid


def prf(pred, gt, tol):
    if pred.sum() == 0 or gt.sum() == 0: return {"P": None, "R": None, "F1": None}
    dg = cv2.distanceTransform((~gt).astype(np.uint8), cv2.DIST_L2, 3); dp = cv2.distanceTransform((~pred).astype(np.uint8), cv2.DIST_L2, 3)
    P = float((dg[pred] <= tol).mean()); R = float((dp[gt] <= tol).mean())
    return {"P": P, "R": R, "F1": 2 * P * R / (P + R) if P + R else 0.0}


def recall_only(pred, gt, tol):
    if gt.sum() == 0: return None
    dp = cv2.distanceTransform((~pred).astype(np.uint8), cv2.DIST_L2, 3)
    return float((dp[gt > 0] <= tol).mean())


def overlap(a, b, valid):
    """Sparse overlap counts between labels a (instances, 0-based shifted to 1..) and b (regions 1..)."""
    m = valid & (a > 0) & (b > 0)
    C = coo_matrix((np.ones(int(m.sum()), np.int64), (a[m], b[m])), shape=(int(a.max()) + 1, int(b.max()) + 1)).tocsr()
    C.sum_duplicates()
    return C


def adjacency(inst1, valid):
    pairs = set()
    for a, b in ((inst1[:, 1:], inst1[:, :-1]), (inst1[1:], inst1[:-1])):
        m = (a != b) & (a > 0) & (b > 0)
        for x, y in np.unique(np.stack([a[m], b[m]], 1), axis=0): pairs.add((int(x), int(y))); pairs.add((int(y), int(x)))
    return pairs


def instance_metrics(reg, R):
    valid = R["valid"]; inst1 = np.where(valid, R["instance"] + 1, 0).astype(np.int64); reg = np.where(valid, reg, 0).astype(np.int64)
    n = int(inst1.max()); nr = int(reg.max())
    ia = np.bincount(inst1.ravel(), minlength=n + 1); ra = np.bincount(reg.ravel(), minlength=nr + 1)
    C = overlap(inst1, reg, valid).tocoo()
    i, r, c = C.row, C.col, C.data
    iou = c / (ia[i] + ra[r] - c)
    best_iou = np.zeros(n + 1); np.maximum.at(best_iou, i, iou)
    cov = c / ia[i]; best_cov = np.zeros(n + 1); np.maximum.at(best_cov, i, cov)
    # best-overlap region per instance (largest intersection)
    order = np.lexsort((-c, i)); first = np.unique(i[order], return_index=True)[1]
    best_r = np.zeros(n + 1, np.int64); best_r[i[order][first]] = r[order][first]
    best_c = np.zeros(n + 1); best_c[i[order][first]] = c[order][first]
    # majority instance of each region
    o2 = np.lexsort((-c, r)); f2 = np.unique(r[o2], return_index=True)[1]
    maj = np.zeros(nr + 1, np.int64); maj[r[o2][f2]] = i[o2][f2]
    adj = adjacency(inst1, valid)
    maxd = np.zeros(n + 1, np.float32); np.maximum.at(maxd, inst1.ravel(), np.where(valid, R["dist"], 0).ravel().astype(np.float32))
    width = 2 * maxd + 1
    ids = np.arange(1, n + 1); area = ia[1:]
    hit = best_iou[1:] >= 0.5
    under = (best_cov[1:] >= 0.5) & ~hit & (ra[best_r[1:]] > 2 * area)
    over = best_cov[1:] < 0.5
    absorbed = np.array([(maj[best_r[k]] != k) and (ia[maj[best_r[k]]] > ia[k]) and ((k, int(maj[best_r[k]])) in adj) if best_r[k] > 0 else False for k in ids])
    groups = {"small": (area >= 200) & (area < 20000), "tiny": area < 200, "large": area >= 20000, "all": area > 0}
    out = {}
    for g, m in groups.items():
        out[g] = {"n": int(m.sum()), "recall_iou50": float(hit[m].mean()) if m.any() else None}
        if g == "small":
            out[g].update(under_seg=float(under[m].mean()), over_seg=float(over[m].mean()), absorbed_by_larger_neighbour=float(absorbed[m].mean()),
                          mean_best_iou=float(best_iou[1:][m].mean()))
    sm = groups["small"]
    out["small_by_width"] = {}
    for name, lo, hi in (("lt3px", 0, 3), ("3-6px", 3, 6), ("6-10px", 6, 10), ("ge10px", 10, 1e9)):
        m = sm & (width[1:] >= lo) & (width[1:] < hi)
        out["small_by_width"][name] = {"n": int(m.sum()), "recall_iou50": float(hit[m].mean()) if m.any() else None,
                                       "absorbed": float(absorbed[m].mean()) if m.any() else None, "over_seg": float(over[m].mean()) if m.any() else None}
    # regions
    rv = ra[1:]
    out["regions"] = {"n_pred": int((rv > 0).sum()), "n_truth_instances": n, "n_pred_lt_50px": int(((rv > 0) & (rv < 50)).sum())}
    # Hungarian 1:1 region-instance (geometry upper bound) and oracle majority-unit mIoU
    M = coo_matrix((iou, (i - 1, r - 1)), shape=(n, nr)).tocsr()
    big = (ia[1:] >= 200)
    rows = np.flatnonzero(big)
    if len(rows) and nr:
        cols = np.unique(M[rows].tocoo().col)
        D = M[rows][:, cols].toarray()
        a, b = linear_sum_assignment(-D)
        out["hungarian_instance_mean_iou_area_ge200"] = float(D[a, b].sum() / len(rows))
    unit = np.where(valid, R["unit"], -1).astype(np.int64)
    mu = unit >= 0; nu = int(unit.max()) + 1
    U = coo_matrix((np.ones(int((mu & (reg > 0)).sum())), (reg[mu & (reg > 0)], unit[mu & (reg > 0)])), shape=(nr + 1, nu)).tocsr().toarray()
    lab_of_reg = U.argmax(1); orac = np.where(reg > 0, lab_of_reg[reg], -1)
    ious = []
    for k in range(nu):
        g = unit == k; p = orac == k
        if g.sum(): ious.append((g & p).sum() / (g | p).sum())
    out["oracle_majority_unit_miou"] = float(np.mean(ious))
    return out, {"hit": hit, "absorbed": absorbed, "over": over, "under": under, "small": sm, "width": width[1:], "best_r": best_r[1:], "maj": maj}


def boundary_metrics(reg, R):
    valid = R["valid"]; pb = both_side_boundary(np.where(valid, reg, -1), valid); gb = R["unit_boundary"] > 0
    out = {f"tol{t}": prf(pb, gb & valid, t) for t in (1, 2, 3)}
    out["recall_printed_contact_tol2"] = recall_only(pb, R["printed_contact"] & valid, 2)
    out["recall_low_ink_tol2"] = recall_only(pb, R["low_ink_boundary"] & valid, 2)
    dn = cv2.distanceTransform((R["neg_candidate"] == 0).astype(np.uint8), cv2.DIST_L2, 3)
    out["false_boundary_share_near_neg_ink_1px"] = float((dn[pb] <= 1).mean()) if pb.any() else None
    out["pred_boundary_px"] = int(pb.sum()); out["truth_boundary_px"] = int((gb & valid).sum())
    return out


def prob_curve(prob, R):
    valid = R["valid"]; gb = (R["unit_boundary"] > 0) & valid; res = {}
    for th in (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9):
        p = (prob > th) & valid
        res[f"{th}"] = {f"tol{t}": prf(p, gb, t) for t in (1, 2, 3)}
    return res


def main(code, regions, out_json, prob=None):
    R = load_ref(code); reg = np.load(regions).astype(np.int64)
    assert reg.shape == R["valid"].shape, (reg.shape, R["valid"].shape)
    inst, _ = instance_metrics(reg, R)
    res = {"sheet": code, "regions_file": str(regions), "valid_px": int(R["valid"].sum()), "instances": inst, "boundary": boundary_metrics(reg, R)}
    if prob:
        res["prob_boundary_diagnostic_curve"] = prob_curve(np.load(prob).astype(np.float32), R)
        res["prob_curve_note"] = "diagnostic only; not used to choose any threshold. Frozen headline thresholds: 0.5 (v1), 0.8 (v2 gate)"
    json.dump(res, open(out_json, "w"), indent=1)
    s = inst["small"]
    print(code, Path(regions).stem, "small recall", round(s["recall_iou50"], 3), "under", round(s["under_seg"], 3), "over", round(s["over_seg"], 3),
          "absorbed", round(s["absorbed_by_larger_neighbour"], 3), "large", inst["large"]["recall_iou50"], "regions", inst["regions"],
          "bF1", [None if res["boundary"][f"tol{t}"]["F1"] is None else round(res["boundary"][f"tol{t}"]["F1"], 3) for t in (1, 2, 3)], flush=True)
    return res


if __name__ == "__main__":
    main(*sys.argv[1:4], *(sys.argv[4:5] or []))
