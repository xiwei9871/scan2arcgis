"""ARCH-0 offline diagnostics for the multi-evidence / multi-scale architecture study.
No training, no tau change, no new sheet. Sheets: the 10 training sheets (in-sample predictions) and the already
exposed 13014 / 15076. Labels are read only to classify and score (diagnostics, never inference inputs).

D1  refined contact-fragment analysis (replaces the min-distance NEAR_CONTACT proxy of R4-C0.1b):
    for RAG_BOUNDARY_ONLY regions < 200 px, both PSEUDO (majority instance >= 5x larger) and TRUE_SMALL (IoU >= 0.5):
    share of region pixels within 1.5 / 2 px of UNIT_BOUNDARY, share on printed ink (1 px), width, and for elongated
    regions (elongation >= 2, >= 10 px) the angle to the local contact (PCA of UB pixels in the padded bbox).
    Categories: INK_BAND_ON_CONTACT (>= 80% within 1.5 px AND >= 60% on ink), STRIP_ALONG_CONTACT (>= 50% within 2 px),
    TOUCHING_CONTACT_ONLY (min distance <= 2 px), AWAY_FROM_CONTACT.
D2  common subdivision on training sheets: initial over-segmentations of M1, M2, B2 (R4-C0 Gate 1 rule) and their
    4-connected intersections; region counts, RAG size, build + full-merge time, Oracle A / B recall per width bin.
D3  narrow-regime base rates and line-pair evidence: B2 edge coverage (p > 0.5, 1-pair tolerance) of the true
    contacts of 3-6 px instances, overall and per side (two dominant neighbours); count of 3-6 px wide PSEUDO
    regions (ink-band look-alikes) vs 3-6 px true instances.
Usage: arch0_diag.py <out_dir>   (.venv-ml)
"""
import json, resource, sys, time
from pathlib import Path
import cv2, numpy as np
from scipy import ndimage as ndi
from skimage.morphology import skeletonize

ROOT = Path(__file__).resolve().parents[2]
for p in ("R4C0", "R4A", "R4B1T", "R4B2"): sys.path.insert(0, str(ROOT / "experiments" / p))
import r4c0_rag as R  # noqa: E402
import r4c0_1b_fragments as F  # noqa: E402
import r4a2_2_eval as EV  # noqa: E402
import r4b1t_width as W  # noqa: E402
import r4b2_edges as E  # noqa: E402
from r4b1t_labels import ink_masks  # noqa: E402

TRAIN = json.load(open(ROOT / "experiments/R4A/r4a2/freeze_config.json"))["data_roles"]["train"]
EXPOSED = ["13014", "15076"]
FOUR = [[0, 1, 0], [1, 1, 1], [0, 1, 0]]


def ref(code):
    Rr = EV.load_ref(code); unit = np.load(ROOT / "runs/r4a2" / code / "unit.npy").astype(np.int32)
    V = (Rr["ignore"] == 0) & (unit >= 0)
    return Rr, unit, V


def pdir(code):
    return ROOT / ("runs/r4c0/pred" if code in TRAIN else "runs/r4c0/pred_test") / code


def angle(ys, xs):
    X = np.stack([ys, xs], 1).astype(float); X -= X.mean(0)
    v = np.linalg.eigh(X.T @ X)[1][:, -1]
    return np.degrees(np.arctan2(v[0], v[1])) % 180


# ---------------- D1 ----------------
def d1_sheet(code):
    reg, sr, sd = F.final_regions(code)
    _, reg = np.unique(reg, return_inverse=True); reg = reg.reshape(sr.shape).astype(np.int64) + 1
    n = int(reg.max()); sz = np.bincount(reg.ravel(), minlength=n + 1)
    _, ink1, _ = ink_masks(cv2.imread(str(ROOT / "runs/r4a2" / code / "geotiff_rgb.png")))
    Rr, _, V = ref(code)
    i1 = np.where(V, Rr["instance"] + 1, 0).astype(np.int64); ia = np.bincount(i1.ravel(), minlength=int(i1.max()) + 1)
    C = R.overlaps(reg, i1, V); o = np.lexsort((-C.data, C.row)); f = np.unique(C.row[o], return_index=True)[1]
    maj = np.zeros(n + 1, np.int64); maj[C.row[o][f]] = C.col[o][f]
    iou = C.data / (sz[C.row] + ia[C.col] - C.data); good = np.zeros(n + 1, bool); good[C.row[iou >= 0.5]] = True
    ub = (Rr["unit_boundary"] > 0) & V; dub = cv2.distanceTransform((~ub).astype(np.uint8), cv2.DIST_L2, 3)
    objs = ndi.find_objects(reg); H, Wd = reg.shape; rows = []
    for k in np.flatnonzero((sz > 0) & (sz < 200)):
        if k == 0: continue
        cls = "PSEUDO" if (maj[k] > 0 and ia[maj[k]] >= 5 * sz[k]) else ("TRUE_SMALL" if good[k] else None)
        if cls is None: continue
        sl = objs[k - 1]; mk = reg[sl] == k; d = dub[sl][mk]; ik = ink1[sl][mk]
        w = 2 * (cv2.distanceTransform(np.pad(mk.astype(np.uint8), 1), cv2.DIST_L2, 5).max() - 0.5)
        el = skeletonize(mk).sum() / max(w, 1)
        w15, w2, oi = float((d <= 1.5).mean()), float((d <= 2).mean()), float(ik.mean())
        cat = ("INK_BAND_ON_CONTACT" if w15 >= 0.8 and oi >= 0.6 else "STRIP_ALONG_CONTACT" if w2 >= 0.5
               else "TOUCHING_CONTACT_ONLY" if d.min() <= 2 else "AWAY_FROM_CONTACT")
        ang = None
        if el >= 2 and mk.sum() >= 10:
            y0, y1 = max(sl[0].start - 4, 0), min(sl[0].stop + 4, H); x0, x1 = max(sl[1].start - 4, 0), min(sl[1].stop + 4, Wd)
            uy, ux = np.nonzero(ub[y0:y1, x0:x1])
            if len(uy) >= 10:
                fy, fx = np.nonzero(mk); a = abs(angle(fy, fx) - angle(uy, ux)); ang = float(min(a, 180 - a))
        rows.append({"sheet": code, "class": cls, "category": cat, "area": int(sz[k]), "width": float(w), "elongation": float(el),
                     "within_1_5px": w15, "within_2px": w2, "on_ink": oi, "angle_to_contact": ang})
    return rows


