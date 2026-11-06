"""Four-state layer audit (T01): raster / pure faces / pure lines / pure text + overlay, and a
pixel<->object anomaly table for one region of a StitchVector GPKG.

Defect classes reported (each row = one object-level anomaly, with ids you can click back to):
  uncovered_px      - pixels inside the region no face covers (BG colour)
  enclosed_face     - a face whose every edge-neighbour is one and the same larger face
  interior_ring     - a Polygon with interior rings (possible false hole)
  island_face       - small face with no same-colour edge-neighbour at all
  glyph_line        - a line object mostly inside text boxes (suspected OCR glyph stroke)
  small_frag        - small face not enclosed but tiny relative to its neighbours
  raster_only       - high raster/vector residual with no vector object anomaly (bleed-through)

coverage=PASS alone is never accepted as proof the interior is clean.
"""
import json
from pathlib import Path
import numpy as np, pyogrio, shapely
import rasterio.features as RF
from affine import Affine
from PIL import Image, ImageDraw

from .render import FACE, LINE, TEXT, layers_of

BG = np.array([128, 128, 128], np.uint8)
_8 = np.ones((3, 3), bool)


def _rgb(s):
    s = str(s); return np.array([int(s[i:i + 2], 16) for i in (1, 3, 5)], np.uint8)


def _burn(geoms, values, shape):
    if not geoms: return np.zeros(shape, np.int32)
    return RF.rasterize(list(zip(geoms, values)), out_shape=shape, fill=0, transform=Affine.identity(), all_touched=False, dtype="int32")


def _edge_neighbours(tree_geoms, i, min_shared=0.5):
    """ids of faces sharing >= min_shared px of boundary with face i (STRtree-accelerated)."""
    geoms, tree = tree_geoms
    b = geoms[i].boundary
    if b.is_empty: return set()
    out = set()
    for j in tree.query(b.buffer(min_shared)):
        if j == i: continue
        inter = b.intersection(geoms[j])
        if not inter.is_empty and inter.length >= min_shared: out.add(j)
    return out


def load(gpkg):
    lay = layers_of(gpkg)
    F = pyogrio.read_dataframe(gpkg, layer=FACE)
    L = pyogrio.read_dataframe(gpkg, layer=LINE) if LINE in lay else F.iloc[:0]
    T = pyogrio.read_dataframe(gpkg, layer=TEXT) if TEXT in lay else F.iloc[:0]
    return F, L, T


def text_boxes_of(T):
    if T is None or not len(T): return np.zeros((0, 4))
    cols = [c for c in ("box_x0", "box_y0", "box_x1", "box_y1") if c in T.columns]
    if len(cols) == 4: return T[cols].to_numpy(float)
    b = np.array([g.bounds for g in T.geometry], float)
    return np.column_stack([b[:, 0] - 8, b[:, 1] - 6, b[:, 2] + 8, b[:, 3] + 6])


