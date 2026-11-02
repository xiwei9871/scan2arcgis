"""Input adapters: any supported upload -> one RasterDocument (raster_document.v1) + a normalised RGB PNG.

The format is detected from the file's magic bytes, never from the extension. Sources are copied read-only into the
project; the normalised raster is a new file. coordinate_mode is GEOREFERENCED only when the source carries a CRS and a
non-identity affine transform (GeoTIFF); everything else is PIXEL_SPACE with crs = transform = null.
"""
import json
from pathlib import Path
import numpy as np
from PIL import Image
from .contracts import sha256_file, write_json_atomic

MAX_BYTES = 500 * 1024 * 1024
MAX_PIXELS = 120_000_000           # decoded raster limit (decompression-bomb guard)
MAX_PDF_DPI = 600
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


class InputError(Exception):
    pass


def sniff(path):
    h = open(path, "rb").read(16)
    if h.startswith(b"\x89PNG\r\n\x1a\n"): return "PNG"
    if h[:3] == b"\xff\xd8\xff": return "JPEG"
    if h[:4] in (b"II*\x00", b"MM\x00*", b"II+\x00", b"MM\x00+"): return "TIFF"
    if h.startswith(b"%PDF-"): return "PDF"
    if h[:2] == b"BM": return "BMP"
    if h[:4] == b"RIFF" and h[8:12] == b"WEBP": return "WEBP"
    if h[:12] == b"\x00\x00\x00\x0cjP  \r\n\x87\n" or h[:4] == b"\xff\x4f\xff\x51": return "JP2"
    return None


def _check_px(w, h):
    if w <= 0 or h <= 0: raise InputError("image has no pixels")
    if w * h > MAX_PIXELS: raise InputError(f"image too large: {w}x{h} px > {MAX_PIXELS} px limit")


def _rgb(a):
    a = np.asarray(a)
    if a.ndim == 2: a = np.stack([a] * 3, -1)
    if a.shape[-1] == 4: a = a[..., :3]
    if a.shape[-1] != 3: raise InputError(f"unsupported band count {a.shape[-1]}")
    if a.dtype != np.uint8:
        a = a.astype(np.float64); lo, hi = np.nanpercentile(a, 0.5), np.nanpercentile(a, 99.5)
        a = np.clip((a - lo) / max(hi - lo, 1e-9) * 255, 0, 255).astype(np.uint8)
    return np.ascontiguousarray(a)


def _tiff_page(src, page):
    """TIFF page -> RGB. GDAL (rasterio) first: it decodes LZW/Deflate/JPEG without extra packages; page k is the
    GDAL subdataset GTIFF_DIR:k+1. tifffile is the fallback for layouts GDAL refuses."""
    import rasterio
    try:
        path = str(src) if page == 0 else f"GTIFF_DIR:{page + 1}:{src}"
        with rasterio.open(path) as ds:
            _check_px(ds.width, ds.height); b = ds.read()[:3]
            return _rgb(b[0] if b.shape[0] == 1 else np.moveaxis(b, 0, -1))
    except InputError: raise
    except Exception:
        import tifffile
        with tifffile.TiffFile(str(src)) as t:
            p = t.pages[page]; _check_px(int(p.imagewidth), int(p.imagelength)); return _rgb(p.asarray())