def d1_summary(rows):
    out = {}
    for cls in ("PSEUDO", "TRUE_SMALL"):
        rs = [r for r in rows if r["class"] == cls]
        angs = [r["angle_to_contact"] for r in rs if r["angle_to_contact"] is not None]
        out[cls] = {"n": len(rs), "categories": {c: sum(r["category"] == c for r in rs) for c in
                                                   ("INK_BAND_ON_CONTACT", "STRIP_ALONG_CONTACT", "TOUCHING_CONTACT_ONLY", "AWAY_FROM_CONTACT")},
                    "median_within_1_5px": float(np.median([r["within_1_5px"] for r in rs])) if rs else None,
                    "median_on_ink": float(np.median([r["on_ink"] for r in rs])) if rs else None,
                    "median_width": float(np.median([r["width"] for r in rs])) if rs else None,
                    "elongated_with_angle": len(angs), "share_parallel_le_20deg": float(np.mean(np.array(angs) <= 20)) if angs else None,
                    "width_lt6": sum(r["width"] < 6 for r in rs)}
    return out


# ---------------- D2 ----------------
def relabel_cc(lab):
    H, Wd = lab.shape; G = np.zeros((2 * H - 1, 2 * Wd - 1), bool)
    G[::2, ::2] = True; G[::2, 1::2] = lab[:, :-1] == lab[:, 1:]; G[1::2, ::2] = lab[:-1] == lab[1:]
    return ndi.label(G, structure=FOUR)[0][::2, ::2].astype(np.int32)


def intersect(*labs):
    key = labs[0].astype(np.int64)
    for l in labs[1:]: key = key * (int(l.max()) + 1) + l
    return relabel_cc(key)


def d2_sheet(code):
    labs = {m: np.load(ROOT / f"runs/r4c0/gate1/{code}_{m}.npz")["lab"] for m in ("M1", "M2", "B2")}
    P = pdir(code) / "B2"; _, sr, sd = R.strengths("B2", {"pr": np.load(P / "prob_right.npy"), "pd": np.load(P / "prob_down.npy")})
    Rr, _, V = ref(code); i1, area, ids, wid = W.canonical_widths(Rr["instance"], V)
    combos = {"B2": labs["B2"], "M2": labs["M2"], "M1": labs["M1"], "M2xB2": intersect(labs["M2"], labs["B2"]),
              "M1xM2xB2": intersect(labs["M1"], labs["M2"], labs["B2"])}
    out = {}
    for name, lab in combos.items():
        t0 = time.time(); rag = R.build_rag(lab, sr, sd); R.merge(rag); t = time.time() - t0
        oa = R.oracle_A(lab, i1, V, ids); regB, _ = R.oracle_B_regions(lab, i1, V)
        ra = np.bincount(regB[V].ravel(), minlength=int(regB.max()) + 1); Cb = R.overlaps(regB, i1, V)
        iouB = Cb.data / (ra[Cb.row] + area[Cb.col] - Cb.data); ob = np.zeros(int(i1.max()) + 1); np.maximum.at(ob, Cb.col, iouB); ob = ob[ids]
        bins = {}
        for b, lo, hi in W.BINS:
            m = (wid >= lo) & (wid < hi)
            if m.any(): bins[b] = {"n": int(m.sum()), "oracle_A": float((oa[m] >= 0.5).mean()), "oracle_B": float((ob[m] >= 0.5).mean())}
        out[name] = {"regions": int(lab.max()), "rag_edges": int(len(rag["u"])), "rag_merge_seconds": round(t, 2), "by_width": bins}
    return out


