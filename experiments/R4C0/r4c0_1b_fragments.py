"""R4-C0.1b diagnostics (exploration only; no tau change, no new sheet): pseudo-fragment causes and label-free separability.

Regions examined: RAG_BOUNDARY_ONLY final regions < 200 px (tau 0.45).
Reference classes (read labels, evaluation only):
  PSEUDO      majority official instance >= 5x the region area (piece of a bigger unit)
  TRUE_SMALL  IoU >= 0.5 with an official instance
Cause proxies for PSEUDO (priority order; contour lines and text are NOT labelled in GSJ data, so these are proxies):
  NEAR_CONTACT   within 2 px of official UNIT_BOUNDARY (noise along a real contact)
  ON_GEOL_LINE   within 2 px of an official geo_L contact or fault line not counted above
  INK_LINEAR     >= 50% of its pixels on printed ink (black-hat > 40, 1 px) and elongation >= 4  (contour / line proxy)
  INK_COMPACT    >= 50% on ink and elongation < 4                                             (text / symbol proxy)
  NON_INK        otherwise (texture, hillshade, colour noise)
Label-free features per region (prediction + image only):
  area, width (2*(max EDT - 0.5)), elongation (skeleton length / width), ink_share, n_neighbours,
  min_cost (lowest median shared-border B2 strength to any neighbour), closure (share of the region's border pairs
  with strength > 0.5), dE_best (Lab dE76 to the lowest-cost neighbour, non-ink means)
Separability: AUC of each feature for PSEUDO vs TRUE_SMALL on the 10 training sheets (in-sample B2) and on 13014 / 15076;
plus, for the two strongest features, the threshold set on TRAINING sheets that keeps >= 95% of TRUE_SMALL, and what it
would do on 13014 / 15076 (diagnostic transfer, not a test).
Usage: r4c0_1b_fragments.py <out_json>   (.venv-ml)
"""
import json, sys
from pathlib import Path
import cv2, numpy as np
from scipy import ndimage as ndi
from skimage.morphology import skeletonize

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "R4A"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "R4B1T"))
import r4c0_rag as R  # noqa: E402
import r4a2_2_eval as EV  # noqa: E402
from r4b1t_labels import ink_masks, lab_image  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
TRAIN = json.load(open(ROOT / "experiments/R4A/r4a2/freeze_config.json"))["data_roles"]["train"]
TAU = json.load(open(ROOT / "experiments/R4C0/gate2/gate2_freeze.json"))["RAG_BOUNDARY_ONLY"]["tau"]
FEATS = ["area", "width", "elongation", "ink_share", "n_neighbours", "min_cost", "closure", "dE_best"]


def final_regions(code):
    if code in TRAIN:
        z = np.load(ROOT / f"runs/r4c0/gate1/{code}_B2.npz"); lab = z["lab"]
        mg = [(float(c), int(k), int(g)) for c, k, g in z["merges"]]
        reg = R.partitions(int(lab.max()), mg, [TAU])[TAU][lab]; P = ROOT / "runs/r4c0/pred" / code / "B2"
    else:
        reg = np.load(ROOT / f"runs/r4c0/gate4/{code}_RAG_BOUNDARY_ONLY.npy"); P = ROOT / "runs/r4c0/pred_test" / code / "B2"
    _, sr, sd = R.strengths("B2", {"pr": np.load(P / "prob_right.npy"), "pd": np.load(P / "prob_down.npy")})
    return reg.astype(np.int64), sr, sd


