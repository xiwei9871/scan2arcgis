"""R4-C0.1b Work 2: same-source attribution on 13014 / 15076 (already exposed; diagnostic, not a new test).

All variants use the SAME saved B2 prediction (runs/r4c0/pred_test/<sheet>/B2):
  B2_HARD_CC          frozen R4-B2 rule (p > 0.5 separates, 4-connected components, < 50 px cleanup) = regions_B2.npy
  B2_TERRAIN_M2SEEDS  watershed on the B2 pixel strength b (r4c0_rag.strengths) from the FROZEN M2_hybrid markers
                      (r4a2_1_seeds.hybrid_markers on the same sheet's M2 distance head)
  RAG_BOUNDARY_ONLY   frozen R4-C0 result (B2 over-segmentation + RAG, tau 0.45)
Reference rows: M2_hybrid (M2 distance terrain + the same hybrid markers) and B2 over-segmentation without merging.
Comparisons isolate: terrain source (M2 dist vs B2 edges, same seeds); seeds/watershed vs region merging (same B2 terrain).
Usage: r4c0_1b_attribution.py <out_json>   (.venv-ml)
"""
import json, sys
from pathlib import Path
import numpy as np
from skimage.segmentation import watershed

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "R4A"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "R4B1T"))
import r4c0_rag as R  # noqa: E402
import r4c0_gate3 as G3  # noqa: E402
import r4a2_2_eval as EV  # noqa: E402
import r4b1t_width as W  # noqa: E402
from r4a2_1_seeds import hybrid_markers  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def main(out_json):
    res = {"note": "same B2 prediction for all B2-based rows; sheets already exposed - attribution only", "sheets": {}}
    for c in ("13014", "15076"):
        P = ROOT / "runs/r4c0/pred_test" / c
        pr, pd = np.load(P / "B2/prob_right.npy"), np.load(P / "B2/prob_down.npy")
        b, sr, sd = R.strengths("B2", {"pr": pr, "pd": pd})
        mk = hybrid_markers(np.load(P / "M2/dist_px.npy").astype(np.float32))
        maps = {"M2_hybrid": np.load(P / "M2/regions_M2_hybrid.npy"),
                "B2_HARD_CC": np.load(P / "B2/regions_B2.npy"),
                "B2_TERRAIN_M2SEEDS": watershed(b.astype(np.float32), mk).astype(np.int32),
                "B2_OVERSEG_NO_MERGE": R.overseg(b),
                "RAG_BOUNDARY_ONLY": np.load(ROOT / f"runs/r4c0/gate4/{c}_RAG_BOUNDARY_ONLY.npy")}
        Rr = EV.load_ref(c); unit = np.load(ROOT / "runs/r4a2" / c / "unit.npy")
        V = (Rr["ignore"] == 0) & (unit >= 0); i1, area, ids, wid = W.canonical_widths(Rr["instance"], V)
        rows = {}
        for k, reg in maps.items():
            inst = EV.instance_metrics(reg.astype(np.int64), Rr)[0]
            best, br, holders, held = G3.per_instance(reg, i1, V, ids, area)
            bins = {bn: round(float((best[(wid >= lo) & (wid < hi)] >= 0.5).mean()), 4) for bn, lo, hi in W.BINS if ((wid >= lo) & (wid < hi)).any()}
            rows[k] = {"small_recall": round(inst["small"]["recall_iou50"], 4), "over_seg": round(inst["small"]["over_seg"], 4),
                       "under_seg": round(inst["small"]["under_seg"], 4), "large_recall": round(inst["large"]["recall_iou50"], 4),
                       "regions": inst["regions"]["n_pred"], "by_width": bins,
                       "small_failures_in_multi_instance_regions": int(((best < 0.5) & (holders[br] >= 2)).sum())}
        g = lambda k: rows[k]["small_recall"]
        rows["decomposition"] = {
            "terrain_source_same_seeds (B2_TERRAIN_M2SEEDS - M2_hybrid)": round(g("B2_TERRAIN_M2SEEDS") - g("M2_hybrid"), 4),
            "reconstruction_same_B2 (RAG - B2_TERRAIN_M2SEEDS)": round(g("RAG_BOUNDARY_ONLY") - g("B2_TERRAIN_M2SEEDS"), 4),
            "total (RAG - M2_hybrid)": round(g("RAG_BOUNDARY_ONLY") - g("M2_hybrid"), 4),
            "RAG vs hard connectivity, same B2": round(g("RAG_BOUNDARY_ONLY") - g("B2_HARD_CC"), 4)}
        res["sheets"][c] = rows
        print(c, json.dumps({k: (v["small_recall"], v["over_seg"], v["regions"]) for k, v in rows.items() if k != "decomposition"}), rows["decomposition"], flush=True)
    json.dump(res, open(out_json, "w"), indent=1)


if __name__ == "__main__":
    main(sys.argv[1])
