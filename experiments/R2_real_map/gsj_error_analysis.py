"""Attribute every wrong pixel of an R1 prediction on a GSJ sheet to one cause.

Uses the outputs of gsj_run_r1.py (pred_*.npy, gt_work.npy, map_mask.npy, r1_eval.json).
Correctness uses the same evaluation-only 1:1 matching as gsj_run_r1.py.

Causes, assigned in this order (first that applies wins):
  no_swatch     the true unit got no matched R1 class -> R1 had no legend entry for it
  boundary_band within 3 work-px of an official boundary (residual registration / edge blur)
  ink           pixel is under black linework/text; R1 fills these from neighbours
  near_color    predicted class belongs to a unit whose in-map colour is within dE<12 of the truth
  other         everything else (pattern/texture units, legend-vs-print colour shift, ...)
Also reports, per unit, the colour difference between its legend swatch and the same unit as
printed in the map (legend/print shift), and the main confusion pairs.
"""
import json, sys
from pathlib import Path
import cv2, numpy as np

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "src"))
from scan2arcgis.recog.legend_classifier import ink_mask  # noqa: E402


def lab_of(rgb):
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32) * np.array([100 / 255, 1, 1], np.float32) - np.array([0, 128, 128], np.float32)


def main(img, r1_dir, method="legend_rf_selftrain"):
    d = Path(r1_dir); ev = json.load(open(d / "r1_eval.json"))
    s = ev["scale"]
    full = cv2.cvtColor(cv2.imread(str(img)), cv2.COLOR_BGR2RGB)
    rgb = cv2.resize(full, tuple(ev["work_size"]), interpolation=cv2.INTER_AREA)
    gt = np.load(d / "gt_work.npy").astype(np.int32); mm = np.load(d / "map_mask.npy")
    pred = np.load(d / f"pred_{method}.npy").astype(np.int32)
    me = ev["methods"][method]; per = me["per_unit"]
    v = mm & (gt >= 0)
    match = {j: int(p["matched_pred"][1:]) for j, p in enumerate(per) if p["matched_pred"]}
    inv = {p: j for j, p in match.items()}
    pred_unit = np.vectorize(lambda x: inv.get(int(x), -2))(pred)
    wrong = v & (pred_unit != gt)
    ink = ink_mask(rgb, mm)
    L = lab_of(cv2.medianBlur(rgb, 5))
    keep = v & ~ink
    nU = len(per)
    med = np.full((nU, 3), np.nan, np.float32)
    for j in range(nU):
        m = keep & (gt == j)
        if m.sum() > 30: med[j] = np.median(L[m], 0)
    # boundary band
    b = np.zeros(gt.shape, bool); b[:, 1:] |= gt[:, 1:] != gt[:, :-1]; b[1:, :] |= gt[1:, :] != gt[:-1, :]
    band = cv2.dilate(b.astype(np.uint8), np.ones((7, 7), np.uint8)).astype(bool)
    dE = np.full(gt.shape, np.inf, np.float32)
    ys, xs = np.nonzero(wrong)
    pu, gu = pred_unit[ys, xs], gt[ys, xs]
    okp = pu >= 0
    dd = np.full(len(ys), np.inf, np.float32)
    dd[okp] = np.linalg.norm(med[pu[okp]] - med[gu[okp]], axis=1)
    dE[ys, xs] = dd
    no_sw = np.isin(gt, [j for j in range(nU) if j not in match])
    cause = np.zeros(gt.shape, np.uint8)  # 0 correct/outside
    order = [("no_swatch", wrong & no_sw), ("boundary_band", wrong & band), ("ink", wrong & ink),
             ("near_color", wrong & (dE < 12)), ("other", wrong)]
    counts = {}
    for k, (name, m) in enumerate(order, 1):
        m = m & (cause == 0); cause[m] = k; counts[name] = int(m.sum())
    nv = int(v.sum())
    out = {"method": method, "valid_px": nv, "wrong_px": int(wrong.sum()), "wrong_frac": float(wrong.sum() / nv),
           "causes_frac_of_all_px": {k: c / nv for k, c in counts.items()},
           "causes_share_of_errors": {k: c / max(int(wrong.sum()), 1) for k, c in counts.items()}}
    # confusion pairs (true unit -> predicted unit), by area
    pairs = {}
    for g_, p_ in zip(gu.tolist(), pu.tolist()):
        pairs[(g_, p_)] = pairs.get((g_, p_), 0) + 1
    top = sorted(pairs.items(), key=lambda kv: -kv[1])[:15]
    out["top_confusions"] = [{"true": per[g_]["major_code"], "true_name": per[g_]["name"],
                              "pred": (per[p_]["major_code"] if p_ >= 0 else "unmatched_class"),
                              "pred_name": (per[p_]["name"] if p_ >= 0 else None), "px": n,
                              "dE_in_map": (None if p_ < 0 or np.isnan(med[[g_, p_]]).any() else float(np.linalg.norm(med[g_] - med[p_])))}
                             for (g_, p_), n in top]
    # legend swatch vs printed map colour, per matched unit
    sw = {x["id"]: np.array(x["fill_rgb"], np.uint8) for x in ev["swatches"]}
    rows = []
    for j, p in enumerate(per):
        r = {"major_code": p["major_code"], "name": p["name"], "gt_px": p["gt_px"], "iou": p["iou_matched"],
             "has_matched_swatch": p["matched_pred"] is not None}
        if p["matched_pred"] and not np.isnan(med[j]).any():
            c = lab_of(sw[p["matched_pred"]][None, None])[0, 0]
            r["dE_swatch_vs_map"] = float(np.linalg.norm(c - med[j]))
        if not np.isnan(med[j]).any():
            others = [k for k in range(nU) if k != j and not np.isnan(med[k]).any()]
            dk = [float(np.linalg.norm(med[j] - med[k])) for k in others]
            r["nearest_unit_dE"] = min(dk) if dk else None
            r["nearest_unit"] = per[others[int(np.argmin(dk))]]["major_code"] if dk else None
        m = keep & (gt == j)
        r["in_map_texture_std"] = float(L[m].std(0).mean()) if m.sum() > 30 else None
        rows.append(r)
    out["per_unit"] = rows
    vals = [r["dE_swatch_vs_map"] for r in rows if "dE_swatch_vs_map" in r]
    out["legend_vs_print_dE"] = {"median": float(np.median(vals)), "p90": float(np.percentile(vals, 90)), "n": len(vals)}
    nd = [r["nearest_unit_dE"] for r in rows if r.get("nearest_unit_dE") is not None]
    out["units_with_neighbour_dE_lt_10"] = int(sum(x < 10 for x in nd))
    # IoU vs texture: patterned units (high std) vs flat ones
    tex = [(r["in_map_texture_std"], r["iou"]) for r in rows if r["in_map_texture_std"] is not None]
    t = np.array(tex); thr = np.median(t[:, 0])
    out["iou_by_texture"] = {"texture_std_median": float(thr), "iou_mean_flat": float(t[t[:, 0] <= thr, 1].mean()),
                             "iou_mean_textured": float(t[t[:, 0] > thr, 1].mean())}
    json.dump(out, open(d / f"errors_{method}.json", "w"), ensure_ascii=False, indent=1, default=float)
    # error map: correct = desaturated image, errors coloured by cause
    pal = {1: (255, 0, 255), 2: (255, 200, 0), 3: (0, 0, 0), 4: (255, 0, 0), 5: (0, 120, 255)}
    g = cv2.cvtColor(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY), cv2.COLOR_GRAY2RGB)
    vis = (0.35 * g + 0.65 * 255).astype(np.uint8)
    for k, c in pal.items(): vis[cause == k] = c
    vis[~mm] = rgb[~mm]
    cv2.imwrite(str(d / f"error_map_{method}.jpg"), cv2.cvtColor(vis, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 85])
    print(json.dumps({k: out[k] for k in ("wrong_frac", "causes_share_of_errors", "legend_vs_print_dE",
                                         "units_with_neighbour_dE_lt_10", "iou_by_texture")}, default=float))
    for c in out["top_confusions"][:8]: print("  ", c)


if __name__ == "__main__":
    main(*sys.argv[1:4])