def sheet(code):
    reg, sr, sd = final_regions(code)
    _, reg = np.unique(reg, return_inverse=True); reg = reg.reshape(sr.shape).astype(np.int64) + 1
    n = int(reg.max()); sz = np.bincount(reg.ravel(), minlength=n + 1)
    bgr = cv2.imread(str(ROOT / "runs/r4a2" / code / "geotiff_rgb.png")); _, ink1, _ = ink_masks(bgr); limg = lab_image(bgr)
    cs, cc = R.region_colour(reg, limg, ink1); mean = cs / np.maximum(cc, 1)[:, None]
    rag = R.build_rag(reg, sr, sd); med = np.array([R._median(h) for h in rag["hist"]]); u, v = rag["u"], rag["v"]
    mincost = np.full(n + 1, np.inf); best = np.zeros(n + 1, np.int64)
    for a, b in ((u, v), (v, u)):
        o = np.lexsort((med, a)); f = np.unique(a[o], return_index=True)[1]
        cand = med[o][f] < mincost[a[o][f]]; ix = a[o][f][cand]; mincost[ix] = med[o][f][cand]; best[ix] = b[o][f][cand]
    nnb = np.bincount(np.concatenate([u, v]), minlength=n + 1)
    a = np.concatenate([reg[:, :-1].ravel(), reg[:-1].ravel()]); c = np.concatenate([reg[:, 1:].ravel(), reg[1:].ravel()])
    s = np.concatenate([sr[:, :-1].ravel(), sd[:-1].ravel()]); m = a != c
    tot = np.bincount(np.concatenate([a[m], c[m]]), minlength=n + 1); strong = np.bincount(np.concatenate([a[m], c[m]]), weights=np.concatenate([s[m] > 0.5] * 2), minlength=n + 1)
    inkn = np.bincount(reg.ravel(), weights=ink1.ravel(), minlength=n + 1)
    # labels (evaluation only)
    Rr = EV.load_ref(code); unit = np.load(ROOT / "runs/r4a2" / code / "unit.npy"); V = (Rr["ignore"] == 0) & (unit >= 0)
    i1 = np.where(V, Rr["instance"] + 1, 0).astype(np.int64); ia = np.bincount(i1.ravel(), minlength=int(i1.max()) + 1)
    C = R.overlaps(reg, i1, V); o = np.lexsort((-C.data, C.row)); f = np.unique(C.row[o], return_index=True)[1]
    maj = np.zeros(n + 1, np.int64); maj[C.row[o][f]] = C.col[o][f]
    iou = C.data / (sz[C.row] + ia[C.col] - C.data); good = np.zeros(n + 1, bool); good[C.row[iou >= 0.5]] = True
    ub = (Rr["unit_boundary"] > 0) & V; d_ub = cv2.distanceTransform((~ub).astype(np.uint8), cv2.DIST_L2, 3)
    gl = (Rr["printed_contact"] > 0) | (np.load(ROOT / "runs/r4a2" / code / "fault.npy") > 0)
    d_gl = cv2.distanceTransform((~gl).astype(np.uint8), cv2.DIST_L2, 3)
    objs = ndi.find_objects(reg); rows = []
    for k in np.flatnonzero((sz > 0) & (sz < 200)):
        if k == 0: continue
        sl = objs[k - 1]; mk = reg[sl] == k
        e = cv2.distanceTransform(np.pad(mk.astype(np.uint8), 1), cv2.DIST_L2, 5).max(); w = 2 * (e - 0.5)
        el = skeletonize(mk).sum() / max(w, 1)
        cls = "PSEUDO" if (maj[k] > 0 and ia[maj[k]] >= 5 * sz[k]) else ("TRUE_SMALL" if good[k] else "OTHER")
        dub = d_ub[sl][mk].min(); dgl = d_gl[sl][mk].min(); ish = inkn[k] / sz[k]
        cause = None
        if cls == "PSEUDO":
            cause = "NEAR_CONTACT" if dub <= 2 else "ON_GEOL_LINE" if dgl <= 2 else ("INK_LINEAR" if el >= 4 else "INK_COMPACT") if ish >= 0.5 else "NON_INK"
        de = float(np.linalg.norm(mean[k] - mean[best[k]])) if best[k] else np.nan
        rows.append({"sheet": code, "region": int(k), "class": cls, "cause": cause, "area": int(sz[k]), "width": float(w), "elongation": float(el),
                     "ink_share": float(ish), "n_neighbours": int(nnb[k]), "min_cost": float(mincost[k]) if np.isfinite(mincost[k]) else np.nan,
                     "closure": float(strong[k] / max(tot[k], 1)), "dE_best": de})
    return rows


