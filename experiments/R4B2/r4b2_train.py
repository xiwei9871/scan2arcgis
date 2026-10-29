"""R4-B2 training: pixel-adjacency edge model (rules: experiments/R4B2/r4b2_preregistration.json).

Network: the frozen R4-A2 U-Net (r4a2_train.UNet, base 24) with 3 output channels:
  0 edge_right logit, 1 edge_down logit, 2 auxiliary distance (sigmoid, official dist.npy / 32, as M2)
Data, sheet roles, tile size, batch, sampling mix and anchors, augmentation, optimiser, schedule, validation
interval, early stopping and wall-clock cap are the frozen R4-A2 settings (r4a2_train.main formal branch).
Only the targets / loss differ: edge targets are recomputed from the AUGMENTED unit crop (rotation and flips
change which neighbour is "right" / "down"), so they are always consistent with the image.
Loss = weighted BCE(pos_weight 4) on supervised pairs (both pixels valid); non-edge pairs within one pair of a
true edge (same orientation, 3x3) get weight 0.3 (1 px registration uncertainty, R4-B1T Gate 3), all other
supervised pairs weight 1; + 1.0 * L1 on the distance channel over valid pixels.
Usage: r4b2_train.py <out_dir> [--smoke]   (.venv-ml)
"""
import json, resource, sys, time
from pathlib import Path
import cv2, numpy as np, torch, torch.nn.functional as F

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "R4A"))
import r4a2_train as base  # noqa: E402

ROOT = base.ROOT
PR = json.load(open(ROOT / "experiments/R4B2/r4b2_preregistration.json"))
LOSS = PR["training"]["loss"]
CFG, SEED, TILE = base.CFG, base.SEED, base.TILE


def load_sheet(code, rng):
    S = base.load_sheet(code, rng)                                  # frozen loader (same rng use, same anchors)
    d = ROOT / "runs/r4a2" / code
    unit = np.load(d / "unit.npy").astype(np.int16); ign = np.load(d / "ignore.npy")
    S["unit"] = unit; S["valid"] = ((ign == 0) & (unit >= 0)).astype(np.uint8)
    for k in ("tb", "ign", "ub"): S.pop(k, None)                    # unused by B2, frees memory
    return S


