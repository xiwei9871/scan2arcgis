# StitchVector Editor: text layer and text-residue clean-up (u2, three boxes)

Branch `feature/stitchvector-editor-text-layer` (from `feature/stitchvector-editor-line-repair @ bcb4802`).
Input: copy of `u2_B2c.gpkg` (SHA-256 unchanged). B2c, M2 and history untouched. No new OCR model.

## What was built
- **Text box tool** (`框文字`): the user drags a box; the server proposes a plan (preview id bound to the document version):
  - residue faces = faces with area <= 60 px² and >= 50 % of their area inside the box;
  - residue groups that touch exactly one ground face are proposed to merge into it;
  - groups touching two or more ground faces (the box may sit on a contact) or none are **uncertain** and left alone,
    unless the user assigns a target; the target must be one of that group's ground faces (otherwise refused);
  - lines with >= 90 % of their length inside the box move to `text_residue_lines` (restorable, not deleted);
    lines crossing the box edge are kept as geology.
- **OCR candidate**: RapidOCR (R3 tooling) run in `.venv-ocr` as a separate process (`tools/stitchvector_editor/ocr_cli.py`).
  The candidate only pre-fills the text field; the user confirms or edits it.
- **`text_labels` point layer** in the GPKG: `text, ocr_text, ocr_score, font_px, angle_deg, anchor, rgb, box_x0..y1, source`.
  Edit (text, size, angle, colour, position), delete, undo/redo.
- **QGIS label style** written to `layer_styles` (one row for `text_labels`) so QGIS can show the labels on open.
  Not checked in QGIS (not installed).
- Text layer toggle in the UI; the left original pane is unchanged.

## Results (DATA_LEVEL_VERIFIED, `sv_text_layer_uat.py`, `text_layer/text_result.json`)

| Box | OCR candidate (score) | Residue before (faces / lines) | After | Note |
|---|---|---|---|---|
| Є-O `(3,25)-(35,42)` | `C-0` (0.73) | 40 / 2 | 0 / 0 | Є read as C, as expected; text confirmed by user |
| Ar₂E `(0,196)-(52,225)` | `ArE` (0.84) | 81 / 3 | 0 / 0 | subscript 2 dropped; 16 faces in 8 groups were uncertain (touch pink face 7 and red face 457); cleared only after the user assigned each group |
| 云 `(24,59)-(41,76)` | `云` (1.00) | 10 / 2 | 0 / 0 | OCR correct |

- Faces 665 -> 534, lines 35 -> 28 (7 moved to `text_residue_lines`), 3 text objects.
- Objects changed whose original geometry does not touch any box: **0 faces, 0 lines**.
- Face layer passes the strict coverage check; save: readback equal, text equal, input SHA-256 unchanged.
- Reopened file: texts `Є-O, Ar₂E, 云`, font 13.6 / 23.2 / 13.6 px, 7 residue lines, 1 `layer_styles` row.
- Negative checks: wrong target for an uncertain group refused; stale text preview refused after edit / undo / redo.

Without the user's assignment, Ar₂E keeps 16 small faces: the box touches two ground faces, so the rule does not merge
on its own. This is the intended behaviour for a box that may sit on a contact.

## Browser (UI_INTERACTION_VERIFIED, script-driven, `tests/stitchvector_editor/e2e_text_layer.js`)
17/17 checks: box drag -> preview with OCR candidate pre-filled -> user text -> apply (Є-O, 云), no residue left,
stale preview refused after undo/redo, text layer on shows 2 labels / off shows 0, edit font 13.6 -> 16 with undo/redo,
save with readback. Ar₂E with group assignment was checked at data level only.

Unit tests: 56 passed (editor + stitchvector).

## Not done / limits
- Text position is the box centre and size is 0.8 × box height; no rotation detection.
- Uncertain-group assignment in the UI is a text field (`组号:面号`), not a click.
- The underlying pink face is continuous after the merge, but the face colour itself was not re-checked.
- QGIS display of labels not verified.
- Only three boxes in one 300×300 window; no automatic text detection.
- Operation time not measured; only operation counts.
