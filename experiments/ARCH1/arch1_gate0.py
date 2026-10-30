"""ARCH-1 Gate 0: D3 recount with strict pair positions next to the 1-pair-tolerance numbers of ARCH-0.
Same definitions as experiments/ARCH0/arch0_diag.d3_sheet; 'two_sided' grouping uses official neighbour instances
(truth-assisted), which is NOT autonomous line-pair detection.
Usage: arch1_gate0.py <out_json>   (.venv-ml)
"""
import json, sys
from pathlib import Path
import numpy as np
from scipy import ndimage as ndi

ROOT = Path(__file__).resolve().parents[2]
for p in ("ARCH0", "R4B2", "R4B1T", "R4A"): sys.path.insert(0, str(ROOT / "experiments" / p))
import arch0_diag as A  # noqa: E402
import r4b2_edges as E  # noqa: E402
import r4b1t_width as W  # noqa: E402


def sheet(code, tol):
    Rr, unit, V = A.ref(code); i1, area, ids, wid = W.canonical_widths(Rr["instance"], V)
    P = A.pdir(code) / "B2"; pr, pd = np.load(P / "prob_right.npy").astype(np.float32), np.load(P / "prob_down.npy").astype(np.float32)
    er, ed, _, _ = E.edges_from_labels(unit, V)
    cr, cd = (pr > 0.5), (pd > 0.5)
    if tol: k3 = np.ones((3, 3), bool); cr, cd = ndi.binary_dilation(cr, k3), ndi.binary_dilation(cd, k3)
    N = int(i1.max()) + 1; A_, B_, C_ = [], [], []
    for a, b, e, c in ((i1[:, :-1], i1[:, 1:], er[:, :-1], cr[:, :-1]), (i1[:-1], i1[1:], ed[:-1], cd[:-1])):
        m = e & (a > 0) & (b > 0); A_ += [a[m], b[m]]; B_ += [b[m], a[m]]; C_ += [c[m], c[m]]
    a, b, c = np.concatenate(A_), np.concatenate(B_), np.concatenate(C_).astype(float)
    uk, inv = np.unique(a * N + b, return_inverse=True); tot = np.bincount(inv); cov = np.bincount(inv, weights=c); ki = uk // N
    rows = []
    for g in ids[(wid >= 3) & (wid < 6)]:
        s = ki == g
        if not s.any(): continue
        t, cv = tot[s], cov[s]; o = np.argsort(-t); share = t[o] / t.sum(); two = len(o) >= 2 and share[1] >= 0.25
        rows.append({"overall": float(cv.sum() / t.sum()), "two": bool(two), "minside": float(min(cv[o[0]] / t[o[0]], cv[o[1]] / t[o[1]])) if two else None})
    return rows


def main(out):
    res = {"note": "two-sided grouping is truth-assisted (official neighbour instances); not autonomous line-pair detection"}
    for g, codes in (("train", A.TRAIN), ("exposed", A.EXPOSED)):
        for tag, tol in (("tol1_pair", True), ("strict", False)):
            rows = [r for c in codes for r in sheet(c, tol)]; two = [r for r in rows if r["two"]]
            both = sum(r["minside"] >= 0.8 for r in two)
            res[f"{g}|{tag}"] = {"narrow_3_6": len(rows), "median_overall_cov": float(np.median([r["overall"] for r in rows])),
                                 "share_overall_ge_0_8": float(np.mean([r["overall"] >= 0.8 for r in rows])),
                                 "two_sided_identifiable": len(two), "both_sides_ge_0_8": int(both),
                                 "both_sides_ge_0_8_share_of_all_narrow": round(both / max(len(rows), 1), 4)}
            print(g, tag, res[f"{g}|{tag}"], flush=True)
    json.dump(res, open(out, "w"), indent=1)


if __name__ == "__main__":
    main(sys.argv[1])
