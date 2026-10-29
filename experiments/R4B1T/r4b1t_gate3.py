"""R4-B1T Gate 3: training-label reliability vs image evidence (rules: r4b1t_preregistration.json gate3_reliability).
10 training sheets: labels, GeoTIFF RGB and the R4-A2 Q3 log only. No model output, no training.
"Narrow" = small instance (200 <= area < 20000, canonical width) with width < 10 px.
Diagnostic best shift: integer (dy, dx) in [-2, 2]^2 maximising the share of UB pixels on ink; label at (y, x) is
compared with ink at (y + dy, x + dx). Diagnostic only, never applied to labels.
Usage: r4b1t_gate3.py <out_dir> <local_dir>   (.venv-ml)
"""
import csv, json, sys
from pathlib import Path
import cv2, numpy as np
from scipy import ndimage as ndi

sys.path.insert(0, str(Path(__file__).parent))
import r4b1t_width as W  # noqa: E402
import r4b1t_labels as L  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
TRAIN = json.load(open(ROOT / "experiments/R4A/r4a2/freeze_config.json"))["data_roles"]["train"]
Q3 = {r["code"]: r["q3"] for r in json.load(open(ROOT / "experiments/R4A/r4a2/dataset_train.json"))["log"] if r.get("status") == "PASS"}
DE_MIN, INK_SUP_MIN = 10.0, 0.8


def share(a, m):
    return float(a[m].mean()) if m.any() else None


def per_sheet(code, vis):
    d0 = ROOT / "runs/r4a2" / code
    inst = np.load(d0 / "instance.npy"); unit = np.load(d0 / "unit.npy").astype(np.int32); ign = np.load(d0 / "ignore.npy")
    ub = np.load(d0 / "unit_boundary.npy") > 0; V = (ign == 0) & (unit >= 0); ub &= V
    bgr = cv2.imread(str(d0 / "geotiff_rgb.png")); ink, ink1, ink2 = L.ink_masks(bgr); lab = L.lab_image(bgr)
    i1, area, ids, wid = W.canonical_widths(inst, V); objs = ndi.find_objects(i1, max_label=int(i1.max()))
    narrow_ids = ids[wid < 10]; narrow = np.isin(i1, narrow_ids) & V
    # diagnostic best shift
    best, scores = (0, 0), {}
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            scores[(dy, dx)] = share(L.shift(ink, -dy, -dx, False), ub)
    best = max(scores, key=scores.get)
    S = {}
    for tag, (dy, dx) in (("shift0", (0, 0)), ("best_shift", best)):
        k0, k1, k2 = (L.shift(a, -dy, -dx, False) for a in (ink, ink1, ink2))
        er, ed = L.edges_B(unit, V)
        eright = er & (k1 | np.roll(k1, -1, 1)); edown = ed & (k1 | np.roll(k1, -1, 0))
        hz = narrow[:, :-1] & narrow[:, 1:] & (i1[:, :-1] == i1[:, 1:]); vt = narrow[:-1] & narrow[1:] & (i1[:-1] == i1[1:])
        hz_ink = hz & (k0[:, :-1] | k0[:, 1:]); vt_ink = vt & (k0[:-1] | k0[1:])
        S[tag] = {"shift_dy_dx": [dy, dx],
                  "A_positive_on_ink": share(k0, ub), "A_positive_ink1": share(k1, ub), "A_positive_ink2": share(k2, ub),
                  "A_negative_conflict_narrow_nonUB_ink1": share(k1, narrow & ~ub),
                  "B_positive_edges_ink1": float((eright.sum() + edown.sum()) / max(er.sum() + ed.sum(), 1)),
                  "B_negative_conflict_narrow_pairs_on_ink": float((hz_ink.sum() + vt_ink.sum()) / max(hz.sum() + vt.sum(), 1))}
    # per small instance classes (shift 0)
    rows = []; H, Wd = inst.shape
    ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    for k, w in zip(ids, wid):
        sl = objs[k - 1]; y0, y1 = max(sl[0].start - 4, 0), min(sl[0].stop + 4, H); x0, x1 = max(sl[1].start - 4, 0), min(sl[1].stop + 4, Wd)
        I = i1[y0:y1, x0:x1]; m = I == k; v = V[y0:y1, x0:x1]
        ubk = ub[y0:y1, x0:x1] & m
        ink_sup = float((ink2[y0:y1, x0:x1][ubk]).mean()) if ubk.any() else None
        inner = m & ~ink1[y0:y1, x0:x1]
        if inner.sum() < 5: inner = m & ~ink[y0:y1, x0:x1]
        ring = (cv2.dilate(m.astype(np.uint8), ker) > 0) & ~m & v & ~ink[y0:y1, x0:x1] & (I > 0)
        de = None
        if inner.sum() >= 1 and ring.any():
            nb = np.bincount(I[ring], minlength=int(k) + 1); nb[k] = 0; j = int(nb.argmax())   # minlength: crash fix (run 1 IndexError)
            if nb[j] > 0:
                c_in = np.median(lab[y0:y1, x0:x1][inner], 0); c_nb = np.median(lab[y0:y1, x0:x1][ring & (I == j)], 0)
                de = float(np.linalg.norm(c_in - c_nb))
        r = {"sheet": code, "instance": int(k - 1), "area_px": int(area[k]), "width_px": round(float(w), 2), "width_bin": W.width_bin(w),
             "ub_px": int(ubk.sum()), "ub_within_2px_of_ink": None if ink_sup is None else round(ink_sup, 4),
             "dE76_vs_dominant_neighbour": None if de is None else round(de, 2),
             "interior_visible": round(float((m & ~ink1[y0:y1, x0:x1]).sum() / m.sum()), 4)}
        r["INK_SUPPORTED"] = bool(ink_sup is not None and ink_sup >= INK_SUP_MIN)
        r["COLOUR_SUPPORTED"] = bool(de is not None and de >= DE_MIN)
        r["VISUALLY_SUPPORTED"] = r["INK_SUPPORTED"] or r["COLOUR_SUPPORTED"]
        r["UNCERTAIN"] = not r["VISUALLY_SUPPORTED"]
        rows.append(r)
    return {"q3": Q3.get(code), "diagnostic_best_shift": list(best), "ub_on_ink_by_shift": {f"{a},{b}": round(v, 4) for (a, b), v in scores.items()},
            "label_vs_ink": S, "narrow_instances": int(len(narrow_ids))}, rows, (bgr, i1, ub, ink1)


