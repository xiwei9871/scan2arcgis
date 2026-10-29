"""R4-B1 Gate 1: audit of the frozen "small_instance_centre" sampling on the 10 training sheets.

Per small instance (200 <= area < 20000 px), for the frozen anchor (first raster pixel) and the proposed
interior anchor (max inscribed distance), record:
  anchor_edt_px       own-mask inscribed distance at the anchor (1 = on the outline)
  anchor_rel_depth    anchor_edt / max own-mask distance of the instance (1 = most interior point)
  anchor_axis_pos     position of the anchor along the instance's principal axis, 0..1 (0/1 = extreme ends)
  at_end              anchor_axis_pos <= 0.1 or >= 0.9
  crop coverage       N_DRAWS simulated crops with the frozen r4a2_train.crop placement (seed fixed):
                      mean share of instance pixels inside the 512 tile, share of crops covering >= 90% / 100%,
                      mean share of the instance's skeleton inside the tile
Width = own-mask inscribed width (R4-B0 definition), bins 3-6 / 6-10 / 10-20 px (+ lt3, ge20 rows).
Only training-sheet labels are read; no validation sheet, no model output.
Usage: r4b1_gate1.py <out_dir> <local_dir>   (.venv-ml)
"""
import csv, json, sys
from pathlib import Path
import cv2, numpy as np
from scipy import ndimage as ndi
from skimage.morphology import skeletonize

sys.path.insert(0, str(Path(__file__).parent))
import r4b1_sampling as SA  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
TRAIN = json.load(open(ROOT / "experiments/R4A/r4a2/freeze_config.json"))["data_roles"]["train"]
N_DRAWS, SEED = 20, 20261029
BINS = [("lt3", 0, 3), ("3-6", 3, 6), ("6-10", 6, 10), ("10-20", 10, 20), ("ge20", 20, 1e9)]


def wbin(w):
    return next(n for n, lo, hi in BINS if lo <= w < hi)


def per_sheet(code, rng, vis_dir, n_vis):
    inst = np.load(ROOT / "runs/r4a2" / code / "instance.npy"); H, W = inst.shape; i1 = inst + 1
    objs = ndi.find_objects(i1)
    fid, fpos = SA.frozen_anchors(inst); iid, ipos = SA.interior_anchors(inst)
    assert (fid == iid).all()
    rows = []
    for k, pf, pi in zip(fid, fpos, ipos):
        sl = objs[k - 1]; oy, ox = sl[0].start, sl[1].start
        m = (i1[sl] == k); mp = np.pad(m.astype(np.uint8), 1)
        d = cv2.distanceTransform(mp, cv2.DIST_L2, 5)[1:-1, 1:-1]; dmax = float(d.max())
        sk = skeletonize(m); ys, xs = np.nonzero(m); sy, sx = np.nonzero(sk)
        c = np.array([ys.mean(), xs.mean()]); X = np.stack([ys, xs], 1) - c
        ev = np.linalg.eigh(X.T @ X)[1][:, -1]; proj = X @ ev; lo, hi = proj.min(), proj.max()
        row = {"sheet": code, "instance": int(k - 1), "area_px": int(m.sum()), "width_own_px": round(2 * (dmax - 0.5), 2),
               "elongation": round(float(sk.sum() / max(2 * (dmax - 0.5), 1)), 2), "bbox_h": int(m.shape[0]), "bbox_w": int(m.shape[1])}
        row["width_bin"] = wbin(row["width_own_px"])
        for name, p in (("frozen", pf), ("interior", pi)):
            y, x = divmod(int(p), W); ly, lx = y - oy, x - ox
            assert m[ly, lx], (code, k, name)
            ap = float(((np.array([ly, lx]) - c) @ ev - lo) / max(hi - lo, 1e-9))
            cov, sk_cov, full90, full100 = [], [], 0, 0
            for _ in range(N_DRAWS):
                y0, x0 = SA.simulate_crop(y, x, H, W, rng)
                iy = (ys + oy >= y0) & (ys + oy < y0 + SA.TILE) & (xs + ox >= x0) & (xs + ox < x0 + SA.TILE)
                ky = (sy + oy >= y0) & (sy + oy < y0 + SA.TILE) & (sx + ox >= x0) & (sx + ox < x0 + SA.TILE)
                cv_ = iy.mean(); cov.append(cv_); sk_cov.append(ky.mean() if len(sy) else 1.0)
                full90 += cv_ >= 0.9; full100 += cv_ >= 1.0
            row.update({f"{name}_anchor_edt_px": round(float(d[ly, lx]), 3), f"{name}_rel_depth": round(float(d[ly, lx] / dmax), 4),
                        f"{name}_axis_pos": round(ap, 4), f"{name}_at_end": bool(ap <= 0.1 or ap >= 0.9),
                        f"{name}_mean_inst_cov": round(float(np.mean(cov)), 4), f"{name}_mean_skel_cov": round(float(np.mean(sk_cov)), 4),
                        f"{name}_crops_ge90": round(full90 / N_DRAWS, 4), f"{name}_crops_full": round(full100 / N_DRAWS, 4)})
        rows.append(row)
    # local visual: the n_vis most elongated small instances with both anchors
    rgb = cv2.imread(str(ROOT / "runs/r4a2" / code / "geotiff_rgb.png"))
    for r in sorted(rows, key=lambda r: -r["elongation"])[:n_vis]:
        k = r["instance"] + 1; sl = objs[k - 1]; pad = 20
        y0, y1, x0, x1 = max(sl[0].start - pad, 0), min(sl[0].stop + pad, H), max(sl[1].start - pad, 0), min(sl[1].stop + pad, W)
        p = (rgb[y0:y1, x0:x1] * 0.6 + 100).astype(np.uint8); mm = i1[y0:y1, x0:x1] == k
        e = mm & ~cv2.erode(mm.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool); p[e] = (255, 255, 0)
        for pos, col in ((fpos[fid == k][0], (0, 0, 255)), (ipos[iid == k][0], (0, 200, 0))):
            yy, xx = divmod(int(pos), W); cv2.circle(p, (xx - x0, yy - y0), 4, col, -1)
        s = max(1, int(400 / max(p.shape[:2])))
        cv2.imwrite(str(vis_dir / f"{code}_{k - 1}.jpg"), cv2.resize(p, None, fx=s, fy=s, interpolation=cv2.INTER_NEAREST))
    return rows


