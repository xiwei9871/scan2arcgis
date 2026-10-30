"""R2 runner (pre-registration R2 + fair comparison). One run = sample x n_colours x method.
Methods: R2_A (direct mosaic, progressive 4->2->1->0), R2_B (ink layer + fill completion, progressive per layer),
SP_t1 / SP_t0 (single-pass trace of the same label image at tolerance 1 / 0). Reads only image pixels.
Usage: sv_r2_run.py one <sample> <n> <method> <out_dir>
"""
import json, sys, time
from pathlib import Path
import numpy as np, shapely
import geopandas as gpd
import sv_common as C
import sv_r2 as R


def trace_layer(lab, method):
    if method == "SP_t0":
        ex = C.polygonize(lab); return [(g, v) for g, v in ex if v != R.TR], None
    if method == "SP_t1":
        ex = C.polygonize(lab); g = R.csimplify([x for x, _ in ex], 1.0)
        return [(a, v) for a, (_, v) in zip(g, ex) if v != R.TR], None
    f, log = R.progressive(lab); return [(g, v) for g, v in f if v != R.TR], log


def run_one(sample, n, method, out_dir):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    img = C.load(sample); a, off = C.centre_crop(img, 1000, 1000); h, w = a.shape[:2]
    t0 = time.time(); lab, pal = C.quantize(a, n)
    variant = "B" if method == "R2_B" else "A"
    lays, info = R.layers(lab, pal, variant)
    feats, logs, renders = [], {}, []
    for z, (name, L) in enumerate(lays):
        f, log = trace_layer(L, method)
        feats += [(g, v, z, name) for g, v in f]; logs[name] = log
        renders.append(R.render([(g, v) for g, v in f], h, w))
    sec = round(time.time() - t0, 2)
    rec = R.compose(renders, pal, h, w)
    qimg = pal[lab]; thin = C.thin_mask(a)
    geoms = [g for g, *_ in feats]
    gdf = gpd.GeoDataFrame({"colour": [v for _, v, _, _ in feats], "z": [z for _, _, z, _ in feats],
                            "layer": [s for *_, s in feats]}, geometry=geoms, crs=None)
    rgb = pal[gdf["colour"].to_numpy()]; gdf["r"], gdf["g"], gdf["b"] = rgb[:, 0], rgb[:, 1], rgb[:, 2]
    tag = f"{sample}_q{n}_{method}"; p = out / f"{tag}.gpkg"
    if p.exists(): p.unlink()
    gdf.to_file(p, layer="sv", driver="GPKG", engine="pyogrio")
    res = {"sample": sample, "n_colours": n, "method": method, "crop_offset_yx": list(off), "size": [h, w],
           "objects": len(feats), "vertices": C.n_vertices(geoms), "gpkg_bytes": p.stat().st_size,
           "seconds": sec, "peak_rss_gb": round(C.peak_rss_gb(), 3),
           "vs_quantized": C.fidelity(qimg, rec, thin), "vs_original": C.fidelity(a, rec, thin),
           "stage_logs": logs}
    if info is not None:
        res["ink_layer"] = {k: v for k, v in info.items() if k != "inferred_mask"}
        res["inferred_fill_px"] = int(info["inferred_mask"].sum())
    json.dump(res, open(out / f"{tag}.json", "w"), indent=1, default=float)
    return res


if __name__ == "__main__":
    if sys.argv[1] == "one":
        r = run_one(sys.argv[2], int(sys.argv[3]), sys.argv[4], sys.argv[5])
        print(json.dumps({k: r[k] for k in ("sample", "n_colours", "method", "objects", "vertices", "seconds")}
                         | {"q_exact": round(r["vs_quantized"]["exact_share"], 4),
                            "o_exact": round(r["vs_original"]["exact_share"], 4),
                            "dE90": round(r["vs_original"]["dE90"], 2),
                            "thin": round(r["vs_original"].get("thin_match_dE10", float("nan")), 3)}))
