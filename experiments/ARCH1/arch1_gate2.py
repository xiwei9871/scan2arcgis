"""ARCH-1 Gate 2: perfect-evidence ORACLE ablations (rules: arch1_criteria.json gate2). Diagnostics only:
every O_ variant reads official labels and is never an inference input or a test result.
Sheets: 10 training (in-sample B2) + exposed 13014 / 15076. Base pipeline = RAG_BOUNDARY_ONLY (B2 over-seg, tau 0.45).
  BASE                 frozen RAG_BOUNDARY_ONLY
  O_CONTACT            B2 pair strength replaced by official edges (1 / 0) in over-segmentation AND merge
  O_NARROW_CANDIDATES  B2 over-seg intersected with official instances of canonical width < 10 px (hard cuts), then frozen merge
  O_INK_BAND           BASE, then every PSEUDO region < 200 px absorbed into the adjacent region with the same majority instance
  O_MERGE_RELATION     B2 over-seg, adjacent regions merged iff same majority instance (Oracle B)
  O_UNIT_CODE          literal pre-registration: different majority geo_A unit -> forbid; same unit AND same majority
                       instance -> force; otherwise frozen cost. Post-hoc variant O_UNIT_CODE_FORBID_ONLY (only the forbid
                       term) is reported separately and marked post-hoc.
Combinations: O_NARROW+O_INK_BAND, O_NARROW+O_MERGE_RELATION, O_CONTACT+O_INK_BAND.
Usage: arch1_gate2.py <out_dir>   (.venv-ml)
"""
import json, sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ARCH0"))
import arch1_feats as F  # noqa: E402
import arch0_diag as A0  # noqa: E402
R, EV, W = F.R, F.EV, F.W
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "R4C0"))
import r4c0_gate3 as G3  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "R4B2"))
import r4b2_edges as E2  # noqa: E402

TAU = F.TAU
WG = [("le6", 0, 6), ("6-10", 6, 10), ("10-20", 10, 20), ("gt20", 20, 1e9)]


def merged(lab, sr, sd, tau=TAU):
    rag = R.build_rag(lab, sr, sd)
    return R.partitions(rag["n"], R.merge(rag, stop=tau), [np.inf])[np.inf][lab].astype(np.int64)


def oracle_b(lab, i1, V):
    return R.oracle_B_regions(lab, i1, V)[0].astype(np.int64)


def ink_band_absorb(reg, X, i1, V, ia):
    reg = F.compact(reg); maj, _, _, sz = F.label_regions(reg, i1, V, ia)
    pseudo = (maj > 0) & (ia[maj] >= 5 * sz) & (sz < 200); pseudo[0] = False
    BS = F.border_stats(reg, X); u, v, L = BS["u"], BS["v"], BS["len"]
    tgt = np.arange(len(sz)); best = np.zeros(len(sz))
    for p, q in ((u, v), (v, u)):
        ok = pseudo[p] & ~pseudo[q] & (maj[p] == maj[q])
        for a, b, l in zip(p[ok], q[ok], L[ok]):
            if l > best[a]: best[a] = l; tgt[a] = b
    return tgt[reg]


