"""ARCH-2 Gate 1: C-PAIR candidate generation (rules: arch2_preregistration.json gate1 + amendment 1 P0_2).
Prediction: C-PAIR on B2 probabilities + RGB only. Labels only for matching / Oracle A / B.
All candidates (no discrimination) are added to the graded subdivision (region-level dedup) -> V1 initial regions.
Per sheet: detection (one-to-one, IoU >= 0.3) per canonical width group, matched IoU quartiles, class counts,
Oracle A / B of 3-6 and 6-10 px instances on B2-only and on the graded subdivision, regions ratio, seconds, peak RSS.
Usage: arch2_gate1.py <train|exposed> <out_dir>   (.venv-ml)
"""
import json, pickle, resource, sys, time
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import arch2_common as A  # noqa: E402
F, R, M, G3 = A.F, A.R, A.M, A.G3


def oracle(lab, L, sel):
    oa = R.oracle_A(lab, L["i1"], L["V"], L["ids"][sel])
    ob = G3.per_instance(R.oracle_B_regions(lab, L["i1"], L["V"])[0], L["i1"], L["V"], L["ids"][sel], L["ia"])[0]
    return int((oa >= 0.5).sum()), int((ob >= 0.5).sum())


def sheet(code):
    t0 = time.time(); X, g, base = A.prediction_part(code); t_gen = time.time() - t0
    t1 = time.time(); lab, info, kept = A.subdivide(base, g["cand"]); t_sub = time.time() - t1
    L = A.label_part(code, X, g)
    (A.LOCAL / "gate1").mkdir(parents=True, exist_ok=True)
    pickle.dump({"cand": g["cand"], "feats": g["feats"], "K": g["K"], "cls": L["cls"], "match": L["match"]},
                open(A.LOCAL / "gate1" / f"{code}_cpair.pkl", "wb"))
    wid, ids = L["wid"], L["ids"]; matched_inst = set(L["match"].values())
    cand_sz = np.bincount(g["cand"].ravel(), minlength=g["K"] + 1)
    out = {"K": g["K"], "n_skeleton": g["n_skeleton"], "pairs": int(len(g["pairs"]["t"])), "bridged_pairs": int(g["pairs"]["bridged"].sum()),
           "missing_colour": int(np.isnan(g["feats"]["s_colour"]).sum()) if g["K"] else 0,
           "class_counts": {k: sum(v == k for v in L["cls"].values()) for k in ("TRUE_NARROW", "INK_BAND", "INCIDENTAL")},
           "B2_regions": int(base.max()), "graded_regions": int(lab.max()), "regions_ratio": round(lab.max() / base.max(), 4),
           "subdivision": info, "seconds": {"generate": round(t_gen, 1), "subdivide": round(t_sub, 2)}}
    ia = L["ia"]; i1 = L["i1"]; iou = {}
    for c, gi in L["match"].items():
        m = g["cand"] == c; inter = int((m & (i1 == gi)).sum()); iou[gi] = inter / (cand_sz[c] + ia[gi] - inter)
    for name, lo, hi in (("3-6", 3, 6), ("6-10", 6, 10)):
        sel = (wid >= lo) & (wid < hi)
        n = int(sel.sum()); det = sum(int(k) in matched_inst for k in ids[sel])
        q = [iou[int(k)] for k in ids[sel] if int(k) in iou]
        a0, b0 = oracle(base, L, sel) if n else (0, 0); a1, b1 = oracle(lab, L, sel) if n else (0, 0)
        out[name] = {"n": n, "detected": det, "matched_iou_quartiles": [float(x) for x in np.percentile(q, [25, 50, 75])] if q else None,
                     "B2_oracleA": a0, "B2_oracleB": b0, "graded_oracleA": a1, "graded_oracleB": b1}
    out["peak_rss_gb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e9, 2)
    return out


def main(group, out_dir):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    codes = F.TRAIN if group == "train" else F.EXPOSED
    res = {"group": group, "per_sheet": {}}
    for c in codes:
        res["per_sheet"][c] = s = sheet(c)
        print(c, {k: s[k] for k in ("K", "class_counts", "regions_ratio")}, s["3-6"], s["6-10"], s["seconds"], flush=True)
    P = res["per_sheet"].values(); pool = {}
    for w in ("3-6", "6-10"):
        n = sum(p[w]["n"] for p in P)
        pool[w] = {"n": n, **{k: M.prop(sum(p[w][k] for p in P), n) for k in ("detected", "B2_oracleA", "B2_oracleB", "graded_oracleA", "graded_oracleB")}}
    res["pooled"] = pool
    am = A.AM["P0_2_gate1_thresholds"]; base = am["b2_only_oracleA_3_6"]
    oa = pool["3-6"]["graded_oracleA"]["value"] or 0.0
    ratio_ok = all(p["regions_ratio"] <= 3 for p in P)
    if group == "train":
        cond = {"pooled_3_6_oracleA_ge_0.65": oa >= 0.65, "pooled_gain_ge_0.10": oa >= base["training_pooled"] + 0.10, "regions_le_3x_every_sheet": ratio_ok}
    else:
        cond = {"pooled_3_6_oracleA_ge_0.74": oa >= 0.74 and oa >= base["exposed_pooled"] + 0.10, "regions_le_3x_every_sheet": ratio_ok}
        for c in codes:
            p = res["per_sheet"][c]["3-6"]; v = p["graded_oracleA"] / max(p["n"], 1)
            cond[f"{c}_3_6_oracleA_ge_{max(0.65, base[c] + 0.10):.4f}"] = v >= max(0.65, base[c] + 0.10)
    res["gate1_conditions"] = cond; res["gate1_pass"] = all(cond.values())
    json.dump(res, open(out / f"gate1_{group}.json", "w"), indent=1, default=float)
    print(json.dumps(pool), cond, "PASS" if res["gate1_pass"] else "FAIL")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
