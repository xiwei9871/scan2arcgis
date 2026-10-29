"""R4-A2.2 P4 visuals (LOCAL ONLY: contain GSJ map pixels and official boundaries; never committed).

Per validation sheet, crops centred on small instances chosen by a fixed rule (no cherry-picking by result):
the 6 small instances (200 <= area < 20000 px) with the narrowest estimated width, then 6 drawn at random
(seed 20261029). Panels per crop: map | official UNIT_BOUNDARY | M0 | M1 | M2_oldseed | M2_hybrid region
boundaries (red), with the target instance outlined in cyan; a region that absorbs the target is tinted.
Usage: r4a2_2_vis.py <code> <pred_root> <out_dir>   (pred_root/<method>/regions_<method>.npy)
"""
import json, sys
from pathlib import Path
import cv2, numpy as np

ROOT = Path(__file__).resolve().parents[2]
METHODS = ["M0", "M1", "M2_oldseed", "M2_hybrid"]
HALF = 128


def bnd(lab):
    b = np.zeros(lab.shape, bool)
    b[:, 1:] |= lab[:, 1:] != lab[:, :-1]; b[1:] |= lab[1:] != lab[:-1]
    return b


def panel(rgb, b, target, region=None, title=""):
    p = (rgb * 0.75 + 64).astype(np.uint8)
    if region is not None: p[region] = (p[region] * 0.5 + np.array([255, 200, 0]) * 0.5).astype(np.uint8)
    p[b] = (220, 0, 0)
    p[bnd(target.astype(np.int32)) & target] = (0, 200, 255)
    p = cv2.resize(p, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST)
    cv2.putText(p, title, (6, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
    return p


def main(code, pred_root, out_dir):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    d = ROOT / "runs/r4a2" / code
    rgb = cv2.cvtColor(cv2.imread(str(d / "geotiff_rgb.png")), cv2.COLOR_BGR2RGB)
    inst = np.load(d / "instance.npy"); ub = np.load(d / "unit_boundary.npy") > 0; dist = np.load(d / "dist.npy")
    regs = {m: np.load(Path(pred_root) / m / f"regions_{m}.npy") for m in METHODS}
    i1 = inst + 1; n = int(i1.max()); area = np.bincount(i1.ravel(), minlength=n + 1)
    maxd = np.zeros(n + 1, np.float32); np.maximum.at(maxd, i1.ravel(), dist.ravel())
    small = np.flatnonzero((area >= 200) & (area < 20000)); small = small[small > 0]
    narrow = small[np.argsort(maxd[small])[:6]]
    rnd = np.random.default_rng(20261029).choice(np.setdiff1d(small, narrow), 6, replace=False)
    H, W = inst.shape; picks = []
    for kind, ids in (("narrow", narrow), ("random", rnd)):
        for k in ids:
            ys, xs = np.nonzero(i1 == k); cy, cx = int(np.median(ys)), int(np.median(xs))
            y0, x0 = int(np.clip(cy - HALF, 0, H - 2 * HALF)), int(np.clip(cx - HALF, 0, W - 2 * HALF))
            sl = (slice(y0, y0 + 2 * HALF), slice(x0, x0 + 2 * HALF)); tgt = i1[sl] == k
            row = [panel(rgb[sl], np.zeros_like(tgt), tgt, title="map"), panel(rgb[sl], ub[sl], tgt, title="official")]
            info = {"instance": int(k) - 1, "kind": kind, "area_px": int(area[k]), "width_est_px": float(2 * maxd[k] + 1), "crop_yx": [y0, x0]}
            for m in METHODS:
                r = regs[m][sl]; vals, cnt = np.unique(r[tgt], return_counts=True); best = vals[cnt.argmax()]
                rr = r == best; iou = (rr & tgt).sum() / (rr | tgt).sum()
                row.append(panel(rgb[sl], bnd(r), tgt, rr if iou < 0.5 else None, f"{m} IoU {iou:.2f}"))
                info[f"{m}_iou_in_crop"] = round(float(iou), 3)
            cv2.imwrite(str(out / f"{code}_{kind}_{int(k) - 1}.jpg"), cv2.cvtColor(np.hstack(row), cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 85])
            picks.append(info)
    json.dump(picks, open(out / f"{code}_vis_index.json", "w"), indent=1)
    print(code, len(picks), "crops ->", out)


if __name__ == "__main__":
    main(*sys.argv[1:4])
