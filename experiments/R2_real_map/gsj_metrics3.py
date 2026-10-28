"""Three separate metric families for an R1 run on a GSJ sheet, plus a legend audit.

1. region  : segmentation quality under the evaluation-only 1:1 Hungarian mapping.
             THIS IS AN UPPER BOUND on legend association, not a system capability.
2. semantic: the system's own class -> stratigraphic symbol mapping. R1's only way to name a
             class is `ocr_code` on its legend swatch (tesseract). A pixel is correct only if
             the OCR'd symbol of its predicted class equals the official symbol of its unit.
             No OCR / unmatched symbol = wrong. Official symbols come from the sheet's xlsx and
             are used only to score, never to predict.
3. topology: per-instance recall (all / small), fragmentation, unit-adjacency graph P/R,
             polygon validity.

Legend audit (xlsx RGB + symbols vs detected swatches), each official unit gets one status:
  same_colour_other_code : another unit has (near-)identical official RGB (dE<3) -> colour alone
                           cannot separate them; needs symbol/pattern
  no_print_swatch        : no symbol in the legend table (e.g. water, unlabelled areas)
  detected               : a detected swatch's fill colour is within dE<10 of the unit's RGB
  missed                 : distinct colour, has a symbol, but no detected swatch matches
Detected swatches matching no unit are counted separately (spurious / colour-shifted).
"""
import json, sys
from pathlib import Path
import cv2, numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "src"))
from scan2arcgis.recog.legend_swatches import ocr_code  # noqa: E402
from scan2arcgis.vector.polygonize import polygons_from_labels  # noqa: E402


def lab1(rgb):
    a = np.asarray(rgb, np.uint8).reshape(1, -1, 3)
    L = cv2.cvtColor(a, cv2.COLOR_RGB2LAB).astype(np.float32)[0]
    return L * np.array([100 / 255, 1, 1], np.float32) - np.array([0, 128, 128], np.float32)


def norm_sym(s):
    if s is None or (isinstance(s, float) and np.isnan(s)): return None
    s = str(s).strip().replace(" ", "")
    return s or None


def read_legend(xlsx):
    leg = pd.read_excel(xlsx, sheet_name="LEGEND_POLY")
    raw = pd.read_excel(xlsx, sheet_name="RGB", header=None)
    rgb = {}
    for _, r in raw.iloc[3:].iterrows():
        try: rgb[str(int(r[0]))] = (int(r[2]), int(r[3]), int(r[4]))
        except (ValueError, TypeError): pass
    out = {}
    for _, r in leg.iterrows():
        k = str(int(r.MAJOR_CODE)); out[k] = {"symbol": norm_sym(r.get("symbol")), "name": r.get("LEGEND01"), "rgb": rgb.get(k)}
    return out


def adjacency(lab, valid):
    v = valid & (lab >= 0); e = set()
    for a, b, m in [(lab[:, 1:], lab[:, :-1], v[:, 1:] & v[:, :-1]), (lab[1:, :], lab[:-1, :], v[1:, :] & v[:-1, :])]:
        d = m & (a != b)
        for x, y in set(zip(a[d].tolist(), b[d].tolist())): e.add((min(x, y), max(x, y)))
    return e


