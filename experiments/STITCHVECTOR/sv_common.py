"""StitchVector POC-01 shared code (frozen by poc01_preregistration.json, commit a9813b4).
Pixel coordinates: x right, y down, identity affine. Evaluation renderer: rasterio rasterize, all_touched=False,
features painted in ascending z. No labels are read anywhere in this module.
"""
import json, resource, time
from pathlib import Path
import numpy as np
from PIL import Image
import rasterio.features as RF
from affine import Affine
import shapely
from shapely.geometry import shape, mapping

ROOT = Path(__file__).resolve().parents[2]
PR = json.load(open(ROOT / "experiments/STITCHVECTOR/poc01_preregistration.json"))
SAMPLES = {"u2": "runs/real/u2/work.png", "u3": "runs/real/u3/work.png", "13014": "runs/r4a2/13014/geotiff_rgb.png"}
ID = Affine.identity()


def load(code):
    return np.asarray(Image.open(ROOT / SAMPLES[code]).convert("RGB"))


def centre_crop(a, h, w):
    H, W = a.shape[:2]; h, w = min(h, H), min(w, W); y, x = (H - h) // 2, (W - w) // 2
    return np.ascontiguousarray(a[y:y + h, x:x + w]), (y, x)


def rgb_key(a):
    return (a[..., 0].astype(np.int32) << 16) | (a[..., 1].astype(np.int32) << 8) | a[..., 2].astype(np.int32)


def key_rgb(k):
    k = np.asarray(k, np.int64); return np.stack([(k >> 16) & 255, (k >> 8) & 255, k & 255], -1).astype(np.uint8)


def quantize(a, n):
    """PIL median cut, no dither. Returns label image (int32), palette (n x 3 uint8)."""
    q = Image.fromarray(a).quantize(colors=n, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    lab = np.asarray(q).astype(np.int32); pal = np.asarray(q.getpalette()[:3 * n], np.uint8).reshape(-1, 3)
    return lab, pal


def polygonize(values, mask=None):
    """Same-value 4-connected components -> list of (shapely polygon, value)."""
    v = values.astype(np.int32)
    return [(shape(g), int(val)) for g, val in RF.shapes(v, mask=mask, connectivity=4, transform=ID)]


def render(feats, h, w, fill=-1):
    """feats: iterable of (geom, value, z). Paint ascending z; later overwrites earlier."""
    out = np.full((h, w), fill, np.int64)
    fs = sorted(feats, key=lambda t: t[2])
    shapes = [(mapping(g), int(v)) for g, v, _ in fs if g is not None and not g.is_empty]
    if shapes:
        # rasterize paints in list order; merge_alg REPLACE = later wins
        out = RF.rasterize(shapes, out_shape=(h, w), fill=fill, transform=ID, all_touched=False,
                           dtype="int64", merge_alg=RF.MergeAlg.replace)
    return out


def n_vertices(geoms):
    return int(sum(shapely.get_num_coordinates(g) for g in geoms))


def peak_rss_gb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e9  # macOS: bytes


class Timer:
    def __enter__(self): self.t = time.time(); return self
    def __exit__(self, *a): self.s = round(time.time() - self.t, 2)


# ---------- metrics (vs a reference RGB image) ----------
def _lab(a):
    from skimage.color import rgb2lab
    return rgb2lab(a.astype(np.float64) / 255.0)


def thin_mask(a):
    """Label-free, fixed: pixels with local inscribed width <= 3 px inside their same-colour component of the
    32-colour quantization (EDT <= 1.5)."""
    import cv2
    lab, _ = quantize(a, 32); m = np.zeros(lab.shape, bool)
    for c in np.unique(lab):
        b = np.pad((lab == c).astype(np.uint8), 1)
        d = cv2.distanceTransform(b, cv2.DIST_L2, 5)[1:-1, 1:-1]
        m |= (lab == c) & (d <= 1.5)
    return m


def fidelity(ref, rec, thin=None):
    import cv2
    from skimage.metrics import structural_similarity as ssim
    eq = (ref == rec).all(-1); d = np.abs(ref.astype(np.int16) - rec.astype(np.int16))
    mse = float((d.astype(np.float64) ** 2).mean()); de = np.sqrt(((_lab(ref) - _lab(rec)) ** 2).sum(-1))
    g1, g2 = cv2.cvtColor(ref, cv2.COLOR_RGB2GRAY), cv2.cvtColor(rec, cv2.COLOR_RGB2GRAY)
    e1, e2 = cv2.Canny(g1, 50, 150) > 0, cv2.Canny(g2, 50, 150) > 0
    if e1.any() and e2.any():
        d1 = cv2.distanceTransform((~e1).astype(np.uint8), cv2.DIST_L2, 3); d2 = cv2.distanceTransform((~e2).astype(np.uint8), cv2.DIST_L2, 3)
        bd = float((d1[e2].mean() + d2[e1].mean()) / 2)
    else:
        bd = None
    out = {"exact_share": float(eq.mean()), "mae": float(d.mean()), "dE50": float(np.percentile(de, 50)),
           "dE90": float(np.percentile(de, 90)), "dE99": float(np.percentile(de, 99)),
           "psnr": None if mse == 0 else float(10 * np.log10(255 ** 2 / mse)),
           "ssim": float(ssim(g1, g2, data_range=255)), "boundary_dist": bd}
    if thin is not None and thin.any(): out["thin_match_dE10"] = float((de[thin] <= 10).mean())
    return out
