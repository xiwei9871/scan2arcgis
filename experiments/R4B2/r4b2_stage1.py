"""R4-B2 Stage 1: reconstruction check with official edges + fixed perturbation test (rules: r4b2_preregistration.json stage1).
10 training sheets, official labels only. Reconstruction from official edges is a property of the pipeline,
NOT a model result. Perturbations measure robustness of the reconstruction rule only.
Usage: r4b2_stage1.py <out_dir>   (.venv-ml)
"""
import json, sys
from pathlib import Path
import numpy as np
from scipy import ndimage as ndi
from scipy.sparse import coo_matrix

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "R4B1T"))
import r4b2_edges as E  # noqa: E402
import r4b1t_width as W  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
PR = json.load(open(ROOT / "experiments/R4B2/r4b2_preregistration.json"))["stage1"]
TRAIN = json.load(open(ROOT / "experiments/R4A/r4a2/freeze_config.json"))["data_roles"]["train"]
FOUR = [[0, 1, 0], [1, 1, 1], [0, 1, 0]]


def valid_components(unit, V):
    ref = np.zeros(unit.shape, np.int64); k0 = 0
    for u in np.unique(unit[V]):
        lab, n = ndi.label((unit == u) & V, structure=FOUR); ref[lab > 0] = lab[lab > 0] + k0; k0 += n
    return ref, k0


def score(reg, i1, V, ids, area):
    m = V & (i1 > 0) & (reg > 0)
    C = coo_matrix((np.ones(int(m.sum())), (i1[m], reg[m])), shape=(int(i1.max()) + 1, int(reg.max()) + 1)).tocsr().tocoo()
    ra = np.bincount(np.where(V, reg, 0).ravel(), minlength=int(reg.max()) + 1)
    iou = C.data / (area[C.row] + ra[C.col] - C.data)
    best = np.zeros(int(i1.max()) + 1); np.maximum.at(best, C.row, iou)
    cov = C.data / area[C.row]; holder = C.col[cov >= 0.5]                 # regions holding >= 50% of an instance
    held = np.bincount(holder, minlength=int(reg.max()) + 1)
    multi = held >= 2
    inst_in_multi = int(sum(multi[c] for c, cv in zip(C.col, cov) if cv >= 0.5))
    return {"small_recall": float((best[ids] >= 0.5).mean()), "regions": int(len(np.unique(reg[V]))),
            "regions_holding_ge2_instances": int(multi.sum()), "instances_absorbed_in_multi_regions": inst_in_multi}


def main(out_dir):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    res = {"label": "official labels: pipeline check and robustness, NOT a model result", "gt_check": {}, "perturbation": {}}
    ok_all = True
    for c in TRAIN:
        d0 = ROOT / "runs/r4a2" / c
        unit = np.load(d0 / "unit.npy").astype(np.int32); V = (np.load(d0 / "ignore.npy") == 0) & (unit >= 0)
        er, ed, mr, md = E.edges_from_labels(unit, V)
        reg, merged = E.regions_from_probs(er.astype(np.float32), ed.astype(np.float32))
        ref, k = valid_components(unit, V)
        pairs = np.unique(np.stack([ref[V], reg[V]], 1), axis=0)
        part_eq = len(pairs) == k == len(np.unique(reg[V]))
        rr, rd = E.region_edges(reg)
        edges_eq = bool(((rr > 0) & mr == er).all() and ((rd > 0) & md == ed).all())
        small = np.bincount(ref[V], minlength=k + 1); n_lt50 = int(((small > 0) & (small < 50)).sum())
        res["gt_check"][c] = {"valid_components": int(k), "reconstructed_regions_in_valid": int(len(np.unique(reg[V]))),
                              "partition_equal": bool(part_eq), "implied_edges_equal_official": edges_eq,
                              "cleanup_merges": int(merged), "valid_components_lt50px": n_lt50}
        print(c, res["gt_check"][c], flush=True)
        ok_all &= part_eq and edges_eq
    res["gt_check_all_exact"] = bool(ok_all)
    if not ok_all:
        json.dump(res, open(out / "stage1_reconstruction.json", "w"), indent=1); print("STOP: official-edge reconstruction mismatch"); return
    rng = np.random.default_rng(PR["perturbation"]["seed"])
    for c in PR["perturbation"]["sheets"]:
        d0 = ROOT / "runs/r4a2" / c
        unit = np.load(d0 / "unit.npy").astype(np.int32); V = (np.load(d0 / "ignore.npy") == 0) & (unit >= 0)
        inst = np.load(d0 / "instance.npy"); i1, area, ids, _ = W.canonical_widths(inst, V)
        er, ed, mr, md = E.edges_from_labels(unit, V); R = {}
        base = E.regions_from_probs(er.astype(np.float32), ed.astype(np.float32))[0]; R["clean"] = score(base, i1, V, ids, area)
        for frac in PR["perturbation"]["cases"]["drop_edges"]:
            rs = []
            for _ in range(PR["perturbation"]["draws"]):
                pr, pd = er.copy(), ed.copy()
                pr[pr & (rng.random(pr.shape) < frac)] = False; pd[pd & (rng.random(pd.shape) < frac)] = False
                rs.append(score(E.regions_from_probs(pr.astype(np.float32), pd.astype(np.float32))[0], i1, V, ids, area))
            R[f"drop_{frac}"] = {k: float(np.mean([r[k] for r in rs])) for k in rs[0]}
        for frac in PR["perturbation"]["cases"]["add_false_edges"]:
            rs = []
            for _ in range(PR["perturbation"]["draws"]):
                pr, pd = er.copy(), ed.copy()
                pr |= mr & ~er & (rng.random(pr.shape) < frac); pd |= md & ~ed & (rng.random(pd.shape) < frac)
                rs.append(score(E.regions_from_probs(pr.astype(np.float32), pd.astype(np.float32))[0], i1, V, ids, area))
            R[f"add_{frac}"] = {k: float(np.mean([r[k] for r in rs])) for k in rs[0]}
        dy, dx = [(0, 1), (1, 0), (0, -1), (-1, 0)][int(rng.integers(4))]
        pr = np.roll(np.roll(er, dy, 0), dx, 1) & mr; pd = np.roll(np.roll(ed, dy, 0), dx, 1) & md
        R["shift_1px"] = {"direction_dy_dx": [dy, dx], **score(E.regions_from_probs(pr.astype(np.float32), pd.astype(np.float32))[0], i1, V, ids, area)}
        res["perturbation"][c] = R
        print(c, json.dumps(R), flush=True)
    json.dump(res, open(out / "stage1_reconstruction.json", "w"), indent=1)


if __name__ == "__main__":
    main(sys.argv[1])