def unit_code(lab, sr, sd, i1, V, unit, forbid_only=False):
    lab = F.compact(lab); n = int(lab.max())
    maj, pur, _, _ = F.label_regions(lab, i1, V, np.bincount(i1.ravel(), minlength=int(i1.max()) + 1))
    U = np.where(V, unit, -1).astype(np.int64)
    C = R.overlaps(lab, U + 1, V); o = np.lexsort((-C.data, C.row)); f = np.unique(C.row[o], return_index=True)[1]
    mu = np.zeros(n + 1, np.int64); mu[C.row[o][f]] = C.col[o][f]
    if not forbid_only:                                   # force: union same-unit, same-majority-instance neighbours
        rag0 = R.build_rag(lab, sr, sd); parent = np.arange(n + 1)
        def find(x):
            while parent[x] != x: parent[x] = parent[parent[x]]; x = parent[x]
            return x
        for a, b in zip(rag0["u"], rag0["v"]):
            if mu[a] == mu[b] and maj[a] == maj[b] and maj[a] > 0:
                ra, rb = find(a), find(b)
                if ra != rb: parent[rb] = ra
        roots = np.array([find(i) for i in range(n + 1)]); lab = F.compact(roots[lab]); n = int(lab.max())
        C = R.overlaps(lab, U + 1, V); o = np.lexsort((-C.data, C.row)); f = np.unique(C.row[o], return_index=True)[1]
        mu = np.zeros(n + 1, np.int64); mu[C.row[o][f]] = C.col[o][f]
    rag = R.build_rag(lab, sr, sd)
    forbid = mu[rag["u"]] != mu[rag["v"]]
    rag["hist"][forbid] = 0; rag["hist"][forbid, R.NB - 1] = 10 ** 6       # median stays at the top bin after any union
    return R.partitions(rag["n"], R.merge(rag, stop=TAU), [np.inf])[np.inf][lab].astype(np.int64)


def score(name, reg, init, Rr, V, i1, ia, ids, wid):
    reg = F.compact(reg); init = F.compact(init)
    inst = EV.instance_metrics(reg, Rr)[0]
    best, br, holders, held = G3.per_instance(reg, i1, V, ids, ia)
    oa = R.oracle_A(init, i1, V, ids)
    ob = G3.per_instance(oracle_b(init, i1, V), i1, V, ids, ia)[0]
    cls = G3.classify(oa, best, br, holders, held)
    maj, _, _, sz = F.label_regions(reg, i1, V, ia); pseudo = int((((maj > 0) & (ia[maj] >= 5 * sz) & (sz < 200))[1:]).sum())
    out = {"small_recall": inst["small"]["recall_iou50"], "large_recall": inst["large"]["recall_iou50"], "regions": inst["regions"]["n_pred"],
           "initial_regions": int(init.max()), "pseudo_fragments": pseudo,
           "failures": {k: int((cls == k).sum()) for k in ("INITIAL_MIXED", "MERGE_ERROR", "UNDER_MERGE_FRAGMENTS", "OTHER")},
           "by_width": {}}
    for g, lo, hi in WG:
        m = (wid >= lo) & (wid < hi)
        if m.any(): out["by_width"][g] = {"n": int(m.sum()), "hits": int((best[m] >= 0.5).sum()),
                                          "oracleA_hits": int((oa[m] >= 0.5).sum()), "oracleB_hits": int((ob[m] >= 0.5).sum())}
    out["n_small"] = int(len(ids)); out["hits"] = int((best >= 0.5).sum())
    return out


def sheet(code):
    X = F.load_inputs(code); Rr, V, i1, ia, ids, wid = F.label_ref(code)
    unit = np.load(F.ROOT / "runs/r4a2" / code / "unit.npy").astype(np.int64)
    sr, sd = X["sr"], X["sd"]
    lab = F.compact(F.initial_regions(code, X)); base = F.final_regions(code, X)
    er, ed, _, _ = E2.edges_from_labels(unit.astype(np.int32), V)
    osr, osd = er.astype(np.float32), ed.astype(np.float32)
    ob_ = np.maximum(osr, osd); ob_[:, 1:] = np.maximum(ob_[:, 1:], osr[:, :-1]); ob_[1:] = np.maximum(ob_[1:], osd[:-1])
    lab_c = F.compact(R.overseg(ob_)); reg_c = merged(lab_c, osr, osd)
    nm = np.zeros(int(i1.max()) + 1, np.int64); nar = ids[wid < 10]; nm[nar] = nar
    lab_n = F.compact(A0.intersect(lab, nm[i1])); reg_n = merged(lab_n, sr, sd)
    V_ = {"BASE": (base, lab), "O_CONTACT": (reg_c, lab_c), "O_NARROW_CANDIDATES": (reg_n, lab_n),
          "O_INK_BAND": (ink_band_absorb(base, X, i1, V, ia), lab), "O_MERGE_RELATION": (oracle_b(lab, i1, V), lab),
          "O_UNIT_CODE": (unit_code(lab, sr, sd, i1, V, unit), lab),
          "O_UNIT_CODE_FORBID_ONLY_posthoc": (unit_code(lab, sr, sd, i1, V, unit, forbid_only=True), lab),
          "O_NARROW+O_INK_BAND": (ink_band_absorb(reg_n, X, i1, V, ia), lab_n), "O_NARROW+O_MERGE_RELATION": (oracle_b(lab_n, i1, V), lab_n),
          "O_CONTACT+O_INK_BAND": (ink_band_absorb(reg_c, X, i1, V, ia), lab_c)}
    return {k: score(k, r, l, Rr, V, i1, ia, ids, wid) for k, (r, l) in V_.items()}


