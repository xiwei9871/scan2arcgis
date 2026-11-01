"""Deterministic raster rendering of a StitchVector GPKG on the scan's own pixel grid, and RGB residuals.

Pixel (col, row) of the output covers [col, col+1) x [row, row+1) in GPKG coordinates (x right, y down, no CRS),
exactly the grid of the scan image. No resampling, no registration, no anti-aliasing: the same GPKG and the same
options always give byte-identical PNGs.

Layer order (fixed): colour_faces (pixel-centre rule, file order) -> visual_lines (ascending draw_order, then file
order; each line is its centre path buffered by max(width_px/2, 0.71), pixel-centre rule) -> optional text_labels
(text box filled with nothing; glyphs are NOT drawn, see render(text=...)). Isolated lines (text_residue_lines) are
never drawn. Colours are the stored rgb attributes.
"""
import hashlib
from pathlib import Path
import numpy as np, pyogrio, shapely
import rasterio.features as RF
from affine import Affine

FACE, LINE, TEXT = "colour_faces", "visual_lines", "text_labels"
BG = np.array([128, 128, 128], np.uint8)          # pixels no face covers (should not exist with strict coverage)


def _rgb(s):
    s = str(s); return np.array([int(s[i:i + 2], 16) for i in (1, 3, 5)], np.uint8)


def _burn(geoms, values, shape):
    """index raster: value of the LAST geometry covering each pixel centre (rasterio burns in order), 0 = none."""
    if not geoms: return np.zeros(shape, np.int32)
    return RF.rasterize(list(zip(geoms, values)), out_shape=shape, fill=0, transform=Affine.identity(), all_touched=False, dtype="int32")


def layers_of(gpkg):
    return [l[0] for l in pyogrio.list_layers(gpkg)]


def render(gpkg, shape, faces=True, lines=True, text_boxes=False):
    """render a GPKG file at the scan's pixel grid; see render_frames."""
    lay = layers_of(gpkg)
    F = pyogrio.read_dataframe(gpkg, layer=FACE) if faces else None
    L = pyogrio.read_dataframe(gpkg, layer=LINE) if lines and LINE in lay else None
    T = pyogrio.read_dataframe(gpkg, layer=TEXT) if text_boxes and TEXT in lay else None
    return render_frames(F, L, T, shape)


def render_frames(F, L, T, shape):
    """returns (rgb uint8 HxWx3, face_id HxW int32 (-1 none), line_id HxW int32 (-1 none)).
    Pixel-centre rasterisation (all_touched=False), faces first, then lines by draw_order (ties by row), no anti-aliasing,
    no registration. face_id / line_id are row positions in F / L (for clicking a residual back to an object).
    T (text_labels) only paints its box outline in black (1 px); glyphs depend on fonts and never enter a residual."""
    H, W = shape; out = np.empty((H, W, 3), np.uint8); out[:] = BG
    fid = np.full(shape, -1, np.int32); lid = np.full(shape, -1, np.int32)
    if F is not None and len(F):
        idx = _burn(list(F.geometry), range(1, len(F) + 1), shape) - 1
        pal = np.stack([_rgb(c) for c in F["rgb"]]); m = idx >= 0; out[m] = pal[idx[m]]; fid = idx
    if L is not None and len(L):
        order = np.lexsort((np.arange(len(L)), L["draw_order"].astype(float).to_numpy()))
        geoms = [L.geometry.iloc[i].buffer(max(float(L["width_px"].iloc[i]) / 2, 0.71), quad_segs=8) for i in order]
        idx = _burn(geoms, [int(i) + 1 for i in order], shape) - 1
        pal = np.stack([_rgb(c) for c in L["rgb"]]); m = idx >= 0; out[m] = pal[idx[m]]; lid = idx
    if T is not None and len(T):
        for _, r in T.iterrows():
            x0, y0, x1, y1 = [int(round(float(r[k]))) for k in ("box_x0", "box_y0", "box_x1", "box_y1")]
            x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, W) - 1, min(y1, H) - 1
            if x1 > x0 and y1 > y0: out[y0, x0:x1 + 1] = 0; out[y1, x0:x1 + 1] = 0; out[y0:y1 + 1, x0] = 0; out[y0:y1 + 1, x1] = 0
    return out, fid, lid


def residual(a, b):
    """raw per-channel absolute RGB difference (uint8, HxWx3) and its per-pixel max (HxW). No registration."""
    if a.shape != b.shape: raise ValueError(f"shape mismatch {a.shape} vs {b.shape}; residuals need the same pixel grid")
    d = np.abs(a.astype(np.int16) - b.astype(np.int16)).astype(np.uint8); return d, d.max(-1)


def heatmap(dmax, mask=None):
    """visual of the per-pixel max difference: 0 = white, 255 = dark red (linear, no threshold). Masked pixels grey."""
    v = dmax.astype(np.float32) / 255.0; out = np.empty(dmax.shape + (3,), np.uint8)
    out[..., 0] = (255 - 115 * v).astype(np.uint8); out[..., 1] = (255 * (1 - v)).astype(np.uint8); out[..., 2] = (255 * (1 - v)).astype(np.uint8)
    if mask is not None: out[mask] = (200, 200, 200)
    return out


def stats(dmax, mask=None, thresholds=(1, 10, 30, 60)):
    """statistics of the per-pixel max residual; pixels where `mask` is True are EXCLUDED."""
    m = np.ones(dmax.shape, bool) if mask is None else ~mask; v = dmax[m]
    return {"pixels": int(v.size), "mean_max_abs": round(float(v.mean()), 3) if v.size else 0.0,
            "p50": float(np.percentile(v, 50)) if v.size else 0.0, "p90": float(np.percentile(v, 90)) if v.size else 0.0,
            "p99": float(np.percentile(v, 99)) if v.size else 0.0,
            **{f"px_ge_{t}": int((v >= t).sum()) for t in thresholds}, **{f"share_ge_{t}": round(float((v >= t).mean()), 5) if v.size else 0.0 for t in thresholds}}


def text_mask(gpkg_or_boxes, shape, pad=1):
    """pixels inside text boxes (+pad): from a GPKG text_labels layer or a list of [x0,y0,x1,y1]."""
    H, W = shape; m = np.zeros(shape, bool)
    if isinstance(gpkg_or_boxes, (str, Path)):
        if TEXT not in layers_of(gpkg_or_boxes): return m
        T = pyogrio.read_dataframe(gpkg_or_boxes, layer=TEXT); boxes = T[["box_x0", "box_y0", "box_x1", "box_y1"]].to_numpy(float)
    else: boxes = np.asarray(gpkg_or_boxes, float).reshape(-1, 4)
    for x0, y0, x1, y1 in boxes:
        m[max(int(np.floor(y0)) - pad, 0):min(int(np.ceil(y1)) + pad, H), max(int(np.floor(x0)) - pad, 0):min(int(np.ceil(x1)) + pad, W)] = True
    return m


def png_bytes(a):
    import io
    from PIL import Image
    b = io.BytesIO(); Image.fromarray(a).save(b, format="PNG", optimize=False, compress_level=6); return b.getvalue()


def sha256_bytes(b): return hashlib.sha256(b).hexdigest()
