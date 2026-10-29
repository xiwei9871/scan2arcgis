"""R4-B1T Gate 1: candidate A (narrow soft target) vs v2, theoretical loss optimum (rules: r4b1t_preregistration.json gate1_A).
10 training sheets, labels only. No model output, no training.
Usage: r4b1t_gate1.py <out_dir>   (.venv-ml)
"""
import csv, json, sys
from pathlib import Path
import cv2, numpy as np
from scipy import ndimage as ndi
from scipy.sparse import coo_matrix
from skimage.segmentation import watershed

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "R4A"))
import r4b1t_width as W  # noqa: E402
import r4b1t_labels as L  # noqa: E402
from r4a2_1_seeds import hybrid_markers, segment  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
TRAIN = json.load(open(ROOT / "experiments/R4A/r4a2/freeze_config.json"))["data_roles"]["train"]


def m1_rule(p):
    n, cc, st, _ = cv2.connectedComponentsWithStats((p < 0.3).astype(np.uint8), connectivity=8)
    keep = np.zeros(n, bool); keep[1:] = st[1:, cv2.CC_STAT_AREA] >= 50
    return watershed(p.astype(np.float32), (np.cumsum(keep) * keep)[cc].astype(np.int32))


def recovered(i1, reg, valid, ids, area):
    m = valid & (i1 > 0) & (reg > 0)
    C = coo_matrix((np.ones(int(m.sum())), (i1[m], reg[m])), shape=(int(i1.max()) + 1, int(reg.max()) + 1)).tocsr().tocoo()
    ra = np.bincount(np.where(valid, reg, 0).ravel(), minlength=int(reg.max()) + 1)
    iou = C.data / (area[C.row] + ra[C.col] - C.data); best = np.zeros(int(i1.max()) + 1); np.maximum.at(best, C.row, iou)
    return best[ids] >= 0.5


def per_sheet(code):
    d0 = ROOT / "runs/r4a2" / code
    inst = np.load(d0 / "instance.npy"); unit = np.load(d0 / "unit.npy"); ign = np.load(d0 / "ignore.npy")
    ub = np.load(d0 / "unit_boundary.npy") > 0; d = np.load(d0 / "dist.npy").astype(np.float32)
    valid = (ign == 0) & (unit >= 0)
    i1, area, ids, wid = W.canonical_widths(inst, valid); objs = ndi.find_objects(i1, max_label=int(i1.max()))
    P = {"v2": L.pstar(L.target_v2(d)), "A": L.pstar(L.target_A(d))}
    rec = {k: recovered(i1, m1_rule(p), valid, ids, area) for k, p in P.items()}
    rec["M2_hybrid_official_dist"] = recovered(i1, segment(d, hybrid_markers(d)), valid, ids, area)
    rows = []
    for j, k in enumerate(ids):
        sl = objs[k - 1]; m = i1[sl] == k
        r = {"sheet": code, "instance": int(k - 1), "area_px": int(area[k]), "width_px": round(float(wid[j]), 2), "width_bin": W.width_bin(wid[j]),
             "ub_share_of_area": round(float((ub[sl] & m).sum() / area[k]), 4),
             "rec_M2_hybrid_official_dist": bool(rec["M2_hybrid_official_dist"][j])}
        for name, p in P.items():
            hi = (p[sl] > 0.5) & m; inner = m & ~hi
            cc = ndi.label(inner, structure=[[0, 1, 0], [1, 1, 1], [0, 1, 0]])[0]
            r.update({f"{name}_flood_share": round(float(hi.sum() / area[k]), 4), f"{name}_flooded90": bool(hi.sum() >= 0.9 * area[k]),
                      f"{name}_interior_px": int(inner.sum()), f"{name}_interior_cc_max": int(np.bincount(cc.ravel())[1:].max()) if inner.any() else 0,
                      f"{name}_rec_M1_rule": bool(rec[name][j])})
        rows.append(r)
    return rows


def summarize(rows):
    out = {}
    for b, _, _ in W.BINS:
        rs = [r for r in rows if r["width_bin"] == b]
        if not rs: continue
        o = {"n": len(rs), "ub_share_of_area_mean": round(float(np.mean([r["ub_share_of_area"] for r in rs])), 4),
             "rec_M2_hybrid_official_dist_same_for_both": round(float(np.mean([r["rec_M2_hybrid_official_dist"] for r in rs])), 4)}
        for name in ("v2", "A"):
            o[name] = {"flood_share_pixels": round(sum(r[f"{name}_flood_share"] * r["area_px"] for r in rs) / sum(r["area_px"] for r in rs), 4),
                       "flooded90_instances": round(float(np.mean([r[f"{name}_flooded90"] for r in rs])), 4),
                       "interior_px_median": float(np.median([r[f"{name}_interior_px"] for r in rs])),
                       "interior_cc_max_median": float(np.median([r[f"{name}_interior_cc_max"] for r in rs])),
                       "instances_interior_cc_ge50": round(float(np.mean([r[f"{name}_interior_cc_max"] >= 50 for r in rs])), 4),
                       "rec_M1_rule_on_pstar": round(float(np.mean([r[f"{name}_rec_M1_rule"] for r in rs])), 4)}
        out[b] = o
    return out


def main(out_dir):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True); rows = []
    for c in TRAIN:
        r = per_sheet(c); rows += r
        s = summarize(r).get("3-6")
        print(c, len(r), "3-6:", None if s is None else (s["n"], s["v2"]["flooded90_instances"], s["A"]["flooded90_instances"], s["v2"]["rec_M1_rule_on_pstar"], s["A"]["rec_M1_rule_on_pstar"]), flush=True)
    with open(out / "gate1_instances.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    res = {"definition_A": "t_A = exp(-d^2 / (2 * 0.5^2)), d <= 1 px; p* = 4t/(3t+1)", "definition_v2": "t = exp(-d^2/2), d <= 2 px",
           "note": "theoretical loss optimum on official labels, NOT a model result; M2_hybrid recovery on official dist is identical for v2 and A (distance target unchanged)",
           "by_width_bin": summarize(rows), "by_sheet": {c: summarize([r for r in rows if r["sheet"] == c]) for c in TRAIN}}
    json.dump(res, open(out / "gate1_candidate_A.json", "w"), indent=1)
    print(json.dumps(res["by_width_bin"], indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
