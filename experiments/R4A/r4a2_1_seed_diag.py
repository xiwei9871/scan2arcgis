"""R4-A2.1 P3 diagnosis: capability ceiling of the M2 seed rules on the OFFICIAL distance map.
The official dist.npy (built from geo_A) is the input here, so these numbers bound what post-processing can
do with a perfect distance prediction; they are NOT a model result. geo_A instances are used only to score.

Per small instance (200 <= area < 20000 px), old rule (dist >= 3, area >= 50) vs new rule (r4a2_1_seeds):
  seeded           some marker pixel lies inside the instance
  fail_dist        (old) no pixel of the instance has dist >= 3
  fail_area        (old) has dist >= 3 pixels, but every such component is < 50 px
  merged_seed      a marker component overlapping this instance also overlaps another instance by >= 10 px
  duplicate        >= 2 marker components with their majority inside this instance
  recall_iou50     watershed region with IoU >= 0.5 exists (watershed on -dist from the markers)
Also all-instance and >= 20000 px recall, and region counts. Sheets: the 10 training sheets (rule fixed
a priori, hybrid added after 05016) and, after the rule is frozen, the two validation sheets.
Usage: r4a2_1_seed_diag.py <out.json> <train|validation>   (.venv-ml)
Rule selection uses the train run only; the validation run is made once, after the chosen rule is frozen.
"""
import json, sys, time
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from r4a2_1_seeds import old_markers, new_markers, hybrid_markers, segment, OLD_DIST, OLD_AREA, RATIO, MIN_DIST, SMOOTH  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CFG = json.load(open(ROOT / "experiments/R4A/r4a2/freeze_config.json"))


def pair_counts(a, b, na, nb):
    """Overlap counts between label maps a (0..na) and b (0..nb) as a dense (na+1, nb+1) array."""
    return np.bincount(a.ravel().astype(np.int64) * (nb + 1) + b.ravel(), minlength=(na + 1) * (nb + 1)).reshape(na + 1, nb + 1)


def iou_recall(inst1, n_inst, reg, areas):
    nr = int(reg.max())
    C = pair_counts(inst1, reg, n_inst, nr)[1:, 1:].astype(np.float64)
    ra = np.bincount(reg.ravel(), minlength=nr + 1)[1:]
    iou = C / (areas[:, None] + ra[None, :] - C)
    return iou.max(1) >= 0.5, nr


def per_sheet(code):
    d = ROOT / "runs/r4a2" / code
    dist = np.load(d / "dist.npy").astype(np.float32); inst = np.load(d / "instance.npy")
    inst1 = (inst + 1).astype(np.int64); n = int(inst1.max())
    areas = np.bincount(inst1.ravel(), minlength=n + 1)[1:]
    small = (areas >= 200) & (areas < 20000); large = areas >= 20000
    out = {"instances": n, "small_instances": int(small.sum())}
    # old-rule failure reasons
    maxd = np.zeros(n + 1, np.float32); np.maximum.at(maxd, inst1.ravel(), dist.ravel()); maxd = maxd[1:]
    for name, fn in (("old", old_markers), ("new", new_markers), ("hybrid", hybrid_markers)):
        t0 = time.time(); mk = fn(dist); nm = int(mk.max())
        C = pair_counts(inst1, mk, n, nm)[1:, 1:]                        # instance x marker overlap
        seeded = C.sum(1) > 0
        multi = (C >= 10).sum(0) >= 2                                    # marker overlapping >= 2 instances
        merged = (C[:, multi] >= 10).any(1)
        owner = C.argmax(0); dup = np.bincount(owner, minlength=n) >= 2
        rec, nr = iou_recall(inst1, n, segment(dist, mk), areas)
        out[name] = {"markers": nm, "regions": nr, "seconds": round(time.time() - t0, 1),
                     "small_seeded": float(seeded[small].mean()), "small_merged_seed": float(merged[small].mean()),
                     "small_duplicate": float(dup[small].mean()), "small_recall_iou50": float(rec[small].mean()),
                     "all_recall_iou50": float(rec.mean()), "large_recall_iou50": float(rec[large].mean()) if large.any() else None}
        if name == "old":
            fail_dist = maxd < OLD_DIST
            out[name]["small_fail_dist"] = float((fail_dist & small).sum() / small.sum())
            out[name]["small_fail_area"] = float((~fail_dist & ~seeded & small).sum() / small.sum())
    print(code, out["small_instances"], {k: {kk: (round(v, 3) if isinstance(v, float) else v) for kk, v in out[k].items()} for k in ("old", "new", "hybrid")}, flush=True)
    return out


def main(out_json, which):
    roles = CFG["data_roles"]; use = ["train"] if which == "train" else ["validation_model_selection"]
    res = {"input": "OFFICIAL dist.npy (geo_A) - capability ceiling only, not a model result",
           "old_rule": {"dist_min_px": OLD_DIST, "area_min_px": OLD_AREA},
           "new_rule": {"h_maxima_on": "log1p(dist)", "ratio": RATIO, "min_dist_px": MIN_DIST, "smooth_sigma_px": SMOOTH},
           "sheets": {}}
    for role in use:
        for c in roles[role]:
            res["sheets"][c] = {"role": role, **per_sheet(c)}
    for role in use:
        rows = [v for v in res["sheets"].values() if v["role"] == role]; w = np.array([r["small_instances"] for r in rows], float)
        res[f"pooled_{role}"] = {m: {k: float(np.average([r[m][k] for r in rows], weights=w)) for k in rows[0][m]
                                     if k.startswith("small_") or k.endswith("_recall_iou50")} for m in ("old", "new", "hybrid")}
        res[f"pooled_{role}"]["small_instances"] = int(w.sum())
    print(json.dumps({k: v for k, v in res.items() if k.startswith("pooled")}, indent=1))
    json.dump(res, open(out_json, "w"), indent=1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
