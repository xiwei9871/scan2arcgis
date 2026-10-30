"""ARCH-2 C-PAIR V0.1: narrow-band candidate generation, features, states and soft-protected merge.
Prediction side only: inputs are the B2 pixel strength b, the RGB-derived Lab image and the image ink mask.
No official label file is read in this module.
Fixed parameters: experiments/ARCH2/arch2_preregistration.json "parameters_fixed_now" (not tuned).

Line graph   skeleton of b > theta_line; orientation from the structure tensor of b (sigma 1.5 / 2.5 px);
             th = normal angle (x = cos th, y = sin th)
Pairing      from every skeleton pixel p, both normal directions, march t = d_min..d_max step 0.5 px; at each t check
             the rounded point and +-k px along the tangent (k <= normal_tolerance); the FIRST skeleton pixel met ends
             the march; it is a partner if the undirected orientation difference <= max_direction_difference
Gaps         for (u, side) without a partner: partnered skeleton pixels of the same skeleton component within max_gap px
             on BOTH tangent sides whose partner direction points the same way (dot >= 0.7); spacings differ by
             <= spacing_change; the bridged midpoint colour differs from the neighbours' midpoint colour by <= dE max;
             then u gets an interpolated partner (bridged = True)
Band         pixels p + dir * t' for t' in [1, t - 1] step 0.5 (strictly between the two lines)
Candidates   4-connected components of the painted band with opposed length (pairs / 2) >= min_opposed_length
Features     s_edge   median over the candidate's pairs of min(b[p], b[q])
             s_width  median spacing t
             s_colour min(dE76(centre, side 1), dE76(centre, side 2)); centre = midpoint +-1 px along the normal,
                      side k = 1..3 px beyond each line; only non-ink pixels; MISSING (nan) if any group has < 5 pixels
States       any feature missing -> UNCERTAIN; PROTECT iff all three >= protect thresholds; MERGE iff s_colour and
             s_width < ink-band thresholds; both true -> UNCERTAIN (conflict); else UNCERTAIN
"""
import heapq, json, sys
from pathlib import Path
import cv2, numpy as np
from scipy import ndimage as ndi
from scipy.spatial import cKDTree
from skimage.morphology import skeletonize

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments/R4C0"))
import r4c0_rag as R  # noqa: E402

P = json.load(open(ROOT / "experiments/ARCH2/arch2_preregistration.json"))["parameters_fixed_now"]
FOUR = [[0, 1, 0], [1, 1, 1], [0, 1, 0]]


def orientation(b):
    g = cv2.GaussianBlur(b.astype(np.float32), (0, 0), 1.5)
    gx, gy = cv2.Sobel(g, cv2.CV_32F, 1, 0), cv2.Sobel(g, cv2.CV_32F, 0, 1)
    Jxx, Jyy, Jxy = (cv2.GaussianBlur(a, (0, 0), 2.5) for a in (gx * gx, gy * gy, gx * gy))
    return 0.5 * np.arctan2(2 * Jxy, Jxx - Jyy)


def angdiff(a, b):
    d = np.abs(np.degrees(a - b)) % 180
    return np.minimum(d, 180 - d)


def find_pairs(sk, th, p=P):
    H, W = sk.shape; ys, xs = np.nonzero(sk); nx, ny = np.cos(th[ys, xs]), np.sin(th[ys, xs])
    T = np.arange(p["pair_distance_px"][0], p["pair_distance_px"][1] + 1e-9, 0.5)
    offs = [0] + [o for k in range(1, p["normal_tolerance_px"] + 1) for o in (-k, k)]
    out = []
    for sign in (1, -1):
        todo = np.ones(len(ys), bool)
        for t in T:
            idx = np.flatnonzero(todo)
            if not len(idx): break
            stop = np.zeros(len(idx), bool); okq = np.full(len(idx), -1); qy = np.zeros(len(idx), int); qx = np.zeros(len(idx), int)
            for o in offs:
                X_ = np.rint(xs[idx] + sign * t * nx[idx] - o * ny[idx]).astype(int)
                Y_ = np.rint(ys[idx] + sign * t * ny[idx] + o * nx[idx]).astype(int)
                ins = (X_ >= 0) & (X_ < W) & (Y_ >= 0) & (Y_ < H)
                h = np.zeros(len(idx), bool); h[ins] = sk[Y_[ins], X_[ins]]
                h &= ~stop | (okq < 0)
                good = h.copy(); good[h] = angdiff(th[ys[idx][h], xs[idx][h]], th[Y_[h], X_[h]]) <= p["max_direction_difference_deg"]
                new = good & (okq < 0); okq[new] = 1; qy[new] = Y_[new]; qx[new] = X_[new]
                stop |= h
            acc = okq > 0
            for j in np.flatnonzero(acc):
                i = idx[j]; out.append((ys[i], xs[i], qy[j], qx[j], t, sign * nx[i], sign * ny[i], 0))
            todo[idx[stop]] = False
    a = np.array(out, float).reshape(-1, 8)
    return {"py": a[:, 0].astype(int), "px": a[:, 1].astype(int), "qy": a[:, 2].astype(int), "qx": a[:, 3].astype(int),
            "t": a[:, 4], "dx": a[:, 5], "dy": a[:, 6], "bridged": a[:, 7].astype(bool)}


