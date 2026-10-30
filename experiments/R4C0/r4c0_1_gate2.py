"""R4-C0.1 Gate 2: GIS repair-burden statistics on 13014 / 15076 (algorithm statistics, NOT measured human time).

Per sheet and method (M2_hybrid, RAG_BOUNDARY_ONLY, RAG_BOUNDARY_APPEARANCE), inside the evaluation valid area:
  regions            total; per million px; counts and total area of regions < 50 px and 50-200 px
  pseudo_fragments   regions < 200 px whose majority official instance is >= 5x larger than the region
                     (a piece of a bigger unit: an obvious GIS merge)
  true_small_regions regions < 200 px that match an official instance with IoU >= 0.5 (must NOT be merged)
  recovered          small instances recovered (IoU >= 0.5) by this method but not by M2_hybrid, and vice versa
  false_boundary     predicted region-boundary pixels farther than 2 px from UNIT_BOUNDARY: length (px) and share,
                     and the share of them within 1 px of image ink (contours / text / patterns are printed ink)
  topology           from the existing export validations (9 checks): valid polygons, shared-boundary consistency
                     (rasterise-back exact, area exact)
Usage: r4c0_1_gate2.py <out_json> <record_csv>   (.venv-ml)
"""
import csv, json, sys
from pathlib import Path
import cv2, numpy as np

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "R4A"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "R4B1T"))
import r4c0_rag as R  # noqa: E402
import r4c0_gate3 as G3  # noqa: E402
import r4a2_2_eval as EV  # noqa: E402
import r4b1t_width as W  # noqa: E402
from r4b1t_labels import ink_masks  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SHEETS = ("13014", "15076"); METHODS = ("M2_hybrid", "RAG_BOUNDARY_ONLY", "RAG_BOUNDARY_APPEARANCE")
EXPORT_JSON = {"RAG_BOUNDARY_ONLY": "experiments/R4C0/gate4/{c}_RAG_BOUNDARY_ONLY_export_validation.json",
               "RAG_BOUNDARY_APPEARANCE": "experiments/R4C0/gate4/{c}_RAG_BOUNDARY_APPEARANCE_export_validation.json",
               "M2_hybrid": "experiments/R4C0/r4c0_1/{c}_M2_hybrid_export_validation.json"}   # exported in R4-C0.1 with the same rules


def load(c, m):
    if m == "M2_hybrid": return np.load(ROOT / f"runs/r4c0/pred_test/{c}/M2/regions_M2_hybrid.npy")
    return np.load(ROOT / f"runs/r4c0/gate4/{c}_{m}.npy")


def main(out_json, record_csv):
    res = {"note": "algorithm statistics only; they are NOT human repair times", "sheets": {}}
    for c in SHEETS:
        Rr = EV.load_ref(c); unit = np.load(ROOT / "runs/r4a2" / c / "unit.npy")
        V = (Rr["ignore"] == 0) & (unit >= 0); i1, area, ids, _ = W.canonical_widths(Rr["instance"], V)
        ub = (Rr["unit_boundary"] > 0) & V; dub = cv2.distanceTransform((~ub).astype(np.uint8), cv2.DIST_L2, 3)
        _, ink1, _ = ink_masks(cv2.imread(str(ROOT / "runs/r4a2" / c / "geotiff_rgb.png")))
        mpx = V.sum() / 1e6; hits = {}; S = {}
        for m in METHODS:
            reg = load(c, m)
            best, _, _, _ = G3.per_instance(reg, i1, V, ids, area); hits[m] = best >= 0.5
            sz = np.bincount(np.where(V, reg, 0).ravel()); sz[0] = 0; live = np.flatnonzero(sz > 0)
            C = R.overlaps(reg, i1, V); maj = np.zeros(len(sz), np.int64); o = np.lexsort((-C.data, C.row))
            f = np.unique(C.row[o], return_index=True)[1]; maj[C.row[o][f]] = C.col[o][f]
            ra = sz; iou = C.data / (ra[C.row] + area[C.col] - C.data)
            good = np.zeros(len(sz), bool); good[C.row[iou >= 0.5]] = True
            small = live[sz[live] < 200]
            pseudo = small[(maj[small] > 0) & (area[maj[small]] >= 5 * sz[small])]
            b = np.zeros(reg.shape, bool); b[:, 1:] |= reg[:, 1:] != reg[:, :-1]; b[1:] |= reg[1:] != reg[:-1]; b &= V
            fb = b & (dub > 2)
            ev = json.load(open(ROOT / EXPORT_JSON[m].format(c=c)))
            S[m] = {"regions": int(len(live)), "regions_per_Mpx": round(len(live) / mpx, 1),
                    "lt50": {"count": int((sz[live] < 50).sum()), "area_px": int(sz[live][sz[live] < 50].sum())},
                    "50_200": {"count": int(((sz[live] >= 50) & (sz[live] < 200)).sum()), "area_px": int(sz[live][(sz[live] >= 50) & (sz[live] < 200)].sum())},
                    "pseudo_fragments_lt200": int(len(pseudo)), "pseudo_fragments_per_Mpx": round(len(pseudo) / mpx, 1),
                    "true_small_regions_lt200": int(good[small].sum()),
                    "false_boundary_px": int(fb.sum()), "false_boundary_share_of_pred_boundary": round(float(fb.sum() / max(b.sum(), 1)), 4),
                    "false_boundary_on_ink_share": round(float((fb & ink1).sum() / max(fb.sum(), 1)), 4),
                    "export_all_checks_pass": ev["summary"]["all_pass"], "valid_polygon_frac": ev["checks"]["validity"]["valid_frac"],
                    "shared_boundary_consistent": bool(ev["checks"]["rasterise_back"]["pass"] and ev["checks"]["area_match"]["pass"])}
        for m in METHODS[1:]:
            S[m]["vs_M2_hybrid"] = {"newly_recovered_small": int((hits[m] & ~hits["M2_hybrid"]).sum()),
                                    "newly_lost_small": int((~hits[m] & hits["M2_hybrid"]).sum()),
                                    "extra_pseudo_fragments": S[m]["pseudo_fragments_lt200"] - S["M2_hybrid"]["pseudo_fragments_lt200"],
                                    "extra_false_boundary_px": S[m]["false_boundary_px"] - S["M2_hybrid"]["false_boundary_px"]}
        res["sheets"][c] = {"valid_Mpx": round(mpx, 3), "small_instances": int(len(ids)), "methods": S}
        print(c, json.dumps({m: {k: S[m][k] for k in ("regions", "pseudo_fragments_lt200", "true_small_regions_lt200", "false_boundary_px", "false_boundary_on_ink_share")} for m in METHODS}),
              {m: S[m].get("vs_M2_hybrid") for m in METHODS[1:]}, flush=True)
    json.dump(res, open(out_json, "w"), indent=1)
    cols = ["sheet", "window_id_or_area", "method", "operation (MERGE / SPLIT / REDRAW / DELETE / RELABEL / NONE)", "count",
            "minutes", "reason (fragment / missed unit / false boundary / wrong merge / other)", "operator", "date", "notes"]
    with open(record_csv, "w", newline="") as f:
        w = csv.writer(f); w.writerow(cols)
        for c in SHEETS:
            for m in METHODS: w.writerow([c, "", m, "", "", "", "", "", "", ""])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
