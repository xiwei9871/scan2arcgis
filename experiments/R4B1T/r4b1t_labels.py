"""R4-B1T candidate boundary representations (training-label audit only; no model, no training).

v2 (current)   soft target t = exp(-d^2 / 2), d <= 2 px, d = DIST_L2 mask 3 distance to UNIT_BOUNDARY (UB, both
               sides of every transition); weights v2 (r4a2_1_labels.sup_weight 0.1 / 0.3).
A  narrow soft single definition: t_A = exp(-d^2 / (2 * 0.5^2)) for d <= 1 px, else 0 (sigma 0.5, support 1 px);
               same UB, same v2 weights. Loss optimum p* = 4t / (3t + 1): UB pixels 1.0, axial neighbours 0.43,
               everything else 0, so at p > 0.5 exactly the UB pixels are boundary. Still two-sided by construction.
B  pixel-adjacency edges from unit.npy on the valid mask V (ignore == 0 and unit >= 0):
               edge_right[y, x] = V[y, x] & V[y, x+1] & unit[y, x] != unit[y, x+1]   (last column False)
               edge_down[y, x]  = V[y, x] & V[y+1, x] & unit[y, x] != unit[y+1, x]   (last row False)
               One label per transition; no pixel area is consumed.
Vector mapping of B (X = col, Y = -row): edge_right[y, x] -> segment (x+1, -y)-(x+1, -(y+1));
               edge_down[y, x] -> segment (x, -(y+1))-(x+1, -(y+1)).
dist_to_edge   Euclidean distance from each pixel centre to the nearest B edge segment (exact on a 2x grid),
               the M2 distance target that B would imply (clipped at 32 like v2).
"""
import cv2, numpy as np
from scipy import ndimage as ndi

POS_WEIGHT = 4.0


def target_v2(d):
    t = np.exp(-(d ** 2) / 2).astype(np.float32); t[d > 2] = 0; return t


def target_A(d):
    t = np.exp(-(d ** 2) / (2 * 0.5 ** 2)).astype(np.float32); t[d > 1] = 0; return t


def pstar(t):
    return POS_WEIGHT * t / ((POS_WEIGHT - 1) * t + 1)


def edges_B(unit, valid):
    V = valid & (unit >= 0)
    er = np.zeros(unit.shape, bool); ed = np.zeros(unit.shape, bool)
    er[:, :-1] = V[:, :-1] & V[:, 1:] & (unit[:, :-1] != unit[:, 1:])
    ed[:-1, :] = V[:-1, :] & V[1:, :] & (unit[:-1, :] != unit[1:, :])
    return er, ed


def reconstruct_B(er, ed, domain):
    """4-connected components of `domain` where a step between neighbours is blocked by an edge."""
    H, W = domain.shape; G = np.zeros((2 * H - 1, 2 * W - 1), bool)
    G[::2, ::2] = domain
    G[::2, 1::2] = domain[:, :-1] & domain[:, 1:] & ~er[:, :-1]
    G[1::2, ::2] = domain[:-1, :] & domain[1:, :] & ~ed[:-1, :]
    lab, n = ndi.label(G, structure=[[0, 1, 0], [1, 1, 1], [0, 1, 0]])
    out = lab[::2, ::2].astype(np.int64)
    u, inv = np.unique(out, return_inverse=True)
    return inv.reshape(out.shape), int((u > 0).sum())


def dist_to_edge(er, ed, clip=32.0):
    H, W = er.shape; G = np.ones((2 * H + 1, 2 * W + 1), bool)          # True = not an edge point
    ys, xs = np.nonzero(er)                                            # vertical segment at column 2x+2, rows 2y..2y+2
    for dy in (0, 1, 2): G[2 * ys + dy, 2 * xs + 2] = False
    ys, xs = np.nonzero(ed)                                            # horizontal segment at row 2y+2, cols 2x..2x+2
    for dx in (0, 1, 2): G[2 * ys + 2, 2 * xs + dx] = False
    if G.all(): return np.full((H, W), clip, np.float32)
    D = ndi.distance_transform_edt(G).astype(np.float32)
    return np.minimum(D[1::2, 1::2] / 2, clip)


def segments_B(er, ed):
    ys, xs = np.nonzero(er); vr = [((x + 1, -y), (x + 1, -(y + 1))) for y, x in zip(ys, xs)]
    ys, xs = np.nonzero(ed); hd = [((x, -(y + 1)), (x + 1, -(y + 1))) for y, x in zip(ys, xs)]
    return vr + hd


def ink_masks(bgr):
    g = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    ink = cv2.morphologyEx(g, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))) > 40
    k = lambda r: cv2.dilate(ink.astype(np.uint8), cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))) > 0
    return ink, k(1), k(2)


def lab_image(bgr):
    return cv2.cvtColor(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB).astype(np.float32) / 255, cv2.COLOR_RGB2LAB)


def shift(a, dy, dx, fill):
    out = np.full_like(a, fill); H, W = a.shape
    ys, yd = (slice(0, H - dy), slice(dy, H)) if dy >= 0 else (slice(-dy, H), slice(0, H + dy))
    xs, xd = (slice(0, W - dx), slice(dx, W)) if dx >= 0 else (slice(-dx, W), slice(0, W + dx))
    out[yd, xd] = a[ys, xs]; return out
