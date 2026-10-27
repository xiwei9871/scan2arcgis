"""Legend-driven area recognizer (new route candidate).

Idea: the legend tells us which colours exist on this map. We train a small
per-map pixel classifier from legend swatch pixels, classify the map area,
then adapt to the map's own appearance with one self-training round
(pseudo-labels from high-margin pixels). Ink (contacts, faults, text,
graticule) is treated as "not a unit" and filled from neighbours.

All scores produced here are UNCALIBRATED ranking signals.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import cv2
import numpy as np
from scipy import ndimage as ndi
from sklearn.ensemble import RandomForestClassifier


@dataclass
class LegendClass:
    class_id: int
    legend_code: str
    swatch_box: tuple[int, int, int, int]  # x, y, w, h in image pixels
    legend_entry_id: str = ""


@dataclass
class AreaResult:
    labels: np.ndarray            # HxW int16, -1 = unknown/outside map
    margin: np.ndarray            # HxW float32 top1 - top2 probability (UNCALIBRATED)
    top1: np.ndarray              # HxW float32 top1 probability (UNCALIBRATED)
    ink: np.ndarray               # HxW bool, pixels treated as ink/non-unit
    timings: dict = field(default_factory=dict)
    method: str = ""


def to_lab(rgb: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)


def features(rgb: np.ndarray, shade_invariant: bool = False) -> np.ndarray:
    """Per-pixel features: Lab at several smoothing scales + chroma.

    Median filtering suppresses thin ink and hillshade texture; chroma (a,b)
    is more stable than lightness under relief shading.
    """
    feats = []
    for k in (1, 5, 11):
        src = rgb if k == 1 else cv2.medianBlur(rgb, k)
        lab = to_lab(src)
        feats += [lab[..., 0] * 0.5, lab[..., 1], lab[..., 2]]
    lab = to_lab(cv2.medianBlur(rgb, 5))
    a, b = lab[..., 1] - 128, lab[..., 2] - 128
    feats += [np.hypot(a, b), np.arctan2(b, a) * 20]
    if shade_invariant:
        # chromaticity r/(r+g+b), g/(r+g+b) is invariant to multiplicative relief shading
        for k in (11, 21):
            s = cv2.medianBlur(rgb, k).astype(np.float32) + 1
            chrom = s / s.sum(-1, keepdims=True) * 300
            feats += [chrom[..., 0], chrom[..., 1]]
    return np.stack(feats, -1).astype(np.float32)


def swatch_samples(F: np.ndarray, classes: list[LegendClass], max_per_class=1500, rng=None):
    rng = rng or np.random.default_rng(0)
    X, y = [], []
    for c in classes:
        x0, y0, w, h = c.swatch_box
        pad = max(1, min(w, h) // 6)
        patch = F[y0 + pad:y0 + h - pad, x0 + pad:x0 + w - pad].reshape(-1, F.shape[-1])
        if len(patch) == 0:
            continue
        idx = rng.choice(len(patch), min(max_per_class, len(patch)), replace=False)
        X.append(patch[idx]); y.append(np.full(len(idx), c.class_id))
    return np.concatenate(X), np.concatenate(y)


def ink_mask(rgb: np.ndarray, map_mask: np.ndarray) -> np.ndarray:
    """Thin dark structures (contacts, faults, text) via black-hat on lightness,
    plus saturated thin lines (e.g. coloured graticule) via per-channel black-hat."""
    L = to_lab(rgb)[..., 0]
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    bh = cv2.morphologyEx(L, cv2.MORPH_BLACKHAT, k)
    dark = (bh > 35) | (L < 60)
    chan = np.max([cv2.morphologyEx(rgb[..., i].astype(np.float32), cv2.MORPH_BLACKHAT, k) for i in range(3)], 0)
    thin_col = chan > 60
    return (dark | thin_col) & map_mask


def _predict(clf, F, mask, chunk=300_000):
    """Chunked prediction returning (argmax label, top1, margin) to bound memory on large maps."""
    H, W, D = F.shape
    lab = np.full((H, W), -1, np.int16); top1 = np.zeros((H, W), np.float32); marg = np.zeros((H, W), np.float32)
    idx = np.flatnonzero(mask.ravel()); Ff = F.reshape(-1, D)
    l1, t1, m1 = lab.ravel(), top1.ravel(), marg.ravel()
    for s in range(0, len(idx), chunk):
        ii = idx[s:s + chunk]
        P = clf.predict_proba(Ff[ii]).astype(np.float32)
        srt = np.sort(P, -1)
        l1[ii] = clf.classes_[P.argmax(-1)]; t1[ii] = srt[:, -1]
        m1[ii] = srt[:, -1] - (srt[:, -2] if P.shape[1] > 1 else 0)
    return lab, top1, marg


def _fill_from_neighbours(labels: np.ndarray, holes: np.ndarray, valid_area: np.ndarray) -> np.ndarray:
    src = ~holes & valid_area & (labels >= 0)
    if not src.any():
        return labels
    _, (iy, ix) = ndi.distance_transform_edt(~src, return_indices=True)
    out = labels.copy()
    fill = holes & valid_area
    out[fill] = labels[iy[fill], ix[fill]]
    return out


def _mode_filter(labels: np.ndarray, n_classes_max: int, k: int = 5) -> np.ndarray:
    best = np.full(labels.shape, -1, np.int16)
    best_cnt = np.zeros(labels.shape, np.float32)
    for c in np.unique(labels[labels >= 0]):
        cnt = cv2.boxFilter((labels == c).astype(np.float32), -1, (k, k), normalize=False)
        m = cnt > best_cnt
        best[m] = c; best_cnt[m] = cnt[m]
    best[labels < 0] = -1
    return best


def remove_small(labels: np.ndarray, valid: np.ndarray, min_px: int) -> np.ndarray:
    """Merge connected components smaller than min_px into surrounding labels."""
    out = labels.copy()
    small = np.zeros(labels.shape, bool)
    for c in np.unique(labels[labels >= 0]):
        n, cc, stats, _ = cv2.connectedComponentsWithStats((labels == c).astype(np.uint8), connectivity=4)
        tiny = np.nonzero(stats[1:, cv2.CC_STAT_AREA] < min_px)[0] + 1
        if len(tiny):
            small |= np.isin(cc, tiny)
    return _fill_from_neighbours(out, small, valid)


def classify(rgb: np.ndarray, map_mask: np.ndarray, classes: list[LegendClass], *,
             self_train: bool = True, min_region_px: int = 150, n_estimators: int = 60,
             seed: int = 0, shade_invariant: bool = False) -> AreaResult:
    t = {}
    t0 = time.perf_counter()
    F = features(rgb, shade_invariant)
    t["features_s"] = time.perf_counter() - t0
    X, y = swatch_samples(F, classes, rng=np.random.default_rng(seed))
    ink = ink_mask(rgb, map_mask)
    usable = map_mask & ~ink
    t0 = time.perf_counter()
    clf = RandomForestClassifier(n_estimators=n_estimators, max_depth=16, min_samples_leaf=3,
                                 n_jobs=-1, random_state=seed).fit(X, y)
    lab0, top1, margin = _predict(clf, F, usable)
    if self_train:
        # Adapt to the map's own colour rendition (print, scan, hillshade).
        rng = np.random.default_rng(seed + 1)
        Xs, ys = [X], [y]
        Ff = F.reshape(-1, F.shape[-1])
        for c in clf.classes_:
            idx = np.flatnonzero((lab0 == c).ravel() & usable.ravel() & (margin.ravel() > 0.6))
            if len(idx):
                pick = rng.choice(idx, min(3000, len(idx)), replace=False)
                Xs.append(Ff[pick]); ys.append(np.full(len(pick), c))
        clf = RandomForestClassifier(n_estimators=n_estimators, max_depth=16, min_samples_leaf=3,
                                     n_jobs=-1, random_state=seed).fit(np.concatenate(Xs), np.concatenate(ys))
        lab0, top1, margin = _predict(clf, F, usable)
    t["classify_s"] = time.perf_counter() - t0
    labels = np.where(usable, lab0, -1).astype(np.int16)
    t0 = time.perf_counter()
    labels = _fill_from_neighbours(labels, ink, map_mask)
    labels = _mode_filter(labels, len(classes), 5)
    labels = remove_small(labels, map_mask, min_region_px)
    # ink pixels inherit confidence from neighbours so review maps are not dominated by lines
    _, (iy, ix) = ndi.distance_transform_edt(ink, return_indices=True)
    margin = np.where(ink, margin[iy, ix], margin); top1 = np.where(ink, top1[iy, ix], top1)
    t["postprocess_s"] = time.perf_counter() - t0
    margin[~map_mask] = 0; top1[~map_mask] = 0
    return AreaResult(labels, margin.astype(np.float32), top1.astype(np.float32), ink, t,
                      ("legend_rf_selftrain" if self_train else "legend_rf") + ("_shadeinv" if shade_invariant else ""))


def classify_nearest_color(rgb: np.ndarray, map_mask: np.ndarray, classes: list[LegendClass],
                           min_region_px: int = 150) -> AreaResult:
    """Simplest legend baseline: nearest swatch mean colour in Lab."""
    t0 = time.perf_counter()
    lab = to_lab(cv2.medianBlur(rgb, 5))
    means = []
    for c in classes:
        x0, y0, w, h = c.swatch_box
        p = max(1, min(w, h) // 6)
        means.append(to_lab(rgb[y0 + p:y0 + h - p, x0 + p:x0 + w - p]).reshape(-1, 3).mean(0))
    means = np.array(means)
    d = np.linalg.norm(lab[..., None, :] - means[None, None], axis=-1)
    order = np.sort(d, -1)
    ids = np.array([c.class_id for c in classes])
    ink = ink_mask(rgb, map_mask)
    labels = np.where(map_mask & ~ink, ids[d.argmin(-1)], -1).astype(np.int16)
    labels = _fill_from_neighbours(labels, ink, map_mask)
    labels = remove_small(_mode_filter(labels, len(classes), 5), map_mask, min_region_px)
    margin = np.clip((order[..., 1] - order[..., 0]) / 30.0, 0, 1).astype(np.float32)
    margin[~map_mask] = 0
    return AreaResult(labels, margin, margin, ink, {"total_s": time.perf_counter() - t0}, "legend_nearest_color")
