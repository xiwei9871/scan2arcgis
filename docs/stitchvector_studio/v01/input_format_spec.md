# Input formats (`tools/stitchvector_studio/inputs.py`)

Type is detected from magic bytes, never the extension. Each upload is written to a `.part` file, probed, then renamed into `original/` with mode 0444.

| Format | Decoder | Pages | Coordinate mode |
|---|---|---|---|
| PNG, JPEG, BMP, WebP | Pillow | 1 | PIXEL_SPACE |
| TIFF (multi-page) | GDAL (`GTIFF_DIR:n`), tifffile fallback | user picks page | PIXEL_SPACE |
| GeoTIFF | GDAL / rasterio | page 0 carries CRS | GEOREFERENCED: CRS WKT, EPSG, affine, nodata, bounds kept |
| PDF (multi-page) | pypdfium2 | user picks page; DPI 36–600 (default 300) | PIXEL_SPACE; `pdf_render` stores dpi, page size and pixel→PDF-point affine |
| JPEG2000 | rasterio if the GDAL driver exists | 1 | PIXEL_SPACE |

Limits: 500 MB upload, 120 M decoded pixels (Pillow decompression-bomb guard set to the same value). `crs` and `transform` are `null` unless the file carries them. The normalised raster is 8-bit RGB with no resampling; its affine is the source's, so pixel → map coordinates stay exact.

Output `raster_document.v1`: `document_id, source_type, source_sha256, page_index, page_count, width, height, colour_space, coordinate_mode, crs, transform, pdf_render, epsg, nodata, geo_bounds, raster_artifact, raster_sha256, preprocess`.

Evidence: `experiments/STITCHVECTOR/studio_v01/input_format_results.json` (real generated samples from `make_samples.py`: 9 accepted, corrupt PNG and fake-extension file rejected).