def bridge(sk, th, pairs, lab_img, p=P):
    H, W = sk.shape; comp = ndi.label(sk, structure=np.ones((3, 3)))[0]
    if len(pairs["py"]) == 0: return pairs
    tree = cKDTree(np.c_[pairs["py"], pairs["px"]])
    mid = lambda y, x, dx, dy, t: lab_img[np.clip(np.rint(y + dy * t / 2).astype(int), 0, H - 1), np.clip(np.rint(x + dx * t / 2).astype(int), 0, W - 1)]
    ys, xs = np.nonzero(sk); nx, ny = np.cos(th[ys, xs]), np.sin(th[ys, xs])
    has = {}
    for y, x, dx, dy in zip(pairs["py"], pairs["px"], pairs["dx"], pairs["dy"]):
        has.setdefault((y, x), []).append((dx, dy))
    cnt = tree.query_ball_point(np.c_[ys, xs], r=p["max_gap_px"], return_length=True)
    cand = np.flatnonzero(cnt > 0); new = []
    nb_lists = tree.query_ball_point(np.c_[ys[cand], xs[cand]], r=p["max_gap_px"])
    for i, nb0 in zip(cand, nb_lists):
        y, x = ys[i], xs[i]
        for s in (1, -1):
            d = np.array([s * nx[i], s * ny[i]])
            if any(np.dot(d, e) >= 0.7 for e in has.get((y, x), [])): continue
            nb = np.array(nb0)                                     # fresh copy per direction (nb0 is not reused)
            nb = nb[comp[pairs["py"][nb], pairs["px"][nb]] == comp[y, x]]
            if len(nb) < 2: continue
            al = pairs["dx"][nb] * d[0] + pairs["dy"][nb] * d[1] >= 0.7; nb = nb[al]
            if len(nb) < 2: continue
            tg = np.array([-d[1], d[0]])
            proj = (pairs["px"][nb] - x) * tg[0] + (pairs["py"][nb] - y) * tg[1]
            lo, hi = nb[proj < 0], nb[proj > 0]
            if not len(lo) or not len(hi): continue
            dist = lambda k: np.hypot(pairs["px"][k] - x, pairs["py"][k] - y)
            a, b = lo[np.argmin(dist(lo))], hi[np.argmin(dist(hi))]
            if abs(pairs["t"][a] - pairs["t"][b]) > p["gap_rules"]["spacing_change_across_gap_px_max"]: continue
            ts = 0.5 * (pairs["t"][a] + pairs["t"][b])
            cm = 0.5 * (mid(pairs["py"][a], pairs["px"][a], pairs["dx"][a], pairs["dy"][a], pairs["t"][a]) +
                        mid(pairs["py"][b], pairs["px"][b], pairs["dx"][b], pairs["dy"][b], pairs["t"][b]))
            cu = mid(y, x, d[0], d[1], ts)
            if np.linalg.norm(cu - cm) > p["gap_rules"]["colour_change_across_gap_dE_max"]: continue
            new.append((y, x, int(np.clip(np.rint(y + d[1] * ts), 0, H - 1)), int(np.clip(np.rint(x + d[0] * ts), 0, W - 1)), ts, d[0], d[1], 1))
    if not new: return pairs
    a = np.array(new, float)
    add = {"py": a[:, 0].astype(int), "px": a[:, 1].astype(int), "qy": a[:, 2].astype(int), "qx": a[:, 3].astype(int),
           "t": a[:, 4], "dx": a[:, 5], "dy": a[:, 6], "bridged": a[:, 7].astype(bool)}
    return {k: np.concatenate([pairs[k], add[k]]) for k in pairs}


