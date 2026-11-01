"""Shared helpers for OCR POC-01 adapters. Each adapter runs in its own venv and only needs numpy + PIL.

CLI contract (all adapters):
  --image PATH --out PATH --image-id ID --scale K [--boxes truth_boxes.json] [--enhance]
  e2e mode (no --boxes): engine detects and recognises; polygons are mapped back to 1x source pixels.
  fixed-box mode (--boxes): recognition only on the given polygons (experiment B), same crops for every engine.
"""
import argparse, json, resource, sys, time
import numpy as np
from PIL import Image, ImageOps

PAD = 2  # source px of context around a fixed box (identical for all engines)


def args():
    p = argparse.ArgumentParser()
    p.add_argument("--image", required=True); p.add_argument("--out", required=True)
    p.add_argument("--image-id", default="u2"); p.add_argument("--scale", type=int, default=1)
    p.add_argument("--boxes"); p.add_argument("--enhance", action="store_true")
    return p.parse_args()


def load(a):
    im = Image.open(a.image).convert("RGB")
    if a.enhance: im = ImageOps.autocontrast(im, cutoff=1)
    return im


def scaled(im, k):
    return im if k == 1 else im.resize((im.width * k, im.height * k), Image.LANCZOS)


def boxes(a):
    return json.load(open(a.boxes))["boxes"] if a.boxes else None


def crop(im, poly, k):
    """axis-aligned crop of a source-pixel polygon, PAD px context, then upscale by k."""
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    x0, y0 = max(0, int(min(xs)) - PAD), max(0, int(min(ys)) - PAD)
    x1, y1 = min(im.width, int(np.ceil(max(xs))) + PAD), min(im.height, int(np.ceil(max(ys))) + PAD)
    return scaled(im.crop((x0, y0, x1, y1)), k)


def orient(poly):
    """angle in degrees of the first edge (0 = horizontal)."""
    (x0, y0), (x1, y1) = poly[0], poly[1]
    return round(float(np.degrees(np.arctan2(y1 - y0, x1 - x0))), 1)


def det(poly, text, conf, k, **extra):
    q = (np.asarray(poly, float) / k).round(2).tolist()
    return {"polygon": q, "raw_text": text, "confidence": None if conf is None else round(float(conf), 4), "orientation": orient(q), **extra}


def write(a, engine, model, dets, t0, meta=None):
    ru, rc = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)
    out = {"engine": engine, "model": model, "image_id": a.image_id, "scale": a.scale, "enhance": a.enhance,
           "mode": "fixed_box" if a.boxes else "e2e", "seconds": round(time.time() - t0, 2),
           "peak_rss_mb_self": round(ru.ru_maxrss / 2**20, 1), "peak_rss_mb_children": round(rc.ru_maxrss / 2**20, 1),
           "meta": meta or {}, "detections": dets}
    json.dump(out, open(a.out, "w"), ensure_ascii=False, indent=1)
    print(f"{engine} {out['mode']} x{a.scale}{' enh' if a.enhance else ''}: {len(dets)} dets {out['seconds']} s", file=sys.stderr)
