"""R1: VTracer single pass (pre-registration R1). Only image pixels are read.
Usage: sv_r1.py one <sample> <input> <config> <out_dir>   (one run, called by the driver)
       sv_r1.py all <out_dir>                             (driver; each run in its own process, 600 s guard)
"""
import io, json, subprocess, sys, time
from pathlib import Path
import numpy as np
import geopandas as gpd
from PIL import Image
import vtracer
import sv_common as C
import sv_svg as S

CFG = {c["name"]: c for c in C.PR["R1"]["configs"]}
CFG["watershed"] = {"name": "watershed", "clustering": "watershed", "watershed_detail": 128}
INPUTS = C.PR["R1"]["inputs"]                     # raw RGB, quantized 16/32/64
RAW_EXTRA = ["default", "watershed"]
TIMEOUT = 600


def window(code):
    return C.centre_crop(C.load(code), 1000, 1000)


def prepare(a, inp):
    if inp == "raw RGB": return a, None, None
    n = int(inp.split()[-1]); lab, pal = C.quantize(a, n)
    return pal[lab], pal, lab


def config(name, pal):
    c = CFG[name]
    kw = {k: v for k, v in c.items() if k not in ("name", "note")}
    cfg = vtracer.Config(**kw) if kw else vtracer.Config()
    if pal is not None: cfg.palette = ["#%02X%02X%02X" % tuple(int(x) for x in p) for p in pal]
    return cfg


def one(code, inp, name, out_dir):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    a, off = window(code); src, pal, _ = prepare(a, inp); h, w = a.shape[:2]
    b = io.BytesIO(); Image.fromarray(src).save(b, "PNG")
    t = time.time(); svg = config(name, pal).convert_bytes(b.getvalue()); t_trace = time.time() - t
    feats = S.svg_features(svg); t_flat = time.time() - t - t_trace
    key = C.render(feats, h, w, fill=0); rec = C.key_rgb(key)
    tag = f"{code}_{inp.replace(' ', '')}_{name}"
    (out / f"{tag}.svg").write_text(svg)
    gdf = gpd.GeoDataFrame({"rgb_key": [v for _, v, _ in feats], "z": [z for _, _, z in feats]},
                           geometry=[g for g, _, _ in feats], crs=None)
    p = out / f"{tag}.gpkg"
    if p.exists(): p.unlink()
    gdf.to_file(p, layer="r1", driver="GPKG", engine="pyogrio")
    thin = C.thin_mask(a)
    r = {"sample": code, "input": inp, "config": name, "crop_offset_yx": list(off), "size": [h, w],
         "objects": len(feats), "svg_paths": S.n_svg_paths(svg), "vertices": C.n_vertices([g for g, _, _ in feats]),
         "svg_bytes": len(svg.encode()), "gpkg_bytes": p.stat().st_size,
         "seconds_trace": round(t_trace, 2), "seconds_flatten_render": round(t_flat, 2),
         "peak_rss_gb": round(C.peak_rss_gb(), 3),
         "vs_original": C.fidelity(a, rec, thin)}
    if pal is not None: r["vs_quantized"] = C.fidelity(src, rec, thin)
    json.dump(r, open(out / f"{tag}.json", "w"), indent=1)
    print(json.dumps({k: r[k] for k in ("sample", "input", "config", "objects", "vertices")} |
                     {"exact_orig": round(r["vs_original"]["exact_share"], 4),
                      "dE90": round(r["vs_original"]["dE90"], 2),
                      "thin": round(r["vs_original"].get("thin_match_dE10", float("nan")), 4)}), flush=True)


def all_runs(out_dir):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True); log = []
    for code in C.SAMPLES:
        for inp in INPUTS:
            names = [c for c in CFG if c != "watershed"] + (["watershed"] if inp == "raw RGB" else [])
            for name in names:
                t = time.time()
                try:
                    p = subprocess.run([sys.executable, __file__, "one", code, inp, name, str(out)],
                                       capture_output=True, text=True, timeout=TIMEOUT)
                    st = "ok" if p.returncode == 0 else "error"; msg = (p.stdout.strip().splitlines() or [""])[-1] if st == "ok" else p.stderr[-300:]
                except subprocess.TimeoutExpired:
                    st, msg = "timeout", f"> {TIMEOUT} s"
                log.append({"sample": code, "input": inp, "config": name, "status": st,
                            "seconds": round(time.time() - t, 1), "msg": msg}); print(st, code, inp, name, msg[:200], flush=True)
    json.dump(log, open(out / "r1_log.json", "w"), indent=1)


if __name__ == "__main__":
    if sys.argv[1] == "one": one(*sys.argv[2:6])
    else: all_runs(sys.argv[2])
