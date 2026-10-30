"""ARCH-2 task 2: re-measure graded subdivision size with the corrected arch2_subdivision.graded (ORACLE stand-in:
official narrow instances of canonical width < 10 px as candidates, exactly as ARCH-1 Gate 4). Not an autonomous
C-PAIR result. Compares pair-level dedup, region-level dedup and the ARCH-1 (defective) numbers.
Usage: arch2_subdivision_recheck.py <out_json>   (.venv-ml)
"""
import json, sys, time
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent)); sys.path.insert(0, str(ROOT / "experiments/ARCH1"))
import arch2_subdivision as S  # noqa: E402
import arch1_feats as F  # noqa: E402
R = F.R


def main(out):
    old = json.load(open(ROOT / "experiments/ARCH1/gate4/gate4_subdivision.json"))["per_sheet"]; res = {"label": "ORACLE stand-in sizing; not a C-PAIR result", "per_sheet": {}}
    for c in F.TRAIN + F.EXPOSED:
        X = F.load_inputs(c); Rr, V, i1, ia, ids, wid = F.label_ref(c)
        lab = F.compact(F.initial_regions(c, X)).astype(np.int32)
        nm = np.zeros(int(i1.max()) + 1, np.int64); nar = ids[wid < 10]; nm[nar] = nar
        m36 = (wid >= 3) & (wid < 6); m610 = (wid >= 6) & (wid < 10); oa0 = R.oracle_A(lab, i1, V, ids)
        row = {"B2_regions": int(lab.max()), "arch1_defective_ratio": old[c]["GRADED_ORACLE"]["ratio_to_B2"], "n_3_6": int(m36.sum()), "n_6_10": int(m610.sum()),
               "B2_oracleA_3_6": round(float((oa0[m36] >= 0.5).mean()), 4) if m36.any() else None}
        for name, fn in (("pair_dedup", S.graded), ("region_dedup", S.graded_region)):
            t0 = time.time(); g, info, _ = fn(lab, nm[i1]); t = time.time() - t0
            oa = R.oracle_A(g, i1, V, ids)
            row[name] = {"regions": int(g.max()), "ratio": round(g.max() / lab.max(), 3), "seconds": round(t, 2), **info,
                         "oracleA_3_6": round(float((oa[m36] >= 0.5).mean()), 4) if m36.any() else None,
                         "oracleA_6_10": round(float((oa[m610] >= 0.5).mean()), 4) if m610.any() else None}
        res["per_sheet"][c] = row
        print(c, res["per_sheet"][c], flush=True)
    P = res["per_sheet"]; res["summary"] = {}
    for name in ("pair_dedup", "region_dedup"):
        r = [v[name]["ratio"] for v in P.values()]
        pool = lambda grp, key, nk: sum((v[name][key] or 0) * v[nk] for c, v in P.items() if c in grp) / max(sum(v[nk] for c, v in P.items() if c in grp), 1)
        res["summary"][name] = {"ratio_median": float(np.median(r)), "ratio_max": float(max(r)), "within_3x_all": all(x <= 3 for x in r),
                                "oracleA_3_6_train": round(pool(F.TRAIN, "oracleA_3_6", "n_3_6"), 4), "oracleA_3_6_exposed": round(pool(F.EXPOSED, "oracleA_3_6", "n_3_6"), 4),
                                "oracleA_6_10_train": round(pool(F.TRAIN, "oracleA_6_10", "n_6_10"), 4), "oracleA_6_10_exposed": round(pool(F.EXPOSED, "oracleA_6_10", "n_6_10"), 4)}
    json.dump(res, open(out, "w"), indent=1); print(res["summary"])


if __name__ == "__main__":
    main(sys.argv[1])