def probe(path):
    """pages / sizes without decoding everything (for the page picker)."""
    path = Path(path); size = path.stat().st_size
    if size == 0: raise InputError("empty file")
    if size > MAX_BYTES: raise InputError(f"file too large ({size} bytes > {MAX_BYTES})")
    kind = sniff(path)
    if kind is None: raise InputError("unrecognised file type (not PNG/JPEG/TIFF/GeoTIFF/PDF/BMP/WebP/JP2 by content)")
    pages = []
    try:
        if kind == "PDF":
            import pypdfium2 as pdfium
            pdf = pdfium.PdfDocument(str(path))
            for i in range(len(pdf)): w, h = pdf[i].get_size(); pages.append({"index": i, "width_pt": round(w, 1), "height_pt": round(h, 1)})
            pdf.close()
        elif kind == "TIFF":
            import tifffile
            with tifffile.TiffFile(str(path)) as t:
                for i, p in enumerate(t.pages): pages.append({"index": i, "width": int(p.imagewidth), "height": int(p.imagelength)})
            try:
                import rasterio
                with rasterio.open(path) as ds:
                    if ds.crs is not None and not ds.transform.is_identity: kind = "GEOTIFF"
            except Exception: pass
        elif kind == "JP2":
            try:
                import rasterio
                with rasterio.open(path) as ds: pages.append({"index": 0, "width": ds.width, "height": ds.height})
            except Exception as e: raise InputError(f"JPEG2000 decoder not available: {e}")
        else:
            with Image.open(path) as im: im.verify()
            with Image.open(path) as im: pages.append({"index": 0, "width": im.width, "height": im.height})
    except InputError: raise
    except Exception as e: raise InputError(f"cannot decode {kind}: {type(e).__name__}: {e}")
    if not pages: raise InputError("no pages / images in file")
    return {"source_type": kind, "pages": pages, "bytes": size}


def normalise(src, out_dir, page=0, dpi=300, document_id="doc-001"):
    """decode page `page` -> out_dir/raster.png + raster_document.json. Returns the document dict."""
    src = Path(src); out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    info = probe(src); kind = info["source_type"]
    if not (0 <= int(page) < len(info["pages"])): raise InputError(f"page {page} out of range (file has {len(info['pages'])})")
    page = int(page); crs = transform = None; mode = "PIXEL_SPACE"; render = {}; extra = {}
    try:
        if kind == "PDF":
            dpi = int(dpi)
            if not (36 <= dpi <= MAX_PDF_DPI): raise InputError(f"PDF dpi must be 36-{MAX_PDF_DPI}")
            import pypdfium2 as pdfium
            pdf = pdfium.PdfDocument(str(src)); pg = pdf[page]; w, h = pg.get_size(); s = dpi / 72.0
            _check_px(int(w * s), int(h * s))
            a = _rgb(pg.render(scale=s).to_pil().convert("RGB")); pdf.close()
            render = {"dpi": dpi, "scale_px_per_pt": s, "page_size_pt": [round(w, 2), round(h, 2)],
                      "pixel_to_pdf_pt": [1 / s, 0, 0, 0, -1 / s, h]}       # x_pt = col/s ; y_pt(up) = h - row/s
        elif kind in ("TIFF", "GEOTIFF"):
            a = _tiff_page(src, page)
            if kind == "GEOTIFF":
                import rasterio
                with rasterio.open(src) as ds:
                    if page == 0 and ds.crs is not None:
                        crs = ds.crs.to_wkt(); transform = list(ds.transform)[:6]; mode = "GEOREFERENCED"
                        extra = {"epsg": ds.crs.to_epsg(), "nodata": ds.nodata, "geo_bounds": list(ds.bounds)}
        elif kind == "JP2":
            import rasterio
            with rasterio.open(src) as ds: _check_px(ds.width, ds.height); a = _rgb(np.moveaxis(ds.read()[:3], 0, -1))
        else:
            with Image.open(src) as im: _check_px(im.width, im.height); a = _rgb(im.convert("RGB"))
    except InputError: raise
    except Exception as e: raise InputError(f"cannot decode {kind} page {page}: {type(e).__name__}: {e}")
    H, W = a.shape[:2]; ras = out_dir / "raster.png"; Image.fromarray(a).save(ras)
    doc = {"schema": "raster_document.v1", "document_id": document_id, "source_type": kind, "source_path": str(src), "source_sha256": sha256_file(src),
           "page_index": page, "page_count": len(info["pages"]), "width": W, "height": H, "colour_space": "sRGB (assumed)",
           "coordinate_mode": mode, "crs": crs, "transform": transform, "pdf_render": render or None, **extra,
           "raster_artifact": str(ras), "raster_sha256": sha256_file(ras), "preprocess": {"decode": "to 8-bit RGB", "resample": "none"}}
    write_json_atomic(out_dir / "raster_document.json", doc); return doc
