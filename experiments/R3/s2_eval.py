"""EVALUATION ONLY: score S2 outputs (s2_lines.py) against official GSJ vectors.

  L0        ink-line candidates vs official geo_L contacts and faults, separately (P/R/F1, tol 1.5 px);
            long lines only and all lines.
  A-oracle  ORACLE: official contact+fault lines -> closed faces -> majority R1 class. Reads GT lines;
            it is an upper bound for route A, not an automatic result.
  A1, B1    region / line / topology metrics with the frozen region_scores(), next to R1.
  Corrections (B1 vs R1): pixels changed, of which right->wrong (damage) and wrong->right (repair),
            judged under R1's evaluation-only Hungarian mapping (held fixed so changes are comparable).
"""
import json, sys
from pathlib import Path
import cv2, numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from eval_common import Sheet, region_scores, line_prf  # noqa: E402
from s2_lines import a1_regions  # noqa: E402


def official_lines_work(run_dir, sh):
    import geopandas as gpd, warnings
    warnings.filterwarnings("ignore")
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "R2_real_map"))
    from gsj_gt import lines, to_px
    sheet = Path(run_dir).name
    H = np.diag([sh.scale, sh.scale, 1.0]) @ np.array(json.load(open(Path(run_dir) / "frame_reg.json"))["H_lonlat_to_px"])
    G = gpd.read_file(Path("data/raw/gsj") / sheet / "shp" / "geo_L.shp", encoding="cp932")
    W = np.zeros(sh.gt.shape, np.uint8)
    for g, k in zip(G.geometry, G["LEGEND01"].astype(str)):
        if "図郭" in k: continue
        for ln in lines(g): cv2.polylines(W, [np.round(to_px(ln, H)).astype(np.int32).reshape(-1, 1, 2)], False, 1, 1)
    return W.astype(bool)


def main(r1_dir, xlsx, gt_dir, s2_dir, out_json):
    sh = Sheet(r1_dir, xlsx, gt_dir); mm = sh.mm
    z = np.load(Path(s2_dir) / "s2_maps.npz"); meta = json.load(open(Path(s2_dir) / "s2_meta.json"))
    r1 = np.load(Path(r1_dir) / "pred_legend_rf_selftrain.npy").astype(np.int32)
    res = {"params": meta["params"], "l0": {}}
    for name, lines in (("all", z["l0"]), ("long", z["l0_long"])):
        res["l0"][name] = {"vs_contacts": line_prf(lines, sh.gt_contacts, mm, 1.5),
                           "vs_faults": line_prf(lines, sh.gt_faults, mm, 1.5),
                           "vs_contacts_or_faults": line_prf(lines, sh.gt_contacts | sh.gt_faults, mm, 1.5)}
    # false-line share: long-line pixels farther than 3 px from any official line
    dg = cv2.distanceTransform((~(sh.gt_contacts | sh.gt_faults)).astype(np.uint8), cv2.DIST_L2, 3)
    res["l0"]["long_px_far_from_official_frac"] = float((dg[z["l0_long"] & mm] > 3).mean())
    # Oracle lines are rasterised directly at work scale: the frozen gt_contacts/gt_faults masks are
    # 1 px lines drawn at 200 dpi and nearest-downscaled, which fragments them (~15k pieces) and
    # cannot close faces. The frozen masks are still used for every line metric.
    oracle_lines = official_lines_work(gt_dir.replace("/gt", ""), sh)
    oracle, n_or = a1_regions(r1, mm, oracle_lines & mm)
    rows = {"R1": r1, "A_oracle": oracle, "A1": z["A1"].astype(np.int32), "B1": z["B1"].astype(np.int32)}
    res["methods"] = {}
    for k, p in rows.items():
        r = region_scores(sh, p); res["methods"][k] = r
        print(f"{k:8s} UBacc={r['region_ub_pixel_acc']:.3f} UBmIoU={r['region_ub_miou']:.3f} contactF1={r['contact']['f1']:.3f} "
              f"P={r['contact']['precision']:.3f} R={r['contact']['recall']:.3f} inst={r['instance_recall']:.3f} "
              f"small={r['small_instance_recall']:.3f} frag={r['fragments_per_instance_mean']:.2f} regions={r['n_regions']}")
    res["methods"]["A_oracle"]["note"] = "ORACLE (official lines) - not an automatic result"
    # B1 corrections judged under R1's Hungarian mapping
    per = res["methods"]["R1"]
    from eval_common import evaluate
    e = evaluate(r1, sh.gt, mm, sh.units, 1.5)
    match = {j: int(p["matched_pred"][1:]) for j, p in enumerate(e["per_unit"]) if p["matched_pred"]}
    inv = {p: j for j, p in match.items()}
    def to_unit(a):
        lut = np.full(int(max(a.max(), r1.max())) + 2, -2, np.int32)
        for p, j in inv.items(): lut[p] = j
        return np.where(a >= 0, lut[np.clip(a, 0, None)], -2)
    v = sh.valid
    u0, u1 = to_unit(r1), to_unit(rows["B1"])
    ch = v & (r1 != rows["B1"])
    ok0, ok1 = u0 == sh.gt, u1 == sh.gt
    res["B1_corrections"] = {"changed_px_frac": float(ch.sum() / v.sum()),
                             "repair_px": int((ch & ~ok0 & ok1).sum()), "damage_px": int((ch & ok0 & ~ok1).sum()),
                             "neutral_px": int((ch & (ok0 == ok1)).sum()),
                             "note": "judged with R1's evaluation-only Hungarian mapping held fixed"}
    print("L0", {k: {kk: round(vv["f1"] or 0, 3) for kk, vv in res["l0"][k].items()} for k in ("all", "long")},
          "far", round(res["l0"]["long_px_far_from_official_frac"], 3))
    print("B1 corrections", res["B1_corrections"])
    json.dump(res, open(out_json, "w"), ensure_ascii=False, indent=1, default=float)


if __name__ == "__main__":
    main(*sys.argv[1:6])