# ---------------- D3 ----------------
def d3_sheet(code):
    Rr, unit, V = ref(code); i1, area, ids, wid = W.canonical_widths(Rr["instance"], V)
    P = pdir(code) / "B2"; pr, pd = np.load(P / "prob_right.npy").astype(np.float32), np.load(P / "prob_down.npy").astype(np.float32)
    er, ed, _, _ = E.edges_from_labels(unit, V); k3 = np.ones((3, 3), bool)
    cr = ndi.binary_dilation(pr > 0.5, k3); cd = ndi.binary_dilation(pd > 0.5, k3)
    N = int(i1.max()) + 1
    A, B, Cv = [], [], []
    for a, b, e, c in ((i1[:, :-1], i1[:, 1:], er[:, :-1], cr[:, :-1]), (i1[:-1], i1[1:], ed[:-1], cd[:-1])):
        m = e & (a > 0) & (b > 0); A += [a[m], b[m]]; B += [b[m], a[m]]; Cv += [c[m], c[m]]
    A, B, Cv = np.concatenate(A), np.concatenate(B), np.concatenate(Cv).astype(float)
    key = A * N + B; uk, inv = np.unique(key, return_inverse=True)
    tot = np.bincount(inv); cov = np.bincount(inv, weights=Cv); ki, kn = uk // N, uk % N
    narrow = ids[(wid >= 3) & (wid < 6)]; rows = []
    for g in narrow:
        s = ki == g
        if not s.any(): continue
        t, c = tot[s], cov[s]; o = np.argsort(-t); share = t[o] / t.sum()
        two = len(o) >= 2 and share[1] >= 0.25
        rows.append({"overall_cov": float(c.sum() / t.sum()), "two_sided": bool(two),
                     "min_side_cov": float(min(c[o[0]] / t[o[0]], c[o[1]] / t[o[1]])) if two else None})
    return rows


def main(out_dir):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True); t0 = time.time()
    d1 = {g: [r for c in codes for r in d1_sheet(c)] for g, codes in (("train", TRAIN), ("exposed", EXPOSED))}
    res1 = {g: d1_summary(rows) for g, rows in d1.items()}
    res1["exposed_per_sheet"] = {c: d1_summary([r for r in d1["exposed"] if r["sheet"] == c]) for c in EXPOSED}
    json.dump(res1, open(out / "d1_contact_fragments.json", "w"), indent=1); print("D1", json.dumps(res1["train"]), json.dumps(res1["exposed"]), flush=True)
    res2 = {"per_sheet": {}}
    for c in TRAIN:
        res2["per_sheet"][c] = d2_sheet(c); print("D2", c, {k: (v["regions"], v["rag_merge_seconds"]) for k, v in res2["per_sheet"][c].items()}, flush=True)
    pooled = {}
    for name in res2["per_sheet"][TRAIN[0]]:
        rs = [res2["per_sheet"][c][name] for c in TRAIN]; pb = {}
        for b, _, _ in W.BINS:
            n = sum(r["by_width"].get(b, {}).get("n", 0) for r in rs)
            if n: pb[b] = {"n": n, **{k: round(sum(r["by_width"][b][k] * r["by_width"][b]["n"] for r in rs if b in r["by_width"]) / n, 4) for k in ("oracle_A", "oracle_B")}}
        pooled[name] = {"regions_median": float(np.median([r["regions"] for r in rs])), "regions_max": max(r["regions"] for r in rs),
                        "rag_edges_max": max(r["rag_edges"] for r in rs), "rag_merge_seconds_max": max(r["rag_merge_seconds"] for r in rs), "by_width": pb}
    res2["pooled"] = pooled; res2["peak_rss_gb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e9, 2)
    json.dump(res2, open(out / "d2_common_subdivision.json", "w"), indent=1); print("D2 pooled", json.dumps(pooled), flush=True)
    res3 = {}
    for g, codes in (("train", TRAIN), ("exposed", EXPOSED)):
        rows = [r for c in codes for r in d3_sheet(c)]; two = [r for r in rows if r["two_sided"]]
        res3[g] = {"narrow_3_6_instances": len(rows), "median_overall_cov": float(np.median([r["overall_cov"] for r in rows])),
                   "share_overall_cov_ge_0_8": float(np.mean([r["overall_cov"] >= 0.8 for r in rows])),
                   "two_sided_identifiable": len(two), "share_both_sides_cov_ge_0_8": float(np.mean([r["min_side_cov"] >= 0.8 for r in two])) if two else None,
                   "pseudo_regions_width_lt6": res1[g]["PSEUDO"]["width_lt6"], "true_small_regions_width_lt6": res1[g]["TRUE_SMALL"]["width_lt6"]}
    json.dump(res3, open(out / "d3_narrow_regime.json", "w"), indent=1); print("D3", json.dumps(res3), "minutes", round((time.time() - t0) / 60, 1), flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