def paint(pairs, shape):
    H, W = shape; n = len(pairs["t"]); steps = np.arange(1.0, 12.0 + 1e-9, 0.5)
    tt = steps[None, :]; ok = tt <= (pairs["t"][:, None] - 1.0 + 1e-9)
    Y = np.rint(pairs["py"][:, None] + pairs["dy"][:, None] * tt).astype(int); X = np.rint(pairs["px"][:, None] + pairs["dx"][:, None] * tt).astype(int)
    ok &= (Y >= 0) & (Y < H) & (X >= 0) & (X < W)
    band = np.zeros(shape, bool); band[Y[ok], X[ok]] = True
    my = np.clip(np.rint(pairs["py"] + pairs["dy"] * pairs["t"] / 2).astype(int), 0, H - 1)
    mx = np.clip(np.rint(pairs["px"] + pairs["dx"] * pairs["t"] / 2).astype(int), 0, W - 1)
    return band, my, mx


def generate(b, lab_img, ink1, p=P):
    """Return dict: cand (int map 0 / 1..K), feats (per candidate dict arrays), pairs, n_skeleton."""
    th = orientation(b); sk = skeletonize(b > p["line_threshold_theta_line"])
    pairs = bridge(sk, th, find_pairs(sk, th, p), lab_img, p)
    band, my, mx = paint(pairs, b.shape)
    lab = ndi.label(band, structure=FOUR)[0]
    pc = lab[my, mx]
    n = int(lab.max()); npairs = np.bincount(pc, minlength=n + 1)
    keep = np.flatnonzero(npairs / 2 >= p["min_opposed_length_px"]); keep = keep[keep > 0]
    lut = np.zeros(n + 1, np.int64); lut[keep] = np.arange(1, len(keep) + 1)
    cand = lut[lab]; pid = lut[pc]
    K = len(keep); feats = features(cand, pid, pairs, b, lab_img, ink1, K)
    return {"cand": cand.astype(np.int32), "feats": feats, "pairs": pairs, "pair_cand": pid, "n_skeleton": int(sk.sum()), "K": K}


