"""EVALUATION ONLY: minimal S1/S2 interface check (no new algorithm).

Uses existing outputs: in-map code anchors (S1 s1_map_spot.py -> runs/r3/<sheet>/map_spot.json,
reader 'rapid', lexicon-matched only) and candidate regions from R1 and from S2-B1.
Questions answered per region set:
  anchors_in_correct_unit : anchor's code == official symbol of the unit under it (same for both sets)
  multi_code_regions      : regions holding >= 2 different anchor codes (merge signal)
  multi_code_true_merge   : of those, regions that really span >= 2 official units with >= 10% each
  regions_with_anchor     : regions containing >= 1 anchor, and their area share
"""
import json, sys
from pathlib import Path
import cv2, numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from eval_common import Sheet  # noqa: E402


def regions_of(pred, mm):
    reg = np.full(pred.shape, -1, np.int32); k0 = 0
    for k in np.unique(pred[mm & (pred >= 0)]):
        n, cc = cv2.connectedComponents(((pred == k) & mm).astype(np.uint8), connectivity=4)
        m = cc > 0; reg[m] = cc[m] - 1 + k0; k0 += n - 1
    return reg, k0


def main(r1_dir, xlsx, gt_dir, spot_json, s2_dir, out_json):
    sh = Sheet(r1_dir, xlsx, gt_dir); s = sh.scale; gt, mm, v = sh.gt, sh.mm, sh.valid
    anchors = [c for c in json.load(open(spot_json))["candidates"] if c["reader"] == "rapid" and c["code"]]
    pts = []
    for c in anchors:
        x, y = int(c["centre_px"][0] * s), int(c["centre_px"][1] * s)
        if 0 <= y < gt.shape[0] and 0 <= x < gt.shape[1] and mm[y, x]: pts.append((x, y, c["code"]))
    sets = {"R1": np.load(Path(r1_dir) / "pred_legend_rf_selftrain.npy").astype(np.int32),
            "B1": np.load(Path(s2_dir) / "s2_maps.npz")["B1"].astype(np.int32)}
    res = {"n_anchors": len(pts),
           "anchors_in_correct_unit": int(sum(1 for x, y, c in pts if gt[y, x] >= 0 and sh.symbols[gt[y, x]] == c)),
           "region_sets": {}}
    for name, pred in sets.items():
        reg, n = regions_of(pred, mm)
        area = np.bincount(reg[reg >= 0], minlength=n)
        by = {}
        for x, y, c in pts:
            r = reg[y, x]
            if r >= 0: by.setdefault(int(r), []).append(c)
        multi = [r for r, cs in by.items() if len(set(cs)) > 1]
        true_merge = 0
        for r in multi:
            m = (reg == r) & v
            h = np.bincount(gt[m], minlength=len(sh.symbols)) / max(m.sum(), 1)
            true_merge += int((h >= 0.10).sum() >= 2)
        res["region_sets"][name] = {"n_regions": int(n), "regions_with_anchor": len(by),
                                    "anchored_area_frac": float(area[list(by)].sum() / max(area.sum(), 1)),
                                    "multi_code_regions": len(multi), "multi_code_true_merge": true_merge}
    json.dump(res, open(out_json, "w"), indent=1)
    print(json.dumps(res))


if __name__ == "__main__":
    main(*sys.argv[1:7])
