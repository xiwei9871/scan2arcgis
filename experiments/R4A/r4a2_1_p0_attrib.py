"""R4-A2.1 P0 attribution (no training): reads the probability maps saved by r4a2_1_p0_diag.py
(runs/r4a2/models/M*_p0/prob.npy) and the same 05016 tile, and splits the excess prediction by zone.

For p > thr: where do the predicted pixels that FAIL the 1 px tolerance lie?
  zone "1-2px" (supervised soft band), "2-8px" (IGNORE_TRAIN), ">8px" (supervised negatives), "ignore_eval".
Also: loss-optimal p* = w t / (w t + 1 - t) at each soft-label distance (threshold mismatch, P0 item 6),
thr 0.8 = p*(t = 0.5), the soft target's half maximum mapped through pos_weight (see p0_report),
and the centreline error of the high-threshold (0.8, 0.9) prediction (is the ridge in the right place?).
Usage: r4a2_1_p0_attrib.py <p0_diag.json> <out.json>   (.venv-ml)
"""
import json, sys
from pathlib import Path
import cv2, numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from r4a2_train import CFG, SEED, load_sheet, crop  # noqa: E402
from r4a2_1_p0_diag import centreline_err  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def main(diag_json, out_json):
    diag = json.load(open(diag_json))
    rng = np.random.default_rng(SEED)
    S = load_sheet(CFG["data_roles"]["train"][0], rng)
    items, where = crop(S, rng, "unit_boundary_pixel")
    assert list(where) == diag["tile"], (where, diag["tile"])          # same tile as the P0 run
    g = items[4] > 0; ign = items[2] > 0
    y0, x0 = where[1], where[2]
    ign_eval = np.load(ROOT / "runs/r4a2/05016/ignore.npy")[y0:y0 + 512, x0:x0 + 512] > 0
    d = cv2.distanceTransform((~g).astype(np.uint8), cv2.DIST_L2, 3)
    zones = {"0-1px": d <= 1, "1-2px": (d > 1) & (d <= 2), "2-4px_IGNORE_TRAIN": ign & ~ign_eval & (d > 2) & (d <= 4), "4-8px_IGNORE_TRAIN": ign & ~ign_eval & (d > 4),
             ">8px_negative": (d > 8) & ~ign, "IGNORE_EVAL": ign_eval}
    res = {"tile": where, "source": diag_json,
           "pstar_by_distance_pos_weight_4": {f"d={k}": round(4 * np.exp(-k * k / 2) / (3 * np.exp(-k * k / 2) + 1), 4)
                                              for k in (0, 1, 1.3693, 1.9100, 2)},
           "pstar_note": "DIST_L2 mask-3 distances: axial 1 px = 0.955, diagonal = 1.3693; p* > 0.5 iff t > 1/(w+1) = 0.2 iff d < 1.79 px",
           "models": {}}
    for m in ("M1", "M2"):
        prob = np.load(ROOT / f"runs/r4a2/models/{m}_p0/prob.npy").astype(np.float32)
        r = {}
        for th in (0.5, 0.8, 0.9):
            p = prob > th; fail = p & (d > 1)
            r[f"thr_{th}"] = {"pred_px": int(p.sum()), "fail_tol1_px": int(fail.sum()),
                              "fail_tol1_share_by_zone": {k: round(float((fail & z).sum() / max(fail.sum(), 1)), 4) for k, z in zones.items()},
                              "pred_share_by_zone": {k: round(float((p & z).sum() / max(p.sum(), 1)), 4) for k, z in zones.items()},
                              "centreline": centreline_err(p, g)}
        r["prob_quantiles_by_zone"] = {k: [round(float(q), 3) for q in np.percentile(prob[z], [10, 50, 90])] for k, z in zones.items() if z.any()}
        res["models"][m] = r
        print(m, json.dumps(r["thr_0.5"]["fail_tol1_share_by_zone"]), r["thr_0.9"]["centreline"], flush=True)
    json.dump(res, open(out_json, "w"), indent=1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
