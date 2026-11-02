# geology-aware-vnext — plan (not implemented)

| Stage | Plugin id (reserved) | Needs before it can be built | Acceptance before switching default |
|---|---|---|---|
| legend | stitchvector.legend.preparse | `legend.v1` producer: legend box, swatch colours, codes, line styles; status LEGEND_PENDING until a person confirms | entries confirmed on ≥ 3 sheets |
| text_process | stitchvector.text.protect_mask | protection mask from OCR polygons, consumed by the line stage | no real line inside a mask is lost on the U2 Oracle window |
| vectorize | stitchvector.vectorize.lines_protected | line detector that reads the mask and looks back at the scan under it | line recall ≥ B2c on Oracle window, fewer text-stroke lines |
| geometry | stitchvector.geometry.faces_legend | face builder using legend classes and lines; ambiguous fragments PENDING_HUMAN | small-face share well below B2c's 86 %; no forced merges |
| quality | stitchvector.quality.legend_residual | confirmed `legend.v1` + full-result render including text glyphs | residual audit reports separately line/face, text, full result |

Each item is a separate research task with its own acceptance; none blocks Studio V0.1. The plugin contract, profile file and NOT_IMPLEMENTED handling already exist, so a stage can be dropped in when it passes.
