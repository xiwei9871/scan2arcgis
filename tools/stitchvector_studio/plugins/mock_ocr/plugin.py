"""Mock OCR for hot-swap tests: one fixed candidate per image quarter. NOT a real OCR."""
import json
from tools.stitchvector_studio.contracts import StageResult, artifact, write_json_atomic, OK


class Plugin:
    def validate_inputs(self, inputs, params):
        if inputs.get("raster", {}).get("schema") != "raster_document.v1": raise ValueError("mock needs raster_document.v1")

    def run(self, ctx, inputs, params):
        doc = json.load(open(inputs["raster"]["path"], encoding="utf-8")); W, H = doc["width"], doc["height"]; items = []
        for i, (x, y) in enumerate([(W / 4, H / 4), (3 * W / 4, H / 4), (W / 4, 3 * H / 4), (3 * W / 4, 3 * H / 4)]):
            items.append({"id": f"M{i}", "scale": 1, "quad": [[x - 10, y - 5], [x + 10, y - 5], [x + 10, y + 5], [x - 10, y + 5]], "text": params["text"],
                          "score": 0.5, "status": "OCR_CANDIDATE"})
        out = ctx.workdir / "ocr_candidates.json"; write_json_atomic(out, {"schema": "ocr_candidates.v1", "engine": "mock", "items": items})
        return StageResult(OK, outputs={"ocr": artifact(out, "ocr_candidates.v1")}, stats={"candidates": len(items)}, warnings=["mock OCR: test data"])