def summarize(rows):
    out = {}
    for b, _, _ in W.BINS:
        rs = [r for r in rows if r["width_bin"] == b]
        if not rs: continue
        g = lambda k: round(float(np.mean([r[k] for r in rs])), 4)
        out[b] = {"n": len(rs), "INK_SUPPORTED": g("INK_SUPPORTED"), "COLOUR_SUPPORTED": g("COLOUR_SUPPORTED"),
                  "VISUALLY_SUPPORTED": g("VISUALLY_SUPPORTED"), "UNCERTAIN": g("UNCERTAIN"),
                  "interior_visible_median": float(np.median([r["interior_visible"] for r in rs])),
                  "dE76_median": float(np.median([r["dE76_vs_dominant_neighbour"] for r in rs if r["dE76_vs_dominant_neighbour"] is not None] or [np.nan]))}
    return out


def panel(cache, r, path):
    bgr, i1, ub, ink1 = cache; k = r["instance"] + 1; ys, xs = np.nonzero(i1 == k); cy, cx = int(np.median(ys)), int(np.median(xs))
    H, Wd = i1.shape; y0, x0 = int(np.clip(cy - 40, 0, H - 80)), int(np.clip(cx - 40, 0, Wd - 80)); s = (slice(y0, y0 + 80), slice(x0, x0 + 80))
    m = i1[s] == k; e = m & ~cv2.erode(m.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    a = bgr[s].copy(); b = (bgr[s] * 0.5).astype(np.uint8); b[ink1[s]] = (255, 0, 0); b[ub[s]] = (0, 0, 255); b[ub[s] & ink1[s]] = (255, 0, 255)
    c = bgr[s].copy(); c[e] = (0, 255, 255)
    cv2.imwrite(str(path), cv2.resize(np.hstack([a, b, c]), None, fx=4, fy=4, interpolation=cv2.INTER_NEAREST))


def main(out_dir, local_dir):
    out, loc = Path(out_dir), Path(local_dir).resolve(); out.mkdir(parents=True, exist_ok=True); (loc / "samples").mkdir(parents=True, exist_ok=True)
    sheets, rows, caches = {}, [], {}
    for c in TRAIN:
        s, r, cache = per_sheet(c, loc); sheets[c] = s; rows += r; caches[c] = cache
        print(c, "best shift", s["diagnostic_best_shift"], {t: {k: (round(v, 3) if isinstance(v, float) else v) for k, v in x.items()} for t, x in s["label_vs_ink"].items()}, flush=True)
    with open(out / "gate3_instances.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    pooled = {}
    for t in ("shift0", "best_shift"):
        pooled[t] = {k: round(float(np.mean([s["label_vs_ink"][t][k] for s in sheets.values()])), 4) for k in sheets[TRAIN[0]]["label_vs_ink"][t] if k != "shift_dy_dx"}
    rng = np.random.default_rng(20261029); samples = []
    for b in ("3-6", "6-10"):
        rs = sorted([r for r in rows if r["width_bin"] == b], key=lambda r: (r["sheet"], r["instance"]))
        for i in sorted(rng.choice(len(rs), min(6, len(rs)), replace=False)):
            r = rs[i]; p = loc / "samples" / f"{b}_{r['sheet']}_{r['instance']}.png"; panel(caches[r["sheet"]], r, p)
            samples.append({k: r[k] for k in ("sheet", "instance", "width_px", "area_px", "ub_within_2px_of_ink", "dE76_vs_dominant_neighbour",
                                              "interior_visible", "INK_SUPPORTED", "COLOUR_SUPPORTED", "UNCERTAIN")} | {"image_local": str(p.relative_to(ROOT))})
    res = {"note": "labels vs printed image only; no model output", "per_sheet": sheets, "pooled_mean_over_sheets": pooled,
           "instance_classes_by_width_bin": summarize(rows), "samples": samples}
    json.dump(res, open(out / "gate3_reliability.json", "w"), indent=1, default=float)
    print(json.dumps(pooled, indent=1)); print(json.dumps(res["instance_classes_by_width_bin"], indent=1))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
