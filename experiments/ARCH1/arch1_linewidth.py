"""ARCH-1 Gate 3: local printed line width from cross-sections (image only; official lines are never an input).

Per sampled ink-skeleton pixel:
  ink        gray black-hat (ellipse 9 px) > 40; skeleton of the ink mask
  normal     dominant gradient direction of the Gaussian-smoothed gray image (structure tensor, sigma 1.5 / 2.5)
  profile    gray values along the normal, t in [-6, 6] px, step 0.25 px (bilinear)
  bg / core  bg = median of the outer samples |t| in [4.5, 6]; core = min within |t| <= 1.5
  darkness   d(t) = clip((bg - I(t)) / (bg - core), 0, 1)
  width      integral of d(t) dt over the contiguous run around the core where d > 0.1  (area / depth width)
Reliability flags (a sample is RELIABLE only if none applies):
  LOW_CONTRAST   bg - core < 40
  JUNCTION       a skeleton branch point (>= 3 skeleton neighbours) or end point within 3 px
  SHORT          skeleton component shorter than 20 px (text, dots, symbols)
  DOUBLE_LINE    outside the central run, another sample with d > 0.5 (a second line / dark fill within 6 px)
  ASYMMETRIC     |left half-width - right half-width| > 1.5 px
  DARK_SIDE      one side's outer median is > 40 grey levels darker than the other side (dark fill on one side)
"""
import cv2, numpy as np
from scipy import ndimage as ndi
from skimage.morphology import skeletonize

T = np.arange(-6.0, 6.0 + 1e-9, 0.25)
FLAGS = ("LOW_CONTRAST", "JUNCTION", "SHORT", "DOUBLE_LINE", "ASYMMETRIC", "DARK_SIDE")


def ink_mask(gray):
    return cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))) > 40


def skeleton_info(ink):
    sk = skeletonize(ink)
    nb = ndi.convolve(sk.astype(np.uint8), np.ones((3, 3), np.uint8), mode="constant") - 1
    special = sk & ((nb >= 3) | (nb <= 1))
    near_special = cv2.dilate(special.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))) > 0
    lab, n = ndi.label(sk, structure=np.ones((3, 3)))
    length = np.bincount(lab.ravel(), minlength=n + 1)
    return sk, near_special, length[lab]


def normals(gray):
    g = cv2.GaussianBlur(gray.astype(np.float32), (0, 0), 1.5)
    gx, gy = cv2.Sobel(g, cv2.CV_32F, 1, 0), cv2.Sobel(g, cv2.CV_32F, 0, 1)
    Jxx, Jyy, Jxy = (cv2.GaussianBlur(a, (0, 0), 2.5) for a in (gx * gx, gy * gy, gx * gy))
    th = 0.5 * np.arctan2(2 * Jxy, Jxx - Jyy)                       # dominant gradient direction = line normal
    return np.cos(th), np.sin(th)


def measure(gray, max_samples=200000, seed=20261029, points=None):
    """Return dict of arrays: y, x, width, reliable, flag bits (one column per FLAGS entry)."""
    gray = gray if gray.ndim == 2 else cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)
    ink = ink_mask(gray); sk, near_special, comp_len = skeleton_info(ink)
    if points is None:
        ys, xs = np.nonzero(sk)
        if len(ys) > max_samples:
            sel = np.sort(np.random.default_rng(seed).choice(len(ys), max_samples, replace=False)); ys, xs = ys[sel], xs[sel]
    else:
        ys, xs = points
    nx, ny = normals(gray)
    cx, cy = nx[ys, xs], ny[ys, xs]
    px = xs[:, None] + cx[:, None] * T[None]; py = ys[:, None] + cy[:, None] * T[None]
    prof = ndi.map_coordinates(gray.astype(np.float32), [py.ravel(), px.ravel()], order=1, mode="nearest").reshape(px.shape)
    outer_l = prof[:, T <= -4.5]; outer_r = prof[:, T >= 4.5]
    bg = np.median(np.concatenate([outer_l, outer_r], 1), 1)
    centre = np.abs(T) <= 1.5; core = prof[:, centre].min(1)
    depth = bg - core
    d = np.clip((bg[:, None] - prof) / np.maximum(depth[:, None], 1e-6), 0, 1)
    ic = int(np.argmin(np.abs(T)))
    cidx = np.flatnonzero(centre)[np.argmin(prof[:, centre], 1)]      # index of the core sample
    run = np.zeros_like(d, bool); step = T[1] - T[0]
    above = d > 0.1
    # contiguous run around the core: walk left and right
    for direction in (-1, 1):
        j = cidx.copy(); alive = np.ones(len(j), bool)
        while alive.any():
            run[np.flatnonzero(alive), j[alive]] = True
            j = j + direction; inside = (j >= 0) & (j < len(T))
            alive &= inside
            alive[alive] &= above[np.flatnonzero(alive), j[alive]]
    width = (d * run).sum(1) * step
    tl = np.where(run, T[None], np.nan)
    left, right = -np.nanmin(np.where(run, tl, np.nan), 1), np.nanmax(tl, 1)
    flags = np.zeros((len(ys), len(FLAGS)), bool)
    flags[:, 0] = depth < 40
    flags[:, 1] = near_special[ys, xs]
    flags[:, 2] = comp_len[ys, xs] < 20
    flags[:, 3] = ((d > 0.5) & ~run).any(1)
    flags[:, 4] = np.abs(left - right) > 1.5
    flags[:, 5] = np.abs(np.median(outer_l, 1) - np.median(outer_r, 1)) > 40
    return {"y": ys, "x": xs, "width": width, "reliable": ~flags.any(1), "flags": flags, "depth": depth}


def synthetic(width, angle=0.0, kind="line", size=200, up=8, ink=40, paper=235):
    """Anti-aliased synthetic test image (8x supersampled, area-averaged)."""
    S = size * up; img = np.full((S, S), paper, np.uint8); w = max(1, int(round(width * up)))
    c = S // 2; t = np.radians(angle); d = np.array([np.cos(t), np.sin(t)])
    if kind in ("line", "dashed", "cross"):
        p0, p1 = (np.array([c, c]) - d * S).astype(int), (np.array([c, c]) + d * S).astype(int)
        if kind == "dashed":
            L = np.linalg.norm(p1 - p0); n = int(L // (40 * up))
            for i in range(n):
                a = p0 + (p1 - p0) * (i / n); b = p0 + (p1 - p0) * ((i + 0.6) / n)
                cv2.line(img, tuple(a.astype(int)), tuple(b.astype(int)), ink, w, cv2.LINE_8)
        else:
            cv2.line(img, tuple(p0), tuple(p1), ink, w, cv2.LINE_8)
        if kind == "cross":
            e = np.array([-d[1], d[0]]); q0, q1 = (np.array([c, c]) - e * S).astype(int), (np.array([c, c]) + e * S).astype(int)
            cv2.line(img, tuple(q0), tuple(q1), ink, w, cv2.LINE_8)
    elif kind == "curve":
        cv2.circle(img, (c, c), int(0.35 * S), ink, w, cv2.LINE_8)
    return cv2.resize(img, (size, size), interpolation=cv2.INTER_AREA)
