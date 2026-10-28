"""S2: independent ink-line candidates and line/polygon fusion (PREDICTION side, no ground truth).

Inputs: sheet image, R1 run dir (pred_legend_rf_selftrain.npy, map_mask.npy, r1_eval.json swatches).
gt_*.npy in that directory are NOT read here.

L0  ink-line detector (independent implementation, OpenCV + scikit-image):
    grey -> black-hat (9 px ellipse at 200 dpi, scaled) -> Otsu on map pixels -> skeletonize ->
    drop skeleton components shorter than MIN_LEN work px. All lines are typed UNKNOWN_LINE.
    "long" lines (>= LONG_LEN) are the only ones allowed to change regions in A1/B1.
A1  route A: regions = connected components of (map minus dilated long L0 lines); each region takes
    the majority R1 class of its pixels; line pixels are filled from the nearest region.
B1  route B: R1 class map; every R1 region crossed by a long L0 line is split along the line; a piece
    is re-labelled by region-median colour to the nearest legend swatch ONLY if the piece is >=
    MIN_PIECE px and the nearest swatch differs from the R1 class by a clear margin (MARGIN_DE);
    otherwise the piece keeps the R1 class. Unsplit regions are untouched.
Review signals: LINE_INSIDE_REGION (long line far from any R1 boundary), BOUNDARY_NO_INK
(R1 boundary pixels with no ink within 3 px), counted per region. UNCALIBRATED.
"""
import json, sys
from pathlib import Path
import cv2, numpy as np
from skimage.morphology import skeletonize

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments" / "R2_real_map"))
from scan2arcgis.recog.legend_classifier import ink_mask  # noqa: E402
from gsj_error_analysis import lab_of  # noqa: E402

MIN_LEN, LONG_LEN, MIN_PIECE, MARGIN_DE = 15, 60, 150, 6.0   # work px (100 dpi); fixed a priori


