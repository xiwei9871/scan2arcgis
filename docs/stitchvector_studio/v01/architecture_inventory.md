# Studio V0.1 — architecture inventory (read-only, before development)

Base: `research/stitchvector-u2-visual-diff` @ `56146bd`. Host: Mac mini M4, 16 GB, macOS 26.6.2.

| Area | What exists | Reused how |
|---|---|---|
| B2c | `experiments/STITCHVECTOR/sv_lf.py`, `sv_b2c.py`, `sv_v3.py`, `sv_d71.py`, `sv_oracle*.py`; full-sheet entry `sv_u2_full_build.py` (multi-part line split adapter) | wrapped unchanged by plugin `stitchvector.vectorize.b2c` |
| RapidOCR | `.venv-ocr` (rapidocr 3.4.5, PP-OCRv4 mobile ONNX); editor `ocr_cli.py`; `sv_u2_full_ocr.py` | plugin `stitchvector.ocr.rapidocr` (fallback) |
| PaddleOCR | OCR POC-01 `research/stitchvector-ocr-poc01` @ `cae5a61`; venv `runs/ocr_poc01/venvs/paddle` (paddleocr 3.7.0, paddlex 3.7.2, paddlepaddle 3.3.1); weights `runs/ocr_poc01/cache/paddle` | plugin `stitchvector.ocr.paddleocr` (default); GENERIC rules copied to `geo_rules.py` |
| Editor | `tools/stitchvector_editor/{core.py, server.py, render.py, static/}` — Document model, undo/redo, atomic save, line repair, legend styles, text layer, visual diff | Studio server subclasses the editor handler; editor page reused unchanged + Studio bar |
| GPKG model | layers `colour_faces`, `visual_lines`, optional `text_labels`, `text_residue_lines`, `legend_styles`, `layer_styles` | unchanged; `text_labels` gains `review_status`, OCR provenance fields |
| Tests | `tests/stitchvector_editor/` (pytest + playwright-cli JS) | kept green; new `tests/stitchvector_studio/` |
| Python env | `.venv-sv` (geopandas 1.2, pyogrio 0.13, shapely 2.2, rasterio 1.4.4/GDAL 3.10.3, tifffile); added `pypdfium2 5.14` | PDF rendering |
| Parallel worktrees | sv-editor-*, sv-ocr-poc01, sv-u2-full, sv-u2-diff | not touched |

Known algorithm limits carried over (not fixed here): 86 % of B2c faces on U2 are ≤ 5 px²; automatic text clearing on U2 changed faces outside text boxes and may isolate real lines (FAIL in `u2_full_validation_report.md`); OCR code accuracy is far from production.