def auc(x, y):
    """P(score(PSEUDO) > score(TRUE_SMALL)); y True = PSEUDO. 0.5 = no separation."""
    m = ~np.isnan(x); x, y = x[m], y[m]
    if y.all() or (~y).all(): return None
    r = np.argsort(np.argsort(x)) + 1.0
    for val in np.unique(x):                                       # average ranks for ties
        t = x == val; r[t] = r[t].mean()
    n1, n0 = y.sum(), (~y).sum()
    return float((r[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def main(out_json):
    res = {"note": "exploration on training (in-sample) and exposed sheets; no rule is adopted here", "tau": TAU}
    groups = {"train": TRAIN, "exposed_13014_15076": ["13014", "15076"]}; data = {}
    for g, codes in groups.items():
        rows = [r for c in codes for r in sheet(c)]; data[g] = rows
        ps = [r for r in rows if r["class"] == "PSEUDO"]; ts = [r for r in rows if r["class"] == "TRUE_SMALL"]
        y = np.array([r["class"] == "PSEUDO" for r in ps + ts])
        res[g] = {"regions_lt200": len(rows), "pseudo": len(ps), "true_small": len(ts), "other": len(rows) - len(ps) - len(ts),
                  "pseudo_causes": {k: sum(r["cause"] == k for r in ps) for k in ("NEAR_CONTACT", "ON_GEOL_LINE", "INK_LINEAR", "INK_COMPACT", "NON_INK")},
                  "auc_pseudo_vs_true": {f: auc(np.array([r[f] for r in ps + ts], float), y) for f in FEATS},
                  "medians": {cl: {f: float(np.nanmedian([r[f] for r in rows if r["class"] == cl])) for f in FEATS} for cl in ("PSEUDO", "TRUE_SMALL")}}
        if g == "exposed_13014_15076":
            res[g]["per_sheet_pseudo_causes"] = {c: {k: sum(r["cause"] == k for r in ps if r["sheet"] == c) for k in ("NEAR_CONTACT", "ON_GEOL_LINE", "INK_LINEAR", "INK_COMPACT", "NON_INK")} for c in codes}
        print(g, {k: res[g][k] for k in ("regions_lt200", "pseudo", "true_small", "pseudo_causes")}, res[g]["auc_pseudo_vs_true"], flush=True)
    # transfer of single-feature thresholds fixed on training sheets (keep >= 95% of TRUE_SMALL)
    tr = data["train"]; ex = data["exposed_13014_15076"]; res["transfer"] = {}
    for f in FEATS:
        a = res["train"]["auc_pseudo_vs_true"][f]
        if a is None: continue
        sign = 1 if a >= 0.5 else -1                                # higher score -> more PSEUDO
        tv = np.array([sign * r[f] for r in tr if r["class"] == "TRUE_SMALL" and not np.isnan(r[f])])
        thr = float(np.percentile(tv, 95))                         # flag PSEUDO if score > thr keeps 95% of true small
        def rate(rows, cl): v = np.array([sign * r[f] for r in rows if r["class"] == cl and not np.isnan(r[f])]); return float((v > thr).mean()) if len(v) else None
        res["transfer"][f] = {"direction": "high=pseudo" if sign > 0 else "low=pseudo", "threshold_score": thr,
                              "train_pseudo_flagged": rate(tr, "PSEUDO"), "train_true_flagged": rate(tr, "TRUE_SMALL"),
                              "exposed_pseudo_flagged": rate(ex, "PSEUDO"), "exposed_true_flagged": rate(ex, "TRUE_SMALL")}
    json.dump(res, open(out_json, "w"), indent=1, default=float)
    print(json.dumps(res["transfer"], indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
