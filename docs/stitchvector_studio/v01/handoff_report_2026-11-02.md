# StitchVector Studio V0.1 — Takeover & UAT Report (2026-11-02, Devin)

Context: previous Claude session stopped mid-E2E with Studio code **uncommitted and unpushed**.
This report covers recovery (issue #2 Phase 0), verification (Phase 1/3) and the remaining fixes (Phase 2).

## Phase 0 — recovery outcome

| Item | State |
| --- | --- |
| Local worktree `~/geomap2arcgis/.claude/worktrees/sv-studio` | FOUND, branch `feature/stitchvector-studio-v01` @ 56146bd, all Studio code untracked |
| Snapshot before changes | `~/sv-studio-rescue-20261102/sv-studio-uncommitted.tar.gz` (2.8 MB, 323 files) |
| Committed | `24c9ba3` editor text ops + review_status; `7e88243` Studio checkpoint (48 files, +2099) |
| Pushed | `origin/feature/stitchvector-studio-v01` = `7e882436f640d14c855e6fcfe36e837e47b99857` (verified via `git ls-remote`, pre-push hook passed) |
| Excluded (artifacts) | `.playwright-cli/` logs, exported zips, scans — kept local per repo policy |
| Other worktrees | only `.playwright-cli` logs pending; all other branches already on remote |

## Module status (verified live)

| Module | Status | Evidence |
| --- | --- | --- |
| contracts / stage_runner / registry | TESTED | mock + real runs pass; code-hash pinning enforced |
| projects / job manager | TESTED | create/upload/normalise/process/cancel/restart all pass |
| inputs (PNG/JPG/BMP/WebP/TIFF/multi-TIFF/GeoTIFF/PDF) | TESTED | 9 accepted, corrupt + fake-ext rejected; GeoTIFF→GEOREFERENCED EPSG:32649, page select honoured |
| b2c vectorize plugin | TESTED | 3 clean runs ~17-18s, 17047 faces / 606 lines; earlier -11 segfault NOT reproduced |
| paddleocr plugin (default) | TESTED | 33-34s, 148 drafts, PP-OCRv6_medium from local cache |
| rapidocr plugin (fallback) | TESTED | 4.88s, 219 candidates, profile selectable |
| exports GPKG / SHP / GEOJSON | TESTED | readback pass; pixel-space GeoJSON→honest `.pixel.json`; SHP needs explicit pixel confirmation |
| server + studio UI | TESTED | running; state survives restart |
| geology-aware-vnext profile | NOT_IMPLEMENTED by design | listed disabled, stages marked NOT_IMPLEMENTED |

## Fixes applied in this session

- `tools/stitchvector_editor/static/app.js`: repaint on `document.fonts` `loadingdone` (CJK/subscript
  fonts load lazily after first `fillText`; first painted frame used fallback metrics — real-user-visible).
- `tests/stitchvector_studio/e2e_studio_u2.js`: canvas-settle gate now polls until two consecutive
  identical pixel hashes (max 10 resamples) instead of a fixed 1 s guess. Honest wait, no fake green.
  Root cause of the previous "FAIL canvas settled": deterministic one-frame font-swap transient,
  not an app bug — the toggle check itself always passed.

## U2 browser E2E — 30/30 PASS (`run-20261102-081020-705cf1`, project `p-20261102-081020-dc82fe`)

create → upload u2_map.png → process (B2c 17.89s + PaddleOCR 33.86s) → 17047 faces / 606 lines /
148 OCR_DRAFT texts → text toggle hash-verified → edit OCR error "Ar2E"→"Ar₂E" (raw kept, HUMAN_EDITED)
→ move/add(J₂d)/delete text → recolour face, rewidth line → undo/redo → visual diff → save v001
(readback identical) → reload + reopen keeps edits → export+download GPKG & SHP (readback pass) →
PIXEL_SPACE shown. Full log: `experiments/STITCHVECTOR/studio_v01/e2e_u2_browser_result.json`.
Additional API-level checks: `devin_reverification_2026-11-02.json`.

## Launch

```
~/geomap2arcgis/.venv-sv/bin/python -m tools.stitchvector_studio.server \
  --workspace ~/geomap2arcgis/runs/stitchvector/studio_v01/e2e_ws_devin --port 8830
# open http://127.0.0.1:8830/
```

Envs (must exist, not in git): `.venv-sv` (server+B2c), `.venv-ocr` (RapidOCR),
`runs/ocr_poc01/venvs/paddle` + `runs/ocr_poc01/cache/paddle` (PaddleOCR models, 139 MB).

## Known open items

- B2c exit -11 (segfault) seen once last session: 3 clean runs since — NOT reproduced, not proven fixed.
- JP2 declared in sniff() but not covered by sample suite.
- geology-aware-vnext stages are declared NOT_IMPLEMENTED (out of V0.1 scope).
- OCR model caches and venvs live outside git; first-time setup on a new host needs them installed.

Status: **STUDIO_V01_READY_FOR_UAT**
