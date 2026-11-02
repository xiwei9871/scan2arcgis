# Current pipeline vs target pipeline

## Current (implemented, `legacy-b2c-v01`)
1. Colour quantisation (`sv_lf.labels`).
2. B2c line detection on the scan **as is, text and symbols included** (`sv_b2c.b2c`, `sv_v3.group`).
3. Faces from line footprint + nearest-label fill (`sv_lf.footprint`, `sv_d71.fill`, `sv_oracle.faces`).
4. OCR (PaddleOCR by default) runs independently; candidates become editable `OCR_DRAFT` text objects with `geometry_status = BACKGROUND_NOT_CLEARED`. Faces and lines are **not** changed by OCR.
5. Visual diff renders faces + lines only, labelled “线面渲染残差”.

Known facts kept: B2c text glyphs remain in the face/line layers; automatic U2 text clearing failed face protection and is not part of any profile; legend use is colour/style mapping in the editor, no automatic legend correction.

## Target (`geology-aware-vnext`, interface only)
Legend pre-parse → OCR detection + protection mask → line detection reading the mask → legend-aware face reconstruction → legend + residual audit → human review → export. Every stage after OCR is `NOT_IMPLEMENTED` in V0.1; see `geology_aware_vnext_plan.md`.

The UI shows the vnext profile disabled with “（未实现，不可运行）”; the server refuses to start it.
