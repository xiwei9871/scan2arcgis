"""EVALUATION ONLY: score S1 code maps (s1_semantic.py output) with the frozen semantic metric.

No remapping: each pixel's system-chosen code string is compared with the official symbol.
Also scores review candidates: fraction of A3 wrong pixels that fall inside flagged regions, and the
flagged area, so the cost/benefit of the review list is measurable.
"""
import json, sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from eval_common import Sheet, semantic_scores  # noqa: E402


def main(r1_dir, xlsx, gt_dir, s1_dir, out_json):
    sh = Sheet(r1_dir, xlsx, gt_dir)
    z = np.load(Path(s1_dir) / "s1_maps.npz"); meta = json.load(open(Path(s1_dir) / "s1_meta.json"))
    codes = meta["codes"]; res = {"methods": {}}
    for k in ("A0", "A1", "A2c", "A2t", "A3"):
        r = semantic_scores(sh, z[k].astype(np.int32), codes)
        res["methods"][k] = r
        print(f"{k:4s} acc={r['pixel_acc']:.3f} mIoU={r['miou']:.3f} iou>=.5={r['units_iou_ge_0.5']}/{r['n_units']} "
              f"unassigned={r['unassigned_frac']:.3f} wrong={r['wrong_assigned_frac']:.3f} "
              f"same-colour mIoU={r['same_colour_mean_iou']:.3f} ({r['same_colour_units_iou_ge_0.5']}/{len(r['same_colour_units'])})")
    # review list effectiveness for A3
    reg = z["regions"]; v = sh.valid
    a3 = z["A3"].astype(np.int32)
    lut = np.array(codes + [None], dtype=object)
    ps = lut[np.where(a3 >= 0, a3, len(codes))]
    gs = np.array(sh.symbols, dtype=object)[np.clip(sh.gt, 0, None)]
    wrong = v & (a3 >= 0) & (ps != gs)
    unas = v & (a3 < 0)
    flagged = np.zeros(reg.shape, bool)
    by_reason = {}
    for rc in meta["review_candidates"]:
        m = reg == rc["region"]; flagged |= m
        for x in rc["reasons"]:
            b = by_reason.setdefault(x, {"regions": 0, "area_frac": 0.0, "wrong_px_caught": 0})
            b["regions"] += 1; b["area_frac"] += float((m & v).sum() / v.sum()); b["wrong_px_caught"] += int((m & wrong).sum())
    res["review_A3"] = {"n_regions": len(meta["review_candidates"]), "flagged_area_frac": float((flagged & v).sum() / v.sum()),
                        "wrong_assigned_px_frac_of_map": float(wrong.sum() / v.sum()),
                        "wrong_caught_frac": float((flagged & wrong).sum() / max(wrong.sum(), 1)),
                        "unassigned_frac": float(unas.sum() / v.sum()),
                        "precision_of_flags": float(((flagged & (wrong | unas)).sum()) / max((flagged & v).sum(), 1)),
                        "by_reason": by_reason, "scores": "UNCALIBRATED"}
    print("review", {k: (round(x, 3) if isinstance(x, float) else x) for k, x in res["review_A3"].items() if k != "by_reason"})
    json.dump(res, open(out_json, "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main(*sys.argv[1:6])
