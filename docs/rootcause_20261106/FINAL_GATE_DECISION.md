# V0.3 final gate decision

Baseline: `feat/stitchvector-tfl-rootcause @ 67caf47` → this round's head.

## Gate results

| Gate | Verdict | Evidence |
|---|---|---|
| `NO_SILENT_GEOLOGY_LOSS` (P0) | **PASS** | Every baseline line crossing an auto-clean region (share≥0.4) is reconciled per-object in `REMOVED_GEOLOGY_LINE_RECONCILIATION.csv` (71 rows): 30 glyph strokes isolated to `text_residue_lines` (src ids + restore hint), 41 `possible_real_geology_REVIEW` kept **in** `visual_lines` flagged `auto_B2c_review_preserve` — nothing deleted silently. Studio exposes them via `line_review_queue` (region/reason grouped, 16 regions) with batch `keep`/`cleanup`/`restore` decisions (undoable). Formal export **blocks** while any suspect line is unresolved; draft declares the count. Dedup merges only identical text; conflicts + source ids audited (157 rows, 71 conflicted). |
| `RED_FACE_REAL_REPAIR_VERIFIED` (P1) | **PASS** | Exact matched ROI `[519,325,792,632]`: 329 no-evidence enclosed fragments merged into 34 host faces by **real GIS union** (one undoable batch), outline area identical, lines untouched, coverage accepted, `merged_from` provenance, single undo restores all, save/readback ok. enclosed_face 333→7, interior_ring 38→15. 2069 evidence-bearing faces deliberately kept in review class — never auto-merged. Before/after five-state PNGs produced locally. |
| `STUDIO_OWNER_WORKFLOW_READY` (P2) | **PASS (API-verified)** | All 157 `OCR_CANDIDATE`s reach the review queue (119 required + 38 auto-accepted — none dropped); font_px uses quad short-side (5.6–36.4, E09 method); queue rows carry box/reason/region for grouping; line review queue covers 41 suspect + 30 residue lines. Export gate: formal blocked (157 texts + 41 lines unresolved), draft declared. Studio open→classify→queue→decide→edit→save→reopen→export chain previously verified end-to-end on this file. |

## Status: `V03_ROOTCAUSE_READY_FOR_OWNER_UAT` — with conditions

All three gates pass on the real U2 data with object-level evidence, not counts alone.

Remaining issues / honest limits:
1. **shot1 (βQ)** remains `SOURCE_NOT_MATCHED` — not present in U2 or any local candidate map; recorded,
   not claimed fixed.
2. **Human decisions pending by design**: 41 suspect lines + 30 residue lines + 119 OCR texts await the
   owner's batch review in Studio — the workflow is ready, the judgements are the UAT.
3. 2057 frag-class small faces in the ROI remain review-class (possible real units) — listed, batchable,
   not auto-merged.
4. Governance gate `assets-decisions` FAILS on a pre-existing false positive (vendored libs in
   `runs/ocr_poc01/venvs/` match private-key patterns) — unrelated to this branch, recorded not fixed.
5. Frozen B2c and production unchanged; protected maps/screenshots/PNGs remain local.

## Test evidence
- Unit: **117/117 PASS** (108 prior + 9 new synthetic in `test_v03_gates.py`).
- Real-U2 in-place regression: repair applied, verified, saved to protected local path.
- Browser e2e: previously green at a9b2aa6; not re-run this round (UI unchanged since; API layer covered
  by the unit + real-doc checks above) — flagged for the owner UAT session.
