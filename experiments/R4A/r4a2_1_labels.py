"""R4-A2.1 v2 supervision weights (torch-free, used by r4a2_1_train.py and the unit tests).

Replaces the frozen binary IGNORE_TRAIN mask (2-8 px ignored) by a per-pixel loss weight. The soft target
train_boundary.npy is unchanged (exp(-d^2/2) for d <= 2 px, 0 beyond), so pixels with d > 2 px are negatives
with the weights below. d = official distance to UNIT_BOUNDARY (dist.npy). Evaluation truth is untouched.
"""
import numpy as np


def sup_weight(dist, ignore_eval, w24, w48):
    """0 on IGNORE_EVAL; 1 for d <= 2 and d > 8; w24 for 2 < d <= 4; w48 for 4 < d <= 8."""
    w = np.ones(dist.shape, np.float32)
    w[(dist > 2) & (dist <= 4)] = w24
    w[(dist > 4) & (dist <= 8)] = w48
    w[ignore_eval > 0] = 0
    return w


def pstar(t, pos_weight):
    """Pointwise optimum of BCE with pos_weight k on soft target t: k t / ((k - 1) t + 1). The pixel weight
    scales the loss but does not move the optimum, so every d > 2 px pixel with weight > 0 has optimum 0."""
    return pos_weight * t / ((pos_weight - 1) * t + 1)
