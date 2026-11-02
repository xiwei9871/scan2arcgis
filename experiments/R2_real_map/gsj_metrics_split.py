"""Split evaluation of R1 on a GSJ sheet into three families (no change to R1 or to evaluate()).

1. region  (UPPER BOUND): evaluate() with evaluation-only 1:1 Hungarian class matching.
2. semantic: the system's OWN class -> code mapping. R1's only code evidence is `ocr_code`
   (tesseract on the legend swatch box, as in R1's prepare_real.py). A pixel is semantically
   correct only if the code string R1 attached to its class equals the official symbol of the
   true unit. Classes with no OCR code are wrong. The official legend table is used only to
   score, never shown to the recognizer. Exact (case-sensitive) and lenient (alnum, casefold)
   string comparison are both reported.
3. topology: per-unit component counts, polygon-level recall, unit adjacency precision/recall
   (pred classes mapped through the upper-bound matching), polygon validity.
"""
import json, re, sys
from pathlib import Path
import cv2, numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).parent))
from scan2arcgis.recog.legend_swatches import ocr_code  # noqa: E402
from scan2arcgis.vector.polygonize import polygons_from_labels  # noqa: E402


def adjacency(lab, valid):
    pairs = set()
    for a, b in ((lab[:, 1:], lab[:, :-1]), (lab[1:, :], lab[:-1, :])):
        v = (a != b) & (a >= 0) & (b >= 0)
        if valid is not None:
            v &= valid[:a.shape[0], :a.shape[1]] if a.shape == valid[:, 1:].shape or a.shape == valid[1:, :].shape else True
        u = np.unique(np.stack([np.minimum(a[v], b[v]), np.maximum(a[v], b[v])], 1), axis=0)
        pairs |= {tuple(map(int, p)) for p in u}
    return pairs


def norm(s, lenient):
    if s is None or (isinstance(s, float) and np.isnan(s)): return None
    s = str(s).strip()
    return re.sub(r"[^0-9a-z]", "", s.casefold()) if lenient else s


def main(img, r1_dir, xlsx, out_json, method="legend_rf_selftrain"):
    d = Path(r1_dir); ev = json.load(open(d / "r1_eval.json")); s = ev["scale"]
    full = cv2.cvtColor(cv2.imread(str(img)), cv2.COLOR_BGR2RGB)
    gt = np.load(d / "gt_work.npy").astype(np.int32); mm = np.load(d / "map_mask.npy")
    pred = np.load(d / f"pred_{method}.npy").astype(np.int32)
    me = ev["methods"][method]; per = me["per_unit"]
    v = mm & (gt >= 0)
    leg = pd.read_excel(xlsx, "LEGEND_POLY")
    sym = {str(float(r.MAJOR_CODE)): r.symbol for r in leg.itertuples()}
    # --- R1's own code evidence: OCR of each swatch box at full resolution ---
    codes = {}
    for k, sw in enumerate(ev["swatches"]):
        x, y, w, h = [int(round(t / s)) for t in sw["box"]]
        codes[k] = ocr_code(full, (x, y, w, h))
    out = {"method": method, "n_swatches": len(codes), "ocr_codes": {f"S{k:02d}": c for k, c in codes.items()},
           "n_swatches_with_ocr_text": int(sum(c is not None for c in codes.values()))}
    # --- 1. region (upper bound) ---
    out["region_upper_bound"] = {k: me[k] for k in ("pixel_acc_matched", "miou_matched_all_units", "fw_iou_matched",
                                                    "units_iou_ge_0.5", "n_gt_units", "n_units_matched")}
    out["region_upper_bound"]["label"] = "UPPER BOUND: evaluation-only 1:1 Hungarian class matching"
    # --- 2. semantic ---
    G = gt[v]; P = pred[v]
    for lenient in (False, True):
        key = "lenient" if lenient else "exact"
        pc = {k: norm(c, lenient) for k, c in codes.items()}
        gs = [norm(sym.get(u["major_code"]), lenient) for u in per]
        lut = np.array([pc.get(int(x)) for x in range(max(codes) + 2)], dtype=object)
        pcode = lut[np.clip(P, 0, len(lut) - 1)]; pcode[P < 0] = None
        gcode = np.array(gs, dtype=object)[G]
        ok = np.array([a is not None and a == b for a, b in zip(pcode, gcode)])
        ious = []
        for j, g in enumerate(gs):
            inu = G == j
            pm = np.array([g is not None and c == g for c in pcode]) if g is not None else np.zeros_like(inu)
            inter = (inu & pm).sum(); union = (inu | pm).sum()
            ious.append(float(inter / union) if union else 0.0)
        ious = np.array(ious)
        n_cls_mapped = len({c for c in pc.values() if c is not None and c in set(gs)})
        out[f"semantic_{key}"] = {"pixel_acc": float(ok.mean()), "miou_all_units": float(ious.mean()),
                                  "units_iou_ge_0.5": int((ious >= 0.5).sum()),
                                  "pred_classes_with_code_matching_some_unit": n_cls_mapped}
    # --- 3. topology ---
    match = {j: int(p["matched_pred"][1:]) for j, p in enumerate(per) if p["matched_pred"]}
    inv = {p: j for j, p in match.items()}
    pm = np.full(pred.shape, -1, np.int32)
    for p, j in inv.items(): pm[pred == p] = j
    pm[~v] = -1; gv = np.where(v, gt, -1)
    A_gt, A_pr = adjacency(gv, None), adjacency(pm, None)
    tp = len(A_gt & A_pr)
    comp = []
    for j in range(len(per)):
        n, cc, st, _ = cv2.connectedComponentsWithStats((gv == j).astype(np.uint8), connectivity=4)
        for c in range(1, n):
            m = cc == c; inter = (m & (pm == j)).sum(); area = st[c, cv2.CC_STAT_AREA]
            bb = st[c, :4]; y0, y1, x0, x1 = bb[1], bb[1] + bb[3], bb[0], bb[2] + bb[0]
            union = area + (pm[y0:y1, x0:x1] == j).sum() - inter   # bbox-local union approximation
            comp.append((area, inter / max(union, 1)))
    comp = np.array(comp)
    small = comp[:, 0] < 5000
    polys = polygons_from_labels(pred, mm, min_area_px=int(50 * s * s * 4))
    out["topology"] = {
        "components_gt": me["components"]["gt"], "components_pred": me["components"]["pred"],
        "adjacency_gt_pairs": len(A_gt), "adjacency_pred_pairs_mapped": len(A_pr),
        "adjacency_precision": tp / max(len(A_pr), 1), "adjacency_recall": tp / max(len(A_gt), 1),
        "gt_polygon_recall_iou_ge_0.5": float((comp[:, 1] >= 0.5).mean()),
        "gt_small_polygon_recall_iou_ge_0.5": float((comp[small, 1] >= 0.5).mean()) if small.any() else None,
        "n_gt_polygons": int(len(comp)), "n_gt_small_polygons_lt_5000px": int(small.sum()),
        "pred_polygons": len(polys), "pred_invalid_polygons": int(sum(not g.is_valid for g, _ in polys)),
        "note": "adjacency/polygon recall use the upper-bound class matching; local IoU uses a bbox-local union"}
    json.dump(out, open(out_json, "w"), ensure_ascii=False, indent=1, default=float)
    print(json.dumps({k: out[k] for k in out if k not in ("ocr_codes",)}, ensure_ascii=False, default=float))


if __name__ == "__main__":
    main(*sys.argv[1:5], *(sys.argv[5:6] or []))
