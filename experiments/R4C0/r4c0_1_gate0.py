"""R4-C0.1 Gate 0: freeze and audit of the R4-C0 pipeline on 13014 / 15076 (no tuning, no new evaluation design).
Checks per sheet:
  weights        B2 best.pt sha256 equals experiments/R4B2/stage2/checkpoint_sha256.txt
  label_free     re-run the frozen prediction part (B2 probs + RGB only) in a fresh process state and compare
                 with the saved region maps (pixel-identical)
  metrics        recompute small recall / over / under / regions with r4a2_2_eval from the saved maps; must equal
                 the committed gate4 JSON
  merge_consistency  for the final partition, recompute from scratch (no use of the merge code's internal state):
                 every final region is 4-connected; every remaining adjacent pair has cost > tau (otherwise the
                 greedy merge would have continued); costs from fresh median histograms + fresh colour means
  export         labels.npy in the export == saved regions inside the export mask; export mask source and the share
                 of predicted pixels it removes (export used ignore.npy, which is label-derived)
Usage: r4c0_1_gate0.py <out_json>   (.venv-ml)
"""
import hashlib, json, sys
from pathlib import Path
import cv2, numpy as np
from scipy import ndimage as ndi

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "R4A"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "R4B1T"))
import r4c0_rag as R  # noqa: E402
import r4a2_2_eval as EV  # noqa: E402
from r4b1t_labels import ink_masks, lab_image  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
FZ = json.load(open(ROOT / "experiments/R4C0/gate2/gate2_freeze.json"))
VARIANTS = {"RAG_BOUNDARY_ONLY": FZ["RAG_BOUNDARY_ONLY"], "RAG_BOUNDARY_APPEARANCE": FZ["RAG_BOUNDARY_APPEARANCE"]}


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()


def remaining_costs(reg, sr, sd, cs_img, ink1, lam):
    """Fresh adjacency costs between final regions (median of shared pair strengths at 64 bins, + colour term)."""
    rag = R.build_rag(reg, sr, sd)
    med = np.array([R._median(h) for h in rag["hist"]])
    if lam > 0:
        cs, cc = R.region_colour(reg, cs_img, ink1)
        m = cs / np.maximum(cc, 1)[:, None]
        d = np.linalg.norm(m[rag["u"]] - m[rag["v"]], axis=1)
        med = med + lam * np.minimum(d / R.DE0, 1.0)
    return med


def main(out_json):
    ck = open(ROOT / "experiments/R4B2/stage2/checkpoint_sha256.txt").read().split()[0]
    res = {"b2_weights_sha256_match": sha(ROOT / "runs/r4b2/B2_formal/best.pt") == ck, "sheets": {}}
    for code in ("13014", "15076"):
        P = ROOT / "runs/r4c0/pred_test" / code; L = ROOT / "runs/r4c0/gate4"
        pr, pd = np.load(P / "B2/prob_right.npy"), np.load(P / "B2/prob_down.npy")
        b, sr, sd = R.strengths("B2", {"pr": pr, "pd": pd}); lab = R.overseg(b); rag = R.build_rag(lab, sr, sd)
        bgr = cv2.imread(str(ROOT / "runs/r4a2" / code / "geotiff_rgb.png")); _, ink1, _ = ink_masks(bgr); limg = lab_image(bgr)
        cs, cc = R.region_colour(lab, limg, ink1)
        gate4 = json.load(open(ROOT / f"experiments/R4C0/gate4/{code}_gate4.json"))
        Rref = EV.load_ref(code)
        s = {"pred_files_sha256": {f: sha(P / "B2" / f) for f in ("prob_right.npy", "prob_down.npy")}}
        for name, p in VARIANTS.items():
            saved = np.load(L / f"{code}_{name}.npy")
            mg = R.merge(rag, cs if p["lambda"] > 0 else None, cc if p["lambda"] > 0 else None, lam=p["lambda"], stop=p["tau"])
            fresh = R.partitions(rag["n"], mg, [np.inf])[np.inf][lab]
            v = {"label_free_rerun_identical": bool((fresh == saved).all())}
            inst = EV.instance_metrics(saved.astype(np.int64), Rref)[0]
            g = gate4[name]
            v["metrics_identical"] = bool(inst["small"] == g["small"] and inst["regions"] == g["regions"] and inst["large"] == g["large"])
            ids = np.unique(saved)
            # 4-connectivity of every final region: relabel components and compare counts
            H, W = saved.shape; G = np.zeros((2 * H - 1, 2 * W - 1), bool)
            G[::2, ::2] = True; G[::2, 1::2] = saved[:, :-1] == saved[:, 1:]; G[1::2, ::2] = saved[:-1] == saved[1:]
            ncc = ndi.label(G, structure=R.FOUR)[1]
            v["final_regions"] = int(len(ids)); v["all_regions_4connected"] = bool(ncc == len(ids))
            rem = remaining_costs(saved, sr, sd, limg, ink1, p["lambda"])
            v["remaining_adjacent_pairs"] = int(len(rem)); v["min_remaining_cost"] = float(rem.min())
            v["no_mergeable_pair_left"] = bool(rem.min() > p["tau"] - 1e-9)
            v["pairs_at_or_below_tau"] = int((rem <= p["tau"] + 1e-9).sum())
            ex = np.load(L / f"export/{code}/{name}/labels.npy"); mm = np.load(L / f"export/{code}/{name}/map_mask.npy")
            ign = np.load(ROOT / "runs/r4a2" / code / "ignore.npy") == 0
            v["export"] = {"export_mask_equals_label_derived_ignore": bool((mm == (ign & (saved > 0))).all()),
                           "labels_equal_saved_inside_mask": bool((ex[mm] == saved[mm] - 1).all()),
                           "predicted_px_removed_by_label_mask_share": round(float((~ign).mean()), 5)}
            s[name] = v
            print(code, name, v, flush=True)
        res["sheets"][code] = s
    json.dump(res, open(out_json, "w"), indent=1, default=float)


if __name__ == "__main__":
    main(sys.argv[1])
