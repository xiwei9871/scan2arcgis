"""R4-C0 region over-segmentation, region adjacency graph (RAG), hierarchical merging and Gate 1 oracles.
All rules and constants are fixed in experiments/R4C0/r4c0_preregistration.json (committed before any run).
Prediction side reads model outputs and the RGB image only; labels are read only by the oracle / metric functions.

Boundary strength b (pixel) per candidate:
  M1  boundary probability of the frozen M1
  M2  boundary-head probability of the frozen M2 (the distance head is not used here)
  B2  max of the edge probabilities of the (up to 4) pixel pairs incident to the pixel
Pair strength s (used on shared borders): M1 / M2 max(b[p], b[q]); B2 the pair's own edge probability.
Over-segmentation (one method for all candidates): q = round(255 b); markers = 4-connected components of the
  h-minima of q with h = 13 (= 0.05); watershed of q from these markers, 4-connectivity, over the full image.
RAG: node = initial region; edge = pair of regions sharing >= 1 4-adjacent pixel pair; edge keeps a 64-bin
  histogram of s over all its shared pairs; region keeps area and the sum / count of Lab colour over non-ink pixels.
Merge (deterministic, greedy): repeatedly merge the adjacent pair with the lowest cost
  cost = median(s on the shared border) + lam * min(dE76(mean Lab_i, mean Lab_j) / 30, 1)
  histograms add on merge (exact median at 1/64 resolution); colour sums add; costs of touched edges recomputed.
  Ties: lower cost first, then smaller (i, j). Stopping at tau = prefix of the merge sequence before the first
  popped cost > tau, which is exactly the greedy run stopped at tau.
"""
import heapq
import numpy as np
from scipy import ndimage as ndi
from scipy.sparse import coo_matrix
from skimage.morphology import h_minima
from skimage.segmentation import watershed

Q, H_DYN, NB, DE0 = 255, 13, 64, 30.0
FOUR = [[0, 1, 0], [1, 1, 1], [0, 1, 0]]


def strengths(model, P):
    if model in ("M1", "M2"):
        b = P["prob"].astype(np.float32)
        sr = np.zeros_like(b); sd = np.zeros_like(b)
        sr[:, :-1] = np.maximum(b[:, :-1], b[:, 1:]); sd[:-1] = np.maximum(b[:-1], b[1:])
        return b, sr, sd
    pr = P["pr"].astype(np.float32).copy(); pd = P["pd"].astype(np.float32).copy()
    pr[:, -1] = 0; pd[-1] = 0
    b = np.maximum(pr, pd)
    b[:, 1:] = np.maximum(b[:, 1:], pr[:, :-1]); b[1:] = np.maximum(b[1:], pd[:-1])
    return b, pr, pd


def overseg(b):
    q = np.clip(np.rint(b * Q), 0, Q).astype(np.uint8)
    mk = ndi.label(h_minima(q, H_DYN), structure=FOUR)[0]
    return watershed(q, mk, connectivity=1).astype(np.int32)