def summarize(rows):
    out = {}
    for b, _, _ in BINS:
        rs = [r for r in rows if r["width_bin"] == b]
        if not rs: continue
        out[b] = {"n": len(rs)}
        for a in ("frozen", "interior"):
            out[b][a] = {k: round(float(np.mean([r[f"{a}_{k}"] for r in rs])), 4) for k in
                         ("anchor_edt_px", "rel_depth", "at_end", "mean_inst_cov", "mean_skel_cov", "crops_ge90", "crops_full")}
    return out


def main(out_dir, local_dir):
    out, loc = Path(out_dir), Path(local_dir).resolve(); out.mkdir(parents=True, exist_ok=True); (loc / "anchors").mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED); rows = []
    for c in TRAIN:
        r = per_sheet(c, rng, loc / "anchors", 2); rows += r
        print(c, len(r), "frozen on-outline", round(np.mean([x["frozen_anchor_edt_px"] <= 1.0 for x in r]), 3),
              "crops>=90% frozen/interior", round(np.mean([x["frozen_crops_ge90"] for x in r]), 3), round(np.mean([x["interior_crops_ge90"] for x in r]), 3), flush=True)
    with open(out / "gate1_anchor_instances.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    res = {"sheets": TRAIN, "n_small_instances": len(rows), "draws_per_instance_and_anchor": N_DRAWS, "seed": SEED,
           "frozen_anchor_definition": "np.unique(inst, return_index=True) -> first pixel in row-major order (r4a2_train.load_sheet)",
           "interior_anchor_definition": "argmax of own-mask inscribed distance (r4b1_sampling.interior_anchors)",
           "share_frozen_anchor_on_outline_edt_le_1": round(float(np.mean([r["frozen_anchor_edt_px"] <= 1.0 for r in rows])), 4),
           "by_width_bin_pooled": summarize(rows), "by_sheet": {c: summarize([r for r in rows if r["sheet"] == c]) for c in TRAIN},
           "visuals_local": str((loc / "anchors").relative_to(ROOT))}
    # elongated subset (elongation >= 4) - the instances the task cares about
    el = [r for r in rows if r["elongation"] >= 4]
    res["elongated_ge4_by_width_bin"] = summarize(el); res["n_elongated_ge4"] = len(el)
    json.dump(res, open(out / "gate1_sampling_audit.json", "w"), indent=1)
    print(json.dumps(res["by_width_bin_pooled"], indent=1))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
