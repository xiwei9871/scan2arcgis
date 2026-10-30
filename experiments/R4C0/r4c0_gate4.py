"""R4-C0 Gate 4: new independent sheets (rules: r4c0_preregistration.json gate4). Committed before the first download.

select  walk experiments/R4B1T/gate5_candidates.json from order 11 onward, skip already visited / used codes,
        run the unchanged Q1/Q2/Q3 (experiments/R4A/gtf_dataset.process). For a PASS sheet build labels
        (experiments/R4A/r4a2_labels.build) and count ONLY the small instances (no model is run).
        < 100 small -> INSUFFICIENT_SAMPLE, continue. Stop at 2 sheets with >= 100 small or after 8 visited.
        Usage: r4c0_gate4.py select <out_json>                                  (.venv)
eval    for one accepted sheet: frozen Gate 3 pipeline (r4c0_gate3.main, same code and parameters) on fresh
        M2 / B2 predictions, then 95% paired bootstrap CIs (2000 resamples, seed 20261029) over small instances
        for RAG - M2_hybrid and APPEARANCE - BOUNDARY_ONLY.
        Usage: r4c0_gate4.py eval <sheet> <pred_dir> <out_dir> <local_dir>       (.venv-ml)
"""
import json, sys, time
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(ROOT / "experiments/R4A"))
sys.path.insert(0, str(ROOT / "experiments/R4B1T"))
PR = json.load(open(ROOT / "experiments/R4C0/r4c0_preregistration.json"))["gate4"]
START_ORDER, MIN_SMALL, MAX_VISIT, TARGET = 11, 100, 8, 2
SKIP = {"13076", "14030", "14071", "15094", "13015", "08011", "08021"}


def select(out_json):
    import gtf_dataset as G, r4a2_labels as LB, r4b1t_width as W
    cands = [c for c in json.load(open(ROOT / "experiments/R4B1T/gate5_candidates.json")) if c["order"] >= START_ORDER]
    log, accepted, visited = [], [], 0
    for c in cands:
        if len(accepted) >= TARGET or visited >= MAX_VISIT: break
        if c["code"] in SKIP or not c.get("eligible_by_history", False):
            log.append({"order": c["order"], "code": c["code"], "status": "SKIP_HISTORY"}); continue
        visited += 1; t0 = time.time()
        row = G.process({"code": c["code"], "year": c["year"], "vct": c["vct"]}); row["order"] = c["order"]
        if row["status"] == "PASS":
            LB.build(c["code"])
            d = ROOT / "runs/r4a2" / c["code"]
            inst = np.load(d / "instance.npy"); unit = np.load(d / "unit.npy"); V = (np.load(d / "ignore.npy") == 0) & (unit >= 0)
            _, _, ids, _ = W.canonical_widths(inst, V); row["small_instances"] = int(len(ids))
            if len(ids) < MIN_SMALL: row["status"] = "INSUFFICIENT_SAMPLE"
            else: accepted.append(c["code"])
        row["seconds"] = round(time.time() - t0, 1); log.append(row)
        print(c["order"], c["code"], row["status"], row.get("small_instances"), flush=True)
    res = {"role": "independent_test_R4C0", "accepted": accepted, "reached_target": len(accepted) >= TARGET, "visited": visited,
           "rules": {"start_order": START_ORDER, "min_small_instances": MIN_SMALL, "max_visited": MAX_VISIT, "skip": sorted(SKIP)},
           "frozen_before_selection": ["experiments/R4C0/gate2/gate2_freeze.json", "experiments/R4C0/r4c0_gate3.py", "experiments/R4C0/r4c0_gate4.py"],
           "log": log}
    json.dump(res, open(out_json, "w"), ensure_ascii=False, indent=1, default=float); print("accepted", accepted)


def boot(a, b, n=2000, seed=20261029):
    rng = np.random.default_rng(seed); d = a.astype(float) - b.astype(float); k = len(d)
    s = np.array([d[rng.integers(0, k, k)].mean() for _ in range(n)])
    return {"mean": float(d.mean()), "ci95": [float(np.percentile(s, 2.5)), float(np.percentile(s, 97.5))]}


def evaluate(sheet, pred_dir, out_dir, local_dir):
    import r4c0_gate3 as G3, r4a2_2_eval as EV, r4b1t_width as W
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True); P = Path(pred_dir)
    js = out / f"{sheet}_gate4.json"
    G3.main(sheet, "INDEPENDENT_TEST", str(P / "B2"), str(P / "M2/regions_M2_hybrid.npy"), str(js), local_dir)
    res = json.load(open(js))
    Rref = EV.load_ref(sheet); unit = np.load(ROOT / "runs/r4a2" / sheet / "unit.npy")
    V = (Rref["ignore"] == 0) & (unit >= 0); i1, area, ids, _ = W.canonical_widths(Rref["instance"], V)
    hit = {}
    for name, f in (("M2_hybrid", P / "M2/regions_M2_hybrid.npy"), ("RAG_BOUNDARY_ONLY", Path(local_dir) / f"{sheet}_RAG_BOUNDARY_ONLY.npy"),
                    ("RAG_BOUNDARY_APPEARANCE", Path(local_dir) / f"{sheet}_RAG_BOUNDARY_APPEARANCE.npy")):
        hit[name] = G3.per_instance(np.load(f), i1, V, ids, area)[0] >= 0.5
    res["paired_bootstrap"] = {"n_small": int(len(ids)),
                               "RAG_BOUNDARY_ONLY_minus_M2_hybrid": boot(hit["RAG_BOUNDARY_ONLY"], hit["M2_hybrid"]),
                               "RAG_BOUNDARY_APPEARANCE_minus_M2_hybrid": boot(hit["RAG_BOUNDARY_APPEARANCE"], hit["M2_hybrid"]),
                               "APPEARANCE_minus_BOUNDARY_ONLY": boot(hit["RAG_BOUNDARY_APPEARANCE"], hit["RAG_BOUNDARY_ONLY"])}
    ci = res["paired_bootstrap"]["APPEARANCE_minus_BOUNDARY_ONLY"]["ci95"]
    res["appearance_verdict"] = "no evidence of independent value yet" if ci[0] <= 0 <= ci[1] else ("positive" if ci[0] > 0 else "negative")
    json.dump(res, open(js, "w"), indent=1, default=float)
    print(sheet, json.dumps(res["paired_bootstrap"]), res["appearance_verdict"], flush=True)


if __name__ == "__main__":
    if sys.argv[1] == "select": select(sys.argv[2])
    else: evaluate(*sys.argv[2:6])
