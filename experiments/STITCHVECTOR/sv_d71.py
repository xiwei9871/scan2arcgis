"""StitchVector 7.1 line/face diagnostic (exploratory). Rules frozen in sv_d71_prereg.json.

One label image (u2 centre 300x300, 32-colour median cut). Small-scale candidates are split into
L (high-confidence overlay line), P (protected: attached to a same-class wide region, elongated between different
colours, or its colour class also fills wide regions elsewhere) and U (undetermined). P takes priority over L. L pixels are kept as a separate pixel line layer (intermediate,
not vectorised); the face layer is the label image with L pixels filled from the nearest non-L pixel (inferred).
Reads only image pixels; no labels.
"""
import json, sys, time
from pathlib import Path
import numpy as np, cv2
from scipy import ndimage as ndi
from skimage.morphology import skeletonize
from skimage.color import rgb2lab
import shapely
from shapely.geometry import LineString

HERE = Path(__file__).resolve().parent
P0 = {"merge_dE": 10.0, "open_px": 4, "min_skel": 15, "elong": 10.0, "branch": 0.05, "side_win": 7,
      "side_px_dom": 0.85, "side_min_ctx": 8, "side_same": 0.8, "side_diff": 0.5, "contrast_dE": 15.0, "attach_min": 2, "fill_min": 200, "fill_share": 0.5}
S4 = ndi.generate_binary_structure(2, 1); S8 = np.ones((3, 3), bool)
CLS = {0: "none", 1: "L_core", 2: "P", 3: "U", 4: "L_halo"}


def pal_lab(pal):
    return rgb2lab(pal[None].astype(np.float64) / 255.0)[0]


