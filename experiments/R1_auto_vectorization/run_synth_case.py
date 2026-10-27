"""R1 comparison on one synthetic case with exact ground truth.

Usage: python run_synth_case.py <case_dir> <out_dir> [--sam MODEL_DIR] [--skip-legacy-boundary]
Writes <out_dir>/<case>/metrics.json and overlay images.
"""
from __future__ import annotations

import argparse, json, sys, time, resource
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from scan2arcgis.recog.legend_classifier import LegendClass, classify, classify_nearest_color  # noqa
from scan2arcgis.recog.lines import contacts_from_labels, fault_candidates  # noqa
from scan2arcgis.eval.raster_metrics import (pixel_metrics, line_buffer_f1, object_f1,  # noqa
                                             rasterize_polylines, class_boundaries, auroc)
from scan2arcgis.adapters import legacy as legacy_adapter  # noqa
from scan2arcgis.confidence.signals import region_confidence, review_tiles, error_capture  # noqa

TOL = 3.0


def overlay(rgb, labels, palette, lines=None, err=None):
    out = rgb.copy()
    col = np.zeros_like(rgb)
    for c, p in palette.items():
        col[labels == c] = p
    out = (0.35 * out + 0.65 * col).astype(np.uint8)
    out[labels < 0] = (rgb[labels < 0] * 0.4).astype(np.uint8)
    if err is not None:
        out[err] = (255, 0, 255)
    if lines is not None:
        out[lines] = (0, 0, 0)
    return out


