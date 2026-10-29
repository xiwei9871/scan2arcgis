"""R4-B0 Gate 4: China transfer attribution (rules: preregistration.json gate4). No training, no accuracy.

1. Line-width estimator (pre-registered) validated on 15023 rescaled 0.5 / 0.75 / 1.5.
2. GSJ reference line width = median over the pooled accepted skeleton pixels of the 10 training sheets.
3. Per China work: descriptive image statistics, line width + reliability, scale factor f = w_gsj / w_work.
   Normalised input only if estimator validated, work reliable and 0.5 <= f <= 2.0; else SCALE_UNCERTAIN.
4. M1 / M2 (R4-A2.2 best.pt, unchanged) on original and normalised input; probability statistics and the
   composition of predicted boundary pixels (ink / colour edge without ink / other). Same stats for GSJ 15023/15041
   from the saved R4-A2.2 probability maps.
5. 12 fixed windows: composition for original and normalised; local overlays only.
Implementation details fixed before the run: Lab = cv2 float conversion of RGB/255 (L 0-100); colour-edge
magnitude = sqrt(sum over L,a,b of Sobel3x^2 + Sobel3y^2) / 4, i.e. the Lab step across a sharp edge.
Usage: r4b0_gate4.py <out_dir> <local_dir>   (.venv-ml)
"""
import json, sys
from pathlib import Path
import cv2, numpy as np, torch
from PIL import Image
from skimage.morphology import skeletonize

sys.path.insert(0, str(Path(__file__).parent))
import r4b0_common as C  # noqa: E402
sys.path.insert(0, str(C.ROOT / "experiments/R4A"))
import r4a2_2_infer as I  # noqa: E402
from r4a2_train import UNet  # noqa: E402

G4 = C.PR["gate4"]; LW = G4["line_width_estimator"]
SRC = {"gm2_roi": "data/raw/gm2.jpg", "u1": "data/raw/u1_hejing_K45E001001.png", "u2": "data/raw/u2_ningwu_jingle.png", "u3": "data/raw/u3_qilian_jiuxi.png"}
TRAIN = json.load(open(C.ROOT / "experiments/R4A/r4a2/freeze_config.json"))["data_roles"]["train"]


def ink_mask(rgb):
    g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    bh = cv2.morphologyEx(g, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15)))
    return bh > 40


