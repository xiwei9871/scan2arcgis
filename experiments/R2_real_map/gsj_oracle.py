"""Oracle diagnostics on a GSJ sheet: is the bottleneck segmentation or legend/colour association?

EVALUATION ONLY. These methods read the ground truth (official regions and/or official colours)
and must never be imported by a recognizer. Outputs go to their own directory.

All methods are scored on the same pixels: inside the map, inside an official unit, not ink.

  P_swatch   pixel  x detected legend swatch colour   (~ R1 nearest_color, no GT)     [Hungarian UB]
  P_xlsx     pixel  x publisher reference RGB (xlsx)   (perfect legend reading)       [direct]
  P_ideal    pixel  x in-map median colour per unit    (ideal colours)                [direct]
  R_vote     ideal regions x majority of R1 pixel labels                              [Hungarian UB]
  R_swatch   ideal regions x region median vs detected swatch colours                 [Hungarian UB]
  R_xlsx     ideal regions x region median vs xlsx RGB                                [direct]
  R_ideal    ideal regions x region median vs in-map unit medians (leave-region-out)  [direct]
  R1         R1 rf_selftrain as shipped                                               [Hungarian UB]

"Ideal regions" = connected components of each official unit (perfect segmentation, unit
identity hidden). "direct" methods output official units, so their score is semantic accuracy;
Hungarian-scored methods output swatch ids and get the evaluation-only best mapping.
"""
import json, sys
from pathlib import Path
import cv2, numpy as np

sys.path.insert(0, str(Path(__file__).parent))
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "src"))
from scan2arcgis.recog.legend_classifier import ink_mask  # noqa: E402
from gsj_error_analysis import lab_of  # noqa: E402
from gsj_metrics3 import read_legend  # noqa: E402
from gsj_run_r1 import evaluate  # noqa: E402


def direct_scores(pred_unit, gt, m, n_units):
    P, G = pred_unit[m], gt[m]
    ious = []
    for j in range(n_units):
        a, b = G == j, P == j
        u = int((a | b).sum()); ious.append(float((a & b).sum() / u) if u else 0.0)
    return {"pixel_acc": float((P == G).mean()), "miou": float(np.mean(ious)), "units_iou_ge_0.5": int(sum(i >= 0.5 for i in ious)),
            "scoring": "direct (predicts official units)"}


def hung_scores(pred, gt, m, units):
    e = evaluate(pred, gt, m, units, 1.5)
    return {"pixel_acc": e["pixel_acc_matched"], "miou": e["miou_matched_all_units"], "units_iou_ge_0.5": e["units_iou_ge_0.5"],
            "scoring": "Hungarian 1:1 (evaluation-only upper bound)"}


def nearest(cols, refs):
    return ((cols[:, None, :] - refs[None]) ** 2).sum(2).argmin(1)