def crop(S, rng, kind):
    """Identical placement to r4a2_train.crop (same rng draws), different arrays."""
    H, W = S["rgb"].shape[:2]
    pts = S["pts"][kind]
    if len(pts) == 0: pts = S["pts"]["uniform_valid"]
    p = int(pts[rng.integers(len(pts))]); y, x = divmod(p, S["W"])
    y0 = int(np.clip(y - TILE // 2 + rng.integers(-TILE // 4, TILE // 4 + 1), 0, H - TILE))
    x0 = int(np.clip(x - TILE // 2 + rng.integers(-TILE // 4, TILE // 4 + 1), 0, W - TILE))
    sl = (slice(y0, y0 + TILE), slice(x0, x0 + TILE))
    return [S[k][sl] for k in ("rgb", "unit", "valid", "dist")], (S["code"], y0, x0)


def targets(unit, valid):
    v = valid > 0
    mr = np.zeros(unit.shape, bool); md = np.zeros(unit.shape, bool)
    mr[:, :-1] = v[:, :-1] & v[:, 1:]; md[:-1] = v[:-1] & v[1:]
    er = np.zeros(unit.shape, bool); ed = np.zeros(unit.shape, bool)
    er[:, :-1] = mr[:, :-1] & (unit[:, :-1] != unit[:, 1:]); ed[:-1] = md[:-1] & (unit[:-1] != unit[1:])
    k = np.ones((3, 3), np.uint8)
    near_r = cv2.dilate(er.astype(np.uint8), k) > 0; near_d = cv2.dilate(ed.astype(np.uint8), k) > 0
    wr = mr.astype(np.float32); wd = md.astype(np.float32)
    wr[mr & ~er & near_r] = LOSS["near_edge_negative_weight"]; wd[md & ~ed & near_d] = LOSS["near_edge_negative_weight"]
    return er.astype(np.float32), ed.astype(np.float32), wr, wd


def to_batch(items, dev):
    rgb = torch.from_numpy(np.stack([a[0] for a in items])).permute(0, 3, 1, 2).contiguous().float().div_(255).sub_(0.5)
    T = [targets(a[1], a[2]) for a in items]
    t = [torch.from_numpy(np.stack([x[i] for x in T])) for i in range(4)]
    valid = torch.from_numpy(np.stack([a[2] for a in items]).astype(np.float32))
    dist = torch.from_numpy(np.stack([a[3] for a in items]).astype(np.float32))
    return rgb.to(dev), [x.to(dev) for x in t], valid.to(dev), dist.to(dev)


def loss_fn(out, t, valid, dist):
    tr, td, wr, wd = t; pw = torch.tensor(LOSS["pos_weight"], device=out.device)
    br = F.binary_cross_entropy_with_logits(out[:, 0], tr, pos_weight=pw, reduction="none")
    bd = F.binary_cross_entropy_with_logits(out[:, 1], td, pos_weight=pw, reduction="none")
    le = ((br * wr).sum() + (bd * wd).sum()) / (wr.sum() + wd.sum()).clamp(min=1)
    ld = ((torch.sigmoid(out[:, 2]) - dist / 32).abs() * valid).sum() / valid.sum().clamp(min=1)
    return le + LOSS["dist_l1_weight"] * ld


def main(out_dir, smoke=False):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(SEED); rng = np.random.default_rng(SEED)
    dev = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    model = base.UNet(3).to(dev); n_params = sum(p.numel() for p in model.parameters())
    assert n_params <= CFG["budget"]["max_params"], n_params
    roles, opt_cfg = CFG["data_roles"], CFG["optimisation"]
    t_load = time.time()
    train = [load_sheet(c, rng) for c in (roles["train"][:1] if smoke else roles["train"])]
    mix = CFG["sampling"]["mix"]; kinds, probs = list(mix), np.array(list(mix.values()))
    log = {"model": "B2_edges", "device": str(dev), "params": n_params, "seed": SEED, "smoke": smoke,
           "load_seconds": round(time.time() - t_load, 1), "history": [], "train_loss_every_100": []}
    val = [load_sheet(c, np.random.default_rng(SEED + 1)) for c in roles["validation_model_selection"]]
    vr = np.random.default_rng(SEED + 2)
    vtiles = [crop(val[i % len(val)], vr, kinds[vr.choice(len(kinds), p=probs)])[0] for i in range(8 if smoke else 64)]
    opt = torch.optim.AdamW(model.parameters(), lr=opt_cfg["lr"], weight_decay=opt_cfg["weight_decay"])
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=opt_cfg["max_steps"], eta_min=1e-5)
    best, bad, tiles_seen, peak = float("inf"), 0, 0, 0
    cap = (0.5 if smoke else opt_cfg["wall_clock_cap_minutes"]) * 60; max_steps = 5 if smoke else opt_cfg["max_steps"]
    t0 = time.time()
    for step in range(1, max_steps + 1):
        batch = []
        for _ in range(CFG["sampling"]["batch"]):
            S = train[rng.integers(len(train))]
            batch.append(base.augment(crop(S, rng, kinds[rng.choice(len(kinds), p=probs)])[0], rng))
        rgb, t, valid, dist = to_batch(batch, dev)
        model.train(); loss = loss_fn(model(rgb), t, valid, dist)
        if not torch.isfinite(loss): log["stopped"] = f"non-finite loss at step {step}"; break
        opt.zero_grad(); loss.backward(); opt.step(); sched.step(); tiles_seen += len(batch)
        if dev.type == "mps": peak = max(peak, torch.mps.driver_allocated_memory())
        if step % 100 == 0:
            log["train_loss_every_100"].append([step, round(float(loss), 5), sched.get_last_lr()[0]])
            print("B2", step, round(float(loss), 4), round((time.time() - t0) / 60, 1), "min", flush=True)
        stop = time.time() - t0 > cap
        if step % 1000 == 0 or stop or (smoke and step == max_steps):
            model.eval(); vl = 0.0
            with torch.no_grad():
                for i in range(0, len(vtiles), 8):
                    r_, t_, v_, d_ = to_batch(vtiles[i:i + 8], dev); vl += float(loss_fn(model(r_), t_, v_, d_)) * len(vtiles[i:i + 8]) / len(vtiles)
            rec = {"step": step, "train_loss": float(loss), "val_loss": vl, "minutes": round((time.time() - t0) / 60, 2), "lr": sched.get_last_lr()[0]}
            if vl < best: best, bad = vl, 0; torch.save(model.state_dict(), out / "best.pt"); rec["saved"] = True
            else: bad += 1
            log["history"].append(rec); print("B2 VAL", rec, flush=True)
            json.dump(log, open(out / "train_log.json", "w"), indent=1)
            if bad >= 5: log["stopped"] = f"early stop at {step}"; break
        if stop: log["stopped"] = f"wall-clock cap at step {step}"; break
    else:
        log["stopped"] = "max_steps"
    log.update(steps=step, tiles_seen=tiles_seen, best_val_loss=best, peak_mps_driver_bytes=int(peak),
               train_minutes=round((time.time() - t0) / 60, 2), peak_rss_mb=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6, 1))
    json.dump(log, open(out / "train_log.json", "w"), indent=1)
    print("B2 done", {k: log.get(k) for k in ("params", "device", "steps", "stopped", "train_minutes", "best_val_loss")})


if __name__ == "__main__":
    main(sys.argv[1], "--smoke" in sys.argv)
