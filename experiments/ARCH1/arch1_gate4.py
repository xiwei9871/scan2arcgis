"""ARCH-1 Gate 4: graded common subdivision feasibility + decision-store survival (rules: arch1_criteria.json gate4).
No generator has validated PROTECT evidence yet, so hard cuts are SIMULATED with official narrow instances
(canonical width < 10 px) - an ORACLE stand-in for a future C-PAIR, used only to size the problem.
Per sheet (10 training + 13014 / 15076):
  B2_ONLY        B2 over-segmentation
  GRADED_ORACLE  B2 over-seg + boundaries of the simulated narrow candidates, deduplicated: a candidate boundary pixel
                 pair within 1 pair (3x3) of an existing B2 over-seg boundary is not added
  ALL_STACKED    M1 x M2 x B2 over-segmentations (ARCH-0 D2 upper bound, training sheets only, from existing npz)
Reported: regions (ratio to B2_ONLY), RAG edges, build + full merge time, peak RSS (process max so far).
Decision store: every simulated candidate is stored (geometry RLE + evidence + state UNCERTAIN) before the frozen
merge on GRADED_ORACLE; after merging, resolve() records survival / absorption; check that each stored mask is
restored exactly.
Usage: arch1_gate4.py <out_dir>   (.venv-ml)
"""
import json, resource, sys, time
from pathlib import Path
import cv2, numpy as np

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ARCH0"))
import arch1_feats as F  # noqa: E402
import arch0_diag as A0  # noqa: E402
from arch1_decision_store import DecisionStore  # noqa: E402
R = F.R


def boundary(lab):
    b = np.zeros(lab.shape, bool); b[:, 1:] |= lab[:, 1:] != lab[:, :-1]; b[1:] |= lab[1:] != lab[:-1]; return b


def graded(lab, cand_lab):
    """Add candidate boundaries that are not within 1 px of an existing boundary; return new partition."""
    old = boundary(lab); near = cv2.dilate(old.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    newb = boundary(cand_lab) & ~near
    cut = cand_lab.copy(); cut[~newb] = 0                            # only the non-duplicated candidate boundary pixels split
    key = lab.astype(np.int64) * (int(cand_lab.max()) + 1) + np.where(newb | (cand_lab > 0), cand_lab, 0)
    return A0.relabel_cc(key), int(newb.sum())


def run(lab, sr, sd):
    t0 = time.time(); rag = R.build_rag(lab, sr, sd); mg = R.merge(rag, stop=F.TAU); t = time.time() - t0
    reg = R.partitions(rag["n"], mg, [np.inf])[np.inf][lab]
    return reg, {"regions": int(lab.max()), "rag_edges": int(len(rag["u"])), "seconds": round(t, 2)}


def sheet(code):
    X = F.load_inputs(code); Rr, V, i1, ia, ids, wid = F.label_ref(code)
    lab = F.compact(F.initial_regions(code, X)).astype(np.int32)
    nar = ids[wid < 10]; nm = np.zeros(int(i1.max()) + 1, np.int64); nm[nar] = nar; cand = nm[i1]
    out = {}
    _, out["B2_ONLY"] = run(lab, X["sr"], X["sd"])
    t0 = time.time(); g, added = graded(lab, cand); tg = time.time() - t0
    reg_g, out["GRADED_ORACLE"] = run(g, X["sr"], X["sd"]); out["GRADED_ORACLE"]["candidate_boundary_px_added"] = added
    out["GRADED_ORACLE"]["subdivision_seconds"] = round(tg, 2)
    if code in F.TRAIN:
        labs = [np.load(F.ROOT / f"runs/r4c0/gate1/{code}_{m}.npz")["lab"] for m in ("M1", "M2", "B2")]
        _, out["ALL_STACKED"] = run(A0.intersect(*labs), X["sr"], X["sd"])
    for k in out: out[k]["ratio_to_B2"] = round(out[k]["regions"] / out["B2_ONLY"]["regions"], 3)
    # decision store
    S = DecisionStore(); masks = {}
    for k, w in zip(ids, wid):
        if w >= 10: continue
        m = i1 == k; masks[k] = m
        S.add("ORACLE_NARROW", m, w, {"width": w}, state="UNCERTAIN", reason=[("simulated", "ORACLE")])
    S.resolve(reg_g)
    exact = all(np.array_equal(S.mask(r["cid"], lab.shape), masks[k]) for r, k in zip(S.records, masks))
    surv = [r["absorbed_into"] is None for r in S.records]
    out["decision_store"] = {"candidates": len(S.records), "geometry_restored_exactly": bool(exact),
                             "survived_as_own_region": int(sum(surv)), "absorbed": int(len(surv) - sum(surv)),
                             "absorbed_share": round(1 - np.mean(surv), 4) if surv else None}
    S.dump(F.ROOT / f"runs/arch1/gate4/{code}_decision_store.json")
    out["peak_rss_gb_process"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e9, 2)
    return out


def main(out_dir):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True); (F.ROOT / "runs/arch1/gate4").mkdir(parents=True, exist_ok=True)
    res = {"label": "hard cuts simulated with official narrow instances (ORACLE stand-in); sizing and interface study only", "per_sheet": {}}
    for c in F.TRAIN + F.EXPOSED:
        res["per_sheet"][c] = sheet(c); r = res["per_sheet"][c]
        print(c, {k: (v["regions"], v["ratio_to_B2"], v["seconds"]) for k, v in r.items() if isinstance(v, dict) and "regions" in v}, r["decision_store"], flush=True)
    ps = res["per_sheet"].values()
    res["summary"] = {k: {"ratio_to_B2_max": max(p[k]["ratio_to_B2"] for p in ps if k in p), "ratio_to_B2_median": float(np.median([p[k]["ratio_to_B2"] for p in ps if k in p])),
                          "seconds_max": max(p[k]["seconds"] for p in ps if k in p)} for k in ("B2_ONLY", "GRADED_ORACLE", "ALL_STACKED")}
    res["summary"]["peak_rss_gb"] = max(p["peak_rss_gb_process"] for p in ps)
    res["summary"]["graded_within_3x_B2_all_sheets"] = all(p["GRADED_ORACLE"]["ratio_to_B2"] <= 3 for p in ps)
    res["summary"]["geometry_restored_all"] = all(p["decision_store"]["geometry_restored_exactly"] for p in ps)
    res["summary"]["narrow_candidates_absorbed_share"] = {c: p["decision_store"]["absorbed_share"] for c, p in res["per_sheet"].items()}
    json.dump(res, open(out / "gate4_subdivision.json", "w"), indent=1, default=float)
    print(json.dumps(res["summary"], indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
