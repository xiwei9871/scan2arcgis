"""ARCH-1 shared feature extraction (prediction + image only; labels are read only by label_* helpers).

Evidence groups and features:
  E-LINE  b2_med (median B2 pair strength on a border), b2_closure (share of a region's border pairs with strength > 0.5)
  E-REG   m1_mean / m2_prob_mean (mean boundary probability on a border or in a region), m2_maxdist (max M2 distance in a region)
  E-APP   de (Lab dE76 between region means, non-ink pixels), tex_std (Lab L std, non-ink), tex_diff (|tex_std_i - tex_std_j|)
  E-INK   ink_share (share of pixels / border pairs on image ink, black-hat 9 px > 40, dilated 1 px)
  E-GEO   area, width (own-mask inscribed width), elongation (skeleton length / width), n_neighbours, border_len
"""
import json, sys
from pathlib import Path
import cv2, numpy as np
from scipy import ndimage as ndi
from skimage.morphology import skeletonize

ROOT = Path(__file__).resolve().parents[2]
for p in ("R4C0", "R4A", "R4B1T"): sys.path.insert(0, str(ROOT / "experiments" / p))
import r4c0_rag as R  # noqa: E402
import r4a2_2_eval as EV  # noqa: E402
import r4b1t_width as W  # noqa: E402
from r4b1t_labels import ink_masks, lab_image  # noqa: E402

TRAIN = json.load(open(ROOT / "experiments/R4A/r4a2/freeze_config.json"))["data_roles"]["train"]
EXPOSED = ["13014", "15076"]
TAU = json.load(open(ROOT / "experiments/R4C0/gate2/gate2_freeze.json"))["RAG_BOUNDARY_ONLY"]["tau"]
GROUP = {"b2_med": "E-LINE", "b2_closure": "E-LINE", "m1_mean": "E-REG", "m2_prob_mean": "E-REG", "m2_maxdist": "E-REG",
         "de": "E-APP", "tex_std": "E-APP", "tex_diff": "E-APP", "ink_share": "E-INK",
         "area": "E-GEO", "width": "E-GEO", "elongation": "E-GEO", "n_neighbours": "E-GEO", "border_len": "E-GEO"}


def pdir(code):
    return ROOT / ("runs/r4c0/pred" if code in TRAIN else "runs/r4c0/pred_test") / code


def load_inputs(code):
    P = pdir(code)
    pr, pd = np.load(P / "B2/prob_right.npy"), np.load(P / "B2/prob_down.npy")
    b, sr, sd = R.strengths("B2", {"pr": pr, "pd": pd})
    m1 = np.load(P / "M1/prob.npy").astype(np.float32); m2 = np.load(P / "M2/prob.npy").astype(np.float32)
    m2d = np.load(P / "M2/dist_px.npy").astype(np.float32)
    bgr = cv2.imread(str(ROOT / "runs/r4a2" / code / "geotiff_rgb.png")); _, ink1, _ = ink_masks(bgr); limg = lab_image(bgr)
    return {"b": b, "sr": sr, "sd": sd, "m1": m1, "m2": m2, "m2d": m2d, "ink1": ink1, "lab": limg, "bgr": bgr}


def initial_regions(code, X):
    if code in TRAIN: return np.load(ROOT / f"runs/r4c0/gate1/{code}_B2.npz")["lab"].astype(np.int64)
    return R.overseg(X["b"]).astype(np.int64)


def final_regions(code, X):
    if code in TRAIN:
        z = np.load(ROOT / f"runs/r4c0/gate1/{code}_B2.npz"); lab = z["lab"]
        mg = [(float(c), int(k), int(g)) for c, k, g in z["merges"]]
        return R.partitions(int(lab.max()), mg, [TAU])[TAU][lab].astype(np.int64)
    return np.load(ROOT / f"runs/r4c0/gate4/{code}_RAG_BOUNDARY_ONLY.npy").astype(np.int64)