def audit(gpkg, img=None, box=None, small_area=60.0, ocr_json=None):
    """Full-region (or box-clipped) audit. Returns {"anomalies": [...], "frames": {...}, "counts": {...}}."""
    F, L, T = load(gpkg)
    boxes = text_boxes_of(T)
    if ocr_json:
        o = json.load(open(ocr_json)); items = o.get("items", o)
        q = np.array([[[p[0] for p in it["quad"]], [p[1] for p in it["quad"]]] for it in items if it.get("quad")], float)
        if q.size:
            qb = np.column_stack([q[:, 0].min(1), q[:, 1].min(1), q[:, 0].max(1), q[:, 1].max(1)])
            boxes = np.vstack([boxes, qb]) if len(boxes) else qb
    W = int(img.shape[1]) if img is not None else int(max(F.total_bounds[2], 1))
    H = int(img.shape[0]) if img is not None else int(max(F.total_bounds[3], 1))
    box = box or [0, 0, W, H]
    B = shapely.box(*box)
    geoms = list(F.geometry); areas = np.array([g.area for g in geoms]); rgbs = list(F["rgb"])
    tree = shapely.STRtree(geoms); tg = (geoms, tree)
    fid = _burn(geoms, range(1, len(geoms) + 1), (H, W)) - 1
    anomalies = []

    # ---- face-side anomalies -------------------------------------------------
    for i, g in enumerate(geoms):
        if not g.intersects(B): continue
        nb = _edge_neighbours(tg, i)
        in_ocr = bool(len(boxes) and np.any((boxes[:, 0] < g.bounds[2]) & (boxes[:, 2] > g.bounds[0]) &
                                            (boxes[:, 1] < g.bounds[3]) & (boxes[:, 3] > g.bounds[1])))
        rec = {"face_id": int(F["_eid"].iloc[i]) if "_eid" in F.columns else i, "row": i,
               "area": round(float(areas[i]), 1), "rgb": rgbs[i],
               "bounds": [round(v, 1) for v in g.bounds], "touches_ocr_box": in_ocr}
        if g.interiors:
            rings = [r for r in g.interiors if shapely.Polygon(r).area > 0.5]
            if rings: anomalies.append({**rec, "type": "interior_ring", "ring_count": len(rings),
                                        "ring_area": round(float(sum(shapely.Polygon(r).area for r in rings)), 1)})
        if len(nb) == 1 and areas[i] < areas[list(nb)[0]]:
            host = list(nb)[0]
            anomalies.append({**rec, "type": "enclosed_face", "enclosing_face_row": host,
                              "enclosing_rgb": rgbs[host], "same_colour_as_host": rgbs[i] == rgbs[host],
                              "enclosing_face_id": int(F["_eid"].iloc[host]) if "_eid" in F.columns else host})
        elif not nb and areas[i] < small_area * 20:
            anomalies.append({**rec, "type": "island_face"})
        elif areas[i] <= small_area and len(nb) >= 1:
            anomalies.append({**rec, "type": "small_frag", "neighbours": len(nb)})

    # ---- uncovered pixels ----------------------------------------------------
    if img is not None:
        x0, y0, x1, y1 = [int(v) for v in box]
        holes = int((fid[y0:y1, x0:x1] < 0).sum())
        if holes: anomalies.append({"type": "uncovered_px", "pixels": holes, "box": box})

    # ---- line-side anomalies -------------------------------------------------
    for i, g in enumerate(L.geometry):
        if g.is_empty or not g.intersects(B): continue
        in_share = 0.0
        if len(boxes):
            tb = shapely.union_all([shapely.box(*b) for b in boxes])
            in_share = float(g.intersection(tb).length / g.length) if g.length else 0.0
        rec = {"line_id": int(L["_eid"].iloc[i]) if "_eid" in L.columns else i, "row": i,
               "length": round(float(g.length), 1), "rgb": L["rgb"].iloc[i] if "rgb" in L.columns else None,
               "logical_id": L["logical_id"].iloc[i] if "logical_id" in L.columns else None,
               "bounds": [round(v, 1) for v in g.bounds],
               "inside_ocr_share": round(in_share, 3),
               "role": L["line_role"].iloc[i] if "line_role" in L.columns else None}
        if in_share >= 0.6: anomalies.append({**rec, "type": "glyph_line"})
        elif in_share > 0: anomalies.append({**rec, "type": "line_crosses_text"})

    # ---- raster-vs-vector residual (bleed-through detection) -----------------
    stats = {}
    if img is not None:
        x0, y0, x1, y1 = [int(v) for v in box]
        vec = np.empty((H, W, 3), np.uint8); vec[:] = BG
        pal = np.stack([_rgb(c) for c in F["rgb"]]); m = fid >= 0; vec[m] = pal[fid[m]]
        d = np.abs(img[y0:y1, x0:x1].astype(int) - vec[y0:y1, x0:x1].astype(int)).max(-1)
        face_only = d > 40
        stats = {"residual_px_gt40_faces_only": int(face_only.sum()),
                 "note": "face-layer-only residual: pixels where raster differs strongly from the flat face colour (lines/text/patterns expected here)"}
    counts = {"faces": len(F), "lines": len(L), "texts": len(T), "ocr_boxes": len(boxes),
              "anomalies": len(anomalies), **stats}
    return {"anomalies": anomalies, "counts": counts, "box": box, "shape": (H, W)}


