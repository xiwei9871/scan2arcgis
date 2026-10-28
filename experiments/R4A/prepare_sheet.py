"""R4-A: normalise one downloaded GSJ sheet so the frozen R2 tools run unchanged.

GSJ vector packages store attribute text either as cp932 (no .cpg) or UTF-8 (.cpg says UTF-8).
The R2 tools read with cp932, so UTF-8 packages would garble LEGEND01 (line types). This script
reads geo_A / geo_L with the correct encoding and writes a cp932 copy to
data/raw/gsj_r4a/norm/<code>/shp/. Geometry is untouched. It also writes sheet_info.json with
the quadrangle bounds used for neatline registration (図郭線 bounds when present, else geo_A).
"""
import json, os, sys, glob, warnings
from pathlib import Path
import geopandas as gpd
warnings.filterwarnings("ignore")


def enc(shp):
    c = shp[:-4] + ".cpg"
    return open(c).read().strip() if os.path.exists(c) else "cp932"


def main(code, root="data/raw/gsj_r4a"):
    src = glob.glob(f"{root}/{code}/**/geo_A.shp", recursive=True)[0]
    srcL = glob.glob(f"{root}/{code}/**/geo_L.shp", recursive=True)[0]
    out = Path(root) / "norm" / code / "shp"; out.mkdir(parents=True, exist_ok=True)
    A = gpd.read_file(src, encoding=enc(src)); L = gpd.read_file(srcL, encoding=enc(srcL))
    for col in list(A.columns) + list(L.columns):
        pass
    A.to_file(out / "geo_A.shp", encoding="cp932"); L.to_file(out / "geo_L.shp", encoding="cp932")
    k = L["LEGEND01"].astype(str)
    frame = L[k.str.contains("図郭")]
    b = [float(x) for x in (frame.total_bounds if len(frame) else A.total_bounds)]
    info = {"code": code, "source_encoding": {"geo_A": enc(src), "geo_L": enc(srcL)},
            "bounds_source": "frame_line" if len(frame) else "geo_A", "bounds_lonlat": b,
            "n_units": int(A.MAJOR_CODE.nunique()), "n_polygons": len(A), "invalid_polygons": int((~A.geometry.is_valid).sum()),
            "line_types": sorted(set(k)), "crs_epsg": A.crs.to_epsg() if A.crs else None}
    json.dump(info, open(out.parent / "sheet_info.json", "w"), ensure_ascii=False, indent=1)
    print(code, info["bounds_source"], [round(x, 4) for x in b], info["line_types"])


if __name__ == "__main__":
    main(*sys.argv[1:])