def compact(reg):
    _, inv = np.unique(reg, return_inverse=True); return inv.reshape(reg.shape).astype(np.int64) + 1


def region_stats(reg, X):
    n = int(reg.max()); l = reg.ravel(); keep = ~X["ink1"].ravel()
    area = np.bincount(l, minlength=n + 1).astype(float)
    cnt = np.bincount(l[keep], minlength=n + 1).astype(float); use = cnt >= 5
    mean = np.zeros((n + 1, 3)); sq = np.zeros(n + 1)
    for k in range(3):
        v = X["lab"][..., k].ravel()
        s_c = np.bincount(l[keep], weights=v[keep], minlength=n + 1); s_a = np.bincount(l, weights=v, minlength=n + 1)
        mean[:, k] = np.where(use, s_c / np.maximum(cnt, 1), s_a / np.maximum(area, 1))
    L = X["lab"][..., 0].ravel()
    s1 = np.where(use, np.bincount(l[keep], weights=L[keep], minlength=n + 1), np.bincount(l, weights=L, minlength=n + 1))
    s2 = np.where(use, np.bincount(l[keep], weights=L[keep] ** 2, minlength=n + 1), np.bincount(l, weights=L ** 2, minlength=n + 1))
    c = np.where(use, cnt, area); tex = np.sqrt(np.maximum(s2 / np.maximum(c, 1) - (s1 / np.maximum(c, 1)) ** 2, 0))
    ink = np.bincount(l, weights=X["ink1"].ravel(), minlength=n + 1) / np.maximum(area, 1)
    m1 = np.bincount(l, weights=X["m1"].ravel(), minlength=n + 1) / np.maximum(area, 1)
    m2 = np.bincount(l, weights=X["m2"].ravel(), minlength=n + 1) / np.maximum(area, 1)
    m2d = np.zeros(n + 1, np.float32); np.maximum.at(m2d, l, X["m2d"].ravel())
    return {"area": area, "mean": mean, "tex": tex, "ink": ink, "m1": m1, "m2": m2, "m2d": m2d}


def border_stats(reg, X):
    """Per adjacent region pair (u < v): pair count, median B2 strength, mean max(M1), mean max(M2), ink share."""
    n = int(reg.max())
    a = np.concatenate([reg[:, :-1].ravel(), reg[:-1].ravel()]); c = np.concatenate([reg[:, 1:].ravel(), reg[1:].ravel()])
    m = a != c
    s = np.concatenate([X["sr"][:, :-1].ravel(), X["sd"][:-1].ravel()])[m]
    def pmax(M): return np.concatenate([np.maximum(M[:, :-1], M[:, 1:]).ravel(), np.maximum(M[:-1], M[1:]).ravel()])[m]
    m1, m2 = pmax(X["m1"]), pmax(X["m2"])
    ik = np.concatenate([(X["ink1"][:, :-1] | X["ink1"][:, 1:]).ravel(), (X["ink1"][:-1] | X["ink1"][1:]).ravel()])[m]
    a, c = a[m], c[m]; lo, hi = np.minimum(a, c), np.maximum(a, c)
    uk, inv = np.unique(lo * (n + 1) + hi, return_inverse=True)
    cnt = np.bincount(inv).astype(float)
    hist = np.zeros((len(uk), R.NB), np.int32); np.add.at(hist, (inv, np.clip((s * R.NB).astype(np.int64), 0, R.NB - 1)), 1)
    med = np.array([R._median(h) for h in hist])
    strong = np.bincount(inv, weights=(s > 0.5)) / cnt
    return {"u": uk // (n + 1), "v": uk % (n + 1), "len": cnt, "b2_med": med, "b2_strong": strong,
            "m1": np.bincount(inv, weights=m1) / cnt, "m2": np.bincount(inv, weights=m2) / cnt, "ink": np.bincount(inv, weights=ik) / cnt}


