"""R4-B1T Gate 0: reconcile historical width / instance counts with the canonical definition (r4b1t_width).
Labels only (no model output). Sheets: 10 training + 15023/15041 (counts only, already used in R4-B0).
Usage: r4b1t_gate0.py <out_json>   (.venv-ml)
"""
import json, sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import r4b1t_width as W  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
ROLES = json.load(open(ROOT / "experiments/R4A/r4a2/freeze_config.json"))["data_roles"]


def counts(ws):
    return {b: int(sum(W.width_bin(w) == b for w in ws)) for b, _, _ in W.BINS}


def sheet(code):
    d = ROOT / "runs/r4a2" / code
    inst = np.load(d / "instance.npy"); unit = np.load(d / "unit.npy"); ign = np.load(d / "ignore.npy"); dist = np.load(d / "dist.npy")
    valid = (ign == 0) & (unit >= 0)
    i1v, av, idv, wc = W.canonical_widths(inst, valid)
    i1f, af, objf = W.instances(inst, None)
    idf = np.flatnonzero((af >= 200) & (af < 20000)); idf = idf[idf > 0]
    ef = W.max_edt(i1f, objf, idf)
    md = np.zeros(int(i1v.max()) + 1, np.float32); np.maximum.at(md, i1v.ravel(), np.where(valid, dist, 0).ravel())
    r = {"instances_total_full_grid": int(inst.max() + 1), "instances_with_valid_px": int((av[1:] > 0).sum()),
         "small_full_grid": int(len(idf)), "small_valid": int(len(idv)),
         "small_ids_only_in_full": int(len(np.setdiff1d(idf, idv))), "small_ids_only_in_valid": int(len(np.setdiff1d(idv, idf))),
         "bins": {"canonical_valid": counts(wc), "H1_precheck_2edt_full": counts(2 * ef), "H4_rb1_full_grid": counts(2 * (ef - 0.5)),
                  "H2_r4a22_old_2maxdist_plus1": counts(2 * md[idv] + 1)}}
    common = np.intersect1d(idf, idv); wf = dict(zip(idf, 2 * (ef - 0.5))); wv = dict(zip(idv, wc))
    r["canonical_vs_H4_same_bin_on_common_ids"] = round(float(np.mean([W.width_bin(wf[k]) == W.width_bin(wv[k]) for k in common])), 4)
    return r


def main(out):
    res = {"definition": W.__doc__, "sheets": {}}
    for role in ("train", "validation_model_selection"):
        for c in ROLES[role]:
            res["sheets"][c] = {"role": role, **sheet(c)}; s = res["sheets"][c]
            print(c, role, s["small_full_grid"], s["small_valid"], s["bins"]["canonical_valid"], s["canonical_vs_H4_same_bin_on_common_ids"], flush=True)
    for role in ("train", "validation_model_selection"):
        rs = [v for v in res["sheets"].values() if v["role"] == role]
        res[f"pooled_{role}"] = {k: {b: sum(v["bins"][k][b] for v in rs) for b, _, _ in W.BINS} for k in rs[0]["bins"]}
    json.dump(res, open(out, "w"), indent=1); print(json.dumps({k: v for k, v in res.items() if k.startswith("pooled")}, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