def four_state_pngs(gpkg, img, box, out_dir, scale=4, ocr_json=None):
    """raster / faces-only / lines-only / text-only / overlay crops of `box` as PNGs."""
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    F, L, T = load(gpkg)
    x0, y0, x1, y1 = [int(v) for v in box]
    H, W = img.shape[:2]
    def crop(a): return np.asarray(a)[y0:y1, x0:x1]
    names = {}
    # A raster
    names["A_raster"] = "A_raster.png"; Image.fromarray(crop(img)).resize(((x1 - x0) * scale, (y1 - y0) * scale), Image.NEAREST).save(out / names["A_raster"])
    # B faces only (opaque)
    canv = Image.new("RGB", (W, H), (255, 255, 255)); dr = ImageDraw.Draw(canv)
    for g, c in zip(F.geometry, F["rgb"]):
        if not g.intersects(shapely.box(x0, y0, x1, y1)): continue
        for poly in ([g] if g.geom_type == "Polygon" else g.geoms):
            dr.polygon(list(poly.exterior.coords), fill="#" + str(c).lstrip("#"))
            for r in poly.interiors: dr.polygon(list(r.coords), fill=(255, 255, 255))
    names["B_faces"] = "B_faces.png"; Image.fromarray(crop(canv)).resize(((x1 - x0) * scale, (y1 - y0) * scale), Image.NEAREST).save(out / names["B_faces"])
    # C lines only
    canv = Image.new("RGB", (W, H), (255, 255, 255)); dr = ImageDraw.Draw(canv)
    for g, c, w in zip(L.geometry, L["rgb"] if "rgb" in L.columns else ["#000000"] * len(L), L["width_px"] if "width_px" in L.columns else [1.0] * len(L)):
        if g.is_empty or not g.intersects(shapely.box(x0, y0, x1, y1)): continue
        for gg in ([g] if g.geom_type == "LineString" else getattr(g, "geoms", [])):
            dr.line(list(gg.coords), fill="#" + str(c).lstrip("#"), width=max(int(round(float(w))), 1))
    names["C_lines"] = "C_lines.png"; Image.fromarray(crop(canv)).resize(((x1 - x0) * scale, (y1 - y0) * scale), Image.NEAREST).save(out / names["C_lines"])
    # D text only (boxes + text)
    canv = Image.new("RGB", (W, H), (255, 255, 255)); dr = ImageDraw.Draw(canv)
    tboxes = text_boxes_of(T)
    for i, (_, r) in enumerate(T.iterrows()):
        bx = list(tboxes[i])
        if bx[2] < x0 or bx[0] > x1 or bx[3] < y0 or bx[1] > y1: continue
        dr.rectangle(bx, outline=(200, 0, 0), width=1); dr.text((bx[0], bx[1]), str(r["text"]), fill=(0, 0, 0))
    names["D_text"] = "D_text.png"; Image.fromarray(crop(canv)).resize(((x1 - x0) * scale, (y1 - y0) * scale), Image.NEAREST).save(out / names["D_text"])
    # E overlay: raster 45% + vector layers on top
    base = Image.fromarray(img.copy()); dr = ImageDraw.Draw(base, "RGBA")
    dr.rectangle([x0, y0, x1, y1], fill=(255, 255, 255, 120))
    for g, c in zip(F.geometry, F["rgb"]):
        if not g.intersects(shapely.box(x0, y0, x1, y1)): continue
        for poly in ([g] if g.geom_type == "Polygon" else g.geoms):
            dr.polygon(list(poly.exterior.coords), fill="#" + str(c).lstrip("#"))
    for g, c, w in zip(L.geometry, L["rgb"] if "rgb" in L.columns else ["#000000"] * len(L), L["width_px"] if "width_px" in L.columns else [1.0] * len(L)):
        if g.is_empty or not g.intersects(shapely.box(x0, y0, x1, y1)): continue
        for gg in ([g] if g.geom_type == "LineString" else getattr(g, "geoms", [])):
            dr.line(list(gg.coords), fill="#" + str(c).lstrip("#"), width=max(int(round(float(w))), 1))
    Image.blend(Image.fromarray(crop(img)), base.crop((x0, y0, x1, y1)), 0.5).resize(((x1 - x0) * scale, (y1 - y0) * scale), Image.NEAREST).save(out / "E_overlay.png")
    names["E_overlay"] = "E_overlay.png"
    return names