def colour_classes(lab, pal, dE):
    """Single-linkage merge of used palette entries with CIE76 dE < dE. Returns class map, label->class lut, centroids."""
    used = [int(u) for u in np.unique(lab)]; PL = pal_lab(pal); parent = {u: u for u in used}
    def f(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i
    for i in used:
        for j in used:
            if i < j and np.linalg.norm(PL[i] - PL[j]) < dE: parent[f(j)] = f(i)
    roots = sorted({f(u) for u in used}); rid = {r: k for k, r in enumerate(roots)}
    lut = np.full(len(pal), -1, np.int32)
    for u in used: lut[u] = rid[f(u)]
    cnt = np.bincount(lab.ravel(), minlength=len(pal)).astype(np.float64)
    cent = np.zeros((len(roots), 3))
    for k in range(len(roots)):
        m = lut == k; cent[k] = (cnt[m, None] * PL[m]).sum(0) / cnt[m].sum()
    return lut[lab], lut, cent


def face_labels(lab):
    out = np.zeros(lab.shape, np.int32); n = 0
    for v in np.unique(lab):
        l, k = ndi.label(lab == v, S4); m = l > 0; out[m] = l[m] + n; n += k
    return out, n


def candidates(K, open_px):
    # scipy opening: cv2.morphologyEx with an even kernel puts the anchor off-centre and the result leaks outside the
    # mask (found by the synthetic test: a pink opening covered a red line)
    ker = np.ones((open_px, open_px), bool); thin = np.zeros(K.shape, bool); wide = np.zeros(K.shape, bool)
    for c in np.unique(K):
        m = K == c; o = ndi.binary_opening(m, ker, border_value=0) & m
        thin |= m & ~o; wide |= o
    return thin, wide


def units(thin, K):
    U = np.zeros(K.shape, np.int32); n = 0
    for c in np.unique(K[thin]):
        l, k = ndi.label(thin & (K == c), S8); m = l > 0; U[m] = l[m] + n; n += k
    return U, n


def _same_unit_degree(sk, U):
    H, W = U.shape; Up = np.pad(U, 1); sp = np.pad(sk, 1); deg = np.zeros(U.shape, np.int32)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy or dx:
                deg += sp[1 + dy:1 + dy + H, 1 + dx:1 + dx + W] & (Up[1 + dy:1 + dy + H, 1 + dx:1 + dx + W] == U)
    return deg * sk


def features(U, n, K, thin, wide, cent, p):
    N = n + 1; ucls = np.full(N, -1, np.int32); ucls[U[U > 0]] = K[U > 0]
    npx = np.bincount(U.ravel(), minlength=N).astype(np.float64)
    sk = np.zeros(K.shape, bool)
    for c in np.unique(K[thin]): sk |= skeletonize(thin & (K == c))
    sk &= U > 0
    deg = _same_unit_degree(sk, U)
    skl = np.bincount(U[sk], minlength=N).astype(np.float64)
    nodes = np.bincount(U[sk & ((deg <= 1) | (deg >= 3))], minlength=N).astype(np.float64)
    attach = np.zeros(K.shape, bool)
    for c in np.unique(K[thin]):
        attach |= thin & (K == c) & ndi.binary_dilation(wide & (K == c), S4)
    att = np.bincount(U[attach], minlength=N)
    ctx = ~thin; w = p["side_win"]; cls_ids = np.unique(K)
    counts = np.stack([cv2.boxFilter((ctx & (K == j)).astype(np.float32), -1, (w, w), normalize=False,
                                     borderType=cv2.BORDER_CONSTANT) for j in cls_ids])
    tot = counts.sum(0); dom = counts.max(0); domcls = cls_ids[counts.argmax(0)]
    same = (tot >= p["side_min_ctx"]) & (dom >= p["side_px_dom"] * np.maximum(tot, 1))
    side = np.bincount(U[sk], weights=same[sk].astype(np.float64), minlength=N) / np.maximum(skl, 1)
    ok = sk & (tot >= p["side_min_ctx"])
    bg = np.full(N, -1, np.int32)
    if ok.any():
        key = U[ok].astype(np.int64) * (len(cent) + 1) + domcls[ok]; uk, c = np.unique(key, return_counts=True)
        uu, cc = uk // (len(cent) + 1), uk % (len(cent) + 1); o = np.lexsort((-c, uu)); f = np.unique(uu[o], return_index=True)[1]
        bg[uu[o][f]] = cc[o][f]
    contrast = np.zeros(N)
    v = (bg >= 0) & (ucls >= 0); contrast[v] = np.linalg.norm(cent[ucls[v]] - cent[bg[v]], axis=1)
    width = npx / np.maximum(skl, 1); elong = skl / np.maximum(width, 1e-9); branch = nodes / np.maximum(skl, 1)
    cw = np.bincount(K[wide], minlength=len(cent)); ct = np.bincount(K.ravel(), minlength=len(cent))
    isfill = (cw >= p["fill_min"]) & (cw >= p["fill_share"] * np.maximum(ct, 1))      # ink also has wide px at crossings/text
    fillc = np.zeros(N, bool); v2 = ucls >= 0; fillc[v2] = isfill[ucls[v2]]
    return {"fill_colour": fillc, "ucls": ucls, "npx": npx, "skel": skl, "width": width, "elong": elong, "branch": branch, "attach_px": att,
            "side_same": side, "bg_cls": bg, "contrast": contrast, "sk": sk}


def classify(ft, p):
    skl, el = ft["skel"], ft["elong"]
    longish = (skl >= p["min_skel"]) & (el >= p["elong"])
    isP = (ft["attach_px"] >= p["attach_min"]) | (longish & (ft["side_same"] < p["side_diff"])) | ft["fill_colour"]
    isL = ~isP & longish & (ft["branch"] <= p["branch"]) & (ft["side_same"] >= p["side_same"]) & (ft["contrast"] >= p["contrast_dE"])
    cls = np.where(isP, 2, np.where(isL, 1, 3)).astype(np.int32); cls[0] = 0
    return cls


def add_halo(cls, U, npx):
    """U units lying entirely within one pixel (8-neighbourhood) of L_core become L_halo (one pass)."""
    core = cls[U] == 1
    if not core.any(): return cls
    dil = ndi.binary_dilation(core, S8)
    inside = np.bincount(U[dil & (cls[U] == 3)], minlength=len(cls))
    out = cls.copy(); out[(cls == 3) & (inside == npx) & (npx > 0)] = 4
    return out


def fill(lab, Lm):
    F = lab.copy()
    if Lm.any():
        _, (iy, ix) = ndi.distance_transform_edt(Lm, return_indices=True); F[Lm] = lab[iy[Lm], ix[Lm]]
    return F


def face_change(lab, F, Lm):
    B, nb = face_labels(lab); G, ng = face_labels(F)
    nB = np.bincount(B.ravel(), minlength=nb + 1); nL = np.bincount(B[Lm], minlength=nb + 1)
    keep = ~Lm; pairs = np.unique(B[keep].astype(np.int64) * (ng + 1) + G[keep])
    pb, pg = pairs // (ng + 1), pairs % (ng + 1)
    bper = np.bincount(pg, minlength=ng + 1); gper = np.bincount(pb, minlength=nb + 1)
    return {"faces_before": int(nb), "faces_after": int(ng),
            "baseline_faces_fully_in_L": int(((nL == nB) & (nB > 0))[1:].sum()),
            "after_faces_merging_2plus_baseline_faces": int((bper[1:] >= 2).sum()),
            "baseline_faces_merged_into_those": int(bper[1:][bper[1:] >= 2].sum()),
            "after_faces_inferred_only": int(ng - len(np.unique(pg))),
            "baseline_faces_split_after": int((gper[1:] >= 2).sum())}


def run_one(lab, pal, p, halo=True):
    K, lut, cent = colour_classes(lab, pal, p["merge_dE"])
    thin, wide = candidates(K, p["open_px"])
    U, n = units(thin, K)
    ft = features(U, n, K, thin, wide, cent, p)
    cls = classify(ft, p)
    if halo: cls = add_halo(cls, U, ft["npx"])
    pix = cls[U]; pix[U == 0] = 0
    Lm = (pix == 1) | (pix == 4)
    F = fill(lab, Lm)
    return {"K": K, "lut": lut, "cent": cent, "thin": thin, "U": U, "n_units": n, "ft": ft, "cls": cls, "pix": pix, "Lm": Lm, "F": F}


def counts(r):
    c = r["cls"][1:]; px = r["pix"]
    return {k: {"units": int((c == i).sum()), "px": int((px == i).sum())} for i, k in CLS.items() if i}


# ---------------- line-layer cost estimates (intermediate; the line layer is NOT vectorised in this diagnostic) ----
def skeleton_chains(sk):
    S = set(zip(*[a.tolist() for a in np.nonzero(sk)]))
    def nb(q): return [(q[0] + dy, q[1] + dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if (dy or dx) and (q[0] + dy, q[1] + dx) in S]
    deg = {q: len(nb(q)) for q in S}; used = set(); out = []
    def key(a, b): return (a, b) if a < b else (b, a)
    def walk(s, t):
        pts = [s, t]; used.add(key(s, t)); prev, cur = s, t
        while deg[cur] == 2:
            nx = [q for q in nb(cur) if q != prev]
            if not nx or key(cur, nx[0]) in used: break
            used.add(key(cur, nx[0])); pts.append(nx[0]); prev, cur = cur, nx[0]
        return pts
    for q in sorted(S):
        if deg[q] != 2:
            for t in nb(q):
                if key(q, t) not in used: out.append(walk(q, t))
    for q in sorted(S):
        for t in nb(q):
            if key(q, t) not in used: out.append(walk(q, t))
    iso = sum(1 for q in S if deg[q] == 0)
    return out, iso


def line_cost(r, lab):
    import sv_common as C
    Lm = r["Lm"]; out = {}
    lu, nlu = ndi.label(Lm, S8); out["logical_line_candidates_8conn"] = int(nlu)
    pf = C.polygonize(lab, mask=Lm)
    out["pixel_faithful_polygons"] = {"objects": len(pf), "vertices_exact": C.n_vertices([g for g, _ in pf]),
                                      "vertices_simplify1_unshared": C.n_vertices([g.simplify(1.0) for g, _ in pf])}
    Ul = np.where(Lm, r["U"], 0)
    up = C.polygonize(Ul, mask=Lm)
    out["single_colour_unit_polygons"] = {"objects": len(up), "vertices_exact": C.n_vertices([g for g, _ in up]),
                                          "vertices_simplify1_unshared": C.n_vertices([g.simplify(1.0) for g, _ in up])}
    sk = skeletonize(Lm)
    ch, iso = skeleton_chains(sk)
    v = sum(len(LineString([(x, y) for y, x in c]).simplify(1.0).coords) for c in ch) + iso
    out["centreline_estimate"] = {"chains": len(ch) + iso, "vertices_simplify1": int(v), "skeleton_px": int(sk.sum())}
    return out


def face_vector(X):
    import sv_arcs as A
    t = time.time(); polys, vals, lines, _ = A.single_pass(X, 0); s = time.time() - t
    H, W = X.shape; R = A.render(polys, vals, H, W)
    return {"faces": len(polys), "arcs": len(lines), "vertices": int(sum(len(l.coords) for l in lines)),
            "mismatch_px": int((R != X).sum()), "topology": {k: bool(v) for k, v in A.topology(polys, H, W).items()},
            "seconds": round(s, 2)}, R


def region_stats(a, rgb, lab_ref, lab_x, m):
    if not m.any(): return None
    from sv_common import _lab
    de = np.sqrt(((_lab(a[m][None]) - _lab(rgb[m][None])) ** 2).sum(-1)).ravel()
    return {"px": int(m.sum()), "label_equal_share": float((lab_ref[m] == lab_x[m]).mean()),
            "dE50_vs_original": float(np.percentile(de, 50)), "dE90_vs_original": float(np.percentile(de, 90))}
