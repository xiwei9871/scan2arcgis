"""Automatic legend swatch detection (R1 PoC).

Finds rectangular, uniformly filled boxes (legend swatches) in a legend region:
dark-bordered rectangles of similar size whose interior colour is homogeneous.
Optionally OCRs the Latin part of the unit code inside the swatch (tesseract eng;
Chinese/Greek glyphs are NOT read reliably -> code_ocr is a hint, not ground truth).
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile

import cv2
import numpy as np


def detect_swatches(rgb: np.ndarray, region: tuple[int, int, int, int], *,
                    min_side=18, max_side=400, aspect=(0.8, 3.5), max_std=28.0):
    x0, y0, w, h = region
    sub = rgb[y0:y0 + h, x0:x0 + w]
    gray = cv2.cvtColor(sub, cv2.COLOR_RGB2GRAY)
    edges = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY_INV, 15, 10)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    cnts, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    cands = []
    for c in cnts:
        bx, by, bw, bh = cv2.boundingRect(c)
        if not (min_side <= bw <= max_side and min_side <= bh <= max_side):
            continue
        if not (aspect[0] <= bw / bh <= aspect[1]):
            continue
        if cv2.contourArea(c) < 0.8 * bw * bh:      # must be (nearly) rectangular
            continue
        p = max(2, min(bw, bh) // 5)
        inner = sub[by + p:by + bh - p, bx + p:bx + bw - p].reshape(-1, 3).astype(np.float32)
        if len(inner) < 30:
            continue
        med = np.median(inner, 0)
        # robust homogeneity: fraction of pixels near the median colour (text inside swatch allowed)
        near = (np.linalg.norm(inner - med, axis=1) < max_std).mean()
        if near < 0.6 or med.mean() > 250:          # skip white/empty boxes
            continue
        cands.append(dict(box=[bx + x0, by + y0, bw, bh], fill_rgb=[int(v) for v in med], homogeneity=float(near)))
    # de-duplicate nested boxes (border inner/outer contours)
    cands.sort(key=lambda d: -d["box"][2] * d["box"][3])
    keep = []
    for d in cands:
        bx, by, bw, bh = d["box"]
        if any(abs(bx - k["box"][0]) < 8 and abs(by - k["box"][1]) < 8 for k in keep):
            continue
        keep.append(d)
    # dominant swatch size: legends use one box size; drop outliers (map symbols, table cells)
    if keep:
        ws = np.array([k["box"][2] for k in keep]); hs = np.array([k["box"][3] for k in keep])
        mw, mh = np.median(ws), np.median(hs)
        keep = [k for k in keep if abs(k["box"][2] - mw) < 0.35 * mw and abs(k["box"][3] - mh) < 0.35 * mh]
    keep.sort(key=lambda d: (d["box"][0] // 200, d["box"][1]))
    for i, k in enumerate(keep):
        k["legend_entry_id"] = f"S{i:02d}"
    return keep


def ocr_code(rgb: np.ndarray, box) -> str | None:
    if not shutil.which("tesseract"):
        return None
    x, y, w, h = box
    patch = cv2.cvtColor(rgb[y:y + h, x:x + w], cv2.COLOR_RGB2GRAY)
    patch = cv2.resize(patch, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    _, bw = cv2.threshold(patch, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    with tempfile.NamedTemporaryFile(suffix=".png") as f:
        cv2.imwrite(f.name, bw)
        r = subprocess.run(["tesseract", f.name, "-", "--psm", "7", "-l", "eng",
                            "-c", "tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-"],
                           capture_output=True, text=True, timeout=20)
    t = r.stdout.strip()
    return t or None