def small_region_features(reg, X, RS, BS, max_area=200):
    """Feature rows for regions < max_area (prediction + image only)."""
    n = int(reg.max()); u, v = BS["u"], BS["v"]
    nnb = np.bincount(np.concatenate([u, v]), minlength=n + 1)
    mincost = np.full(n + 1, np.inf); best = np.zeros(n + 1, np.int64)
    for p, q in ((u, v), (v, u)):
        o = np.lexsort((BS["b2_med"], p)); f = np.unique(p[o], return_index=True)[1]
        ix, val, nb = p[o][f], BS["b2_med"][o][f], q[o][f]; up = val < mincost[ix]; mincost[ix[up]] = val[up]; best[ix[up]] = nb[up]
    tot = np.bincount(np.concatenate([u, v]), weights=np.concatenate([BS["len"]] * 2), minlength=n + 1)
    strong = np.bincount(np.concatenate([u, v]), weights=np.concatenate([BS["len"] * BS["b2_strong"]] * 2), minlength=n + 1)
    objs = ndi.find_objects(reg); rows = []
    for k in np.flatnonzero((RS["area"] > 0) & (RS["area"] < max_area)):
        if k == 0 or best[k] == 0: continue
        sl = objs[k - 1]; mk = reg[sl] == k
        w = 2 * (cv2.distanceTransform(np.pad(mk.astype(np.uint8), 1), cv2.DIST_L2, 5).max() - 0.5)
        j = best[k]
        rows.append({"region": int(k), "area": float(RS["area"][k]), "width": float(w), "elongation": float(skeletonize(mk).sum() / max(w, 1)),
                     "n_neighbours": float(nnb[k]), "b2_med": float(mincost[k]), "b2_closure": float(strong[k] / max(tot[k], 1)),
                     "m1_mean": float(RS["m1"][k]), "m2_prob_mean": float(RS["m2"][k]), "m2_maxdist": float(RS["m2d"][k]),
                     "de": float(np.linalg.norm(RS["mean"][k] - RS["mean"][j])), "tex_std": float(RS["tex"][k]),
                     "tex_diff": float(abs(RS["tex"][k] - RS["tex"][j])), "ink_share": float(RS["ink"][k]), "border_len": float(tot[k])})
    return rows


def border_features(BS, RS):
    u, v = BS["u"], BS["v"]
    return {"b2_med": BS["b2_med"], "b2_closure": BS["b2_strong"], "m1_mean": BS["m1"], "m2_prob_mean": BS["m2"],
            "de": np.linalg.norm(RS["mean"][u] - RS["mean"][v], axis=1), "tex_diff": np.abs(RS["tex"][u] - RS["tex"][v]),
            "ink_share": BS["ink"], "border_len": BS["len"], "area": np.minimum(RS["area"][u], RS["area"][v])}


# ---------------- labels (evaluation only) ----------------
def label_ref(code):
    Rr = EV.load_ref(code); unit = np.load(ROOT / "runs/r4a2" / code / "unit.npy")
    V = (Rr["ignore"] == 0) & (unit >= 0); i1, area, ids, wid = W.canonical_widths(Rr["instance"], V)
    return Rr, V, i1, area, ids, wid


def label_regions(reg, i1, V, ia):
    """Majority instance, purity, IoU-matched flag per region."""
    n = int(reg.max()); sz = np.bincount(reg.ravel(), minlength=n + 1)
    C = R.overlaps(reg, i1, V); o = np.lexsort((-C.data, C.row)); f = np.unique(C.row[o], return_index=True)[1]
    maj = np.zeros(n + 1, np.int64); cnt = np.zeros(n + 1); maj[C.row[o][f]] = C.col[o][f]; cnt[C.row[o][f]] = C.data[o][f]
    vs = np.bincount(np.where(V, reg, 0).ravel(), minlength=n + 1)
    pur = cnt / np.maximum(vs, 1)
    iou = C.data / (sz[C.row] + ia[C.col] - C.data); good = np.zeros(n + 1, bool); good[C.row[iou >= 0.5]] = True
    return maj, pur, good, sz
