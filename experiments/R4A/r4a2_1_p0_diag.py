"""R4-A2.1 P0: diagnose the failed R4-A2 overfit gate on the SAME 05016 tile (no tile change).

Reruns the frozen R4-A2 overfit procedure (r4a2_train.py: tile, seed, 300 steps, loss) for M1 and M2,
saves the probability map, and separates four explanations:
  A. position not learned        -> centreline error large, recall low
  B. position learned, too wide  -> centreline error small, band width large
  C. threshold / soft-label mismatch -> F1 changes strongly with threshold; optimum p* differs from 0.5 crossing
  D. post-processing             -> not involved in the gate (gate scores raw probabilities)
Also reports the label geometry itself (truth width, soft-label support, IGNORE_TRAIN share) and the
theoretical optimum p* = w t / (w t + 1 - t) (w = pos_weight 4) at 1/2/3 px.
Run in .venv-ml. Output: JSON + local probability maps (runs/r4a2/models/*_p0/).
"""
import json, sys, time
from pathlib import Path
import cv2, numpy as np, torch
from skimage.morphology import skeletonize

sys.path.insert(0, str(Path(__file__).parent))
from r4a2_train import CFG, SEED, UNet, load_sheet, crop, to_batch, loss_fn  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def prf(p, g, tol):
    if p.sum() == 0 or g.sum() == 0: return {"P": 0.0, "R": 0.0, "F1": 0.0}
    dg = cv2.distanceTransform((~g).astype(np.uint8), cv2.DIST_L2, 3); dp = cv2.distanceTransform((~p).astype(np.uint8), cv2.DIST_L2, 3)
    P = float((dg[p] <= tol).mean()); R = float((dp[g] <= tol).mean())
    return {"P": P, "R": R, "F1": 2 * P * R / (P + R) if P + R else 0.0}


def centreline_err(p, g):
    """Symmetric mean distance (px) between the skeleton of the prediction and the skeleton of the truth."""
    sp, sg = skeletonize(p), skeletonize(g)
    if sp.sum() == 0 or sg.sum() == 0: return None
    dg = cv2.distanceTransform((~sg).astype(np.uint8), cv2.DIST_L2, 3); dp = cv2.distanceTransform((~sp).astype(np.uint8), cv2.DIST_L2, 3)
    return {"pred_to_truth_mean": float(dg[sp].mean()), "truth_to_pred_mean": float(dp[sg].mean()),
            "pred_to_truth_p90": float(np.percentile(dg[sp], 90))}


def describe(prob, g, tgt, ign, pstar):
    out = {}
    for th in (0.3, 0.5, 0.7, 0.9):
        p = prob > th
        out[f"thr_{th}"] = {f"tol{t}": prf(p, g, t) for t in (1, 2, 3)}
        out[f"thr_{th}"]["band_width"] = float(p.sum() / max(skeletonize(g).sum(), 1))
        out[f"thr_{th}"]["skeleton_F1_tol1"] = prf(skeletonize(p), g, 1)["F1"]
        out[f"thr_{th}"]["share_pred_in_ignore_band"] = float((p & ign).sum() / max(p.sum(), 1))
    p = prob > 0.5
    out["centreline_thr0.5"] = centreline_err(p, g)
    sup = ~ign
    out["fit_mae_supervised"] = float(np.abs(prob - pstar)[sup].mean())
    out["fit_mae_target_band"] = float(np.abs(prob - pstar)[sup & (tgt > 0)].mean())
    d = cv2.distanceTransform((~g).astype(np.uint8), cv2.DIST_L2, 3)
    out["mean_prob_by_distance_to_truth"] = {f"{a}-{b}px": float(prob[(d >= a) & (d < b)].mean()) for a, b in ((0, 1), (1, 2), (2, 3), (3, 4), (4, 6), (6, 8), (8, 12), (12, 99))}
    return out


def main(out_json):
    torch.manual_seed(SEED)
    dev = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    rng = np.random.default_rng(SEED)
    S = load_sheet(CFG["data_roles"]["train"][0], rng)
    items, where = crop(S, rng, "unit_boundary_pixel")
    g = items[4] > 0; tgt = items[1].astype(np.float32); ign = items[2] > 0
    pstar = 4 * tgt / (3 * tgt + 1)
    res = {"tile": where, "device": str(dev), "labels": {
        "truth_px": int(g.sum()), "truth_skeleton_px": int(skeletonize(g).sum()),
        "truth_width_px": float(g.sum() / max(skeletonize(g).sum(), 1)),
        "truth_note": "UNIT_BOUNDARY marks the pixel on BOTH sides of each unit transition -> ~2 px wide, not 1 px",
        "soft_target_support_px": int((tgt > 0).sum()), "soft_target_gt_0.5_px": int((tgt > 0.5).sum()),
        "ignore_train_share": float(ign.mean()), "supervised_share": float((~ign).mean()),
        "soft_target_values": {f"d={k}": float(np.exp(-k * k / 2)) for k in (0, 1, 2)}},
        "theoretical_optimum": describe(pstar, g, tgt, ign, pstar)}
    for model_name in ("M1", "M2"):
        torch.manual_seed(SEED)
        model = UNet(1 if model_name == "M1" else 2).to(dev)
        opt = torch.optim.AdamW(model.parameters(), lr=CFG["optimisation"]["lr"], weight_decay=CFG["optimisation"]["weight_decay"])
        t0 = time.time(); curve = []
        for step in range(1, 301):
            rgb, tb, ig, dist, _ = to_batch([items], dev)
            model.train(); loss = loss_fn(model(rgb), tb, ig, dist, model_name)
            opt.zero_grad(); loss.backward(); opt.step()
            if step % 25 == 0: curve.append([step, float(loss)])
        model.eval()
        with torch.no_grad(): prob = torch.sigmoid(model(to_batch([items], dev)[0])[0, 0]).float().cpu().numpy()
        od = ROOT / f"runs/r4a2/models/{model_name}_p0"; od.mkdir(parents=True, exist_ok=True)
        np.save(od / "prob.npy", prob.astype(np.float16))
        res[model_name] = {"minutes": round((time.time() - t0) / 60, 2), "loss_curve": curve, **describe(prob, g, tgt, ign, pstar)}
        r = res[model_name]
        print(model_name, "F1@1/2/3 thr0.5", [round(r["thr_0.5"][f"tol{t}"]["F1"], 3) for t in (1, 2, 3)],
              "band", round(r["thr_0.5"]["band_width"], 2), "in_ignore", round(r["thr_0.5"]["share_pred_in_ignore_band"], 3),
              "centre", {k: round(v, 2) for k, v in (r["centreline_thr0.5"] or {}).items()}, flush=True)
    t = res["theoretical_optimum"]["thr_0.5"]
    print("optimum p* F1@1/2/3", [round(t[f"tol{k}"]["F1"], 3) for k in (1, 2, 3)], "band", round(t["band_width"], 2), "| labels", res["labels"])
    json.dump(res, open(out_json, "w"), indent=1)


if __name__ == "__main__":
    main(sys.argv[1])
