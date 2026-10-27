"""Run the unmodified R1 legend-driven recognizer on a GSJ sheet and score it against the
official GSJ vectors (rasterized on the same pixel grid by gsj_gt.py).

R1 is run exactly as shipped: swatches detected automatically in the sheet's legend column,
`classify(..., self_train=True)` and `classify_nearest_color`, polygonized with R1's
`polygons_from_labels`. Nothing from the ground truth is used to produce predictions.

Evaluation needs a correspondence between R1 classes (swatch ids S00..) and official units
(MAJOR_CODE). R1 has no OCR'd codes here, so the correspondence is computed *for evaluation only*
by maximum-weight 1:1 matching on pixel overlap (Hungarian). This is an upper bound on what
correct legend association could give R1's segmentation; it is reported next to many-to-one
purity so the two are not confused.
"""
import json, sys, time, resource
from pathlib import Path
import cv2, numpy as np
from scipy.optimize import linear_sum_assignment

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "src"))
from scan2arcgis.recog.legend_classifier import LegendClass, classify, classify_nearest_color  # noqa: E402
from scan2arcgis.recog.legend_swatches import detect_swatches  # noqa: E402
from scan2arcgis.vector.polygonize import polygons_from_labels  # noqa: E402

cv2.setNumThreads(4)


def neatline_mask(fr, shape, s):
    c = np.array([fr["corners_px"][k] for k in ("tl", "tr", "br", "bl")], np.float64) * s
    m = np.zeros(shape, np.uint8); cv2.fillPoly(m, [np.round(c).astype(np.int32)], 1)
    return m.astype(bool)


def boundary(lab):
    b = np.zeros(lab.shape, bool)
    b[:, 1:] |= lab[:, 1:] != lab[:, :-1]; b[1:, :] |= lab[1:, :] != lab[:-1, :]
    return b


def line_prf(pred, gt, valid, tol):
    pred = pred & valid; gt = gt & valid
    if gt.sum() == 0 or pred.sum() == 0: return {"precision": None, "recall": None, "f1": None}
    dg = cv2.distanceTransform((~gt).astype(np.uint8), cv2.DIST_L2, 3)
    dp = cv2.distanceTransform((~pred).astype(np.uint8), cv2.DIST_L2, 3)
    p = float((dg[pred] <= tol).mean()); r = float((dp[gt] <= tol).mean())
    return {"precision": p, "recall": r, "f1": 2 * p * r / (p + r) if p + r else 0.0,
            "pred_px": int(pred.sum()), "gt_px": int(gt.sum())}


def evaluate(pred, gt, valid, units, tol):
    v = valid & (gt >= 0)
    P, G = pred[v], gt[v]
    pk = np.unique(P[P >= 0]); gk = np.arange(len(units))
    pi = {k: i for i, k in enumerate(pk)}
    M = np.zeros((len(pk), len(gk)), np.int64)
    sel = P >= 0
    np.add.at(M, (np.vectorize(pi.get)(P[sel]), G[sel]), 1)
    area_p = M.sum(1); area_g = np.bincount(G, minlength=len(gk))
    r, c = linear_sum_assignment(-M)
    match = {int(gk[j]): int(pk[i]) for i, j in zip(r, c) if M[i, j] > 0}
    per = []
    for j, u in enumerate(units):
        inter = M[pi[match[j]], j] if j in match else 0
        union = area_g[j] + (area_p[pi[match[j]]] if j in match else 0) - inter
        dom = int(pk[M[:, j].argmax()]) if M[:, j].sum() else None
        per.append({"major_code": u["major_code"], "name": u["legend"].get("LEGEND01"),
                    "gt_px": int(area_g[j]), "matched_pred": None if j not in match else f"S{match[j]:02d}",
                    "iou_matched": float(inter / union) if union else 0.0,
                    "dominant_pred": None if dom is None else f"S{dom:02d}",
                    "dominant_share": float(M[:, j].max() / max(area_g[j], 1)),
                    "n_pred_classes_covering_5pct": int((M[:, j] > 0.05 * area_g[j]).sum())})
    # pixel accuracy under the 1:1 matching (unmatched pred classes count as wrong)
    lut = {p: g for g, p in match.items()}
    mapped = np.array([lut.get(int(x), -2) for x in P]) if len(P) < 3_000_000 else None
    acc = float((mapped == G).mean()) if mapped is not None else float(sum(M[pi[p], g] for g, p in match.items()) / len(G))
    # many-to-one purity: each pred class -> its majority GT unit
    purity = float(M.max(1).sum() / max(M.sum(), 1))
    # fragmentation: connected components of each GT unit in prediction vs GT
    gt_cc = sum(cv2.connectedComponents((gt == j).astype(np.uint8) & v.astype(np.uint8), connectivity=4)[0] - 1 for j in gk)
    pr_cc = sum(cv2.connectedComponents((pred == k).astype(np.uint8) & v.astype(np.uint8), connectivity=4)[0] - 1 for k in pk)
    gb, pb = boundary(np.where(v, gt, -1)) & v, boundary(np.where(v, pred, -1)) & v
    ious = np.array([p["iou_matched"] for p in per]); w = np.array([p["gt_px"] for p in per], float)
    small = [p for p in per if p["gt_px"] < 20000 * (pred.shape[0] / 3050) ** 2]
    return {"n_gt_units": len(units), "n_pred_classes_used": int(len(pk)), "n_units_matched": len(match),
            "pixel_acc_matched": acc, "purity_many_to_one": purity,
            "miou_matched_all_units": float(ious.mean()), "fw_iou_matched": float((ious * w).sum() / w.sum()),
            "units_iou_ge_0.5": int((ious >= 0.5).sum()), "units_iou_lt_0.2": int((ious < 0.2).sum()),
            "small_units": {"n": len(small), "n_iou_ge_0.5": int(sum(p["iou_matched"] >= 0.5 for p in small))},
            "components": {"gt": int(gt_cc), "pred": int(pr_cc), "ratio": float(pr_cc / max(gt_cc, 1))},
            "boundary_from_areas": line_prf(pb, gb, v, tol), "per_unit": per,
            "matching_note": "1:1 Hungarian on pixel overlap, evaluation only (upper bound of legend association)"}


