"""ARCH-1 Gate 1: evidence value audit (rules: arch1_criteria.json gate1). Training (in-sample) + exposed 13014 / 15076.
Region tasks use RAG_BOUNDARY_ONLY final regions < 200 px:
  T1  TRUE_SMALL (positive) vs PSEUDO, predicted width < 10 px
  T3  TRUE_SMALL (positive) vs PSEUDO, all regions < 200 px
Border tasks use the B2 INITIAL regions (where merge decisions are taken); a border is labelled from the majority
official instance of the two regions (purity >= 0.7 on both sides, else skipped):
  T2  borders touching a region whose majority instance is SMALL: DIFF (must stay separate, positive) vs SAME
  T4  borders between regions whose majority instances are both LARGE (>= 20000 px): DIFF (positive) vs SAME
Width groups: T1 / T3 by predicted width of the region; T2 by canonical width of the small instance (grouping only).
For every feature: AUC (P(positive scores higher)), direction, threshold fixed on TRAINING sheets keeping 95% of the
positive class, then precision / recall / FPR on training and exposed; per-sheet AUC min / max; base rates.
Independence: Spearman between features and phi / Jaccard between ERROR sets at those thresholds (T1 and T3).
Usage: arch1_gate1.py <out_dir>   (.venv-ml)
"""
import csv, json, sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import arch1_feats as F  # noqa: E402

RFEATS = ["b2_med", "b2_closure", "m1_mean", "m2_prob_mean", "m2_maxdist", "de", "tex_std", "tex_diff", "ink_share",
          "area", "width", "elongation", "n_neighbours", "border_len"]
BFEATS = ["b2_med", "b2_closure", "m1_mean", "m2_prob_mean", "de", "tex_diff", "ink_share", "border_len", "area"]
WG = [("le6", 0, 6), ("6-10", 6, 10), ("10-20", 10, 20), ("gt20", 20, 1e9)]


def wg(w): return next(n for n, lo, hi in WG if lo <= w < hi)


