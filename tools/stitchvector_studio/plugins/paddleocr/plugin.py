"""PaddleOCR 3.7.0 (PP-OCRv6_medium det+rec, textline orientation) adapter, runs in the POC paddle venv.
Same call as experiments/STITCHVECTOR/ocr_poc01/adapters/paddleocr_adapter.py (e2e mode). Model weights are read from the
local POC cache (PADDLE_PDX_CACHE_HOME); nothing is downloaded or committed. Output: OCR candidates with raw text,
score, polygon, and GENERIC geological rule suggestions (status OCR_CANDIDATE, nothing confirmed)."""
import json, os
from pathlib import Path
from tools.stitchvector_studio.contracts import StageResult, artifact, write_json_atomic, OK
from tools.stitchvector_studio import geo_rules as G

CACHE = Path.home() / "geomap2arcgis/runs/ocr_poc01/cache/paddle"


def _iou(a, b):
    ax0, ay0, ax1, ay1 = a; bx0, by0, bx1, by1 = b
    iw, ih = max(0, min(ax1, bx1) - max(ax0, bx0)), max(0, min(ay1, by1) - max(ay0, by0)); i = iw * ih
    u = (ax1 - ax0) * (ay1 - ay0) + (bx1 - bx0) * (by1 - by0) - i
    return i / u if u > 0 else 0.0


class Plugin:
    def validate_inputs(self, inputs, params):
        if inputs.get("raster", {}).get("schema") != "raster_document.v1": raise ValueError("paddleocr needs a raster_document.v1 input")
        if not CACHE.is_dir(): raise ValueError(f"PaddleOCR model cache not found: {CACHE}")

    def run(self, ctx, inputs, params):
        os.environ.setdefault("PADDLE_PDX_CACHE_HOME", str(CACHE)); os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
        import numpy as np, paddleocr
        from PIL import Image
        from paddleocr import PaddleOCR
        doc = json.load(open(inputs["raster"]["path"], encoding="utf-8")); im = Image.open(doc["raster_artifact"]).convert("RGB")
        ocr = PaddleOCR(lang="ch", use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=True, device="cpu")
        raw = []
        for k in params["scales"]:
            a = np.asarray(im if k == 1 else im.resize((im.width * k, im.height * k), Image.LANCZOS))[:, :, ::-1].copy()
            d = ocr.predict(a)[0]
            for p, s, c in zip(d["rec_polys"], d["rec_texts"], d["rec_scores"]):
                if not str(s).strip() or float(c) < params["min_score"]: continue
                q = (np.asarray(p, float) / k).round(1).tolist(); xs = [x for x, _ in q]; ys = [y for _, y in q]
                raw.append({"scale": k, "quad": q, "bbox": [min(xs), min(ys), max(xs), max(ys)], "text": str(s), "score": round(float(c), 3)})
            ctx.log(f"scale {k}: {len(d['rec_texts'])} detections")
        keep = []
        for r in sorted(raw, key=lambda r: -r["score"]):
            if params["deduplicate"] and any(_iou(r["bbox"], q["bbox"]) > 0.5 for q in keep): continue
            keep.append(r)
        items = []
        for i, r in enumerate(sorted(keep, key=lambda r: (r["bbox"][1], r["bbox"][0]))):
            sug, cands, why = G.suggest(r["text"]) if params["geological_generic_rules"] else (r["text"], [r["text"]], [])
            items.append({"id": f"O{i}", "scale": r["scale"], "quad": r["quad"], "text": r["text"], "score": r["score"], "status": "OCR_CANDIDATE",
                          "suggested_text": sug, "candidate_texts": cands, "rule_reasons": why})
        out = ctx.workdir / "ocr_candidates.json"
        write_json_atomic(out, {"schema": "ocr_candidates.v1", "engine": f"paddleocr {paddleocr.__version__}", "model": "PP-OCRv6_medium_det+PP-OCRv6_medium_rec+PP-LCNet_x1_0_textline_ori",
                                "rules": G.RULES_VERSION if params["geological_generic_rules"] else None, "items": items})
        return StageResult(OK, outputs={"ocr": artifact(out, "ocr_candidates.v1")},
                           stats={"candidates": len(items), "raw_detections": len(raw), "rule_changed": sum(1 for x in items if x["rule_reasons"])},
                           provenance={"engine": f"paddleocr {paddleocr.__version__}", "model_cache": str(CACHE), "scales": params["scales"], "rules": G.RULES_VERSION})
