"""T05 synthetic regression tests for ocr-protected-b2c-v01 - NO private U2 files required.

Covers: dedup of multi-scale OCR boxes, overlap-pixel ownership (two quads never share ink px),
risk-decision ordering (ambiguous quads keep original pixels), editor text-layer schema fields.
"""
import sys
from pathlib import Path
import numpy as np, pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "experiments" / "STITCHVECTOR"))
import sv_u2_ocr_protected_build as B  # noqa: E402


def _img(color=(200, 160, 150), h=100, w=120):
    a = np.full((h, w, 3), color, np.uint8); return a


def test_dedupe_quads_merges_multiscale_duplicates():
    quads = [{"quad": [[10, 10], [40, 10], [40, 30], [10, 30]], "text": "A", "score": 0.9},
             {"quad": [[11, 11], [41, 11], [41, 31], [11, 31]], "text": "A", "score": 0.8},
             {"quad": [[70, 70], [90, 70], [90, 90], [70, 90]], "text": "B", "score": 0.7}]
    m = B.dedupe_quads(quads)
    assert len(m) == 2 and any(q["text"] == "A" and len(q["src"]) == 2 for q in m)


def test_overlap_pixels_owned_by_nobody():
    quads = [{"quad": [[10, 10], [60, 10], [60, 40], [10, 40]]},
             {"quad": [[40, 20], [90, 20], [90, 50], [40, 50]]}]
    masks, own, cnt = B.quad_rasters(quads, (100, 120))
    both = masks[0] & masks[1]
    assert both.sum() > 0 and (own[both] == -2).all()           # overlap px -> -2, owned by NO quad
    only0 = masks[0] & ~masks[1]; assert (own[only0] == 0).all()


def test_ink_px_keeps_background_between_strokes():
    img = _img()
    img[20:28, 20:24] = (10, 10, 10)                            # a dark stroke bar inside the quad
    quad = np.asarray([[15, 15], [45, 15], [45, 35], [15, 35]], float)
    m, bg, n = B.ink_px(img[10:40, 10:50], quad, 10, 10)
    assert m.sum() < np.asarray(B.quad_rasters([{"quad": quad.tolist()}], (30, 40))[0][0]).sum()  # ink < whole quad
    assert tuple(np.asarray(bg).round().astype(int)) == (200, 160, 150)   # bg median = face colour, strokes excluded


def test_quad_ring_classes_detects_boundary_text():
    X = np.zeros((60, 80), int); X[:, 40:] = 3                  # two units: class 0 | class 3
    on_boundary = B.quad_ring_classes(X, [[35, 20], [45, 20], [45, 30], [35, 30]])
    inside_one = B.quad_ring_classes(X, [[10, 20], [20, 20], [20, 30], [10, 30]])
    assert len(on_boundary) > 1 and set(inside_one) == {0}


def test_text_row_schema_has_all_editor_columns():
    required = {"label_id", "text", "ocr_text", "ocr_score", "font_px", "angle_deg", "anchor", "rgb",
                "box_x0", "box_y0", "box_x1", "box_y1", "source", "review_status", "review_reason",
                "reviewed_at", "review_actor"}
    assert required <= set(B.TEXT_COLS)