def auc(x, y):
    m = ~np.isnan(x); x, y = x[m], y[m]
    if len(y) == 0 or y.all() or (~y).all(): return None
    o = np.argsort(x, kind="mergesort"); r = np.empty(len(x)); r[o] = np.arange(1, len(x) + 1)
    _, inv, cnt = np.unique(x, return_inverse=True, return_counts=True)
    s = np.bincount(inv, weights=r); r = (s / cnt)[inv]
    n1, n0 = y.sum(), (~y).sum(); return float((r[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def sheet_rows(code):
    X = F.load_inputs(code); Rr, V, i1, ia, ids, wid = F.label_ref(code)
    reg = F.compact(F.final_regions(code, X)); RS = F.region_stats(reg, X); BS = F.border_stats(reg, X)
    maj, pur, good, sz = F.label_regions(reg, i1, V, ia)
    reg_rows = []
    for r in F.small_region_features(reg, X, RS, BS):
        k = r["region"]
        cls = "PSEUDO" if (maj[k] > 0 and ia[maj[k]] >= 5 * sz[k]) else ("TRUE_SMALL" if good[k] else None)
        if cls: reg_rows.append({**r, "sheet": code, "pos": cls == "TRUE_SMALL", "wg": wg(r["width"])})
    lab0 = F.compact(F.initial_regions(code, X)); RS0 = F.region_stats(lab0, X); BS0 = F.border_stats(lab0, X)
    maj0, pur0, _, _ = F.label_regions(lab0, i1, V, ia); bf = F.border_features(BS0, RS0)
    wmap = np.zeros(int(i1.max()) + 1); wmap[ids] = wid
    small = np.zeros(int(i1.max()) + 1, bool); small[ids] = True; large = ia >= 20000; large[0] = False
    u, v = BS0["u"], BS0["v"]; mu, mv = maj0[u], maj0[v]
    ok = (pur0[u] >= 0.7) & (pur0[v] >= 0.7) & (mu > 0) & (mv > 0)
    brd = []
    for i in np.flatnonzero(ok):
        a, b = mu[i], mv[i]; diff = a != b
        row = {f: float(bf[f][i]) for f in BFEATS}; row.update(sheet=code, pos=bool(diff))
        if small[a] or small[b]:
            s = a if small[a] else b; brd.append({**row, "task": "T2", "wg": wg(wmap[s])})
        if large[a] and large[b]: brd.append({**row, "task": "T4", "wg": "gt20"})
    return reg_rows, brd


def evaluate(train, expo, feats):
    out = {}
    for f in feats:
        xt = np.array([r[f] for r in train], float); yt = np.array([r["pos"] for r in train])
        xe = np.array([r[f] for r in expo], float); ye = np.array([r["pos"] for r in expo])
        at = auc(xt, yt)
        if at is None: out[f] = None; continue
        sgn = 1 if at >= 0.5 else -1; pos_t = sgn * xt[yt & ~np.isnan(xt)]
        thr = float(np.percentile(pos_t, 5)) if len(pos_t) else np.nan        # positive if sgn*x >= thr keeps 95% of positives
        def pr(x, y):
            m = ~np.isnan(x); p = (sgn * x[m] >= thr); yy = y[m]
            tp, fp = (p & yy).sum(), (p & ~yy).sum()
            return {"precision": float(tp / max(tp + fp, 1)), "recall": float(tp / max(yy.sum(), 1)), "fpr": float(fp / max((~yy).sum(), 1))}
        sheets = sorted({r["sheet"] for r in train + expo}); per = []
        for s in sheets:
            rr = [r for r in train + expo if r["sheet"] == s]
            a = auc(np.array([r[f] for r in rr], float), np.array([r["pos"] for r in rr]))
            if a is not None: per.append(a)
        out[f] = {"group": F.GROUP.get(f, "E-GEO"), "auc_train": at, "auc_exposed": auc(xe, ye), "direction": "high=positive" if sgn > 0 else "low=positive",
                  "threshold": thr, "train": pr(xt, yt), "exposed": pr(xe, ye) if len(ye) else None,
                  "per_sheet_auc_min": float(min(per)) if per else None, "per_sheet_auc_max": float(max(per)) if per else None}
    return out


def errors(rows, feat, ev):
    e = ev[feat]
    if e is None: return None
    sgn = 1 if e["direction"] == "high=positive" else -1
    x = np.array([r[feat] for r in rows], float); y = np.array([r["pos"] for r in rows])
    pred = sgn * np.nan_to_num(x, nan=-1e9) >= e["threshold"]
    return pred != y


def phi(a, b):
    n11, n10, n01, n00 = (a & b).sum(), (a & ~b).sum(), (~a & b).sum(), (~a & ~b).sum()
    d = np.sqrt(float((n11 + n10) * (n01 + n00) * (n11 + n01) * (n10 + n00)))
    return float((n11 * n00 - n10 * n01) / d) if d else None


def independence(rows, ev, feats):
    E = {f: errors(rows, f, ev) for f in feats if ev.get(f)}
    keys = list(E); res = {}
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            ea, eb = E[a], E[b]
            res[f"{a}|{b}"] = {"error_phi": phi(ea, eb), "error_jaccard": float((ea & eb).sum() / max((ea | eb).sum(), 1)),
                               "groups": [F.GROUP.get(a, "E-GEO"), F.GROUP.get(b, "E-GEO")]}
    return res


def main(out_dir):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    regs, brds = {}, {}
    for g, codes in (("train", F.TRAIN), ("exposed", F.EXPOSED)):
        regs[g], brds[g] = [], []
        for c in codes:
            r, b = sheet_rows(c); regs[g] += r; brds[g] += b; print(g, c, len(r), len(b), flush=True)
    res = {"note": "ARCH-1 Gate 1; base rates are of the RAG candidate set, not geological base rates", "tasks": {}}
    def task(name, tr, ex, feats):
        t = {"base_rate": {"train": {"n": len(tr), "positive_share": float(np.mean([r["pos"] for r in tr])) if tr else None},
                           "exposed": {"n": len(ex), "positive_share": float(np.mean([r["pos"] for r in ex])) if ex else None}},
             "all": evaluate(tr, ex, feats), "by_width": {}}
        for w, _, _ in WG:
            a = [r for r in tr if r["wg"] == w]; b = [r for r in ex if r["wg"] == w]
            if len(a) >= 10 and len({r["pos"] for r in a}) == 2:
                t["by_width"][w] = {"n_train": len(a), "n_exposed": len(b), "pos_train": int(sum(r["pos"] for r in a)), "pos_exposed": int(sum(r["pos"] for r in b)),
                                    "auc": {f: (lambda e: None if e is None else {"train": e["auc_train"], "exposed": e["auc_exposed"]})(v) for f, v in evaluate(a, b, feats).items()}}
        return t
    t1tr = [r for r in regs["train"] if r["width"] < 10]; t1ex = [r for r in regs["exposed"] if r["width"] < 10]
    res["tasks"]["T1_narrow_vs_ink_band"] = task("T1", t1tr, t1ex, RFEATS)
    res["tasks"]["T3_absorb_fragments"] = task("T3", regs["train"], regs["exposed"], RFEATS)
    res["tasks"]["T2_protect_from_merge"] = task("T2", [r for r in brds["train"] if r["task"] == "T2"], [r for r in brds["exposed"] if r["task"] == "T2"], BFEATS)
    res["tasks"]["T4_large_integrity"] = task("T4", [r for r in brds["train"] if r["task"] == "T4"], [r for r in brds["exposed"] if r["task"] == "T4"], BFEATS)
    for tn, rows in (("T1_narrow_vs_ink_band", t1tr + t1ex), ("T3_absorb_fragments", regs["train"] + regs["exposed"])):
        ev = res["tasks"][tn]["all"]; feats = [f for f in RFEATS if ev.get(f)]
        res["tasks"][tn]["error_independence"] = independence(rows, ev, feats)
        X = np.array([[r[f] for f in feats] for r in rows], float); Xr = np.argsort(np.argsort(np.nan_to_num(X), 0), 0).astype(float)
        cm = np.corrcoef(Xr.T); res["tasks"][tn]["spearman"] = {f"{a}|{b}": float(cm[i, j]) for i, a in enumerate(feats) for j, b in enumerate(feats) if j > i}
    json.dump(res, open(out / "gate1_evidence_audit.json", "w"), indent=1, default=float)
    with open(out / "gate1_matrix.csv", "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["task", "width_group", "feature", "group", "auc_train", "auc_exposed"])
        for tn, t in res["tasks"].items():
            for f, e in t["all"].items():
                if e: w.writerow([tn, "all", f, e["group"], round(e["auc_train"], 4), None if e["auc_exposed"] is None else round(e["auc_exposed"], 4)])
            for wn, b in t["by_width"].items():
                for f, e in b["auc"].items():
                    if e: w.writerow([tn, wn, f, F.GROUP.get(f, "E-GEO"), round(e["train"], 4), None if e["exposed"] is None else round(e["exposed"], 4)])
    for tn, t in res["tasks"].items():
        print(tn, t["base_rate"], {f: (round(e["auc_train"], 3), None if e["auc_exposed"] is None else round(e["auc_exposed"], 3)) for f, e in t["all"].items() if e}, flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