def l0_lines(rgb, mm):
    g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    bh = cv2.morphologyEx(g, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    thr, _ = cv2.threshold(bh[mm].reshape(-1, 1), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    b = (bh > thr) & mm
    sk = skeletonize(b)
    n, lab, st, _ = cv2.connectedComponentsWithStats(sk.astype(np.uint8), connectivity=8)
    length = st[:, cv2.CC_STAT_AREA]
    keep = np.zeros(n, bool); keep[1:] = length[1:] >= MIN_LEN
    long_ = np.zeros(n, bool); long_[1:] = length[1:] >= LONG_LEN
    return keep[lab], long_[lab], {"otsu_blackhat_thr": float(thr), "n_components": int(keep.sum()), "n_long": int(long_.sum())}


def fill_from_nearest(lab, holes, valid):
    src = (~holes) & valid & (lab >= 0)
    if not src.any(): return lab
    _, idx = cv2.distanceTransformWithLabels((~src).astype(np.uint8), cv2.DIST_L2, 3, labelType=cv2.DIST_LABEL_PIXEL)
    ys, xs = np.nonzero(src); lut = np.zeros(idx.max() + 1, np.int64); lut[idx[ys, xs]] = ys * lab.shape[1] + xs
    out = lab.copy(); m = holes & valid
    out[m] = lab.ravel()[lut[idx[m]]]
    return out


def components(mask):
    n, cc = cv2.connectedComponents(mask.astype(np.uint8), connectivity=4)
    return n - 1, cc - 1


def a1_regions(pred, mm, long_lines):
    cut = cv2.dilate(long_lines.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    n, reg = components(mm & ~cut)
    out = np.full(pred.shape, -1, np.int32)
    flat = reg[reg >= 0]; cls = pred[reg >= 0]
    ok = cls >= 0
    if n:
        votes = np.zeros((n, int(pred.max()) + 1), np.int64)
        np.add.at(votes, (flat[ok], cls[ok]), 1)
        maj = votes.argmax(1); maj[votes.sum(1) == 0] = -1
        out[reg >= 0] = maj[flat]
    return fill_from_nearest(out, mm & (out < 0), mm), n


def b1_split(pred, mm, long_lines, rgb, swatches):
    L = lab_of(cv2.medianBlur(rgb, 3)); ink = ink_mask(rgb, mm)
    sw = []
    for s in swatches:
        x, y, w, h = s["box"]; sw.append(np.median(L[y + 2:y + h - 2, x + 2:x + w - 2].reshape(-1, 3), 0))
    sw = np.array(sw)
    cut = cv2.dilate(long_lines.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    out = pred.copy(); n_split = n_relab = 0
    for k in np.unique(pred[mm & (pred >= 0)]):
        n, cc = cv2.connectedComponents(((pred == k) & mm).astype(np.uint8), connectivity=4)
        for r in range(1, n):
            m = cc == r
            if not (m & cut).any(): continue
            npc, pc = cv2.connectedComponents((m & ~cut).astype(np.uint8), connectivity=4)
            if npc - 1 < 2: continue
            n_split += 1
            for q in range(1, npc):
                pm = pc == q
                if pm.sum() < MIN_PIECE: continue
                px = L[pm & ~ink]
                if len(px) < 30: continue
                med = np.median(px, 0); d = np.linalg.norm(sw - med, axis=1)
                best = int(d.argmin())
                if best != k and d[k] - d[best] > MARGIN_DE:
                    out[pm] = best; n_relab += 1
    return out, {"regions_split": n_split, "pieces_relabelled": n_relab}


def review(pred, mm, lines, long_lines):
    b = np.zeros(pred.shape, bool)
    b[:, 1:] |= pred[:, 1:] != pred[:, :-1]; b[1:, :] |= pred[1:, :] != pred[:-1, :]; b &= mm
    d_b = cv2.distanceTransform((~b).astype(np.uint8), cv2.DIST_L2, 3)
    d_i = cv2.distanceTransform((~lines).astype(np.uint8), cv2.DIST_L2, 3)
    inside = long_lines & (d_b > 4)
    no_ink = b & (d_i > 3)
    return inside, no_ink


def main(img, r1_dir, out_dir):
    d = Path(r1_dir); out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    ev = json.load(open(d / "r1_eval.json"))
    rgb = cv2.resize(cv2.cvtColor(cv2.imread(str(img)), cv2.COLOR_BGR2RGB), tuple(ev["work_size"]), interpolation=cv2.INTER_AREA)
    mm = np.load(d / "map_mask.npy"); pred = np.load(d / "pred_legend_rf_selftrain.npy").astype(np.int32)
    lines, long_lines, info = l0_lines(rgb, mm)
    a1, n_a1 = a1_regions(pred, mm, long_lines)
    b1, binfo = b1_split(pred, mm, long_lines, rgb, ev["swatches"])
    inside, no_ink = review(pred, mm, lines, long_lines)
    np.savez_compressed(out / "s2_maps.npz", l0=lines, l0_long=long_lines, A1=a1.astype(np.int16), B1=b1.astype(np.int16),
                        review_line_inside=inside, review_boundary_no_ink=no_ink)
    meta = {"params": {"MIN_LEN": MIN_LEN, "LONG_LEN": LONG_LEN, "MIN_PIECE": MIN_PIECE, "MARGIN_DE": MARGIN_DE},
            "l0": info, "l0_px": int(lines.sum()), "l0_long_px": int(long_lines.sum()), "A1_regions_before_fill": int(n_a1),
            "B1": binfo, "review_px": {"LINE_INSIDE_REGION": int(inside.sum()), "BOUNDARY_NO_INK": int(no_ink.sum())},
            "line_type": "UNKNOWN_LINE", "scores": "UNCALIBRATED"}
    json.dump(meta, open(out / "s2_meta.json", "w"), indent=1)
    print(json.dumps(meta))


if __name__ == "__main__":
    main(*sys.argv[1:4])
