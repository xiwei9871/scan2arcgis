# StitchVector U2 — text-layer check and full-sheet visual residual V0.1

Status: `U2_VISUAL_DIFF_READY` (not merged, not deployed). Base: `research/stitchvector-u2-full-validation @ 988699e`.

## A. Why the text-layer switch showed no change on `u2_full_B2c.gpkg`

| File | `text_labels` objects | Notes |
|---|---|---|
| `u2_full_B2c.gpkg` | **0** (layer absent) | Only `colour_faces` + `visual_lines`. Glyph shapes are ordinary faces/lines (B2c text residue), not a text layer. |
| `u2_full_text_cleared.gpkg` | 126 | Created by the automatic audit run (`sv_u2_full_audit.py`) from OCR strings; `ocr_text` is empty for all 126, so whether a human confirmed any of them is unknown. Treat as unconfirmed. |
| `u2_ocr_full.json` | 219 raw OCR items → 127 boxes after de-duplication | Candidates only; the editor never turns them into objects. |

Cause: the text switch only draws `text_labels`. `u2_full_B2c.gpkg` has none, so toggling it cannot change anything. The text visible on screen in that file is B2c residue (faces/lines), which the switch does not control. The front-end switch itself works (verified on the cleared file: canvas changes when toggled).

UI change: the header now shows `OCR 候选 N ｜ 独立文字对象 N ｜ 无 OCR 记录 N ｜ 与 OCR 相同 N ｜ 改过 OCR N（人工确认未记录）` (needs `--ocr-json`). Human confirmation is not stored in the data, so none of these counts proves it.

No OCR model change, no automatic clearing of text crossing lines.

## B. Deterministic re-render on the scan's pixel grid

Renderer: `tools/stitchvector_editor/render.py`.
- Output size = scan size (805×780); pixel (c, r) covers [c, c+1)×[r, r+1) in GPKG coordinates. No resampling, registration or warping; no browser screenshots.
- Order: `colour_faces` (pixel-centre rule) → `visual_lines` by `draw_order` (centre path buffered by max(width/2, 0.71)). `text_residue_lines` are never drawn; text glyphs are not rasterised (font dependent).
- Colours = stored `rgb`. No anti-aliasing.
- Residual = per-channel |a−b| (uint8, H×W×3), raw arrays saved as `.npy`; heat-map PNGs are views (0 white → 255 dark red, linear, no threshold).

Outputs (local only, pre-push blocks binaries), `/Users/xiwei/geomap2arcgis/runs/stitchvector/u2_full/visual_diff/`:

| File | SHA-256 |
|---|---|
| `u2_render_B2c.png` | `41c69eeab32c20fd804221938bf57b596b25a853def1f5aacef423286dd71e06` |
| `u2_render_cleared.png` | `8dc04b80778057ad07de38fecb4ebdc645e0305006662be2acba5a8579a4e68e` |
| `u2_residual_full.png` (scan vs B2c) | `314477e40661745d8f69287bb9762792e93e83268c10b93f891e4b8f0ffcf19a` |
| `u2_residual_no_text.png` (same, text boxes greyed) | `d165e160f9f01a2a7851735e95a3f4f35ed9bdf2b658c1e1d88859bf8f7f506e` |
| `u2_residual_before_after.png` (B2c vs cleared) | `b23d7a263075c1439aa7e759488fee8f3d57272811858aa6efceae0564ee8f13` |
| `residual_*_rgb.npy` | raw residuals; hashes in `u2_visual_diff_metrics.json` |

## C. Interactive residual view (editor "差异" mode)

Modes: off · left scan / right vector render · left scan / right residual heat map · left original B2c (`--compare`) / right current document. Threshold and opacity sliders change display only. Both panes share one view transform (zoom/pan sync). Clicking a pixel reports its raw residual value and selects the face/line there. Residuals are computed on the server from the in-memory document, so they follow edits.

## D. Checks

| # | Check | Result |
|---|---|---|
| 1 | scan vs itself | max 0 — PASS |
| 2 | same GPKG rendered twice | byte-identical — PASS |
| 3 | delete one line (u2 line 1, 535.8 px) | 762 px changed, all within 3 px of the line — PASS |
| 4 | recolour one face (9735, 521 px²) | 521 px changed, all inside that face — PASS |
| 5 | U2 full residual produced | yes, 5 PNG + 3 `.npy` — PASS |
| 6 | inputs unchanged (scan, B2c, cleared GPKG) | SHA-256 equal before/after — PASS |
| 7 | uncovered pixels in render | 0 / 0 — PASS |
| — | unit tests (`test_render_diff.py` + editor) | 33 passed |
| — | browser (`e2e_visual_diff.js`) | 10/10 |

## Full-sheet numbers (627,900 px; text mask = 126 boxes +1 px = 84,323 px)

| Comparison | mean | p50 | p90 | p99 | ≥10 | ≥30 | ≥60 |
|---|---|---|---|---|---|---|---|
| scan vs B2c, whole sheet | 23.2 | 15 | 50 | 110 | 56.6% | 37.6% | 6.8% |
| scan vs B2c, outside text | 21.8 | 12 | 48 | 101 | 53.4% | 36.2% | 6.1% |
| scan vs B2c, inside text | 31.9 | 27 | 63 | 152 | 76.9% | 46.3% | 11.3% |
| scan vs cleared, inside text | 41.3 | 31 | 95 | 215 | 77.6% | 51.5% | 18.9% |
| scan vs cleared, outside text | 21.8 | 12 | 48 | 101 | 53.4% | 36.2% | 6.2% |

B2c vs cleared: 12,758 px differ (2.03%); 12,736 inside text boxes, **22 outside**.

## Interpretation (what this does and does not show)

- The residual measures appearance, not geology. Text, legend symbols, fault teeth, hatching, colour quantisation and scan noise all appear in it. Nothing here is a confirmed geological error.
- About half the sheet differs by ≥10 levels even outside text. Most of this is expected: B2c paints each face one flat class colour while the scan has screening, anti-aliasing and paper tone. The ≥60 band (6.1% outside text) is the part worth inspecting; use the heat-map view with threshold 60 to browse it.
- Inside text boxes the scan residual goes **up** after clearing (mean 31.9 → 41.3). Expected: the glyph ink is no longer copied into faces/lines and glyph text is not rasterised. This is the intended outcome, not damage.
- The 22 changed pixels outside text boxes match the earlier finding (16 merged residue faces stick out of their box). They stay `PENDING_REVIEW`.
- The cleared GPKG used unconfirmed OCR strings; it is an experiment, not an acceptance sample.

## Reproduce

```bash
cd ~/geomap2arcgis/.claude/worktrees/sv-u2-diff
~/geomap2arcgis/.venv-sv/bin/python experiments/STITCHVECTOR/sv_u2_visual_diff.py
~/geomap2arcgis/.venv-sv/bin/python -m tools.stitchvector_editor.server \
  --image ~/geomap2arcgis/runs/stitchvector/u2_full/u2_map.png \
  --gpkg ~/geomap2arcgis/runs/stitchvector/u2_full/u2_full_text_cleared.gpkg \
  --compare ~/geomap2arcgis/runs/stitchvector/u2_full/u2_full_B2c.gpkg \
  --ocr-json ~/geomap2arcgis/runs/stitchvector/u2_full/u2_ocr_full.json \
  --out-dir ~/geomap2arcgis/runs/stitchvector/u2_full/diff_review --port 8813
```

Open http://127.0.0.1:8813/ and choose a mode under "差异".

B2c, M2 and the OCR baseline are unchanged.