def main(img, frame_json, gt_dir, out_dir, scale=0.5):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    fr = json.load(open(frame_json)); s = float(scale)
    full = cv2.cvtColor(cv2.imread(str(img)), cv2.COLOR_BGR2RGB)
    rgb = cv2.resize(full, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    h, w = rgb.shape[:2]
    gt = cv2.resize(np.load(Path(gt_dir) / "gt_units.npy"), (w, h), interpolation=cv2.INTER_NEAREST)
    gtc = cv2.resize(np.load(Path(gt_dir) / "gt_contacts.npy"), (w, h), interpolation=cv2.INTER_NEAREST) > 0
    gtf = cv2.resize(np.load(Path(gt_dir) / "gt_faults.npy"), (w, h), interpolation=cv2.INTER_NEAREST) > 0
    units = json.load(open(Path(gt_dir) / "units.json"))
    mm = neatline_mask(fr, (h, w), s)
    # inner margin: the neatline itself and outside-of-sheet tick labels are not map content
    mm = cv2.erode(mm.astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool)
    xl = int(min(fr["corners_px"]["tl"][0], fr["corners_px"]["bl"][0]) * s) - 10
    sw = detect_swatches(rgb, (0, 0, xl, h), min_side=max(8, int(18 * s * 2) // 2), max_side=int(400 * s))
    classes = [LegendClass(i, d["legend_entry_id"], tuple(d["box"]), d["legend_entry_id"]) for i, d in enumerate(sw)]
    res = {"image": Path(img).name, "scale": s, "work_size": [w, h], "n_swatches": len(sw),
           "n_official_units": len(units), "methods": {}}
    tol = max(1.5, 3.0 * s * 2 / 2)
    for name, fn in [("legend_nearest_color", lambda: classify_nearest_color(rgb, mm, classes)),
                     ("legend_rf", lambda: classify(rgb, mm, classes, self_train=False)),
                     ("legend_rf_selftrain", lambda: classify(rgb, mm, classes, self_train=True))]:
        t0 = time.time(); r0 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        ar = fn(); dt = time.time() - t0
        lab = ar.labels.astype(np.int32)
        ev = evaluate(lab, gt, mm, units, tol)
        polys = polygons_from_labels(lab, mm, min_area_px=int(50 * s * s * 4))
        cb = boundary(np.where(mm, lab, -1)) & mm
        ev["contacts_vs_official_geoL"] = line_prf(cb, gtc, mm, tol)
        ev["faults_vs_official_geoL_recall_only"] = line_prf(cb, gtf, mm, tol)["recall"]
        ev["n_polygons"] = len(polys); ev["runtime_s"] = dt
        ev["peak_rss_mb"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6
        res["methods"][name] = ev
        np.save(out / f"pred_{name}.npy", lab.astype(np.int16))
        print(name, json.dumps({k: (round(v, 3) if isinstance(v, float) else v) for k, v in ev.items()
                                if k not in ("per_unit", "boundary_from_areas", "contacts_vs_official_geoL", "matching_note")}), flush=True)
    res["swatches"] = [{"id": d["legend_entry_id"], "box": d["box"], "fill_rgb": d["fill_rgb"]} for d in sw]
    np.save(out / "gt_work.npy", gt.astype(np.int16)); np.save(out / "map_mask.npy", mm)
    json.dump(res, open(out / "r1_eval.json", "w"), ensure_ascii=False, indent=1, default=float)


if __name__ == "__main__":
    main(*sys.argv[1:5], *(sys.argv[5:6] or []))
