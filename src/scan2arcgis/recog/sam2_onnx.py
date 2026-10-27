"""SAM 2.1-tiny (ONNX, CPU) wrapper used as a boundary-refinement candidate.

Weights: onnx-community/sam2.1-hiera-tiny-ONNX (export of facebook/sam2.1-hiera-tiny,
Apache-2.0). Downloaded at run time to a local cache; never committed.

Use in this project: SAM does not know geology. We prompt it with points
sampled from a legend-driven region and keep the mask as a *geometry*
candidate; class labels still come from the legend classifier.
"""
from __future__ import annotations

import time
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)


class Sam2Onnx:
    def __init__(self, model_dir: Path, threads: int = 4):
        so = ort.SessionOptions()
        so.intra_op_num_threads = threads
        p = ["CPUExecutionProvider"]
        self.enc = ort.InferenceSession(str(model_dir / "onnx/vision_encoder.onnx"), so, providers=p)
        self.dec = ort.InferenceSession(str(model_dir / "onnx/prompt_encoder_mask_decoder.onnx"), so, providers=p)
        self.emb = None
        self.tile_shape = None

    def set_image(self, rgb: np.ndarray) -> float:
        """rgb: HxWx3 uint8 tile. Resized (non-aspect-preserving) to 1024x1024."""
        t = time.perf_counter()
        self.tile_shape = rgb.shape[:2]
        x = cv2.resize(rgb, (1024, 1024), interpolation=cv2.INTER_LINEAR).astype(np.float32) / 255.0
        x = ((x - MEAN) / STD).transpose(2, 0, 1)[None]
        self.emb = self.enc.run(None, {"pixel_values": x})
        return time.perf_counter() - t

    def predict(self, points_xy: np.ndarray, labels: np.ndarray):
        """points in tile pixel coords; labels 1=fg 0=bg. Returns (mask HxW bool, iou_score)."""
        h, w = self.tile_shape
        pts = points_xy.astype(np.float32).copy()
        pts[:, 0] *= 1024.0 / w
        pts[:, 1] *= 1024.0 / h
        feeds = {
            "input_points": pts[None, None],
            "input_labels": labels.astype(np.int64)[None, None],
            "input_boxes": np.zeros((1, 0, 4), np.float32),
            "image_embeddings.0": self.emb[0], "image_embeddings.1": self.emb[1], "image_embeddings.2": self.emb[2],
        }
        iou, masks, _ = self.dec.run(None, feeds)
        k = int(np.argmax(iou[0, 0]))
        m = cv2.resize(masks[0, 0, k].astype(np.float32), (w, h), interpolation=cv2.INTER_LINEAR) > 0
        return m, float(iou[0, 0, k])
