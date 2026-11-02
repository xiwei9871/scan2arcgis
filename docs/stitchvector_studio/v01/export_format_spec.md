# Exports (`tools/stitchvector_studio/exports.py`)

Layers: `geological_faces` (colour_faces), `geological_lines` (visual_lines), `text_confirmed` (review_status OCR_CONFIRMED / HUMAN_EDITED? no — see below), `text_unconfirmed`, `isolated_lines` (text_residue_lines). Default: faces, lines, confirmed text. Unconfirmed text (OCR_DRAFT) is only exported when selected and always in its own layer.

Confirmed set: `OCR_CONFIRMED, HUMAN_EDITED, TEXT_VECTOR_CREATED, TEXT_LAYER_COMPLETE`. Every text row carries `review_status`, `ocr_text`, `text`, engine and model.

| Format | GEOREFERENCED | PIXEL_SPACE |
|---|---|---|
| GPKG | geometries transformed with the source affine, CRS written | pixel coordinates, no CRS (never a fake EPSG) |
| Shapefile ZIP | one .shp set per layer, .cpg UTF-8, .prj, `field_mapping.json` (10-char names), `export_manifest.json` | needs explicit confirmation; no .prj |
| GeoJSON | ZIP of per-layer RFC 7946 files in EPSG:4326 | refused as GeoJSON; a `*.pixel.json` exchange file marked `PIXEL_SPACE` is written instead |

Every export is written to a temp folder, re-read (feature count, geometry validity, types, rgb and text equality, lon/lat range for GeoJSON, no .prj in pixel mode) and only then moved into `exports/<id>/`. Exports are made from the saved working copy; with unsaved edits the server asks for a version first.
