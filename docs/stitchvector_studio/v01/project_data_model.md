# Project data model

```
<workspace>/projects/<project_id>/
  project.json            name, source, document, runs[], versions[], current_version, working_from, working_dirty, coordinate_mode
  original/<file>         upload, read-only (0444)
  normalized/doc-p<page>-d<dpi>/raster.png + raster_document.json
  runs/<run_id>/manifest.json, <stage>/{request.json, result.json, stage.log, plugin.log, outputs}
  working/current.gpkg    editable copy; working/ocr_candidates.json
  versions/vNNN.gpkg (+ .edits.json)  saved snapshots
  exports/e-<id>/<file> + <file>.manifest.json
  audit/edits.jsonl       one line per saved version: the edit log of that session
```
Version kinds: original input (sha in `source`), algorithm runs (`runs/`), human versions (`versions/`), exports (`exports/`). Nothing in `original/`, `runs/` or `versions/` is rewritten.

Save: `Document.save_as` writes a temp GPKG, re-reads and validates it (faces strict coverage, read-back equals memory, input unchanged), then renames; on failure nothing is left and the editor stays dirty. The working copy is replaced with `os.replace` after the version is written. Opening a version checks its sha256 first.

## text_labels (per text object)
`label_id, text (editable), ocr_text (raw OCR, never overwritten), ocr_score, candidate_texts (JSON), rule_reasons (JSON), font_px, angle_deg, anchor, rgb, box_x0..y1, source, review_status, geometry_status, ocr_engine, ocr_model, ocr_candidate_id, run_id`.

`review_status`: `OCR_DRAFT` (from OCR, shown, not confirmed) → `HUMAN_EDITED` (text changed by a person) / `OCR_CONFIRMED`; `TEXT_VECTOR_CREATED` for the text-box tool. `geometry_status = BACKGROUND_NOT_CLEARED` means the glyph is still in the faces/lines.
