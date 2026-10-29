"""R4-A2 training for M1 (boundary) and M2 (boundary + distance-to-boundary).
All settings come from experiments/R4A/r4a2/freeze_config.json (frozen in 0083d28).
Training targets are the offline labels from r4a2_labels.py (built from official vectors).
Usage: r4a2_train.py <M1|M2> <out_dir> [--overfit]
Runs in .venv-ml. Weights and logs go to out_dir (local, under runs/, git-ignored).
"""
import json, resource, sys, time
from pathlib import Path
import cv2, numpy as np, torch, torch.nn as nn, torch.nn.functional as F

ROOT = Path(__file__).resolve().parents[2]
CFG = json.load(open(ROOT / "experiments/R4A/r4a2/freeze_config.json"))
TILE = CFG["sampling"]["tile"]; SEED = CFG["sampling"]["seed"]


class DC(nn.Module):
    def __init__(self, a, b):
        super().__init__()
        self.f = nn.Sequential(nn.Conv2d(a, b, 3, padding=1, bias=False), nn.BatchNorm2d(b), nn.ReLU(inplace=True),
                               nn.Conv2d(b, b, 3, padding=1, bias=False), nn.BatchNorm2d(b), nn.ReLU(inplace=True))

    def forward(self, x): return self.f(x)


class UNet(nn.Module):
    """4 down / 4 up, base 24, BatchNorm, ReLU, bilinear upsampling (freeze_config models.M1.arch)."""
    def __init__(self, heads, base=24):
        super().__init__()
        ch = [base * 2 ** i for i in range(5)]
        self.down = nn.ModuleList([DC(3, ch[0])] + [DC(ch[i - 1], ch[i]) for i in range(1, 5)])
        self.up = nn.ModuleList([DC(ch[i] + ch[i - 1], ch[i - 1]) for i in range(4, 0, -1)])
        self.head = nn.Conv2d(ch[0], heads, 1)

    def forward(self, x):
        skips = []
        for i, d in enumerate(self.down):
            x = d(x if i == 0 else F.max_pool2d(x, 2)); skips.append(x)
        for j, u in enumerate(self.up):
            s = skips[3 - j]
            x = u(torch.cat([F.interpolate(x, size=s.shape[-2:], mode="bilinear", align_corners=False), s], 1))
        return self.head(x)


def load_sheet(code, rng):
    d = ROOT / "runs/r4a2" / code
    S = {"code": code, "rgb": cv2.cvtColor(cv2.imread(str(d / "geotiff_rgb.png")), cv2.COLOR_BGR2RGB),
         "tb": np.load(d / "train_boundary.npy").astype(np.float16), "ign": np.load(d / "ignore_train.npy").astype(np.uint8),
         "dist": np.load(d / "dist.npy").astype(np.float16), "ub": np.load(d / "unit_boundary.npy").astype(np.uint8)}
    inst = np.load(d / "instance.npy").ravel()
    ids, first, cnt = np.unique(inst[inst >= 0], return_index=True, return_counts=True)
    pos = np.flatnonzero(inst >= 0)[first]
    small = pos[(cnt >= 200) & (cnt < 20000)]
    W = S["rgb"].shape[1]
    def sub(flat, n=200000):
        return flat if len(flat) <= n else rng.choice(flat, n, replace=False)
    S["pts"] = {"small_instance_centre": small, "unit_boundary_pixel": sub(np.flatnonzero(S["ub"].ravel())),
                "neg_candidate_ink": sub(np.flatnonzero(np.load(d / "neg_candidate.npy").ravel())),
                "uniform_valid": sub(np.flatnonzero(S["ign"].ravel() == 0))}
    S["W"] = W
    return S


