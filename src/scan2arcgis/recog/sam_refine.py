"""SAM 2.1-tiny boundary refinement of a legend-classified label map (R1 candidate).

For each tile (<=1024 px) and each predicted region in it, prompt SAM with the
region's most interior point (+) and interior points of neighbouring regions (-).
Only pixels that are LOW-margin in the classifier are allowed to change: SAM
supplies geometry, the legend classifier keeps the semantics.
"""
from __future__ import annotations

import time
from pathlib import Path

import cv2
import numpy as np

from .sam2_onnx import Sam2Onnx
from ..eval.raster_metrics import instances_from_labels


def _interior_point(mask):
    d = cv2.distanceTransform(mask.astype(np.uint8), cv2.DIST_L2, 5)
    y, x = np.unravel_index(int(d.argmax()), d.shape)
    return x, y, float(d.max())


def sam_refine(model_dir: Path, rgb, labels, margin, valid, map_box, *, tile=1024,
               low_margin=0.5, min_region_px=400, max_neg=4):
    sam = Sam2Onnx(model_dir)
    out = labels.copy()
    x0, y0, w, h = map_box
    info = {"tiles": 0, "prompts": 0, "changed_px": 0, "encode_s": 0.0, "decode_s": 0.0}
    for ty in range(y0, y0 + h, tile):
        for tx in range(x0, x0 + w, tile):
            sl = (slice(ty, min(ty + tile, y0 + h)), slice(tx, min(tx + tile, x0 + w)))
            sub_rgb, sub_lab, sub_m, sub_v = rgb[sl], labels[sl], margin[sl], valid[sl]
            info["encode_s"] += sam.set_image(np.ascontiguousarray(sub_rgb)); info["tiles"] += 1
            inst = instances_from_labels(sub_lab, sub_v)
            ids, cnt = np.unique(inst[inst > 0], return_counts=True)
            centres = {}
            for i in ids[cnt >= min_region_px]:
                px, py, depth = _interior_point(inst == i)
                if depth >= 4:
                    centres[int(i)] = (px, py)
            t = time.perf_counter()
            for i, (px, py) in centres.items():
                region = inst == i
                ring = cv2.dilate(region.astype(np.uint8), np.ones((15, 15), np.uint8)) > 0
                neigh = [j for j in np.unique(inst[ring & ~region]) if j in centres and j != i][:max_neg]
                pts = np.array([(px, py)] + [centres[j] for j in neigh], np.float32)
                lbl = np.array([1] + [0] * len(neigh))
                m, _ = sam.predict(pts, lbl)
                info["prompts"] += 1
                cls = sub_lab[py, px]
                change = m & ~region & (sub_m < low_margin) & sub_v
                # never let SAM grow a region beyond its neighbours (bounded by dilation ring)
                change &= cv2.dilate(region.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
                out[sl][change] = cls
                info["changed_px"] += int(change.sum())
            info["decode_s"] += time.perf_counter() - t
    return out, info
