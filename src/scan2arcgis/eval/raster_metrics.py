"""Raster-based evaluation used by the R1 comparison experiment.

All inputs are label rasters in original image pixel coordinates.
Metrics are deliberately simple and reproducible; see docs/design/evaluation_framework.md.
"""
from __future__ import annotations

import cv2
import numpy as np
from scipy.optimize import linear_sum_assignment


def class_boundaries(labels: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """1-px boundary mask between different labels (inside valid)."""
    b = np.zeros(labels.shape, bool)
    d1 = labels[:, 1:] != labels[:, :-1]
    d0 = labels[1:, :] != labels[:-1, :]
    b[:, 1:] |= d1; b[1:, :] |= d0
    return b & valid


def pixel_metrics(pred: np.ndarray, gt: np.ndarray, valid: np.ndarray) -> dict:
    v = valid & (gt >= 0)
    acc = float((pred[v] == gt[v]).mean())
    ious = {}
    for c in np.unique(gt[v]):
        a = (pred == c) & v; b = (gt == c) & v
        ious[int(c)] = float((a & b).sum() / max(1, (a | b).sum()))
    return {"pixel_accuracy": acc, "miou": float(np.mean(list(ious.values()))), "iou_per_class": ious}


def line_buffer_f1(pred_mask: np.ndarray, gt_mask: np.ndarray, tol_px: float, valid: np.ndarray) -> dict:
    """Pixel buffer P/R/F1 between two thin-line masks (both skeleton-like)."""
    k = int(np.ceil(tol_px)) * 2 + 1
    se = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    p = pred_mask & valid; g = gt_mask & valid
    gd = cv2.dilate(g.astype(np.uint8), se) > 0
    pd = cv2.dilate(p.astype(np.uint8), se) > 0
    prec = float((p & gd).sum() / max(1, p.sum()))
    rec = float((g & pd).sum() / max(1, g.sum()))
    f1 = 0.0 if prec + rec == 0 else 2 * prec * rec / (prec + rec)
    return {"precision": prec, "recall": rec, "f1": f1, "tol_px": tol_px,
            "pred_px": int(p.sum()), "gt_px": int(g.sum())}


def instances_from_labels(labels: np.ndarray, valid: np.ndarray) -> np.ndarray:
    inst = np.zeros(labels.shape, np.int32); nxt = 1
    for c in np.unique(labels[valid & (labels >= 0)]):
        n, cc = cv2.connectedComponents(((labels == c) & valid).astype(np.uint8), connectivity=4)
        m = cc > 0
        inst[m] = cc[m] + nxt - 1
        nxt += n - 1
    return inst


def object_f1(pred_lab: np.ndarray, gt_lab: np.ndarray, gt_inst: np.ndarray, valid: np.ndarray,
              iou_min: float = 0.5, min_gt_px: int = 200) -> dict:
    """Instance-level matching (Hungarian on IoU). An object is correct when IoU>=iou_min
    and the class matches. Returns counts plus per-pred-object correctness for confidence analysis."""
    pred_inst = instances_from_labels(pred_lab, valid)
    g_ids, g_cnt = np.unique(gt_inst[valid & (gt_inst > 0)], return_counts=True)
    g_ids = g_ids[g_cnt >= min_gt_px]
    p_ids, p_cnt = np.unique(pred_inst[pred_inst > 0], return_counts=True)
    keep = p_cnt >= min_gt_px
    p_ids = p_ids[keep]
    # intersection matrix via joint histogram
    gi = np.searchsorted(g_ids, gt_inst); gi_ok = (gi < len(g_ids)) & (g_ids[np.minimum(gi, len(g_ids) - 1)] == gt_inst)
    pi = np.searchsorted(p_ids, pred_inst); pi_ok = (pi < len(p_ids)) & (p_ids[np.minimum(pi, len(p_ids) - 1)] == pred_inst)
    both = gi_ok & pi_ok & valid
    inter = np.zeros((len(g_ids), len(p_ids)), np.int64)
    np.add.at(inter, (gi[both], pi[both]), 1)
    g_area = np.array([(gt_inst == g).sum() for g in g_ids]) if len(g_ids) else np.zeros(0)
    p_area = np.bincount(pi[pi_ok], minlength=len(p_ids))
    union = g_area[:, None] + p_area[None, :] - inter
    iou = np.where(union > 0, inter / np.maximum(union, 1), 0.0)
    rows, cols = linear_sum_assignment(-iou) if iou.size else (np.array([], int), np.array([], int))
    gt_cls = {g: int(np.bincount(gt_lab[gt_inst == g].astype(np.int64) + 1).argmax() - 1) for g in g_ids}
    pred_cls = {}
    for j, p in enumerate(p_ids):
        ys, xs = np.nonzero(pred_inst == p)
        pred_cls[p] = int(pred_lab[ys[0], xs[0]])
    correct_pred = {int(p): False for p in p_ids}
    pred_best_iou = {int(p): float(iou[:, j].max()) if len(g_ids) else 0.0 for j, p in enumerate(p_ids)}
    tp = 0
    for r, c in zip(rows, cols):
        if iou[r, c] >= iou_min and gt_cls[g_ids[r]] == pred_cls[p_ids[c]]:
            tp += 1; correct_pred[int(p_ids[c])] = True
    fp = len(p_ids) - tp; fn = len(g_ids) - tp
    prec = tp / max(1, tp + fp); rec = tp / max(1, tp + fn)
    return {"tp": tp, "fp": fp, "fn": fn, "precision": prec, "recall": rec,
            "f1": 0.0 if tp == 0 else 2 * prec * rec / (prec + rec), "iou_min": iou_min,
            "n_gt": int(len(g_ids)), "n_pred": int(len(p_ids)),
            "_pred_inst": pred_inst, "_correct": correct_pred, "_best_iou": pred_best_iou}


def rasterize_polylines(lines, shape, width=1) -> np.ndarray:
    m = np.zeros(shape, np.uint8)
    for pts in lines:
        a = np.round(np.asarray(pts)).astype(np.int32).reshape(-1, 1, 2)
        if len(a) >= 2:
            cv2.polylines(m, [a], False, 1, width)
    return m > 0


def auroc(scores: np.ndarray, positive: np.ndarray) -> float | None:
    """AUROC of score for predicting `positive` (Mann-Whitney). None if one class missing."""
    s = np.asarray(scores, float); y = np.asarray(positive, bool)
    if y.all() or (~y).all():
        return None
    order = np.argsort(s); ranks = np.empty(len(s)); ranks[order] = np.arange(1, len(s) + 1)
    # average ties
    for v in np.unique(s):
        m = s == v
        if m.sum() > 1:
            ranks[m] = ranks[m].mean()
    n1 = y.sum(); n0 = len(y) - n1
    return float((ranks[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))
