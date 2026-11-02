# Pipelines and jobs

| Profile | Kind | Stages | Runnable |
|---|---|---|---|
| `legacy-b2c-v01` (default) | CURRENT_BASELINE | input → B2c → PaddleOCR (optional) → quality | yes |
| `legacy-b2c-v01-rapidocr` | CURRENT_BASELINE | input → B2c → RapidOCR (optional) → quality | yes |
| `mock-swap-test` | TEST | input → mock vectoriser → mock OCR → quality | yes |
| `geology-aware-vnext` | TARGET_NOT_RUNNABLE | legend → OCR+protect → protected lines → legend-aware faces → legend/residual audit | no (5 stages NOT_IMPLEMENTED) |

Job states: `QUEUED → RUNNING → COMPLETED | FAILED | CANCELLED`; each stage also records `QUEUED/RUNNING/COMPLETED/FAILED/SKIPPED/NOT_RUN/CANCELLED` and seconds. No percentage is shown; only the current stage. Cancel terminates the stage subprocess. A timeout per stage comes from the manifest.

Reproducibility record (`runs/<run_id>/manifest.json`): source sha256, document id (page, dpi), raster sha256, profile, every stage's plugin id/version/code hash/interpreter/params, Studio git commit, timings, output artifacts with sha256, quality summary. Run ID format `run-YYYYmmdd-HHMMSS-xxxxxx`.

After a completed run the user's working copy is created from it ("adopt"): B2c vectors are copied to `working/current.gpkg`, and OCR candidates become `OCR_DRAFT` text objects. Adopt is refused while the working copy has edits not yet saved as a version, so re-processing never overwrites human edits.
