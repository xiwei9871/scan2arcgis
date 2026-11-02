"""RapidOCR (PP-OCRv4 ONNX, Apache-2.0) adapter. Runs in its own venv. Output = candidates only (status OCR_CANDIDATE):
nothing is confirmed, nothing in the vector layers is touched."""
import json
from tools.stitchvector_studio.contracts import StageResult, artifact, write_json_atomic, OK


class Plugin:
    def validate_inputs(self, inputs, params):
        if inputs.get("raster", {}).get("schema") != "raster_document.v1": raise ValueError("rapidocr needs a raster_document.v1 input")

    def run(self, ctx, inputs, params):
        import numpy as np, rapidocr
        from PIL import Image
        from rapidocr import RapidOCR
        doc = json.load(open(inputs["raster"]["path"], encoding="utf-8")); im = Image.open(doc["raster_artifact"]).convert("RGB")
        eng = RapidOCR(); items = []
        for k in params["scales"]:
            a = np.asarray(im.resize((im.width * k, im.height * k), Image.LANCZOS)); r = eng(a)
            for b, s, c in zip(r.boxes if r.boxes is not None else [], r.txts or [], r.scores or []):
                if float(c) < params["min_score"]: continue
                items.append({"id": f"O{len(items)}", "scale": k, "quad": (np.asarray(b) / k).round(1).tolist(), "text": s, "score": round(float(c), 3), "status": "OCR_CANDIDATE"})
        out = ctx.workdir / "ocr_candidates.json"
        write_json_atomic(out, {"schema": "ocr_candidates.v1", "engine": f"rapidocr {rapidocr.__version__ if hasattr(rapidocr, '__version__') else ''}".strip(), "items": items})
        return StageResult(OK, outputs={"ocr": artifact(out, "ocr_candidates.v1")}, stats={"candidates": len(items)},
                           provenance={"model": "PP-OCRv4 det/rec (bundled ONNX)", "scales": params["scales"]})
