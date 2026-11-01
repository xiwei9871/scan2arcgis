"""POC 0 (read-only): where do the small faces of an existing GPKG come from?
Each face with area <= SMALL px2 inside the map area gets the first matching class:
  under_known_line   within (line width / 2 + 2) px of a visual_lines feature
  on_unrecognised_ink  within 2 px of elongated ink (contrast to a 15x15 median > 12 dE, skeleton >= 15 px) that no
                       visual_lines feature covers: a line that was not recognised, its strokes stay in the face layer
  near_text_or_symbol  within 2 px of compact dark ink (L* < 50 component, not elongated): text or symbol strokes
  quantisation_shade   its colour is within 10 dE of the face it shares the longest edge with: same fill, split by colour
                       quantisation / anti-aliasing
  distinct_small       none of the above: small and clearly different from its neighbour (may be a real feature)
Usage: sv_poc0_fragments.py <image> <gpkg> <json_out> <png_out> [--map-cols 94]   (.venv-sv)"""
import json, sys, collections
import numpy as np, cv2, shapely, pyogrio
from scipy import ndimage as ndi
from skimage.morphology import skeletonize
from skimage.color import rgb2lab
from PIL import Image, ImageDraw

SMALL, C_INK, MIN_SKEL, DE_SAME = 5.0, 12.0, 15, 10.0
CLASSES = ["under_known_line", "on_unrecognised_ink", "near_text_or_symbol", "quantisation_shade", "distinct_small"]
COL = {"under_known_line": (0, 120, 255), "on_unrecognised_ink": (230, 0, 0), "near_text_or_symbol": (150, 0, 200),
       "quantisation_shade": (255, 170, 0), "distinct_small": (0, 170, 0)}


def hexrgb(s): return np.array([int(s[i:i + 2], 16) for i in (1, 3, 5)], float)


def main(image, gpkg, js, png, map_cols=94):
    a = np.asarray(Image.open(image).convert("RGB")); H, W = a.shape[:2]
    L = rgb2lab(a / 255.0); con = np.sqrt(((L - rgb2lab(cv2.medianBlur(a, 15) / 255.0)) ** 2).sum(-1))
    F = pyogrio.read_dataframe(gpkg, layer="colour_faces")
    layers = [l[0] for l in pyogrio.list_layers(gpkg)]
    V = pyogrio.read_dataframe(gpkg, layer="visual_lines") if "visual_lines" in layers else None
    mapbox = shapely.box(0, 0, map_cols, H)
    lines_zone = shapely.union_all([g.buffer(w / 2 + 2) for g, w in zip(V.geometry, V["width_px"])]) if V is not None and len(V) else None
    # elongated ink not covered by any recognised line
    ink = con > C_INK; lab_, n = ndi.label(ink, np.ones((3, 3))); sk = skeletonize(ink)
    skl = np.bincount(lab_[sk], minlength=n + 1); elong = np.zeros(n + 1, bool); elong[1:] = skl[1:] >= MIN_SKEL
    cov = np.zeros((H, W), bool)
    if lines_zone is not None:
        import rasterio.features as RF
        from affine import Affine
        cov = RF.rasterize([(lines_zone, 1)], out_shape=(H, W), fill=0, transform=Affine.identity(), dtype="uint8") > 0
    unrec = sk & elong[lab_] & ~cov; ur_lab, ur_n = ndi.label(unrec, np.ones((3, 3))); ur_len = np.bincount(ur_lab.ravel(), minlength=ur_n + 1)
    unrec = np.isin(ur_lab, np.nonzero(ur_len >= MIN_SKEL)[0][1:] if ur_n else [])
    dark = (L[..., 0] < 50) & ~elong[lab_]
    d_unrec = ndi.distance_transform_edt(~unrec) if unrec.any() else np.full((H, W), 1e9)
    d_dark = ndi.distance_transform_edt(~dark) if dark.any() else np.full((H, W), 1e9)
    geoms = np.asarray(F.geometry.values, object); area = shapely.area(geoms); tree = shapely.STRtree(geoms)
    small = [i for i in range(len(F)) if area[i] <= SMALL and geoms[i].intersects(mapbox)]
    recs = []
    for i in small:
        g = geoms[i]; c = g.representative_point(); x, y = int(np.clip(c.x, 0, W - 1)), int(np.clip(c.y, 0, H - 1))
        nb = [j for j in tree.query(g, predicate="touches") if j != i]
        shared = [(shapely.length(shapely.intersection(g, geoms[j])), j) for j in nb]
        shared = [s for s in shared if s[0] > 0]
        best = max(shared)[1] if shared else None
        dE = float(np.linalg.norm(rgb2lab(hexrgb(F["rgb"].iloc[i]).reshape(1, 1, 3) / 255)[0, 0] - rgb2lab(hexrgb(F["rgb"].iloc[best]).reshape(1, 1, 3) / 255)[0, 0])) if best is not None else None
        if lines_zone is not None and g.intersects(lines_zone): k = "under_known_line"
        elif d_unrec[y, x] <= 2: k = "on_unrecognised_ink"
        elif d_dark[y, x] <= 2: k = "near_text_or_symbol"
        elif dE is not None and dE <= DE_SAME: k = "quantisation_shade"
        else: k = "distinct_small"
        recs.append({"face": int(i), "area": float(area[i]), "class": k, "dE_to_main_neighbour": dE, "xy": [round(c.x, 1), round(c.y, 1)],
                     "inferred_px": int(F["inferred_px"].iloc[i]) if "inferred_px" in F.columns else None})
    cnt = collections.Counter(r["class"] for r in recs)
    res = {"image": image, "gpkg": gpkg, "faces": len(F), "small_faces_in_map": len(recs), "by_class": {k: cnt[k] for k in CLASSES},
           "share_by_class": {k: cnt[k] / max(len(recs), 1) for k in CLASSES}, "unrecognised_ink_skeleton_px": int(unrec.sum()),
           "params": {"small_px2": SMALL, "c_ink": C_INK, "min_skeleton_px": MIN_SKEL, "de_same": DE_SAME, "map_cols": map_cols}, "faces_detail": recs}
    json.dump(res, open(js, "w"), indent=1)
    k = 6; base = np.kron(a[:, :map_cols], np.ones((k, k, 1), np.uint8)); im = Image.fromarray((base * 0.45 + 255 * 0.55).astype(np.uint8)); d = ImageDraw.Draw(im)
    for y, x in zip(*np.nonzero(unrec[:, :map_cols])): d.rectangle([x * k, y * k, x * k + k - 1, y * k + k - 1], fill=(255, 120, 120))
    if V is not None:
        for g in V.geometry:
            for q in shapely.get_parts(g): d.line([(x * k, y * k) for x, y in q.coords], fill=(0, 90, 255), width=2)
    for r in recs:
        g = geoms[r["face"]]
        for ring in [g.exterior]: d.polygon([(x * k, y * k) for x, y in ring.coords], outline=COL[r["class"]], fill=COL[r["class"]])
    Image.fromarray(np.hstack([base, np.asarray(im)])).save(png)
    print(json.dumps({k_: v for k_, v in res.items() if k_ not in ("faces_detail",)}, indent=1))


if __name__ == "__main__":
    a = sys.argv[1:]; mc = int(a[a.index("--map-cols") + 1]) if "--map-cols" in a else 94
    main(a[0], a[1], a[2], a[3], mc)