def build_rag(lab, sr, sd):
    n = int(lab.max())
    a = np.concatenate([lab[:, :-1].ravel(), lab[:-1].ravel()]); c = np.concatenate([lab[:, 1:].ravel(), lab[1:].ravel()])
    s = np.concatenate([sr[:, :-1].ravel(), sd[:-1].ravel()])
    m = a != c; a, c, s = a[m].astype(np.int64), c[m].astype(np.int64), s[m]
    lo, hi = np.minimum(a, c), np.maximum(a, c)
    uk, inv = np.unique(lo * (n + 1) + hi, return_inverse=True)
    hist = np.zeros((len(uk), NB), np.int32)
    np.add.at(hist, (inv, np.clip((s * NB).astype(np.int64), 0, NB - 1)), 1)
    return {"n": n, "u": (uk // (n + 1)).astype(np.int64), "v": (uk % (n + 1)).astype(np.int64), "hist": hist}


def region_colour(lab, lab_img, ink1):
    n = int(lab.max()); l = lab.ravel(); keep = ~ink1.ravel()
    s_clean = np.stack([np.bincount(l[keep], weights=lab_img[..., k].ravel()[keep], minlength=n + 1) for k in range(3)], 1)
    c_clean = np.bincount(l[keep], minlength=n + 1).astype(np.float64)
    s_all = np.stack([np.bincount(l, weights=lab_img[..., k].ravel(), minlength=n + 1) for k in range(3)], 1)
    c_all = np.bincount(l, minlength=n + 1).astype(np.float64)
    use = c_clean >= 5
    return np.where(use[:, None], s_clean, s_all), np.where(use, c_clean, c_all)


def _median(h):
    cs = np.cumsum(h)
    return (int(np.searchsorted(cs, cs[-1] / 2.0)) + 0.5) / NB


def merge(rag, colsum=None, colcnt=None, lam=0.0, stop=np.inf):
    """Greedy hierarchical merge. Returns list of (cost, keep, absorbed) in pop order."""
    n, hist = rag["n"], rag["hist"].copy()
    adj = [dict() for _ in range(n + 1)]
    for e, (a, b) in enumerate(zip(rag["u"].tolist(), rag["v"].tolist())):
        adj[a][b] = e; adj[b][a] = e
    ver = np.zeros(len(hist), np.int64); alive = np.ones(n + 1, bool); alive[0] = False
    cs = None if colsum is None else colsum.astype(np.float64).copy(); cc = None if colcnt is None else colcnt.astype(np.float64).copy()

    def cost(e, a, b):
        c = _median(hist[e])
        if lam > 0:
            d = np.linalg.norm(cs[a] / max(cc[a], 1) - cs[b] / max(cc[b], 1))
            c += lam * min(d / DE0, 1.0)
        return c
    heap = []
    for e, (a, b) in enumerate(zip(rag["u"].tolist(), rag["v"].tolist())):
        heap.append((cost(e, a, b), a, b, e, 0))
    heapq.heapify(heap); merges = []
    while heap:
        c, a, b, e, v = heapq.heappop(heap)
        if v != ver[e] or not (alive[a] and alive[b]): continue
        if c > stop: break
        keep, gone = (a, b) if len(adj[a]) >= len(adj[b]) else (b, a)
        merges.append((c, keep, gone)); alive[gone] = False
        del adj[keep][gone]; del adj[gone][keep]
        for k, eg in list(adj[gone].items()):
            del adj[k][gone]
            if k in adj[keep]:
                ek = adj[keep][k]; hist[ek] += hist[eg]; ver[eg] += 1
            else:
                ek = eg; adj[keep][k] = ek; adj[k][keep] = ek
            ver[ek] += 1
            if lam == 0:
                lo, hi = (keep, k) if keep < k else (k, keep)
                heapq.heappush(heap, (cost(ek, lo, hi), lo, hi, ek, int(ver[ek])))
        adj[gone] = {}
        if lam > 0:
            cs[keep] += cs[gone]; cc[keep] += cc[gone]
            for k, ek in adj[keep].items():
                ver[ek] += 1; lo, hi = (keep, k) if keep < k else (k, keep)
                heapq.heappush(heap, (cost(ek, lo, hi), lo, hi, ek, int(ver[ek])))
    return merges


def partitions(n, merges, taus):
    """Root label per initial region for every tau (prefix of merges before the first cost > tau)."""
    parent = np.arange(n + 1); costs = np.array([m[0] for m in merges]) if merges else np.zeros(0)
    cut = {t: int(np.argmax(costs > t)) if (costs > t).any() else len(merges) for t in taus}
    out, done = {}, 0
    for t in sorted(taus, key=lambda t: cut[t]):
        for c, keep, gone in merges[done:cut[t]]: parent[gone] = keep
        done = cut[t]
        r = parent.copy()
        while True:
            nr = r[r]
            if (nr == r).all(): break
            r = nr
        out[t] = r
    return out


# ---------------- oracles / metrics (read labels) ----------------

def overlaps(lab, i1, V):
    m = V & (i1 > 0)
    C = coo_matrix((np.ones(int(m.sum())), (lab[m], i1[m])), shape=(int(lab.max()) + 1, int(i1.max()) + 1)).tocsr()
    C.sum_duplicates(); return C.tocoo()


def asa_ue(lab, i1, V):
    C = overlaps(lab, i1, V); s, g, x = C.row, C.col, C.data
    ssz = np.bincount(lab[V].ravel(), minlength=int(lab.max()) + 1)
    best = np.zeros(int(lab.max()) + 1); np.maximum.at(best, s, x)
    asa = float(best.sum() / V.sum())
    ue = float(np.minimum(x, ssz[s] - x).sum() / V.sum())
    return asa, ue


def oracle_A(lab, i1, V, ids):
    """Per instance best IoU over unions of initial regions (purity-sorted prefixes = optimum for one target).
    Ignores exclusivity (a region may serve several instances) and connectivity of the union."""
    C = overlaps(lab, i1, V).tocsc(); ssz = np.bincount(lab[V].ravel(), minlength=int(lab.max()) + 1)
    area = np.bincount(i1[V].ravel(), minlength=int(i1.max()) + 1); out = np.zeros(len(ids))
    for j, g in enumerate(ids):
        col = C.getcol(g); s = col.indices; x = col.data
        if len(s) == 0: continue
        o = np.argsort(-(x / ssz[s])); I = np.cumsum(x[o]); S = np.cumsum(ssz[s][o])
        out[j] = float((I / (area[g] + S - I)).max())
    return out


def oracle_B_regions(lab, i1, V):
    """Each initial region takes its majority instance (valid pixels; none -> 0); adjacent regions with the same
    majority are merged (4-connected components of equal values). Respects adjacency, indivisibility, exclusivity."""
    C = overlaps(lab, i1, V); maj = np.zeros(int(lab.max()) + 1, np.int64)
    o = np.lexsort((-C.data, C.row)); f = np.unique(C.row[o], return_index=True)[1]; maj[C.row[o][f]] = C.col[o][f]
    R = maj[lab]
    sep_r = np.zeros(R.shape, bool); sep_d = np.zeros(R.shape, bool)
    sep_r[:, :-1] = R[:, :-1] != R[:, 1:]; sep_d[:-1] = R[:-1] != R[1:]
    H, W = R.shape; G = np.zeros((2 * H - 1, 2 * W - 1), bool)
    G[::2, ::2] = True; G[::2, 1::2] = ~sep_r[:, :-1]; G[1::2, ::2] = ~sep_d[:-1]
    return ndi.label(G, structure=FOUR)[0][::2, ::2].astype(np.int32), maj
