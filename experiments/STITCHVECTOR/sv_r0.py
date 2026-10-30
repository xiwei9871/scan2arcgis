"""R0: strict lossless joint-RGB polygonization (pre-registration R0). Only image pixels are read."""
import json, sys, time
from pathlib import Path
import numpy as np
import geopandas as gpd
import sv_common as C


def r0_features(a):
    k = C.rgb_key(a); return [(g, v, 0) for g, v in C.polygonize(k)]


def write_gpkg(feats, path, layer="r0"):
    gdf = gpd.GeoDataFrame({"rgb_key": [v for _, v, _ in feats], "z": [z for _, _, z in feats]},
                           geometry=[g for g, _, _ in feats], crs=None)
    rgb = C.key_rgb(gdf["rgb_key"].to_numpy())
    gdf["r"], gdf["g"], gdf["b"] = rgb[:, 0], rgb[:, 1], rgb[:, 2]
    gdf.to_file(path, layer=layer, driver="GPKG", engine="pyogrio")
    return gdf


def read_render(path, h, w, layer="r0"):
    gdf = gpd.read_file(path, layer=layer, engine="pyogrio")
    lab = C.render(zip(gdf.geometry, gdf["rgb_key"], gdf["z"]), h, w)
    return C.key_rgb(lab)


def run(out_dir):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True); res = {}
    for code, sizes in C.PR["inputs"]["R0_small"].items():
        img = C.load(code)
        for s in sizes:
            a, off = C.centre_crop(img, s, s); t = time.time()
            f = r0_features(a); p = out / f"{code}_{s}.gpkg"
            if p.exists(): p.unlink()
            write_gpkg(f, p); rec = read_render(p, *a.shape[:2])
            sec = round(time.time() - t, 2); eq = float((rec == a).all(-1).mean())
            r = {"crop_offset_yx": list(off), "size": list(a.shape[:2]), "objects": len(f),
                 "vertices": C.n_vertices([g for g, _, _ in f]), "gpkg_bytes": p.stat().st_size,
                 "seconds": sec, "peak_rss_gb": round(C.peak_rss_gb(), 3), "exact_share": eq,
                 "objects_per_px": round(len(f) / a.shape[0] / a.shape[1], 4), "pass": eq == 1.0}
            res[f"{code}_{s}"] = r; print(code, s, r, flush=True)
            if sec > 600 or C.peak_rss_gb() > 4: print("resource guard hit", code, s)
    res["R0_PASS"] = all(v["pass"] for k, v in res.items() if isinstance(v, dict))
    return res


if __name__ == "__main__":
    r = run(sys.argv[2] if len(sys.argv) > 2 else "../../runs/stitchvector/r0")
    json.dump(r, open(Path(sys.argv[1]) / "r0_results.json", "w"), indent=1)
    print("R0_PASS", r["R0_PASS"])
