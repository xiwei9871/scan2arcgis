"""R4-B1 Gate 2: label-conflict audit of narrow-unit interior supervision (10 training sheets, labels only).

For every small instance (200 <= area < 20000) and narrow instance (own width < 10 px) records, by width bin:
  pixels, UB pixels, HARD-rule pixels and what the frozen v2 supervision says about them:
    soft-positive (t_v2 > 0, i.e. d <= 2)  -> HARD would flip a positive target to 0 = direct conflict
    v2 low-weight negative (2 < d <= 4 w 0.1, 4 < d <= 8 w 0.3) -> HARD only raises the weight
    on ink within 1 / 2 px (possible printed line under a 1-2 px registration error)
  SAFE-rule pixels (d > 2, not ink1, not UB/IGNORE_EVAL) and instances with usable SAFE support
  (>= 20 px and >= 10% of the instance)
Theoretical target: share of HARD pixels whose loss optimum moves (p*_v2 = 4t/(3t+1) vs 0).
Unchanged-elsewhere check: SAFE weight map equals the v2 weight map on every pixel outside narrow instances.
M2 distance head: target dist/32 is untouched by both rules; reported: mean official dist on SAFE pixels.
Usage: r4b1_gate2.py <out_dir> <local_dir>   (.venv-ml)
"""
import csv, json, sys
from pathlib import Path
import cv2, numpy as np

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "R4A"))
import r4b1_labels as L  # noqa: E402
from r4a2_1_labels import sup_weight  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
TRAIN = json.load(open(ROOT / "experiments/R4A/r4a2/freeze_config.json"))["data_roles"]["train"]
BINS = [("lt3", 0, 3), ("3-6", 3, 6), ("6-10", 6, 10), ("10-20", 10, 20), ("ge20", 20, 1e9)]
USABLE_MIN_PX, USABLE_MIN_SHARE = 20, 0.10


def wbin(w):
    return next(n for n, lo, hi in BINS if lo <= w < hi)


def per_sheet(code, vis_dir):
    d0 = ROOT / "runs/r4a2" / code
    inst = np.load(d0 / "instance.npy"); ub = np.load(d0 / "unit_boundary.npy") > 0; d = np.load(d0 / "dist.npy").astype(np.float32)
    ign = np.load(d0 / "ignore.npy") > 0; t = np.load(d0 / "train_boundary.npy").astype(np.float32)
    bgr = cv2.imread(str(d0 / "geotiff_rgb.png")); ink, ink1, ink2 = L.ink_masks(bgr)
    width = L.own_width(inst); i1 = inst + 1; n = int(i1.max())
    narrow_px, cand, hard, safe = L.rule_sets(inst, ub, d, ign, ink1, width)
    w_v2 = sup_weight(d, ign.astype(np.uint8), 0.1, 0.3); w_safe = L.safe_weight(w_v2, safe)
    unchanged_outside = bool((w_safe[~narrow_px] == w_v2[~narrow_px]).all())
    target_unchanged = True                                              # t_v2 is never written
    cnt = lambda m: np.bincount(i1[m], minlength=n + 1)
    area = np.bincount(i1.ravel(), minlength=n + 1)
    C = {"ub": cnt(ub & ~ign), "hard": cnt(hard), "hard_softpos": cnt(hard & (t > 0)), "hard_d24": cnt(hard & (d > 2) & (d <= 4)),
         "hard_d48": cnt(hard & (d > 4) & (d <= 8)), "hard_dgt8": cnt(hard & (d > 8)), "hard_ink1": cnt(hard & ink1), "hard_ink2": cnt(hard & ink2),
         "safe": cnt(safe)}
    pstar_shift = np.bincount(i1[hard], weights=(4 * t[hard] / (3 * t[hard] + 1)), minlength=n + 1)
    rows = []
    for k in range(1, n + 1):
        if not (200 <= area[k] < 20000): continue
        r = {"sheet": code, "instance": k - 1, "area_px": int(area[k]), "width_own_px": round(float(width[k]), 2), "width_bin": wbin(width[k]),
             "narrow": bool(width[k] < L.NARROW_MAX), **{f"{a}_px": int(v[k]) for a, v in C.items()},
             "hard_mean_pstar_v2": round(float(pstar_shift[k] / max(C["hard"][k], 1)), 4)}
        r["safe_usable"] = bool(C["safe"][k] >= USABLE_MIN_PX and C["safe"][k] >= USABLE_MIN_SHARE * area[k])
        rows.append(r)
    # local sample visual: 3 narrowest small instances, panels map | v2 target | HARD (red) | SAFE (green) with ink (blue)
    for r in sorted([r for r in rows if r["narrow"]], key=lambda r: r["width_own_px"])[:3]:
        k = r["instance"] + 1; ys, xs = np.nonzero(i1 == k); cy, cx = int(np.median(ys)), int(np.median(xs))
        H, W = inst.shape; y0, x0 = int(np.clip(cy - 48, 0, H - 96)), int(np.clip(cx - 48, 0, W - 96)); s = (slice(y0, y0 + 96), slice(x0, x0 + 96))
        base = bgr[s].copy(); tv = cv2.applyColorMap((t[s] * 255).astype(np.uint8), cv2.COLORMAP_VIRIDIS)
        hp = (base * 0.5).astype(np.uint8); hp[ink1[s]] = (255, 0, 0); hp[hard[s]] = (0, 0, 255); hp[hard[s] & ink1[s]] = (255, 0, 255)
        sp = (base * 0.5).astype(np.uint8); sp[ink1[s]] = (255, 0, 0); sp[safe[s]] = (0, 255, 0)
        cv2.imwrite(str(vis_dir / f"{code}_{k - 1}.png"), cv2.resize(np.hstack([base, tv, hp, sp]), None, fx=4, fy=4, interpolation=cv2.INTER_NEAREST))
    sheet = {"unchanged_outside_narrow": unchanged_outside, "target_t_v2_unchanged": target_unchanged,
             "narrow_px": int(narrow_px.sum()), "hard_px": int(hard.sum()), "safe_px": int(safe.sum()),
             "hard_softpos_px": int((hard & (t > 0)).sum()), "hard_ink1_px": int((hard & ink1).sum()), "hard_ink2_px": int((hard & ink2).sum()),
             "safe_mean_official_dist": round(float(d[safe].mean()), 3) if safe.any() else None,
             "safe_share_of_all_supervised_px": round(float(safe.sum() / max((w_v2 > 0).sum(), 1)), 6),
             "weight_mass_added": round(float((w_safe - w_v2).sum()), 1), "weight_mass_v2": round(float(w_v2.sum()), 1)}
    return rows, sheet


