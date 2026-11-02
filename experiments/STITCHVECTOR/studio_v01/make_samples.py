"""Builds real sample files for the Studio input-format test (each written by its own encoder, never a renamed file).

Output: ~/geomap2arcgis/runs/stitchvector/studio_v01/samples/  (local only; binaries are not pushed)
  s_png.png s_jpg.jpg s_bmp.bmp s_webp.webp  - 260x260 crop of the U2 map
  s_tiff.tif       plain TIFF (LZW)            s_multipage.tif  3-page TIFF (pages differ)
  s_geotiff.tif    GeoTIFF, EPSG:32649, 2 m pixels, LZW
  s_pdf1.pdf       1-page PDF (image page)     s_pdf3.pdf       3-page PDF
  s_corrupt.png    PNG header + garbage        s_fake_ext.png   text file named .png
"""
from pathlib import Path
import numpy as np
from PIL import Image

OUT = Path.home() / "geomap2arcgis/runs/stitchvector/studio_v01/samples"
SRC = Path.home() / "geomap2arcgis/runs/stitchvector/u2_full/u2_map.png"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    a = np.asarray(Image.open(SRC).convert("RGB"))[260:520, 300:560]; im = Image.fromarray(a)
    im.save(OUT / "s_png.png"); im.save(OUT / "s_jpg.jpg", quality=90); im.save(OUT / "s_bmp.bmp"); im.save(OUT / "s_webp.webp", quality=90)
    im.save(OUT / "s_tiff.tif", compression="tiff_lzw")
    pages = [Image.fromarray(np.roll(a, k * 40, axis=1)) for k in range(3)]
    pages[0].save(OUT / "s_multipage.tif", save_all=True, append_images=pages[1:], compression="tiff_lzw")
    import rasterio
    from rasterio.transform import from_origin
    with rasterio.open(OUT / "s_geotiff.tif", "w", driver="GTiff", width=a.shape[1], height=a.shape[0], count=3, dtype="uint8",
                       crs="EPSG:32649", transform=from_origin(500000.0, 4300000.0, 2.0, 2.0), compress="lzw") as ds:
        ds.write(np.moveaxis(a, -1, 0))
    im.save(OUT / "s_pdf1.pdf", resolution=100.0)
    small = [p.resize((130, 130)) for p in pages]; small[0].save(OUT / "s_pdf3.pdf", save_all=True, append_images=small[1:], resolution=50.0)
    (OUT / "s_corrupt.png").write_bytes(b"\x89PNG\r\n\x1a\n" + bytes(range(200)))
    (OUT / "s_fake_ext.png").write_text("this is not an image\n" * 13)
    for p in sorted(OUT.iterdir()): print(p.name, p.stat().st_size)


if __name__ == "__main__":
    main()
