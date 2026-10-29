"""R4-A2.1 training: R4-A2 code (r4a2_train.py, unchanged) with the v2 supervision and the v2 overfit gate.
All v2 settings come from experiments/R4A/r4a2_1/freeze_config_v2.json.

Supervision change (only change to training): the per-pixel loss weight replaces the binary IGNORE_TRAIN mask.
  IGNORE_EVAL (outside geo_A, image-edge band)  weight 0
  d <= 2 px   soft target exp(-d^2/2) (unchanged)  weight 1
  2 < d <= 4  target 0 (was ignored)               weight W_2_4
  4 < d <= 8  target 0 (was ignored)               weight W_4_8
  d > 8 px    target 0 (unchanged)                 weight 1
d = official distance to UNIT_BOUNDARY (dist.npy, same as the frozen labels). The M2 distance loss uses the same
weights. Evaluation truth (unit_boundary.npy) is not moved or widened.
Usage: r4a2_1_train.py <M1|M2> <out_dir> [--overfit]   (.venv-ml)
"""
import json, sys, time
from pathlib import Path
import cv2, numpy as np, torch, torch.nn.functional as F
from skimage.morphology import skeletonize

sys.path.insert(0, str(Path(__file__).parent))
import r4a2_train as base  # noqa: E402
from r4a2_1_p0_diag import prf, centreline_err  # noqa: E402
from r4a2_1_labels import sup_weight, pstar as _pstar  # noqa: E402

ROOT = base.ROOT
CFG2 = json.load(open(ROOT / "experiments/R4A/r4a2_1/freeze_config_v2.json"))
_frozen_load_sheet = base.load_sheet       # kept before formal() patches base.load_sheet (else infinite recursion)
SUP = CFG2["supervision"]; GATE = {**CFG2["overfit_gate"], **CFG2["overfit_gate"]["criteria_all_required"]}


def load_sheet(code, rng):
    """Frozen loader (same sampling points and rng use), then S["ign"] is replaced by the v2 weight map, so the
    frozen crop()/augment()/to_batch() carry the weight in the slot that held IGNORE_TRAIN."""
    S = _frozen_load_sheet(code, rng)
    d = ROOT / "runs/r4a2" / code
    S["ign"] = sup_weight(np.load(d / "dist.npy"), np.load(d / "ignore.npy"), SUP["weight_2_4px"], SUP["weight_4_8px"]).astype(np.float16)
    return S


def loss_fn(out, tb, w, dist, model_name):
    bce = F.binary_cross_entropy_with_logits(out[:, 0], tb, pos_weight=torch.tensor(SUP["pos_weight"], device=out.device), reduction="none")
    loss = (bce * w).sum() / w.sum().clamp(min=1)
    if model_name == "M2":
        loss = loss + SUP["m2_dist_l1_weight"] * ((torch.sigmoid(out[:, 1]) - dist / 32).abs() * w).sum() / w.sum().clamp(min=1)
    return loss


def pstar(tb, w):
    return np.where(w > 0, _pstar(tb, SUP["pos_weight"]), np.nan)


def gate_metrics(prob, items, dist_pred=None):
    tb = items[1].astype(np.float32); w = items[2].astype(np.float32); g = items[4] > 0
    thr = GATE["threshold"]; sk = max(int(skeletonize(g).sum()), 1)
    sup = w > 0; ps = pstar(tb, w)
    m = {"fit_mae_supervised": float(np.abs(prob - ps)[sup].mean())}
    for th in sorted({0.5, thr}):
        p = prob > th
        m[f"thr_{th}"] = {**{f"F1_tol{t}": prf(p, g, t)["F1"] for t in (1, 2, 3)},
                          "P_tol1": prf(p, g, 1)["P"], "R_tol1": prf(p, g, 1)["R"],
                          "band_width": float(p.sum() / sk), "centreline": centreline_err(p, g)}
    if dist_pred is not None:
        m["m2_dist_mae_px_supervised"] = float(np.abs(dist_pred - items[3].astype(np.float32))[sup].mean())
    return m