def main(img, r1_dir, xlsx, out_json, method="legend_rf_selftrain"):
    d = Path(r1_dir); ev = json.load(open(d / "r1_eval.json")); s = ev["scale"]
    full = cv2.cvtColor(cv2.imread(str(img)), cv2.COLOR_BGR2RGB)
    gt = np.load(d / "gt_work.npy").astype(np.int32); mm = np.load(d / "map_mask.npy")
    pred = np.load(d / f"pred_{method}.npy").astype(np.int32)
    me = ev["methods"][method]; per = me["per_unit"]; codes = [p["major_code"] for p in per]
    codes_int = [str(int(float(c))) for c in codes]
    legend = read_legend(xlsx)
    v = mm & (gt >= 0); n_valid = int(v.sum())
    out = {"method": method, "image": Path(img).name}

    # ---- 1. region (upper bound)
    out["region_upper_bound"] = {k: me[k] for k in ("pixel_acc_matched", "miou_matched_all_units", "fw_iou_matched",
                                                    "units_iou_ge_0.5", "n_gt_units", "n_units_matched", "purity_many_to_one")}
    out["region_upper_bound"]["label"] = "Hungarian 1:1 class mapping computed from ground truth (evaluation-only upper bound)"

    # ---- 2. semantic via R1's own OCR of swatch codes
    ocr = {}
    for sw in ev["swatches"]:
        x, y, w, h = [int(round(t / s)) for t in sw["box"]]
        ocr[sw["id"]] = norm_sym(ocr_code(full, (x, y, w, h)))
    sym_of_unit = [legend.get(c, {}).get("symbol") for c in codes_int]
    pred_sym = {int(k[1:]): v_ for k, v_ in ocr.items()}
    # pixel-level: predicted symbol vs true symbol
    P, G = pred[v], gt[v]
    ps = np.array([pred_sym.get(int(p)) for p in range(P.max() + 1)] + [None], dtype=object)
    gs = np.array(sym_of_unit, dtype=object)
    pp = ps[np.where(P >= 0, P, len(ps) - 1)]; gg = gs[G]
    correct = np.array([a is not None and a == b for a, b in zip(pp, gg)])
    sem_iou = []
    for j, sym in enumerate(sym_of_unit):
        gm = G == j
        if sym is None: sem_iou.append(0.0); continue
        pm = pp == sym
        inter = int((gm & pm).sum()); union = int((gm | pm).sum())
        sem_iou.append(inter / union if union else 0.0)
    n_ocr = sum(1 for t in ocr.values() if t); n_ocr_valid = sum(1 for t in ocr.values() if t and t in set(filter(None, sym_of_unit)))
    out["semantic_system"] = {"pixel_acc": float(correct.mean()), "miou_symbol": float(np.mean(sem_iou)),
                              "units_iou_ge_0.5": int(sum(x >= 0.5 for x in sem_iou)),
                              "swatches": len(ocr), "ocr_nonempty": n_ocr, "ocr_matches_an_official_symbol": n_ocr_valid,
                              "ocr_codes": ocr, "label": "system's own mapping: R1 ocr_code on each legend swatch"}

    # ---- 3. topology
    match = {j: int(p["matched_pred"][1:]) for j, p in enumerate(per) if p["matched_pred"]}
    inv = {p: j for j, p in match.items()}
    pu = np.vectorize(lambda x: inv.get(int(x), -2))(pred)
    inst_rec, inst_small, frags = [], [], []
    small_thr = int(5000 * (s / 0.5) ** 2)
    for j in range(len(per)):
        n, cc = cv2.connectedComponents(((gt == j) & mm).astype(np.uint8), connectivity=4)
        for k in range(1, n):
            m = cc == k; a = int(m.sum())
            if a < 20: continue
            hit = float((pu[m] == j).mean()) >= 0.5
            inst_rec.append(hit)
            if a < small_thr: inst_small.append(hit)
            if j in match:
                nf, _ = cv2.connectedComponents((m & (pred == match[j])).astype(np.uint8), connectivity=4)
                frags.append(nf - 1)
    eg = adjacency(gt, mm); ep = adjacency(np.where(pu >= 0, pu, -1), mm)
    tp = len(eg & ep)
    polys = polygons_from_labels(pred, mm, min_area_px=int(50 * (s / 0.5) ** 2))
    out["topology"] = {"instances": len(inst_rec), "instance_recall": float(np.mean(inst_rec)),
                       "small_instances": len(inst_small), "small_instance_recall": float(np.mean(inst_small)) if inst_small else None,
                       "small_threshold_work_px": small_thr,
                       "fragments_per_gt_instance_mean": float(np.mean(frags)) if frags else None,
                       "fragments_per_gt_instance_p90": float(np.percentile(frags, 90)) if frags else None,
                       "adjacency_precision": tp / max(len(ep), 1), "adjacency_recall": tp / max(len(eg), 1),
                       "n_polygons": len(polys), "invalid_polygons": int(sum(not g.is_valid for g, _ in polys)),
                       "components_ratio_pred_over_gt": me["components"]["ratio"],
                       "note": "adjacency uses the Hungarian mapping (inherits the upper-bound caveat)"}

    # ---- legend audit
    units_rgb = {c: legend.get(c, {}).get("rgb") for c in codes_int}
    lab_units = {c: lab1(r)[0] for c, r in units_rgb.items() if r}
    sw_lab = {sw["id"]: lab1(sw["fill_rgb"])[0] for sw in ev["swatches"]}
    status, used = {}, set()
    for c in codes_int:
        info = legend.get(c, {}); r = lab_units.get(c)
        same = [o for o in lab_units if o != c and r is not None and np.linalg.norm(lab_units[o] - r) < 3]
        near = sorted(((float(np.linalg.norm(l - r)), k) for k, l in sw_lab.items()), key=lambda t: t[0])[:1] if r is not None else []
        if info.get("symbol") is None: st = "no_print_swatch"
        elif same: st = "same_colour_other_code"
        elif near and near[0][0] < 10: st = "detected"; used.add(near[0][1])
        else: st = "missed"
        status[c] = {"status": st, "symbol": info.get("symbol"), "same_colour_as": same,
                     "nearest_swatch": near[0][1] if near else None, "nearest_swatch_dE": near[0][0] if near else None,
                     "gt_px": int((gt == codes_int.index(c)).sum())}
    for c, st in status.items():   # swatches also explained by same-colour groups
        if st["status"] == "same_colour_other_code" and st["nearest_swatch_dE"] is not None and st["nearest_swatch_dE"] < 10:
            used.add(st["nearest_swatch"])
    cnt = {k: sum(1 for x in status.values() if x["status"] == k) for k in ("detected", "missed", "same_colour_other_code", "no_print_swatch")}
    area = {k: sum(x["gt_px"] for x in status.values() if x["status"] == k) / max(n_valid, 1) for k in cnt}
    out["legend_audit"] = {"n_units": len(codes_int), "n_legend_rows": len(legend), "n_detected_swatches": len(sw_lab),
                           "counts": cnt, "area_frac": area,
                           "swatches_matching_no_unit": sorted(set(sw_lab) - used),
                           "granularity": {"legend_rows_not_on_map": sorted(set(legend) - set(codes_int)),
                                           "map_units_not_in_legend": sorted(set(codes_int) - set(legend))},
                           "per_unit": status,
                           "note": "official RGB from xlsx is the publisher's reference colour; GSJ notes patterns are not encoded"}
    json.dump(out, open(out_json, "w"), ensure_ascii=False, indent=1, default=float)
    show = {"region_upper_bound": {k: out["region_upper_bound"][k] for k in ("pixel_acc_matched", "miou_matched_all_units")},
            "semantic": {k: out["semantic_system"][k] for k in ("pixel_acc", "miou_symbol", "ocr_nonempty", "ocr_matches_an_official_symbol", "swatches")},
            "topology": {k: out["topology"][k] for k in ("instance_recall", "small_instance_recall", "fragments_per_gt_instance_mean", "adjacency_precision", "adjacency_recall", "invalid_polygons")},
            "legend": {"counts": cnt, "spurious_swatches": len(out["legend_audit"]["swatches_matching_no_unit"]), "granularity": out["legend_audit"]["granularity"]}}
    print(json.dumps(show, default=lambda x: round(float(x), 3)))


if __name__ == "__main__":
    main(*sys.argv[1:5], *(sys.argv[5:6] or []))