def features(cand, pid, pairs, b, lab_img, ink1, K):
    H, W = cand.shape; sel = pid > 0
    if K == 0: return {k: np.zeros(0) for k in ("s_edge", "s_width", "s_colour", "n_pairs", "area", "bridged_share")}
    bp = b[pairs["py"], pairs["px"]]; bq = b[pairs["qy"], pairs["qx"]]; mn = np.minimum(bp, bq)
    ids = np.arange(1, K + 1)
    s_edge = np.asarray(ndi.median(mn[sel], labels=pid[sel], index=ids), float)
    s_width = np.asarray(ndi.median(pairs["t"][sel], labels=pid[sel], index=ids), float)
    npair = np.bincount(pid, minlength=K + 1)[1:].astype(float)
    bridged = np.bincount(pid, weights=pairs["bridged"].astype(float), minlength=K + 1)[1:] / np.maximum(npair, 1)
    area = np.bincount(cand.ravel(), minlength=K + 1)[1:].astype(float)
    # orientation reference per candidate: first pair's direction
    first = np.full(K + 1, -1); order = np.flatnonzero(sel)
    for i in order[::-1]: first[pid[i]] = i
    rx, ry = pairs["dx"][first[pid[sel]]], pairs["dy"][first[pid[sel]]]
    flip = (pairs["dx"][sel] * rx + pairs["dy"][sel] * ry) < 0
    py, px, qy, qx = pairs["py"][sel], pairs["px"][sel], pairs["qy"][sel], pairs["qx"][sel]
    dx, dy, t, c = pairs["dx"][sel], pairs["dy"][sel], pairs["t"][sel], pid[sel]
    groups = []
    for k in (-1, 0, 1):
        groups.append((c, np.zeros_like(c), py + dy * (t / 2 + k), px + dx * (t / 2 + k)))
    for k in (1, 2, 3):
        g_start = np.where(flip, 2, 1); g_end = np.where(flip, 1, 2)
        groups.append((c, g_start, py - dy * k, px - dx * k))
        groups.append((c, g_end, qy + dy * k, qx + dx * k))
    cc = np.concatenate([g[0] for g in groups]); gg = np.concatenate([g[1] for g in groups])
    YY = np.clip(np.rint(np.concatenate([g[2] for g in groups])).astype(int), 0, H - 1)
    XX = np.clip(np.rint(np.concatenate([g[3] for g in groups])).astype(int), 0, W - 1)
    key = np.unique(((cc * 3 + gg) * H + YY) * W + XX)
    XX = key % W; YY = (key // W) % H; cg = key // (W * H); cc = cg // 3; gg = cg % 3
    keep = ~ink1[YY, XX]; cc, gg, YY, XX = cc[keep], gg[keep], YY[keep], XX[keep]
    idx = cc * 3 + gg; n3 = (K + 1) * 3
    cnt = np.bincount(idx, minlength=n3).reshape(K + 1, 3)
    mean = np.stack([np.bincount(idx, weights=lab_img[YY, XX, ch], minlength=n3) for ch in range(3)], 1).reshape(K + 1, 3, 3) / np.maximum(cnt, 1)[..., None]
    d1 = np.linalg.norm(mean[:, 0] - mean[:, 1], axis=1); d2 = np.linalg.norm(mean[:, 0] - mean[:, 2], axis=1)
    s_colour = np.minimum(d1, d2); s_colour[(cnt < 5).any(1)] = np.nan
    return {"s_edge": s_edge, "s_width": s_width, "s_colour": s_colour[1:], "n_pairs": npair, "area": area, "bridged_share": bridged}


def states(feats, thr):
    """thr: {'protect': {s_edge, s_colour, s_width}, 'ink': {s_colour, s_width}} -> array of strings."""
    e, c, w = feats["s_edge"], feats["s_colour"], feats["s_width"]
    miss = np.isnan(e) | np.isnan(c) | np.isnan(w)
    prot = (e >= thr["protect"]["s_edge"]) & (c >= thr["protect"]["s_colour"]) & (w >= thr["protect"]["s_width"])
    merge = (c < thr["ink"]["s_colour"]) & (w < thr["ink"]["s_width"])
    st = np.full(len(e), "UNCERTAIN", object)
    st[prot & ~merge] = "PROTECT_SOFT"; st[merge & ~prot] = "MERGE"; st[miss] = "UNCERTAIN"
    return st


def merge_protected(rag, pc, lam_p, stop):
    """Greedy median merge (as r4c0_rag.merge) with a soft protection term: an edge between regions whose protection
    ids differ and at least one is > 0 costs median + lam_p. A merged region keeps the id only if both ids are equal."""
    n, hist = rag["n"], rag["hist"].copy(); pc = pc.astype(np.int64).copy()
    adj = [dict() for _ in range(n + 1)]
    for e, (a, b) in enumerate(zip(rag["u"].tolist(), rag["v"].tolist())):
        adj[a][b] = e; adj[b][a] = e
    ver = np.zeros(len(hist), np.int64); alive = np.ones(n + 1, bool); alive[0] = False

    def cost(e, a, b):
        return R._median(hist[e]) + (lam_p if (pc[a] != pc[b] and (pc[a] > 0 or pc[b] > 0)) else 0.0)
    heap = [(cost(e, a, b), a, b, e, 0) for e, (a, b) in enumerate(zip(rag["u"].tolist(), rag["v"].tolist()))]
    heapq.heapify(heap); merges = []
    while heap:
        c, a, b, e, v = heapq.heappop(heap)
        if v != ver[e] or not (alive[a] and alive[b]): continue
        if c > stop: break
        keep, gone = (a, b) if len(adj[a]) >= len(adj[b]) else (b, a)
        merges.append((c, keep, gone)); alive[gone] = False
        pc[keep] = pc[keep] if pc[keep] == pc[gone] else 0
        del adj[keep][gone]; del adj[gone][keep]
        for k, eg in list(adj[gone].items()):
            del adj[k][gone]
            if k in adj[keep]:
                ek = adj[keep][k]; hist[ek] += hist[eg]; ver[eg] += 1
            else:
                ek = eg; adj[keep][k] = ek; adj[k][keep] = ek
        adj[gone] = {}
        for k, ek in adj[keep].items():
            ver[ek] += 1; lo, hi = (keep, k) if keep < k else (k, keep)
            heapq.heappush(heap, (cost(ek, lo, hi), lo, hi, ek, int(ver[ek])))
    return merges