def main(img, r1_dir, xlsx, out_dir):
    d = Path(r1_dir); out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    ev = json.load(open(d / "r1_eval.json"))
    rgb = cv2.resize(cv2.cvtColor(cv2.imread(str(img)), cv2.COLOR_BGR2RGB), tuple(ev["work_size"]), interpolation=cv2.INTER_AREA)
    gt = np.load(d / "gt_work.npy").astype(np.int32); mm = np.load(d / "map_mask.npy")
    r1 = np.load(d / "pred_legend_rf_selftrain.npy").astype(np.int32)
    per = ev["methods"]["legend_rf_selftrain"]["per_unit"]; nU = len(per)
    units = [{"major_code": p["major_code"], "legend": {"LEGEND01": p["name"]}} for p in per]
    codes = [str(int(float(p["major_code"]))) for p in per]
    legend = read_legend(xlsx)
    ink = ink_mask(rgb, mm)
    m = mm & (gt >= 0) & ~ink
    L = lab_of(cv2.medianBlur(rgb, 5))
    # official instances (ideal regions)
    inst = np.full(gt.shape, -1, np.int32); inst_unit = []; k0 = 0
    for j in range(nU):
        n, cc = cv2.connectedComponents(((gt == j) & mm).astype(np.uint8), connectivity=4)
        sel = cc > 0; inst[sel] = cc[sel] - 1 + k0; inst_unit += [j] * (n - 1); k0 += n - 1
    inst_unit = np.array(inst_unit)
    ys, xs = np.nonzero(m); ii = inst[ys, xs]; order = np.argsort(ii, kind="stable")
    ii_s = ii[order]; cols_s = L[ys, xs][order]; r1_s = r1[ys, xs][order]
    starts = np.r_[0, np.flatnonzero(np.diff(ii_s)) + 1]; ids = ii_s[starts]
    groups = np.split(np.arange(len(ii_s)), starts[1:])
    reg_med = {int(i): np.median(cols_s[g], 0) for i, g in zip(ids, groups)}
    reg_n = {int(i): len(g) for i, g in zip(ids, groups)}
    reg_vote = {int(i): int(np.bincount(r1_s[g][r1_s[g] >= 0]).argmax()) if (r1_s[g] >= 0).any() else -1 for i, g in zip(ids, groups)}
    # unit medians from in-map pixels (ideal colours) and per-region sums for leave-region-out
    unit_med = np.array([np.median(L[m & (gt == j)], 0) if (m & (gt == j)).sum() > 20 else [np.nan] * 3 for j in range(nU)], np.float32)
    sw = np.array([lab_of(np.array(s["fill_rgb"], np.uint8)[None, None])[0, 0] for s in ev["swatches"]], np.float32)
    has_x = [legend.get(c, {}).get("rgb") is not None for c in codes]
    xl = np.array([lab_of(np.array(legend[c]["rgb"], np.uint8)[None, None])[0, 0] if h else [1e6] * 3 for c, h in zip(codes, has_x)], np.float32)
    um = np.nan_to_num(unit_med, nan=1e6)
    res = {"image": Path(img).name, "n_units": nU, "n_instances": int(len(inst_unit)), "scored_px": int(m.sum()),
           "note": "ORACLE diagnostics read ground truth; evaluation only", "methods": {}}
    pix = L[m]
    def paint(vals):
        a = np.full(gt.shape, -1, np.int32); a[m] = vals; return a
    res["methods"]["R1"] = hung_scores(r1, gt, m, units)
    res["methods"]["P_swatch"] = hung_scores(paint(nearest(pix, sw)), gt, m, units)
    res["methods"]["P_xlsx"] = direct_scores(paint(nearest(pix, xl)), gt, m, nU)
    res["methods"]["P_ideal"] = direct_scores(paint(nearest(pix, um)), gt, m, nU)
    # region-level
    rid = np.array(sorted(reg_med)); med = np.array([reg_med[i] for i in rid], np.float32)
    def region_paint(lbl_of_region):
        lut = np.full(int(inst.max()) + 2, -1, np.int32); lut[rid] = lbl_of_region
        return np.where(m, lut[inst], -1)
    res["methods"]["R_vote"] = hung_scores(region_paint(np.array([reg_vote[i] for i in rid])), gt, m, units)
    res["methods"]["R_swatch"] = hung_scores(region_paint(nearest(med, sw)), gt, m, units)
    res["methods"]["R_xlsx"] = direct_scores(region_paint(nearest(med, xl)), gt, m, nU)
    # leave-region-out unit medians (approximated by pixel-weighted means of region medians)
    w = np.array([reg_n[i] for i in rid], np.float64); u_of = inst_unit[rid]
    S = np.zeros((nU, 3)); W = np.zeros(nU)
    np.add.at(S, u_of, med * w[:, None]); np.add.at(W, u_of, w)
    lro = []
    for k in range(len(rid)):
        Sk, Wk = S.copy(), W.copy(); Sk[u_of[k]] -= med[k] * w[k]; Wk[u_of[k]] -= w[k]
        ref = np.where(Wk[:, None] > 0, Sk / np.maximum(Wk, 1e-9)[:, None], 1e6)
        lro.append(int(((ref - med[k]) ** 2).sum(1).argmin()))
    res["methods"]["R_ideal"] = direct_scores(region_paint(np.array(lro)), gt, m, nU)
    res["methods"]["R_ideal"]["note"] = "unit reference = pixel-weighted mean of the unit's OTHER regions' medians; units with one region cannot be predicted for it"
    json.dump(res, open(out / "oracle.json", "w"), ensure_ascii=False, indent=1, default=float)
    for k, v in res["methods"].items():
        print(f"{k:9s} acc={v['pixel_acc']:.3f} mIoU={v['miou']:.3f} iou>=.5={v['units_iou_ge_0.5']}/{nU}  [{v['scoring'][:9]}]")


if __name__ == "__main__":
    main(*sys.argv[1:5])
