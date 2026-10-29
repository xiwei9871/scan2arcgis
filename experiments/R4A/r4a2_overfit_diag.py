"""R4-A2 diagnosis of the failed overfit gate (does NOT replace the frozen gate result).

Reruns the frozen overfit procedure of r4a2_train.py (same tile, seed, steps, loss) and, at the
same checkpoints, reports alongside the frozen gate metric (F1 @1 px of p>0.5 against the 1 px
UNIT_BOUNDARY):
  f1_1px_thin   same, after skeletonising p>0.5 (one-pixel-wide prediction)
  f1_2px        p>0.5 at 2 px tolerance
  prec/rec_1px  components of the frozen metric
  band_width    mean width of p>0.5 across the boundary (pixels predicted per boundary pixel)
  fit_mae       mean |sigmoid(logit) - optimal p| on non-ignored pixels, where the optimum of the
                weighted BCE for soft target t and pos_weight w is p* = w t / (w t + 1 - t)
Usage: r4a2_overfit_diag.py <M1|M2> <out_json>    (run in .venv-ml)
"""
import json, sys, time
from pathlib import Path
import cv2, numpy as np, torch
from skimage.morphology import skeletonize

sys.path.insert(0, str(Path(__file__).parent))
from r4a2_train import CFG, SEED, UNet, load_sheet, crop, to_batch, loss_fn  # noqa: E402


def prf(p, g, tol):
    if p.sum() == 0 or g.sum() == 0: return 0.0, 0.0, 0.0
    dg = cv2.distanceTransform((~g).astype(np.uint8), cv2.DIST_L2, 3); dp = cv2.distanceTransform((~p).astype(np.uint8), cv2.DIST_L2, 3)
    P = float((dg[p] <= tol).mean()); R = float((dp[g] <= tol).mean())
    return P, R, (2 * P * R / (P + R) if P + R else 0.0)


def main(model_name, out_json):
    torch.manual_seed(SEED); rng = np.random.default_rng(SEED)
    dev = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    model = UNet(1 if model_name == "M1" else 2).to(dev)
    train = [load_sheet(c, rng) for c in CFG["data_roles"]["train"][:1]]
    opt = torch.optim.AdamW(model.parameters(), lr=CFG["optimisation"]["lr"], weight_decay=CFG["optimisation"]["weight_decay"])
    items, where = crop(train[0], rng, "unit_boundary_pixel")
    g = items[4] > 0; t = items[1].astype(np.float32); ign = items[2] > 0
    pstar = 4 * t / (4 * t + 1 - t)
    hist, t0 = [], time.time()
    for step in range(1, 301):
        rgb, tb, ig, dist, _ = to_batch([items], dev)
        model.train(); loss = loss_fn(model(rgb), tb, ig, dist, model_name)
        opt.zero_grad(); loss.backward(); opt.step()
        if step % 50 == 0:
            model.eval()
            with torch.no_grad(): prob = torch.sigmoid(model(rgb)[0, 0]).float().cpu().numpy()
            p = prob > 0.5
            P1, R1, F1 = prf(p, g, 1); _, _, F1t = prf(skeletonize(p), g, 1); _, _, F2 = prf(p, g, 2)
            rec = {"step": step, "loss": float(loss), "f1_1px_frozen_metric": F1, "prec_1px": P1, "rec_1px": R1,
                   "f1_1px_thin": F1t, "f1_2px": F2, "band_width": float(p.sum() / max(g.sum(), 1)),
                   "fit_mae": float(np.abs(prob - pstar)[~ign].mean())}
            hist.append(rec); print(model_name, {k: round(v, 3) for k, v in rec.items()}, flush=True)
    res = {"model": model_name, "tile": where, "device": str(dev), "minutes": round((time.time() - t0) / 60, 2), "history": hist,
           "note": "diagnostic rerun of the frozen overfit procedure; the frozen gate result (fail) stands in overfit_log.json"}
    json.dump(res, open(out_json, "w"), indent=1)


if __name__ == "__main__":
    main(*sys.argv[1:3])
