"""U2 full-map automatic build (validation branch). Frozen code reused unchanged: sv_b2c.b2c (lines), sv_v3.group
(logical ids), sv_lf.labels / footprint, sv_d71.fill, sv_oracle.faces / provenance, sv_oracle_v2.write / render_gpkg.

Only adapter step added here (recorded in the run JSON): B2c can return MultiLineString objects on the full map; the
frozen linker accepts LineString only, so each multi-part object is split into its parts (same geometry, same width and
colour) before grouping. Nothing else is changed. No Oracle lines, no protected masks, no manual input.

Input : runs/stitchvector/u2_full/u2_map.png  (map box [0,0,805,780] of runs/real/u2/work.png, legend excluded)
Output: runs/stitchvector/u2_full/u2_full_B2c.gpkg + experiments/STITCHVECTOR/u2_full/u2_build_run.json
"""
import hashlib, json, platform, subprocess, sys, time, traceback
from pathlib import Path
import numpy as np
from PIL import Image
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
import sv_lf as LF, sv_b2c as C, sv_v3 as V, sv_d71 as D, sv_oracle as O, sv_oracle_v2 as O2  # noqa: E402

RUN = Path.home() / "geomap2arcgis/runs/stitchvector/u2_full"
OUTJ = HERE / "u2_full"


def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()


def line_objects(img, log):
    objs = C.b2c(img)[0]; flat = []
    for o in objs:
        g = o["geom"]
        if g.geom_type == "LineString": flat.append(o)
        else:
            parts = [p for p in g.geoms if p.length > 0]; log["multipart_split"].append({"parts": len(parts), "length": round(g.length, 1)})
            flat += [{**o, "geom": p} for p in parts]
    lg, _ = V.group(img, flat); lid = {i: g["logical_id"] for g in lg for i in g["parts"]}
    return objs, [{"id": f"L{i}", "group": f"G{lid[i]}", "kind": "auto_B2c", "width": float(o["width"]), "rgb": np.asarray(o["rgb"], np.uint8),
                   "geom": o["geom"]} for i, o in enumerate(flat)]


if __name__ == "__main__":
    src = RUN / "u2_map.png"; img = np.asarray(Image.open(src).convert("RGB")); shape = img.shape[:2]
    log = {"input": str(src), "input_sha256": sha(src), "shape_hw": list(shape), "multipart_split": [], "errors": [],
           "code_commit": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=HERE).stdout.strip(),
           "python": platform.python_version(), "manual_steps": "none", "oracle_used": False}
    t0 = time.time(); out = RUN / "u2_full_B2c.gpkg"
    try:
        X, kpal = LF.labels(img); t1 = time.time()
        raw, lines = line_objects(img, log); t2 = time.time()
        rem = LF.footprint(lines, shape, LF.Q["halo"]); Fimg = D.fill(X, rem); fc = O.faces(Fimg, LF.Q["tol"]); obs, inf = O.provenance(Fimg, rem, fc); t3 = time.time()
        if out.exists(): out.unlink()
        O2.write(out, fc, kpal, np.arange(len(kpal)), obs, inf, lines, []); t4 = time.time()
        rgb, holes, secs, R = O2.render_gpkg(out, shape, kpal, LF.P, np.zeros(shape, bool)); t5 = time.time()
        Image.fromarray(rgb).save(RUN / "u2_full_B2c_render.png")
        log.update(ok=True, colour_classes=int(len(kpal)), b2c_objects=len(raw), line_records=len(lines), faces=int(len(fc["polys"])),
                   render_holes_px=int(np.asarray(holes).sum()) if holes is not None else None,
                   seconds={"labels": round(t1 - t0, 1), "lines_b2c_group": round(t2 - t1, 1), "faces": round(t3 - t2, 1), "write": round(t4 - t3, 1),
                            "render_readback": round(t5 - t4, 1), "total": round(t5 - t0, 1)},
                   output=str(out), output_sha256=sha(out))
    except Exception as e:
        log.update(ok=False, seconds_until_error=round(time.time() - t0, 1)); log["errors"].append({"type": type(e).__name__, "msg": str(e), "trace": traceback.format_exc()[-2000:]})
    OUTJ.mkdir(exist_ok=True); json.dump(log, open(OUTJ / "u2_build_run.json", "w"), indent=1, default=str)
    print(json.dumps({k: v for k, v in log.items() if k not in ("multipart_split",)}, default=str)[:1500]); print("multipart split", len(log["multipart_split"]))
