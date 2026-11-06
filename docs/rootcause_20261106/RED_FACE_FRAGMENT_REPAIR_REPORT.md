# Red-face internal-fragment repair — real-U2 report (V0.3 P1)

- Source: `u2_map.png` (sha256 `05cdada4…64c7`), ROI `[519,325,792,632]` — the exact region matched to the
  user's red-face screenshot (match conf 0.78, 108 ORB inliers).
- Input: `u2_full_ocr_protected.gpkg` (OCR-protected build); output kept local
  (`runs/stitchvector/u2_full/u2_full_ocr_protected_redfix.gpkg`) — protected data never pushed.
- Tool: `tools/stitchvector_editor/red_face_repair.py` (seed/host-driven, triage → confirmed batch → real GIS union).

## What the scan found

`internal_fragment_scan()` on the ROI:

| class | count | handling |
|---|---|---|
| batch_safe | 329 | enclosed inside one host, no label, no drawn-line evidence, ≤120px², not elongated → batch mergeable after confirmation |
| review | 2069 | frag kind (touches ≥2 faces) or enclosed with label/line/elongated evidence → **never auto-merged** |
| keep | 0 | — |

`auto_merge == 0` from the generic scan is NOT proof nothing is repairable: same-colour evidence is absent
in B2c-style output (labels are colour-class ids), so this tool uses the **structural** criterion — a face
fully enclosed inside one host cannot change the outline when unioned, which is provably outline-safe.
Colour is no longer the gate; geological evidence (label/line/elongation/size) remains the gate for review.

## Real geometric merge — verified

`apply_safe()` performs **one undoable batch op** (`Document._do`): each host + its enclosed fragments is
unioned separately inside the single op — hosts are never unioned with each other.

- 329 fragments → 34 host groups merged; `merged_from` provenance on every host face.
- `coverage_report` accepted after merge; ROI outline area identical (627 900 px² before/after).
- `visual_lines` untouched (590 map-wide, 120 in ROI before/after).
- Interior rings 38 → 15, enclosed faces 333 → 7 (audit recount, ROI scope).
- ONE `undo_op()` restores all 329 merges (single undo record — one confirmation = one undo).
- save/readback accepted; Heterochromatic candidates merge only via this explicit confirmed path.

## Before/after evidence (local, not pushed)

`runs/stitchvector/u2_full/rootcause/v03_redfix_{before,after}/` — five-state PNGs
(A raster, B pure faces, C pure lines, D pure text, E overlay) at ROI ×4.
Metrics: `RED_FACE_BEFORE_AFTER_METRICS.csv`.

## Honest limits

- 2 057 small `frag` faces and 7 enclosed faces remain — deliberately kept for human review
  (possible real small geological units / boundary evidence). They are listed in the scan output,
  batch-excludable/confirmable, not per-face clicks.
- Repair changes geometry only; no layer is hidden, no fill-over, no transparency tricks.
