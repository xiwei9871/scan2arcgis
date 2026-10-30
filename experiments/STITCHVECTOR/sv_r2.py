"""R2 (pre-registration R2): quantize -> variant A (direct mosaic) | B (ink layer + fill completion) ->
progressive repair at 4 -> 2 -> 1 px with exact-pixel fallback. Reads only image pixels.

Repair replaces geometry: accepted residual blocks are cut out of existing features (geometric difference)
and re-filled with the target labels traced at the next tolerance, so the result stays a planar partition.
"""
import json, sys, time
from pathlib import Path
import numpy as np, shapely
from scipy import ndimage as ndi
import rasterio.features as RF
from shapely.geometry import mapping
import sv_common as C

TR = -2                                   # transparent class (ink layer: "no ink here"); never drawn
FOUR = ndi.generate_binary_structure(2, 1)
TOLS = C.PR["R2"]["progressive"]["stage_tolerances_px"]


def csimplify(geoms, t):
    if t == 0 or not len(geoms): return list(geoms)
    return list(shapely.coverage_simplify(np.asarray(geoms, object), float(t), simplify_boundary=False))


def render(feats, h, w):
    s = [(mapping(g), int(v)) for g, v in feats if v != TR and not g.is_empty]
    if not s: return np.full((h, w), -1, np.int32)
    return RF.rasterize(s, out_shape=(h, w), fill=-1, transform=C.ID, all_touched=False, dtype="int32")


def _cut(feats, blocks):
    """Remove the union of block polygons from every feature that intersects them."""
    geoms = np.asarray([g for g, _ in feats], object); vals = [v for _, v in feats]
    if not len(blocks): return feats, 0, 0
    bp = np.asarray(blocks, object); tree = shapely.STRtree(bp)
    fi, bi = tree.query(geoms, predicate="intersects")
    o = np.argsort(fi, kind="stable"); fi, bi = fi[o], bi[o]
    uf, start = np.unique(fi, return_index=True); ends = np.append(start[1:], len(fi))
    for f, s, e in zip(uf, start, ends):
        hole = bp[bi[s]] if e - s == 1 else shapely.union_all(bp[bi[s:e]])
        geoms[f] = shapely.difference(geoms[f], hole)
    empty = shapely.is_empty(geoms)
    return [(g, v) for g, v, z in zip(geoms, vals, empty) if not z], int(empty.sum()), int(len(uf) - empty.sum())


def _node_local(feats, blocks, tol=1e-6):
    """Make shared boundaries noded around repaired blocks: features touching a block are snapped to the union
    of the boundaries of all such features (inserts the missing vertices at T-junctions). Found by the synthetic
    planar-partition test before any real run; it moves no vertex by more than tol."""
    if not len(blocks): return feats
    geoms = np.asarray([g for g, _ in feats], object)
    zone = shapely.buffer(shapely.union_all(np.asarray(blocks, object)), 0.5)
    idx = np.flatnonzero(shapely.intersects(geoms, zone))
    if not len(idx): return feats
    # one ring of neighbours: unchanged features sharing an edge with a cut/inserted feature also need the new
    # T-junction vertices (found by the synthetic test: features 6-8 lay outside the zone but touched 9-10)
    tree = shapely.STRtree(geoms); _, nb = tree.query(geoms[idx], predicate="intersects")
    idx = np.unique(np.concatenate([idx, nb]))
    # per-feature local snap (performance fix, same result as snapping to the global union: a vertex can only
    # be missing where a feature touches a neighbour, so each feature is snapped to its neighbours' boundaries)
    bnd = shapely.boundary(geoms); src, dst = tree.query(geoms[idx], predicate="intersects")
    o = np.argsort(src, kind="stable"); src, dst = src[o], dst[o]
    us, st = np.unique(src, return_index=True); en = np.append(st[1:], len(src))
    new = geoms.copy()
    for s, a, b in zip(us, st, en):
        f = idx[s]; nb_ = dst[a:b]; nb_ = nb_[nb_ != f]
        if len(nb_): new[f] = shapely.snap(geoms[f], shapely.union_all(bnd[nb_]), tol)
    geoms = new
    return [(g, v) for g, (_, v) in zip(geoms, feats)]