def line_width(rgb, return_samples=False):
    ink = ink_mask(rgb); H, W = ink.shape
    n, cc = cv2.connectedComponents(ink.astype(np.uint8), connectivity=8)
    sk = skeletonize(ink); dt = cv2.distanceTransform(ink.astype(np.uint8), cv2.DIST_L2, 5)
    lab = cc[sk]; ws = 2 * dt[sk] - 1
    L = np.bincount(lab, minlength=n); S_ = np.bincount(lab, weights=ws, minlength=n); mw = S_ / np.maximum(L, 1)
    acc = (L >= 40) & (L / np.maximum(mw, 1e-6) >= 8); acc[0] = False
    keep = acc[lab]; ys, xs = np.nonzero(sk); ys, xs, wk = ys[keep], xs[keep], ws[keep]
    cells = [float(np.median(wk[(ys * 3 // H == i) & (xs * 3 // W == j)])) for i in range(3) for j in range(3)
             if ((ys * 3 // H == i) & (xs * 3 // W == j)).sum() >= 100]
    cv = float(np.std(cells) / np.mean(cells)) if len(cells) >= 2 else None
    out = {"median_width_px": float(np.median(wk)) if len(wk) else None, "accepted_skeleton_px": int(len(wk)),
           "accepted_line_components": int(acc.sum()), "cells_with_ge100px": len(cells), "cell_median_cv": cv,
           "reliable": bool(len(wk) >= 2000 and len(cells) >= 5 and cv is not None and cv <= 0.25),
           "line_density_skeleton_px_per_1000px2": round(len(wk) / (H * W) * 1000, 3)}
    return (out, wk) if return_samples else out


def image_stats(rgb):
    g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32); ink = ink_mask(rgb)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    hp = g - cv2.GaussianBlur(g, (0, 0), 2)
    return {"size_hw": list(rgb.shape[:2]), "rgb_mean": [round(float(v), 1) for v in rgb.reshape(-1, 3).mean(0)],
            "rgb_std": [round(float(v), 1) for v in rgb.reshape(-1, 3).std(0)], "hsv_saturation_median": float(np.median(hsv[..., 1])),
            "ink_share_blackhat40": round(float(ink.mean()), 4),
            "hillshade_proxy_std_blur8": round(float(cv2.GaussianBlur(g, (0, 0), 8).std()), 2),
            "pattern_proxy_std_highpass2_noink": round(float(hp[~ink].std()), 2)}


def edge_masks(rgb):
    ink1 = cv2.dilate(ink_mask(rgb).astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    lab = cv2.cvtColor(cv2.medianBlur(rgb, 5).astype(np.float32) / 255, cv2.COLOR_RGB2LAB)
    gm = np.sqrt(sum(cv2.Sobel(lab[..., c], cv2.CV_32F, 1, 0) ** 2 + cv2.Sobel(lab[..., c], cv2.CV_32F, 0, 1) ** 2 for c in range(3))) / 4
    return ink1, gm > 20


def prob_stats(prob, ink1, ce):
    p = prob > 0.5; n = max(int(p.sum()), 1)
    return {"share_p_gt_0.5": round(float(p.mean()), 4), "share_p_gt_0.8": round(float((prob > 0.8).mean()), 4),
            "quantiles_50_90_99": [round(float(v), 3) for v in np.percentile(prob, [50, 90, 99])],
            "composition_p_gt_0.5": {"on_ink": round(float((p & ink1).sum() / n), 4), "colour_edge_no_ink": round(float((p & ~ink1 & ce).sum() / n), 4),
                                     "other_texture": round(float((p & ~ink1 & ~ce).sum() / n), 4)},
            "image_share_ink_1px": round(float(ink1.mean()), 4), "image_share_colour_edge": round(float(ce.mean()), 4)}


def load_models(dev):
    ms = {}
    for name, heads in (("M1", 1), ("M2", 2)):
        m = UNet(heads).to(dev); m.load_state_dict(torch.load(C.ROOT / f"runs/r4a2/models/{name}_formal/best.pt", map_location=dev, weights_only=True)); ms[name] = (m, heads)
    return ms


def run_models(ms, rgb, dev):
    o1 = I.predict(*ms["M1"][:1], rgb, dev, 1); o2 = I.predict(ms["M2"][0], rgb, dev, 2)
    r = {"M1_prob": o1[0], "M2_prob": o2[0], "M2_dist": o2[1] * 32}
    regs = {**I.regions_for("M1", r["M1_prob"], None), **I.regions_for("M2", r["M2_prob"], r["M2_dist"])}
    return r, regs


def main(out_dir, local_dir):
    out, loc = Path(out_dir), Path(local_dir).resolve(); out.mkdir(parents=True, exist_ok=True); (loc / "windows").mkdir(parents=True, exist_ok=True)
    dev = torch.device("mps" if torch.backends.mps.is_available() else "cpu"); ms = load_models(dev)
    res = {"device": str(dev), "no_accuracy": "no reference labels: descriptive statistics only, no precision / recall / F1"}
    # 1. estimator validation
    g15 = cv2.cvtColor(cv2.imread(str(C.ROOT / "runs/r4a2/15023/geotiff_rgb.png")), cv2.COLOR_BGR2RGB)
    w0 = line_width(g15)["median_width_px"]; val = {"original_median_width_px": w0, "rescaled": {}}
    for f, interp in ((0.5, cv2.INTER_AREA), (0.75, cv2.INTER_AREA), (1.5, cv2.INTER_CUBIC)):
        wf = line_width(cv2.resize(g15, None, fx=f, fy=f, interpolation=interp))["median_width_px"]
        rec = wf / w0; val["rescaled"][str(f)] = {"median_width_px": wf, "recovered_factor": round(rec, 4), "rel_error": round(abs(rec / f - 1), 4), "ok": bool(abs(rec / f - 1) <= 0.15)}
    val["validated"] = all(v["ok"] for v in val["rescaled"].values()); res["estimator_validation"] = val
    print("estimator validation", json.dumps(val), flush=True)
    # 2. GSJ reference
    pooled, per = [], {}
    for c in TRAIN:
        rgb = cv2.cvtColor(cv2.imread(str(C.ROOT / "runs/r4a2" / c / "geotiff_rgb.png")), cv2.COLOR_BGR2RGB)
        s, wk = line_width(rgb, True); per[c] = s; pooled.append(wk)
    w_gsj = float(np.median(np.concatenate(pooled)))
    res["gsj_reference"] = {"median_width_px_pooled_10_training_sheets": w_gsj, "per_sheet": per}
    print("GSJ reference width", w_gsj, flush=True)
    res["gsj_validation_sheets"] = {}
    for c in ("15023", "15041"):
        rgb = cv2.cvtColor(cv2.imread(str(C.ROOT / "runs/r4a2" / c / "geotiff_rgb.png")), cv2.COLOR_BGR2RGB); ink1, ce = edge_masks(rgb)
        res["gsj_validation_sheets"][c] = {"source_dpi": "~200 (GSJ GeoTIFF grid)", "image": image_stats(rgb), "line_width": line_width(rgb),
                                           "M1": prob_stats(np.load(C.PRED / c / "M1/prob.npy").astype(np.float32), ink1, ce),
                                           "M2": prob_stats(np.load(C.PRED / c / "M2/prob.npy").astype(np.float32), ink1, ce)}
    # 3-4. China works
    res["works"] = {}; cache = {}
    for w in G4["works"]:
        wj = json.load(open(C.ROOT / f"runs/real/{w}/work.json")); x, y, ww, hh = wj["map_box_work"]
        rgb = cv2.cvtColor(cv2.imread(str(C.ROOT / f"runs/real/{w}/work.png")), cv2.COLOR_BGR2RGB)[y:y + hh, x:x + ww]
        src = Image.open(C.ROOT / SRC[w])
        lw = line_width(rgb); f = w_gsj / lw["median_width_px"] if lw["median_width_px"] else None
        if val["validated"] and lw["reliable"] and f is not None and 0.5 <= f <= 2.0: status = "NORMALISED"
        else: status = "SCALE_UNCERTAIN"
        r = {"source": SRC[w], "source_size": list(src.size), "source_dpi_metadata": src.info.get("dpi"), "work_scale_vs_source": wj.get("scale"),
             "image": image_stats(rgb), "line_width": lw, "scale_factor_f": None if f is None else round(f, 4), "scale_status": status}
        ink1, ce = edge_masks(rgb)
        o, regs = run_models(ms, rgb, dev)
        r["original"] = {"M1": prob_stats(o["M1_prob"], ink1, ce), "M2": prob_stats(o["M2_prob"], ink1, ce),
                         "regions": {k: int(v.max()) for k, v in regs.items()}}
        if status == "NORMALISED":
            rs = cv2.resize(rgb, None, fx=f, fy=f, interpolation=cv2.INTER_AREA if f < 1 else cv2.INTER_CUBIC)
            on, rn = run_models(ms, rs, dev)
            back = {k: cv2.resize(v, (ww, hh), interpolation=cv2.INTER_NEAREST) for k, v in on.items()}
            r["normalised"] = {"size_hw": list(rs.shape[:2]), "M1": prob_stats(back["M1_prob"], ink1, ce), "M2": prob_stats(back["M2_prob"], ink1, ce),
                               "regions_at_normalised_scale": {k: int(v.max()) for k, v in rn.items()},
                               "line_width_after": line_width(rs)["median_width_px"]}
        else:
            back = None
        res["works"][w] = r; cache[w] = (rgb, o, back, ink1, ce)
        print(w, status, "f", r["scale_factor_f"], "lw", lw, "M1 p>0.5", r["original"]["M1"]["share_p_gt_0.5"],
              "->", r.get("normalised", {}).get("M1", {}).get("share_p_gt_0.5"), flush=True)
    # 5. windows
    res["windows"] = []
    for i, wd in enumerate(G4["windows"]):
        rgb, o, back, ink1, ce = cache[wd["work"]]; s = (slice(wd["y"], wd["y"] + 256), slice(wd["x"], wd["x"] + 256))
        e = {"id": i, **wd, "original_M1": prob_stats(o["M1_prob"][s], ink1[s], ce[s]), "original_M2": prob_stats(o["M2_prob"][s], ink1[s], ce[s])}
        if back is not None:
            e["normalised_M1"] = prob_stats(back["M1_prob"][s], ink1[s], ce[s]); e["normalised_M2"] = prob_stats(back["M2_prob"][s], ink1[s], ce[s])
        comp = e["original_M1"]["composition_p_gt_0.5"]
        e["dominant_original_M1"] = max(comp, key=comp.get)
        res["windows"].append(e)
        pan = [rgb[s]]
        for pr in [o["M1_prob"][s]] + ([back["M1_prob"][s]] if back is not None else []):
            p = rgb[s].copy(); p[pr > 0.5] = (255, 0, 0); pan.append(p)
        pan.append(np.dstack([ink1[s] * 255, ce[s] * 255, np.zeros((256, 256))]).astype(np.uint8))
        cv2.imwrite(str(loc / "windows" / f"w{i:02d}_{wd['work']}.jpg"), cv2.cvtColor(np.hstack(pan), cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 88])
    json.dump(res, open(out / "gate4_transfer.json", "w"), indent=1, default=float)
    print("windows", [(e["id"], e["work"], e["dominant_original_M1"], e["original_M1"]["share_p_gt_0.5"]) for e in res["windows"]])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
