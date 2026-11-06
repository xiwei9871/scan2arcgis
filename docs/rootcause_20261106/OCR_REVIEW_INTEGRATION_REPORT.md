# OCR review workflow & data-contract integration (V0.3 P2)

## Candidate volume & dedup provenance

- Raw PaddleOCR run: 219 quads (`u2_ocr_full.json`, engine paddleocr_raw_u2_full, seconds=3.5).
- Conflict-aware dedup (`dedupe_quads`): merge requires IoU>0.5 **and identical normalised text**.
  Different texts at the same spot are never merged — they stay as separate candidates with all source
  ids and rival strings recorded. Result: **157 candidates**, 71 of which carry `conflicts` annotations
  (`experiments/STITCHVECTOR/u2_full/dedup_audit.csv`).
- The earlier 148-item Studio `ocr_candidates.v1` baseline differs: Studio-side dedup + 4px input offset
  + generic geological rules. Raw run provenance is stored per quad (`engine`, `src_ids`).

## Editor schema (verified on real GPKG)

`text_labels` layer: Point geometry, all `TEXT_COLS` present, `review_status=OCR_CANDIDATE` for all 157;
`ocr_quads` layer: quad geometry + cand_id/score/src_ids/conflicts/decision/flags/ink_px/engine.
`font_px` = quad short side (E09 method) — range 5.6–36.4, no rotated-bbox giant fonts.
`angle_deg` from the quad's long edge direction.

## Review queue (real document test)

- `classify_review(0.90)`: 157 → **119 REVIEW_REQUIRED + 38 AUTO_ACCEPTED_UNVERIFIED**, 0 dropped.
- `review_queue()` returns all 119 pending items with text, score, box, status, reasons — every
  candidate is visible and decidable; `review_decide` supports batch confirm/skip (undoable).
- `review_reason` carries build-time risk flags (preserve_review quads → flagged rows), so the queue is
  groupable by reason; rows carry `box`/`x`/`y` for map location against the original raster.

## Suspect-line review (P0 closure in the same workflow)

- `line_review_queue()`: 71 items — 41 `possible_real_geology_REVIEW` (kept in `visual_lines`,
  `kind=auto_B2c_review_preserve`, baseline id in `rev-<line_id>`) + 30 `ocr_glyph_residue` rows
  (`text_residue_lines`, `src_line_id`/`src_logical_id` + restore_hint).
- Every row carries `region` (4×4 grid cell over the map), `reason`, `box`, `length` — groupable by
  region/reason/status; 16 distinct regions on U2.
- `line_review_decide(ids, keep|cleanup|restore|confirm_cleanup)`: batch keep → `auto_B2c_review_keep`
  (geometry untouched); batch cleanup → moved to `text_residue_lines` (recoverable); restore brings a
  residue row back into `visual_lines`. All undoable, one op = one undo.

## Export gate (real document test)

- Formal export of the working file is blocked twice over: 157 unresolved OCR texts **and**
  41 unresolved suspect lines (`ExportError`, explicit counts).
- Draft export succeeds, manifest declares `export_mode=draft`, `unreviewed=157`,
  `unresolved_suspect_lines=41` — nothing leaves silently.

## Studio UI chain

Verified earlier end-to-end on this working file: open → classify → queue → confirm → edit → undo →
save version (readback-verified) → reopen → draft export (confirmed/unconfirmed split) → formal export
blocked. Browser e2e suites (`e2e_studio_closeout.js`, `e2e_closeout_ui.js`) remain available for the
owner UAT run; they were green at commit a9b2aa6 against the prior baseline.
