# StitchVector Editor: line repair + line roles + Legend + dual view (local closed loop)

Branch `feature/stitchvector-editor-line-repair`, cut from `feature/stitchvector-editor-poc1 @ 79619c5`.
Status: `STITCHVECTOR_EDITOR_LINE_REPAIR_LEGEND_READY_FOR_UAT`. B2c / M2 / historical results unchanged.

## 1. Reliability fixes

| Requirement | Implementation | Test |
|---|---|---|
| Atomic save | `save_as` writes `.<name>.<rand>.tmp.gpkg` in the target folder, closes it, re-reads and validates; only an accepted file is renamed (`os.replace`) to the requested path | `test_failed_save_leaves_nothing_and_stays_dirty`: forced validation failure leaves no file at the target and no temp file; document stays dirty |
| Failure leaves nothing | on any exception the temp file and its `-wal`/`-shm` are removed, `dirty` is not cleared | same test |
| Server-side previews | `heal_preview` and `split_face_preview` store the plan under a preview id bound to the document version; `heal_apply` / `split_face_apply` accept only that id (plus, for heal, ids of *uncertain* candidates the user explicitly accepts) | browser: a client-made plan without preview id is refused |
| Previews expire | every edit, undo and redo bumps `version` and clears all stored previews | `test_stale_preview_rejected_after_edit_undo_redo` |
| Re-check on apply | heal re-checks that candidate and target still exist and still share an edge; result must be one polygon and pass the strict coverage check | `test_heal_rechecks_adjacency` |
| Non-adjacent merge refused | unchanged rule, now with a negative test | `test_non_adjacent_merge_refused` |
| Concurrency | one `threading.Lock` around every request that reads or changes the document (state, edits, save) | code review only |

## 2. Line roles

`visual_lines.line_role` ∈ `COVER`, `SPLIT`, `UNKNOWN`. Every existing line and every newly drawn line starts as `UNKNOWN`; nothing infers a role.

* COVER: the heal brush may propose merging faces that lie ≥ 50% under the line.
* SPLIT: the only role that can cut faces (`split_face_preview` / `split_face_apply`); the cut is snapped to the pixel grid, shared vertices are inserted, and the whole face layer must pass the strict coverage check.
* UNKNOWN (and SPLIT, for the heal brush): faces under the line are always `uncertain`, never proposed for merge.

## 3. Legend (style only, never geometry)

* New non-spatial GPKG table `legend_styles` (legend_id, kind, name, rgb, width, line_type, dash, tooth_spacing, tooth_size, tooth_side) and a `legend_id` column on faces and lines.
* Line types: solid, dash (`"6,4"`), teeth (spacing, size, side left/right); faces: fill colour.
* Starter library of 5 entries (`L_SOLID_BLACK`, `L_DASH_RED`, `L_TEETH_RED`, `F_PINK`, `F_GREEN`); it is a placeholder, not a recognised map legend. Styles can be edited in the UI and are saved per file.
* Dash and teeth are computed for display from the centre line every time; they are not stored as geometry. Applying or editing a style changes only `legend_id`, `rgb` and `width_px`.

## 4. Dual view

Left pane: the original scan, read-only. Right pane: the vector result, editable. One shared view transform: wheel zoom and drag pan in either pane move both; a cross-hair shows the cursor position in both. Toggle with the "左右对照" checkbox.

## 5. Acceptance on u2 (copies of `u2_B2c.gpkg`; input SHA-256 unchanged)

Line roles in these cases are **test assumptions**; the geology of these u2 lines has not been verified.

### 5.1 COVER case: Oracle trace F3, missing 21.6 px

`DATA_LEVEL_VERIFIED` (`experiments/STITCHVECTOR/sv_line_repair_uat.py`)