def gate_pass(hist, model_name):
    last = hist[-1]["metrics"]; t = last[f"thr_{GATE['threshold']}"]; c = t["centreline"] or {}
    peak = max(h["metrics"][f"thr_{GATE['threshold']}"]["F1_tol1"] for h in hist)
    checks = {"fit_mae_supervised": last["fit_mae_supervised"] <= GATE["fit_mae_supervised_max"],
              "centreline_pred_to_truth": c.get("pred_to_truth_mean", 99) <= GATE["centreline_mean_px_max"],
              "centreline_truth_to_pred": c.get("truth_to_pred_mean", 99) <= GATE["centreline_mean_px_max"],
              "F1_tol1": t["F1_tol1"] >= GATE["F1_tol1_min"], "F1_tol2": t["F1_tol2"] >= GATE["F1_tol2_min"],
              "F1_tol3": t["F1_tol3"] >= GATE["F1_tol3_min"], "band_width": t["band_width"] <= GATE["band_width_max"],
              "no_degradation_F1": t["F1_tol1"] >= peak - GATE["degradation_F1_drop_max"],
              "no_degradation_loss": hist[-1]["loss"] <= hist[len(hist) // 2 - 1]["loss"]}
    if model_name == "M2":
        checks["m2_dist_mae"] = last["m2_dist_mae_px_supervised"] <= GATE["m2_dist_mae_px_max"]
    return checks, all(checks.values())


def save_vis(prob, items, path):
    """Local-only visual: RGB | probability | p>thr (green) vs UNIT_BOUNDARY (magenta)."""
    rgb = items[0][..., ::-1].copy(); pr = cv2.applyColorMap((prob * 255).astype(np.uint8), cv2.COLORMAP_VIRIDIS)
    ov = (rgb * 0.5).astype(np.uint8); ov[items[4] > 0] = (255, 0, 255); ov[prob > GATE["threshold"]] = (0, 255, 0)
    ov[(prob > GATE["threshold"]) & (items[4] > 0)] = (255, 255, 255)
    cv2.imwrite(str(path), np.hstack([rgb, pr, ov]))


def overfit(model_name, out_dir):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(base.SEED); rng = np.random.default_rng(base.SEED)
    dev = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    model = base.UNet(1 if model_name == "M1" else 2).to(dev)
    S = load_sheet(base.CFG["data_roles"]["train"][0], rng)
    items, where = base.crop(S, rng, "unit_boundary_pixel")
    assert list(where) == GATE["tile"], where
    opt = torch.optim.AdamW(model.parameters(), lr=base.CFG["optimisation"]["lr"], weight_decay=base.CFG["optimisation"]["weight_decay"])
    log = {"model": model_name, "version": "R4-A2.1", "device": str(dev), "tile": where, "seed": base.SEED, "loss_curve": [], "history": []}
    t0 = time.time()
    for step in range(1, GATE["steps"] + 1):
        rgb, tb, w, dist, _ = base.to_batch([items], dev)
        model.train(); loss = loss_fn(model(rgb), tb, w, dist, model_name)
        opt.zero_grad(); loss.backward(); opt.step()
        if step % 25 == 0: log["loss_curve"].append([step, float(loss)])
        if step % 50 == 0:
            model.eval()
            with torch.no_grad(): o = model(rgb)[0]
            prob = torch.sigmoid(o[0]).float().cpu().numpy()
            dp = torch.sigmoid(o[1]).float().cpu().numpy() * 32 if model_name == "M2" else None
            log["history"].append({"step": step, "loss": float(loss), "metrics": gate_metrics(prob, items, dp)})
            t = log["history"][-1]["metrics"][f"thr_{GATE['threshold']}"]
            print(model_name, step, round(float(loss), 4), "F1@1/2/3", [round(t[f"F1_tol{k}"], 3) for k in (1, 2, 3)],
                  "band", round(t["band_width"], 2), flush=True)
        if time.time() - t0 > GATE["minutes_max"] * 60: log["stopped"] = "time cap"; break
    log["minutes"] = round((time.time() - t0) / 60, 2)
    log["checks"], log["pass"] = gate_pass(log["history"], model_name) if "stopped" not in log else ({}, False)
    np.save(out / "prob.npy", prob.astype(np.float16)); save_vis(prob, items, out / "overfit_vis.png")
    json.dump(log, open(out / "overfit_log.json", "w"), indent=1)
    print(model_name, "PASS" if log["pass"] else "FAIL", log["checks"], log["minutes"], "min")
    return log


def formal(model_name, out_dir):
    """Frozen R4-A2 formal loop (r4a2_train.main) with the v2 loader and loss swapped in; nothing else changes."""
    base.load_sheet = load_sheet; base.loss_fn = loss_fn
    base.main(model_name, out_dir, overfit=False)


if __name__ == "__main__":
    (overfit if "--overfit" in sys.argv else formal)(sys.argv[1], sys.argv[2])
