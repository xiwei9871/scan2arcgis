# Pipeline ↔ plugin contract

See `plugin_contract.md` for the plugin side. This page covers how profiles bind stages to plugins.

Profile file `tools/stitchvector_studio/profiles/<id>.json`:
```json
{"profile_id": "...", "kind": "CURRENT_BASELINE | TARGET_NOT_RUNNABLE | TEST",
 "stages": [{"stage": "vectorize", "plugin": "stitchvector.vectorize.b2c"},
            {"stage": "ocr", "plugin": "stitchvector.ocr.paddleocr", "optional": true},
            {"stage": "legend", "plugin": "...", "status": "NOT_IMPLEMENTED", "needs": [...]}],
 "options": {"auto_text_clear": false, "create_text_drafts": true}}
```
Rules:
- A stage marked `NOT_IMPLEMENTED` makes the profile not runnable; the UI lists it disabled and the server refuses it.
- An `optional` stage that fails is recorded `FAILED` and the job continues (OCR failure keeps the vector result).
- `auto_text_clear` is `false` in every profile; no profile runs automatic text clearing.
- Swapping an algorithm = editing a profile line or adding a profile. No UI or orchestrator change.

Data passed between stages: `raster` (raster_document.v1) → `vectors` (vector_layers.v1), `ocr` (ocr_candidates.v1); builtin quality writes a `quality_report.v1` summary into the manifest.