def evaluate_area(name, lab, gt, gt_inst, valid, raw_scores=None):
    pm = pixel_metrics(lab, gt, valid)
    ob = object_f1(lab, gt, gt_inst, valid)
    bd = line_buffer_f1(class_boundaries(lab, valid), class_boundaries(gt, valid), TOL, valid)
    res = {"pixel": {k: v for k, v in pm.items() if k != "iou_per_class"}, "object": {k: v for k, v in ob.items() if not k.startswith("_")},
           "contact_from_area": bd}
    return res, ob


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("case"); ap.add_argument("out")
    ap.add_argument("--sam", default=None); ap.add_argument("--skip-legacy-boundary", action="store_true")
    ap.add_argument("--legacy", default=str(ROOT / "legacy" / "backend"))
    a = ap.parse_args()
    case = Path(a.case); out = Path(a.out) / case.name; out.mkdir(parents=True, exist_ok=True)
    rgb_full = cv2.cvtColor(cv2.imread(str(case / "image.png")), cv2.COLOR_BGR2RGB)
    gt_full = np.load(case / "gt_labels.npy"); inst_full = np.load(case / "gt_instances.npy")
    meta = json.loads((case / "gt.json").read_text())
    x, y, w, h = meta["map_box"]
    valid_full = np.zeros(gt_full.shape, bool); valid_full[y:y + h, x:x + w] = True
    palette = {e["class_id"]: tuple(e["fill_rgb"]) for e in meta["legend"]}
    classes = [LegendClass(e["class_id"], e["legend_code"], tuple(e["swatch_box"]), e["legend_entry_id"]) for e in meta["legend"]]
    gt_contacts = class_boundaries(gt_full, valid_full)
    gt_faults = rasterize_polylines(meta["faults"], gt_full.shape, 1) & valid_full
    gt_all = gt_contacts | gt_faults
    report = {"case": case.name, "config": meta["config"], "tol_px": TOL, "methods": {}}
    S = (slice(y, y + h), slice(x, x + w))

    # --- new: legend-driven classifiers (see full image incl. legend panel for swatches)
    for fn, kw in [(classify_nearest_color, {}), (classify, {"self_train": False}), (classify, {"self_train": True})]:
        t = time.perf_counter(); r = fn(rgb_full, valid_full, classes, **kw); secs = time.perf_counter() - t
        res, ob = evaluate_area(r.method, r.labels, gt_full, inst_full, valid_full)
        conf = region_confidence(r.labels, r.margin, valid_full, ob["_pred_inst"])
        ids = sorted(ob["_correct"]); sc = np.array([conf.get(i, 0.0) for i in ids]); ok = np.array([ob["_correct"][i] for i in ids])
        res["confidence"] = {"status": "UNCALIBRATED", "signal": "mean_margin_of_region",
                             "auroc_correct_vs_signal": auroc(sc, ok), "n_objects": int(len(ids))}
        err = (r.labels != gt_full) & valid_full
        tiles = review_tiles(r.margin, valid_full, tile=64)
        res["review_tiles"] = error_capture(tiles, err, fractions=(0.05, 0.1, 0.2, 0.3))
        flt, _, _ = fault_candidates(rgb_full, r.labels, valid_full)
        res["fault_candidates"] = line_buffer_f1(flt, gt_faults, TOL, valid_full)
        res["all_lines"] = line_buffer_f1(contacts_from_labels(r.labels, valid_full) | flt, gt_all, TOL, valid_full)
        res["runtime_s"] = secs
        report["methods"][r.method] = res
        np.save(out / f"labels_{r.method}.npy", r.labels); np.save(out / f"margin_{r.method}.npy", r.margin)
        cv2.imwrite(str(out / f"overlay_{r.method}.jpg"), cv2.cvtColor(overlay(rgb_full, r.labels, palette, contacts_from_labels(r.labels, valid_full) | flt, err), cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 85])

    # --- legacy stratigraphy (map area only; legacy needs exact legend RGB, which we give it)
    try:
        lab_c, feats, secs = legacy_adapter.run_stratigraphy(Path(a.legacy), rgb_full[S], meta["legend"])
        lab = np.full(gt_full.shape, -1, np.int16); lab[S] = lab_c
        res, ob = evaluate_area("legacy_stratigraphy", lab, gt_full, inst_full, valid_full)
        res["n_polygons"] = len(feats); res["runtime_s"] = secs
        res["unlabeled_fraction"] = float((lab[valid_full] < 0).mean())
        scores = [f["raw_score"] for f in feats if f["raw_score"] is not None]
        res["confidence"] = {"status": "UNCALIBRATED", "signal": "legacy confidence",
                             "distinct_values": sorted(set(round(s, 3) for s in scores))[:10]}
        report["methods"]["legacy_stratigraphy"] = res
        err = (lab != gt_full) & valid_full
        cv2.imwrite(str(out / "overlay_legacy_stratigraphy.jpg"), cv2.cvtColor(overlay(rgb_full, lab, palette, class_boundaries(lab, valid_full), err), cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 85])
    except Exception as e:  # record, do not hide
        report["methods"]["legacy_stratigraphy"] = {"error": repr(e)}

    if not a.skip_legacy_boundary:
        try:
            lines, lmeta, secs = legacy_adapter.run_boundary(Path(a.legacy), rgb_full[S])
            shifted = [[(px + x, py + y) for px, py in ln] for ln in lines]
            m = rasterize_polylines(shifted, gt_full.shape, 1) & valid_full
            report["methods"]["legacy_boundary"] = {
                "all_lines": line_buffer_f1(m, gt_all, TOL, valid_full),
                "faults_recall_only": line_buffer_f1(m, gt_faults, TOL, valid_full)["recall"],
                "n_lines": len(lines), "runtime_s": secs,
                "kinds": {k: sum(1 for q in lmeta if q["kind"] == k) for k in set(q["kind"] for q in lmeta)},
                "confidence": {"status": "UNCALIBRATED", "distinct_values": sorted(set(round(q["raw_score"], 3) for q in lmeta if q["raw_score"] is not None))[:10]}}
            np.save(out / "legacy_boundary_mask.npy", m)
        except Exception as e:
            report["methods"]["legacy_boundary"] = {"error": repr(e)}

    if a.sam:
        from scan2arcgis.recog.sam_refine import sam_refine
        base = np.load(out / "labels_legend_rf_selftrain.npy"); margin = np.load(out / "margin_legend_rf_selftrain.npy")
        t = time.perf_counter(); lab, info = sam_refine(Path(a.sam), rgb_full, base, margin, valid_full, (x, y, w, h)); secs = time.perf_counter() - t
        res, ob = evaluate_area("sam_refined", lab, gt_full, inst_full, valid_full)
        res["runtime_s"] = secs; res["sam"] = info
        report["methods"]["legend_rf_selftrain+sam2"] = res
        cv2.imwrite(str(out / "overlay_sam.jpg"), cv2.cvtColor(overlay(rgb_full, lab, palette, class_boundaries(lab, valid_full), (lab != gt_full) & valid_full), cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 85])

    report["peak_rss_mb"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    (out / "metrics.json").write_text(json.dumps(report, indent=1, default=float))
    print(json.dumps({m: {k: (v.get("f1") if isinstance(v, dict) and "f1" in v else v.get("miou") if isinstance(v, dict) and "miou" in v else None)
                          for k, v in r.items() if isinstance(v, dict)} for m, r in report["methods"].items()}, indent=0, default=float))


if __name__ == "__main__":
    main()