def crop(S, rng, kind):
    H, W = S["rgb"].shape[:2]
    pts = S["pts"][kind]
    if len(pts) == 0: pts = S["pts"]["uniform_valid"]
    p = int(pts[rng.integers(len(pts))]); y, x = divmod(p, S["W"])
    y0 = int(np.clip(y - TILE // 2 + rng.integers(-TILE // 4, TILE // 4 + 1), 0, H - TILE))
    x0 = int(np.clip(x - TILE // 2 + rng.integers(-TILE // 4, TILE // 4 + 1), 0, W - TILE))
    sl = (slice(y0, y0 + TILE), slice(x0, x0 + TILE))
    return [S[k][sl] for k in ("rgb", "tb", "ign", "dist", "ub")], (S["code"], y0, x0)


def augment(arrs, rng):
    rgb, *rest = arrs
    k = int(rng.integers(4)); fh, fv = rng.random() < 0.5, rng.random() < 0.5
    def geo(a):
        a = np.rot90(a, k)
        if fh: a = a[:, ::-1]
        if fv: a = a[::-1]
        return np.ascontiguousarray(a)
    rgb = geo(rgb); rest = [geo(a) for a in rest]
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV).astype(np.int16)
    hsv[..., 0] = (hsv[..., 0] + int(np.rint(rng.uniform(-1.5, 1.5)))) % 180        # +-3 deg hue (OpenCV H = deg/2)
    rgb = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2RGB).astype(np.float32)
    rgb = np.clip((rgb - 128) * rng.uniform(0.9, 1.1) + 128 + 255 * rng.uniform(-0.1, 0.1), 0, 255)
    return [rgb.astype(np.uint8)] + rest


def to_batch(items, dev):
    # .contiguous(): MPS conv backward fails on the non-contiguous permuted view (found in the overfit test)
    rgb = torch.from_numpy(np.stack([a[0] for a in items])).permute(0, 3, 1, 2).contiguous().float().div_(255).sub_(0.5)
    tb, ign, dist, ub = (torch.from_numpy(np.stack([a[i] for a in items]).astype(np.float32)) for i in (1, 2, 3, 4))
    return rgb.to(dev), tb.to(dev), ign.to(dev), dist.to(dev), ub


def loss_fn(out, tb, ign, dist, model_name):
    w = 1 - ign
    bce = F.binary_cross_entropy_with_logits(out[:, 0], tb, pos_weight=torch.tensor(4.0, device=out.device), reduction="none")
    loss = (bce * w).sum() / w.sum().clamp(min=1)
    if model_name == "M2":
        loss = loss + ((torch.sigmoid(out[:, 1]) - dist / 32).abs() * w).sum() / w.sum().clamp(min=1)
    return loss


def f1_1px(prob, ub):
    p = prob > 0.5; g = ub > 0
    if p.sum() == 0 or g.sum() == 0: return 0.0
    dg = cv2.distanceTransform((~g).astype(np.uint8), cv2.DIST_L2, 3); dp = cv2.distanceTransform((~p).astype(np.uint8), cv2.DIST_L2, 3)
    P = float((dg[p] <= 1).mean()); R = float((dp[g] <= 1).mean())
    return 2 * P * R / (P + R) if P + R else 0.0


def main(model_name, out_dir, overfit=False):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(SEED); rng = np.random.default_rng(SEED)
    dev = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    heads = 1 if model_name == "M1" else 2
    model = UNet(heads).to(dev)
    n_params = sum(p.numel() for p in model.parameters())
    assert n_params <= CFG["budget"]["max_params"], n_params
    roles = CFG["data_roles"]; opt_cfg = CFG["optimisation"]
    t_load = time.time()
    train = [load_sheet(c, rng) for c in (roles["train"][:1] if overfit else roles["train"])]
    mix = CFG["sampling"]["mix"]; kinds, probs = list(mix), np.array(list(mix.values()))
    log = {"model": model_name, "device": str(dev), "params": n_params, "seed": SEED, "overfit": overfit,
           "load_seconds": round(time.time() - t_load, 1), "history": []}
    opt = torch.optim.AdamW(model.parameters(), lr=opt_cfg["lr"], weight_decay=opt_cfg["weight_decay"])
    t0 = time.time()
    if overfit:
        items, where = crop(train[0], rng, "unit_boundary_pixel")
        log["overfit_tile"] = where
        for step in range(1, 301):
            rgb, tb, ign, dist, ub = to_batch([items], dev)
            model.train(); loss = loss_fn(model(rgb), tb, ign, dist, model_name)
            opt.zero_grad(); loss.backward(); opt.step()
            if step % 50 == 0 or step == 300:
                model.eval()
                with torch.no_grad(): prob = torch.sigmoid(model(rgb)[0, 0]).float().cpu().numpy()
                f1 = f1_1px(prob, items[4]); log["history"].append({"step": step, "loss": float(loss), "f1_1px": f1})
                print(model_name, "overfit", step, round(float(loss), 4), "F1@1px", round(f1, 3), flush=True)
            if time.time() - t0 > CFG["budget"]["overfit_minutes_per_model"] * 60: log["stopped"] = "time cap"; break
        log["pass"] = log["history"][-1]["f1_1px"] >= 0.9
    else:
        val = [load_sheet(c, np.random.default_rng(SEED + 1)) for c in roles["validation_model_selection"]]
        vr = np.random.default_rng(SEED + 2)
        vtiles = [crop(val[i % len(val)], vr, kinds[vr.choice(len(kinds), p=probs)])[0] for i in range(64)]
        sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=opt_cfg["max_steps"], eta_min=1e-5)
        best, bad, tiles_seen, peak = float("inf"), 0, 0, 0
        cap = opt_cfg["wall_clock_cap_minutes"] * 60
        for step in range(1, opt_cfg["max_steps"] + 1):
            batch = []
            for _ in range(CFG["sampling"]["batch"]):
                S = train[rng.integers(len(train))]
                batch.append(augment(crop(S, rng, kinds[rng.choice(len(kinds), p=probs)])[0], rng))
            rgb, tb, ign, dist, _ = to_batch(batch, dev)
            model.train(); loss = loss_fn(model(rgb), tb, ign, dist, model_name)
            opt.zero_grad(); loss.backward(); opt.step(); sched.step(); tiles_seen += len(batch)
            if dev.type == "mps": peak = max(peak, torch.mps.driver_allocated_memory())
            if step % 100 == 0: print(model_name, step, round(float(loss), 4), round((time.time() - t0) / 60, 1), "min", flush=True)
            stop = time.time() - t0 > cap
            if step % 1000 == 0 or stop:
                model.eval(); vl = 0.0
                with torch.no_grad():
                    for i in range(0, 64, 8):
                        r_, tb_, ig_, di_, _ = to_batch(vtiles[i:i + 8], dev); vl += float(loss_fn(model(r_), tb_, ig_, di_, model_name)) / 8
                rec = {"step": step, "train_loss": float(loss), "val_loss": vl, "minutes": round((time.time() - t0) / 60, 2), "lr": sched.get_last_lr()[0]}
                if vl < best: best, bad = vl, 0; torch.save(model.state_dict(), out / "best.pt"); rec["saved"] = True
                else: bad += 1
                log["history"].append(rec); print(model_name, "VAL", rec, flush=True)
                json.dump(log, open(out / "train_log.json", "w"), indent=1)
                if bad >= 5: log["stopped"] = f"early stop at {step}"; break
            if stop: log["stopped"] = f"wall-clock cap at step {step}"; break
        else:
            log["stopped"] = "max_steps"
        log.update(steps=step, tiles_seen=tiles_seen, best_val_loss=best, peak_mps_driver_bytes=int(peak))
    log["train_minutes"] = round((time.time() - t0) / 60, 2)
    log["peak_rss_mb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6, 1)
    json.dump(log, open(out / ("overfit_log.json" if overfit else "train_log.json"), "w"), indent=1)
    print(model_name, "done", {k: log.get(k) for k in ("params", "device", "steps", "stopped", "train_minutes", "pass", "best_val_loss")})


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], "--overfit" in sys.argv)
