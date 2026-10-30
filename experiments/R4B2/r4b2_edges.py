"""R4-B2 pixel-adjacency edges: labels, direct region reconstruction, cleanup, edge metrics (numpy only).

Conventions (same as R4-B1T candidate B):
  edge_right[y, x]  pair (y, x)-(y, x+1) belongs to different geological units; last column unused
  edge_down[y, x]   pair (y, x)-(y+1, x); last row unused
  supervised pairs  both pixels valid (ignore == 0 and unit >= 0)
Reconstruction (frozen in r4b2_preregistration.json "reconstruction"):
  1. a pair is separated iff its edge probability > THR (0.5)
  2. 4-connected components over ALL image pixels, linking non-separated neighbours (exact, via a 2x lattice)
  3. every region < MIN_AREA (50 px) is merged into the neighbouring region with the lowest mean edge probability
     along their shared border; smallest regions first, union-find; a region without neighbours stays
No watershed, no seeds, no official label is read at prediction time.
"""
import numpy as np
from scipy import ndimage as ndi

THR, MIN_AREA = 0.5, 50
FOUR = [[0, 1, 0], [1, 1, 1], [0, 1, 0]]


def edges_from_labels(unit, valid):
    V = valid & (unit >= 0)
    mr = np.zeros(unit.shape, bool); md = np.zeros(unit.shape, bool)
    mr[:, :-1] = V[:, :-1] & V[:, 1:]; md[:-1] = V[:-1] & V[1:]
    er = np.zeros(unit.shape, bool); ed = np.zeros(unit.shape, bool)
    er[:, :-1] = mr[:, :-1] & (unit[:, :-1] != unit[:, 1:]); ed[:-1] = md[:-1] & (unit[:-1] != unit[1:])
    return er, ed, mr, md


def components(sep_r, sep_d, domain=None):
    """Label map (0 = outside domain, regions 1..n)."""
    H, W = sep_r.shape
    dom = np.ones((H, W), bool) if domain is None else domain
    G = np.zeros((2 * H - 1, 2 * W - 1), bool)
    G[::2, ::2] = dom
    G[::2, 1::2] = dom[:, :-1] & dom[:, 1:] & ~sep_r[:, :-1]
    G[1::2, ::2] = dom[:-1] & dom[1:] & ~sep_d[:-1]
    lab = ndi.label(G, structure=FOUR)[0][::2, ::2]
    u, inv = np.unique(lab, return_inverse=True); inv = inv.reshape(lab.shape)
    if u[0] != 0: inv = inv + 1
    return inv.astype(np.int32)


def cleanup(lab, pr, pd, min_area=MIN_AREA):
    n = int(lab.max()); size = np.bincount(lab.ravel(), minlength=n + 1).astype(np.int64)
    small = np.flatnonzero((size < min_area) & (size > 0)); small = small[small > 0]
    if len(small) == 0: return lab, 0
    a = np.concatenate([lab[:, :-1].ravel(), lab[:-1].ravel()]); b = np.concatenate([lab[:, 1:].ravel(), lab[1:].ravel()])
    p = np.concatenate([pr[:, :-1].ravel(), pd[:-1].ravel()]).astype(np.float64)
    m = (a != b) & (a > 0) & (b > 0); a, b, p = a[m], b[m], p[m]
    a, b, p = np.concatenate([a, b]), np.concatenate([b, a]), np.concatenate([p, p])
    is_small = np.zeros(n + 1, bool); is_small[small] = True
    k = is_small[a]; a, b, p = a[k].astype(np.int64), b[k].astype(np.int64), p[k]
    best = np.zeros(n + 1, np.int64)
    if len(a):
        key = a * (n + 1) + b; uk, inv = np.unique(key, return_inverse=True)
        mean = np.bincount(inv, weights=p) / np.bincount(inv); ka, kb = uk // (n + 1), uk % (n + 1)
        o = np.lexsort((kb, mean, ka)); first = np.unique(ka[o], return_index=True)[1]
        best[ka[o][first]] = kb[o][first]
    parent = np.arange(n + 1)

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    merged = 0
    for s in small[np.argsort(size[small], kind="stable")]:
        r = find(s)
        if size[r] >= min_area or best[s] == 0: continue
        t = find(best[s])
        if t == r: continue
        parent[r] = t; size[t] += size[r]; merged += 1
    roots = np.array([find(i) for i in range(n + 1)])
    _, inv = np.unique(roots, return_inverse=True)
    return inv[lab].astype(np.int32), merged


def regions_from_probs(pr, pd, thr=THR, min_area=MIN_AREA, domain=None):
    """domain=None is the frozen B2 inference rule (all pixels). An explicit domain is for the Stage 1 label check
    (D_gt) and separately marked diagnostics only; official autonomous results never pass a label-derived domain."""
    lab = components(pr > thr, pd > thr, domain)
    return cleanup(lab, pr, pd, min_area)


def region_edges(reg):
    """Edges implied by a region map (pairs with different region ids), as 0/1 float arrays."""
    pr = np.zeros(reg.shape, np.float32); pd = np.zeros(reg.shape, np.float32)
    pr[:, :-1] = reg[:, :-1] != reg[:, 1:]; pd[:-1] = reg[:-1] != reg[1:]
    return pr, pd


def edge_metrics(pr, pd, er, ed, mr, md, thr=THR):
    pe_r = (pr > thr) & mr; pe_d = (pd > thr) & md; npred = int(pe_r.sum() + pe_d.sum()); ngt = int(er.sum() + ed.sum())
    k = np.ones((3, 3), bool); out = {"pred_edges": npred, "gt_edges": ngt}
    for name, tol in (("strict", 0), ("tol1", 1)):
        if tol == 0:
            tp_p = tp_r = int((pe_r & er).sum() + (pe_d & ed).sum())
        else:
            tp_p = int((pe_r & ndi.binary_dilation(er, k)).sum() + (pe_d & ndi.binary_dilation(ed, k)).sum())
            tp_r = int((er & ndi.binary_dilation(pe_r, k)).sum() + (ed & ndi.binary_dilation(pe_d, k)).sum())
        P = tp_p / max(npred, 1); R = tp_r / max(ngt, 1)
        out[name] = {"P": P, "R": R, "F1": 2 * P * R / (P + R) if P + R else 0.0}
    return out
