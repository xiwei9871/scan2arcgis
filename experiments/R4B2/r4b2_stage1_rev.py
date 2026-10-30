"""R4-B2 Stage 1 (revised, rules: r4b2_stage1_amendment.json). The original r4b2_stage1.py and its FAIL stay unchanged.
10 training sheets, official labels only; NOT a model result.
  check a  D_gt-domain reconstruction of official edges, no cleanup: exact partition + implied edges == official edges
  check b  D_gt-domain reconstruction with the frozen < 50 px cleanup: small-instance recall == 1.000
  perturbation (05016, 06054) from the check-a edge graph, reconstructed on D_gt with cleanup, and with the frozen
  full-image rule for comparison (robustness only)
Usage: r4b2_stage1_rev.py <out_dir>   (.venv-ml)
"""
import json, sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "R4B1T"))
import r4b2_edges as E  # noqa: E402
import r4b1t_width as W  # noqa: E402
from r4b2_stage1 import valid_components, score  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
PR = json.load(open(ROOT / "experiments/R4B2/r4b2_preregistration.json"))["stage1"]
TRAIN = json.load(open(ROOT / "experiments/R4A/r4a2/freeze_config.json"))["data_roles"]["train"]


def load(c):
    d0 = ROOT / "runs/r4a2" / c
    unit = np.load(d0 / "unit.npy").astype(np.int32); V = (np.load(d0 / "ignore.npy") == 0) & (unit >= 0)
    inst = np.load(d0 / "instance.npy"); i1, area, ids, _ = W.canonical_widths(inst, V)
    return unit, V, i1, area, ids


def main(out_dir):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    res = {"label": "official labels on D_gt: label/pipeline check and robustness, NOT a model result", "check_a": {}, "check_b": {}, "perturbation": {}}
    for c in TRAIN:
        unit, V, i1, area, ids = load(c)
        er, ed, mr, md = E.edges_from_labels(unit, V); fr, fd = er.astype(np.float32), ed.astype(np.float32)
        ref, k = valid_components(unit, V)
        comp = E.components(er, ed, V)
        pairs = np.unique(np.stack([ref[V], comp[V]], 1), axis=0)
        rr, rd = E.region_edges(comp)
        a = {"valid_components": int(k), "regions": int(len(np.unique(comp[V]))),
             "partition_equal": bool(len(pairs) == k == len(np.unique(comp[V]))),
             "implied_edges_equal_official": bool((((rr > 0) & mr) == er).all() and (((rd > 0) & md) == ed).all())}
        a["pass"] = a["partition_equal"] and a["implied_edges_equal_official"]; res["check_a"][c] = a
        reg, merged = E.regions_from_probs(fr, fd, domain=V)
        sz = np.bincount(ref[V], minlength=k + 1); tiny = (sz > 0) & (sz < E.MIN_AREA)
        s = score(reg, i1, V, ids, area)
        b = {"small_recall": s["small_recall"], "small_instances": int(len(ids)), "cleanup_merges": int(merged),
             "tiny_components": int(tiny.sum()), "tiny_component_px": int(sz[tiny].sum()),
             "regions_before": int(len(np.unique(comp[V]))), "regions_after": int(len(np.unique(reg[V]))),
             "regions_holding_ge2_small_instances": s["regions_holding_ge2_instances"]}
        b["pass"] = b["small_recall"] == 1.0; res["check_b"][c] = b
        print(c, "a", a["pass"], "b", b["pass"], b["small_recall"], "tiny merged", merged, flush=True)
    res["check_a_pass_all"] = all(v["pass"] for v in res["check_a"].values())
    res["check_b_pass_all"] = all(v["pass"] for v in res["check_b"].values())
    if not (res["check_a_pass_all"] and res["check_b_pass_all"]):
        json.dump(res, open(out / "stage1_rev.json", "w"), indent=1); print("STOP: revised check failed"); return
    P = PR["perturbation"]; rng = np.random.default_rng(P["seed"])
    for c in P["sheets"]:
        unit, V, i1, area, ids = load(c); er, ed, mr, md = E.edges_from_labels(unit, V)

        def run(pr, pd):
            return {"D_gt": score(E.regions_from_probs(pr.astype(np.float32), pd.astype(np.float32), domain=V)[0], i1, V, ids, area),
                    "full_image": score(E.regions_from_probs(pr.astype(np.float32), pd.astype(np.float32))[0], i1, V, ids, area)}
        R = {"clean": run(er, ed)}
        def avg(rs): return {dom: {k: float(np.mean([r[dom][k] for r in rs])) for k in rs[0][dom]} for dom in rs[0]}
        for frac in P["cases"]["drop_edges"]:
            rs = []
            for _ in range(P["draws"]):
                pr, pd = er.copy(), ed.copy(); pr[pr & (rng.random(pr.shape) < frac)] = False; pd[pd & (rng.random(pd.shape) < frac)] = False
                rs.append(run(pr, pd))
            R[f"drop_{frac}"] = avg(rs)
        for frac in P["cases"]["add_false_edges"]:
            rs = []
            for _ in range(P["draws"]):
                pr, pd = er.copy(), ed.copy(); pr |= mr & ~er & (rng.random(pr.shape) < frac); pd |= md & ~ed & (rng.random(pd.shape) < frac)
                rs.append(run(pr, pd))
            R[f"add_{frac}"] = avg(rs)
        dy, dx = [(0, 1), (1, 0), (0, -1), (-1, 0)][int(rng.integers(4))]
        R["shift_1px"] = {"direction_dy_dx": [dy, dx], **run(np.roll(np.roll(er, dy, 0), dx, 1) & mr, np.roll(np.roll(ed, dy, 0), dx, 1) & md)}
        res["perturbation"][c] = R; print(c, json.dumps(R), flush=True)
    json.dump(res, open(out / "stage1_rev.json", "w"), indent=1)


if __name__ == "__main__":
    main(sys.argv[1])