def progressive(target, tols=TOLS, check=False):
    """target: int label image (TR = transparent). Returns feats [(geom, value)], per-stage log."""
    h, w = target.shape; tgt = np.where(target == TR, -1, target)
    ex = C.polygonize(target)
    feats = list(zip(csimplify([g for g, _ in ex], tols[0]), [v for _, v in ex]))
    log = [{"stage_tol": tols[0], "features": len(feats)}]
    for t in list(tols[1:]) + [0]:
        cur = render(feats, h, w); res = cur != tgt; e0 = int(res.sum())
        rec = {"next_tol": t, "residual_px_before": e0}
        if e0 == 0: log.append(rec); break
        blk, nb = ndi.label(res, structure=FOUR)
        cex = C.polygonize(target, mask=res)
        cand = list(zip(csimplify([g for g, _ in cex], t), [v for _, v in cex]))
        after = np.where(res, render(cand, h, w), cur)
        eb = np.bincount(blk.ravel(), weights=res.ravel(), minlength=nb + 1)
        ea = np.bincount(blk.ravel(), weights=((after != tgt) & res).ravel(), minlength=nb + 1)
        acc = ea < eb; acc[0] = False
        rp = shapely.point_on_surface(np.asarray([g for g, _ in cand], object))
        ys = np.clip(np.floor(shapely.get_y(rp)).astype(int), 0, h - 1); xs = np.clip(np.floor(shapely.get_x(rp)).astype(int), 0, w - 1)
        bid = blk[ys, xs]; keep = [c for c, b in zip(cand, bid) if acc[b]]
        Macc = acc[blk]
        blocks = [g for g, _ in C.polygonize(Macc.astype(np.int32), mask=Macc)]
        n_before = len(feats)
        feats, removed, modified = _cut(feats, blocks)
        feats = _node_local(feats + keep, blocks)
        rec.update(blocks=int(nb), accepted_blocks=int(acc.sum()), rejected_blocks=int(nb - acc.sum()),
                   features_before=n_before, removed=removed, modified=modified, inserted=len(keep),
                   features_after=len(feats), trace_ok=bool(len(feats) == n_before - removed + len(keep)))
        if check: rec.update(partition_check(feats, h, w))
        log.append(rec)
    final = render(feats, h, w)
    log.append({"final_residual_px": int((final != tgt).sum())})
    return feats, log


def partition_check(feats, h, w):
    g = np.asarray([x for x, _ in feats], object)
    # pre-registered check: sum of areas == window AND area of the union == window  <=>  no overlap and no gap.
    # (shapely.coverage_is_valid was used first but also rejects raw rasterio polygonize output, whose shared
    #  edges carry different vertex sets / T-junctions; it is stricter than the pre-registration and is reported
    #  only as information.)
    s = float(shapely.area(g).sum()); u = float(shapely.area(shapely.union_all(g)))
    return {"area_sum_equals_window": bool(abs(s - h * w) < 1e-6),
            "union_area_equals_window": bool(abs(u - h * w) < 1e-6),
            "coverage_valid_no_overlap": bool(abs(s - h * w) < 1e-6 and abs(u - h * w) < 1e-6),
            "coverage_is_valid_strict_info": bool(shapely.coverage_is_valid(g))}


# ---------- variant B: ink layer + fill completion ----------
def ink_classes(pal):
    from skimage.color import rgb2lab
    L = rgb2lab(pal[None].astype(np.float64) / 255.0)[0, :, 0]
    return np.flatnonzero(L < 35)


def fill_complete(lab, ink, max_iter=500):
    """Iteratively give each ink pixel the majority non-ink label among its 8 neighbours (ties -> lowest label)."""
    H, W = lab.shape; L = lab.copy(); todo = ink.copy(); n = int(L.max()) + 1; it = 0
    while todo.any() and it < max_iter:
        P = np.pad(np.where(todo, -1, L), 1, constant_values=-1)
        cnt = np.zeros((n, H, W), np.int16)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == 0 and dx == 0: continue
                nb = P[1 + dy:1 + dy + H, 1 + dx:1 + dx + W]
                for c in np.unique(nb[todo & (nb >= 0)]): cnt[c] += (nb == c)
        has = cnt.max(0) > 0; upd = todo & has
        if not upd.any(): break
        L[upd] = cnt.argmax(0)[upd]; todo &= ~upd; it += 1
    return L, int(it), int(todo.sum())


def layers(lab, pal, variant):
    if variant == "A": return [("all", lab)], None
    ink = np.isin(lab, ink_classes(pal))
    fill, it, left = fill_complete(lab, ink)
    return [("fill", fill), ("ink", np.where(ink, lab, TR))], {"ink_px": int(ink.sum()), "iterations": it,
                                                              "unfilled_px": left, "inferred_mask": ink}


def compose(layer_renders, pal, h, w):
    out = np.zeros((h, w, 3), np.uint8)
    for r in layer_renders:
        m = r >= 0; out[m] = pal[r[m]]
    return out