def summarize(rows):
    out = {}
    for b, _, _ in BINS:
        rs = [r for r in rows if r["width_bin"] == b]
        if not rs: continue
        S = lambda k: int(sum(r[k] for r in rs))
        hard = S("hard_px")
        out[b] = {"n_instances": len(rs), "area_px": S("area_px"), "ub_px": S("ub_px"), "hard_px": hard,
                  "hard_share_softpos_conflict": round(S("hard_softpos_px") / max(hard, 1), 4),
                  "hard_share_d2_4_lowweight": round(S("hard_d24_px") / max(hard, 1), 4), "hard_share_d4_8": round(S("hard_d48_px") / max(hard, 1), 4),
                  "hard_share_d_gt8": round(S("hard_dgt8_px") / max(hard, 1), 4),
                  "hard_share_on_ink_1px": round(S("hard_ink1_px") / max(hard, 1), 4), "hard_share_on_ink_2px": round(S("hard_ink2_px") / max(hard, 1), 4),
                  "hard_mean_pstar_v2": round(float(np.average([r["hard_mean_pstar_v2"] for r in rs], weights=[max(r["hard_px"], 1e-9) for r in rs])), 4) if hard else None,
                  "safe_px": S("safe_px"), "safe_share_of_area": round(S("safe_px") / max(S("area_px"), 1), 4),
                  "instances_with_any_safe": round(float(np.mean([r["safe_px"] > 0 for r in rs])), 4),
                  "instances_safe_usable": round(float(np.mean([r["safe_usable"] for r in rs])), 4)}
    return out


def main(out_dir, local_dir):
    out, loc = Path(out_dir), Path(local_dir).resolve(); out.mkdir(parents=True, exist_ok=True); (loc / "samples").mkdir(parents=True, exist_ok=True)
    rows, sheets = [], {}
    for c in TRAIN:
        r, s = per_sheet(c, loc / "samples"); rows += r; sheets[c] = s
        print(c, s, flush=True)
    with open(out / "gate2_instances.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    tot = lambda k: int(sum(s[k] for s in sheets.values()))
    res = {"rules": {"HARD": "narrow-unit pixel not in UB -> target 0, weight 1 (R4-B0.1 proposal)",
                     "SAFE": "narrow-unit pixel with d > 2, not within 1 px of ink, not UB / IGNORE_EVAL -> weight 1 (target already 0); target map never changed"},
           "narrow_definition": "own-mask inscribed width < 10 px", "usable": f"SAFE >= {USABLE_MIN_PX} px and >= {USABLE_MIN_SHARE:.0%} of the instance",
           "by_width_bin": summarize(rows), "per_sheet": sheets,
           "totals": {"hard_px": tot("hard_px"), "hard_softpos_conflict_px": tot("hard_softpos_px"), "hard_on_ink1_px": tot("hard_ink1_px"),
                      "safe_px": tot("safe_px"), "all_unchanged_outside_narrow": all(s["unchanged_outside_narrow"] for s in sheets.values())},
           "samples_local": str((loc / "samples").relative_to(ROOT))}
    json.dump(res, open(out / "gate2_label_audit.json", "w"), indent=1)
    print(json.dumps(res["by_width_bin"], indent=1)); print(res["totals"])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