def pool(rows):
    out = {}
    for k in rows[0]:
        rs = [r[k] for r in rows]; n = sum(r["n_small"] for r in rs)
        o = {"small_recall": sum(r["hits"] for r in rs) / n, "regions_median": float(np.median([r["regions"] for r in rs])),
             "initial_regions_median": float(np.median([r["initial_regions"] for r in rs])), "pseudo_fragments": sum(r["pseudo_fragments"] for r in rs),
             "large_recall_mean": float(np.mean([r["large_recall"] for r in rs if r["large_recall"] is not None])),
             "failures": {f: sum(r["failures"][f] for r in rs) for f in rs[0]["failures"]}, "by_width": {}}
        for g, _, _ in WG:
            nn = sum(r["by_width"].get(g, {}).get("n", 0) for r in rs)
            if nn: o["by_width"][g] = {"n": nn, **{m: round(sum(r["by_width"][g][m] for r in rs if g in r["by_width"]) / nn, 4) for m in ("hits", "oracleA_hits", "oracleB_hits")}}
        out[k] = o
    return out


def main(out_dir):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True); res = {"label": "ORACLE diagnostics, not model results", "per_sheet": {}}
    for g, codes in (("train", F.TRAIN), ("exposed", F.EXPOSED)):
        rows = []
        for c in codes:
            r = sheet(c); res["per_sheet"][c] = r; rows.append(r)
            print(g, c, {k: round(v["small_recall"], 3) for k, v in r.items()}, flush=True)
        res[f"pooled_{g}"] = pool(rows)
    base = {g: res[f"pooled_{g}"]["BASE"] for g in ("train", "exposed")}
    res["keep_rule"] = {}
    for k in res["pooled_train"]:
        if k == "BASE": continue
        d = {}
        for g in ("train", "exposed"):
            p = res[f"pooled_{g}"][k]; b = base[g]
            d[g] = {"overall_gain": round(p["small_recall"] - b["small_recall"], 4),
                    "le6_gain": round(p["by_width"]["le6"]["hits"] - b["by_width"]["le6"]["hits"], 4) if "le6" in p["by_width"] else None,
                    "6_10_gain": round(p["by_width"]["6-10"]["hits"] - b["by_width"]["6-10"]["hits"], 4),
                    "pseudo_reduction": round(1 - p["pseudo_fragments"] / max(b["pseudo_fragments"], 1), 4)}
        d["keep"] = any((d[g]["le6_gain"] or 0) >= 0.03 or d[g]["6_10_gain"] >= 0.03 or d[g]["overall_gain"] >= 0.01 or d[g]["pseudo_reduction"] >= 0.30 for g in ("train", "exposed"))
        res["keep_rule"][k] = d
    json.dump(res, open(out / "gate2_oracle_ablation.json", "w"), indent=1, default=float)
    for g in ("train", "exposed"):
        for k, v in res[f"pooled_{g}"].items():
            print(g, k, round(v["small_recall"], 4), {w: (x["hits"], x["oracleA_hits"], x["oracleB_hits"]) for w, x in v["by_width"].items()},
                  "reg", v["regions_median"], "init", v["initial_regions_median"], "pseudo", v["pseudo_fragments"], v["failures"], flush=True)
    print(json.dumps(res["keep_rule"], indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