| Item | Before | After |
|---|---|---|
| F3 axis covered by a line (2 px) | 0.812, one 22 px gap | 1.000, no gap |
| Faces ≤ 5 px² within 3 px of the redrawn piece | 7 | 3 |
| Heal preview | — | merge 4, keep 0, uncertain 3 (uncertain left untouched) |
| Objects changed outside the working zone | — | 0 |
| Legend `L_TEETH_RED` applied, then spacing 10→8, side left→right | — | centre line unchanged; 6 teeth rendered |
| Save → reopen | — | accepted, read-back equal, style and roles reproduced (6 teeth, spacing 8, size 4, side right) |

Operations: draw 1, select group 1, set role 1, heal preview 1, heal apply 1, apply legend 1, edit style 1, save 1.

### 5.2 SPLIT case: Oracle trace C (red line inside the green unit)

| Item | Result |
|---|---|
| Faces touched by the drawn line | 22 |
| Faces cut | 4, into 9 pieces; face count 665 → 670 |
| Strict coverage after the cut | valid, area sum = window, no holes |
| Drawn line lying on a face boundary afterwards | 0.93 |
| C axis covered by a line | 1.00 |
| Objects changed outside the working zone | 0 |
| Save → reopen | accepted, read-back equal, roles `SPLIT` / `UNKNOWN` reproduced |

Operations: draw 1, set role 1, split preview 1, split apply 1, apply legend 1, save 1.

### 5.3 Negative cases

* Heal preview, then an edit → apply refused ("unknown or expired preview").
* Heal preview, then undo → apply refused.
* Split on an `UNKNOWN` line → refused ("only a line marked SPLIT can cut faces").
* Faces under an `UNKNOWN` line in a heal preview: 2 candidates, 0 proposed for merge.

### 5.4 Browser end-to-end

`tests/stitchvector_editor/e2e_line_repair.js` drives the real UI with Playwright (mouse clicks, wheel, drags): **30 / 30 checks pass** (`UI_INTERACTION_VERIFIED`, scripted). It covers: dual view sync (zoom and pan from the left pane, left pane makes no edit, cross-hair), drawing a line, default `UNKNOWN`, UNKNOWN never proposes merges, role → COVER, heal preview and apply, reuse of an applied preview refused, client-made plan refused, teeth legend, spacing 10 → 5 doubles the teeth, side flip, centre line unchanged after legend and style edits, split refused on UNKNOWN, role → SPLIT, split preview 4 faces → 11 pieces, split apply, undo/redo of a legend, face legend on a split piece, save with read-back, dirty cleared.

Recorded browser operations: draw tool 2, draw line 2, heal tool 2, brush stroke 2, pick-line tool 1, set role 2, heal apply 1, apply legend 3, edit style 1, split preview 1, split apply 1, save 1. These are operation counts, not human working time.

## 6. What is not verified

* **Geological correctness is not measured here.** u2 has no face truth, so no boundary-overflow area is reported for these cases. The 275 px² (synthetic 7001, lasso merge) and 69 px² (u2 PN2, line-to-face) from earlier rounds are different scenarios and are not compared with anything here.
* Topological validity is verified; whether the cut follows the real contact is judged only visually in the dual view.
* Human operating time: not measured; needs your own run.
* QGIS: not verified (pixel coordinates, no CRS). `legend_styles` is a plain table; QGIS will not render dash/teeth from it.
* The starter legend library is a placeholder. Teeth are display-only and not exported as geometry.

## 7. Files

* Code: `tools/stitchvector_editor/core.py`, `server.py`, `static/index.html`, `static/app.js`
* Tests: `tests/stitchvector_editor/test_line_repair.py` (7 new), `e2e_line_repair.js`
* Scenarios: `experiments/STITCHVECTOR/sv_line_repair_uat.py`; results `experiments/STITCHVECTOR/line_repair/lr_result.json`, `lr_ui_e2e_result.json`
* Binary artefacts (local only, pre-push hook not bypassed): `runs/stitchvector/editor_lr/`, screenshots in `/tmp/lr_e2e/`; SHA-256 in `experiments/STITCHVECTOR/line_repair/artifacts_sha256.txt`
* User guide: `docs/research/stitchvector/editor_line_repair_guide.md`
