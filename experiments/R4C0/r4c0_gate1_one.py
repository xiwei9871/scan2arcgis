"""R4-C0 Gate 1, one (sheet, candidate): over-segmentation, RAG, full merge sequence, ASA / UE, Oracle A / B.
Rules: r4c0_preregistration.json gate1. Labels are read only for the oracle / metric part.
Writes <out_dir>/<sheet>_<cand>.json and local <local_dir>/<sheet>_<cand>.npz (initial regions + merge sequence).
Usage: r4c0_gate1_one.py <sheet> <M1|M2|B2> <pred_root> <out_dir> <local_dir>   (.venv-ml)
"""
import json, resource, sys, time
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "R4B1T"))
import r4c0_rag as R  # noqa: E402
import r4b1t_width as W  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def load_pred(cand, d):
    if cand == "M1": return {"prob": np.load(d / "M1/prob.npy")}
    if cand == "M2": return {"prob": np.load(d / "M2/prob.npy")}
    return {"pr": np.load(d / "B2/prob_right.npy"), "pd": np.load(d / "B2/prob_down.npy")}


def recall_from_regions(reg, i1, V, ids, area):
    C = R.overlaps(reg, i1, V); ra = np.bincount(reg[V].ravel(), minlength=int(reg.max()) + 1)
    iou = C.data / (ra[C.row] + area[C.col] - C.data); best = np.zeros(int(i1.max()) + 1); np.maximum.at(best, C.col, iou)
    return best[ids]


def main(sheet, cand, pred_root, out_dir, local_dir):
    out, loc = Path(out_dir), Path(local_dir); out.mkdir(parents=True, exist_ok=True); loc.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    b, sr, sd = R.strengths(cand, load_pred(cand, Path(pred_root) / sheet))
    lab = R.overseg(b); t_os = time.time() - t0
    t1 = time.time(); rag = R.build_rag(lab, sr, sd); t_rag = time.time() - t1
    t2 = time.time(); merges = R.merge(rag); t_mg = time.time() - t2
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e9                    # macOS: bytes -> GB
    np.savez_compressed(loc / f"{sheet}_{cand}.npz", lab=lab, merges=np.array(merges, np.float64).reshape(-1, 3))
    # ---- oracle / metric part (reads labels) ----
    d0 = ROOT / "runs/r4a2" / sheet
    inst = np.load(d0 / "instance.npy"); unit = np.load(d0 / "unit.npy"); V = (np.load(d0 / "ignore.npy") == 0) & (unit >= 0)
    i1, area, ids, wid = W.canonical_widths(inst, V)
    sz = np.bincount(lab[V].ravel(), minlength=int(lab.max()) + 1); sz = sz[sz > 0]
    asa, ue = R.asa_ue(lab, i1, V)
    oa = R.oracle_A(lab, i1, V, ids)
    regB, _ = R.oracle_B_regions(lab, i1, V); ob = recall_from_regions(regB, i1, V, ids, area)
    bins = {}
    for name, lo, hi in W.BINS:
        m = (wid >= lo) & (wid < hi)
        if m.any(): bins[name] = {"n": int(m.sum()), "oracle_A_recall": float((oa[m] >= 0.5).mean()), "oracle_B_recall": float((ob[m] >= 0.5).mean()),
                                  "mixed_share": float((oa[m] < 0.5).mean())}
    m620 = (wid >= 6) & (wid < 20)
    big = np.flatnonzero(area >= 20000); big = big[big > 0]
    C = R.overlaps(lab, i1, V).tocsc(); frag = []
    for g in big:
        col = C.getcol(g); frag.append(int((col.data >= 0.01 * area[g]).sum()))
    res = {"sheet": sheet, "candidate": cand, "initial_regions": int(lab.max()), "regions_in_valid": int(len(sz)),
           "region_area_mean": float(sz.mean()), "region_area_median": float(np.median(sz)),
           "rag_nodes": int(rag["n"]), "rag_edges": int(len(rag["u"])), "merges_in_full_sequence": len(merges),
           "seconds": {"overseg": round(t_os, 1), "rag": round(t_rag, 1), "merge_full": round(t_mg, 1), "total": round(t_os + t_rag + t_mg, 1)},
           "peak_rss_gb": round(peak, 3), "ASA": asa, "UE": ue, "small_instances": int(len(ids)),
           "oracle_A_small_recall": float((oa >= 0.5).mean()), "oracle_B_small_recall": float((ob >= 0.5).mean()),
           "n_6_20": int(m620.sum()), "oracle_A_6_20_hits": int((oa[m620] >= 0.5).sum()), "oracle_B_6_20_hits": int((ob[m620] >= 0.5).sum()),
           "by_width": bins, "large_instances": int(len(big)),
           "large_fragments_median": float(np.median(frag)) if frag else None, "large_fragments_p90": float(np.percentile(frag, 90)) if frag else None}
    json.dump(res, open(out / f"{sheet}_{cand}.json", "w"), indent=1)
    print(sheet, cand, {k: res[k] for k in ("initial_regions", "rag_edges", "peak_rss_gb", "ASA", "UE", "oracle_A_small_recall", "oracle_B_small_recall")}, res["seconds"], flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:6])
