"""Line + face integration POC (rules: sv_lf_prereg.json). Fully automatic: no oracle lines, no protected masks.

Reused unchanged: sv_oracle.faces (sv_arcs shared arcs, strict coverage), sv_d71.fill (nearest-label fill under the line
footprint), sv_oracle.provenance (observed / inferred px per face), sv_oracle_v2.write / render_gpkg (GPKG layers
colour_faces + visual_lines, re-rendered from the file), sv_v3.group (logical_id from the frozen linker).
Adapter: automatic line objects (B0 = frozen 2.0, B2c = B0 + luminance-filtered additions) become the line records
write() expects; protected areas are always empty, so prot_geoms = [] and the render mask is all False.
Face labels: 32-colour median cut merged at dE < 10 into colour classes (the Oracle 'class' configuration), tol 0.
Truth (lines, bands, fill edges) is used only in sv_lf_eval.
"""
import numpy as np, shapely
import sv_common as Cm, sv_d71 as D, sv_oracle as O, sv_oracle_v2 as O2, sv_v3 as V, sv_ld_fix as F, sv_b2c as C

P = dict(O.P); P.update(O2.PRE["params"])          # Oracle v2 params (r_min, halo, ...), unchanged
Q = {"halo": 1.0, "merge_dE": 10.0, "tol": 0}


def line_objects(img, method):
    objs = F.b0(img) if method == "B0" else C.b2c(img)[0]
    lg, _ = V.group(img, objs); lid = {i: g["logical_id"] for g in lg for i in g["parts"]}
    return [{"id": f"L{i}", "group": f"G{lid[i]}", "kind": f"auto_{method}", "width": float(o["width"]), "rgb": np.asarray(o["rgb"], np.uint8),
             "geom": o["geom"]} for i, o in enumerate(objs)]


def labels(img, q=Q):
    lab, pal = Cm.quantize(img, 32); K, lut, _ = D.colour_classes(lab, pal, q["merge_dE"]); kpal = O.class_palette(lab, lut, pal)
    return lut[lab], kpal


def footprint(lines, shape, extra):
    m = np.zeros(shape, bool)
    for f in lines: m |= O2.footprint(f, shape, P, extra)
    return m


def compose_memory(Fimg, kpal, lines, shape):
    rgb = kpal[Fimg].copy()
    for f in lines: rgb[O2.footprint(f, shape, P)] = f["rgb"]
    return rgb


def build(img, method, gpkg_path, q=Q):
    """method: F0 (faces only, no line layer), B0, B2c. Returns everything needed for evaluation."""
    shape = img.shape[:2]; X, kpal = labels(img, q)
    lines = [] if method == "F0" else line_objects(img, method)
    rem = footprint(lines, shape, q["halo"]) if lines else np.zeros(shape, bool)
    Fimg = D.fill(X, rem); fc = O.faces(Fimg, q["tol"]); obs, inf = O.provenance(Fimg, rem, fc)
    O2.write(gpkg_path, fc, kpal, np.arange(len(kpal)), obs, inf, lines, [])
    rgb, holes, secs, R = O2.render_gpkg(gpkg_path, shape, kpal, P, np.zeros(shape, bool))
    mem = compose_memory(Fimg, kpal, lines, shape)
    return {"lines": lines, "faces": fc, "X": X, "F": Fimg, "kpal": kpal, "removed": rem, "rgb": rgb, "R": R, "holes": holes,
            "readback_seconds": secs, "memory_vs_gpkg_px": int((mem != rgb).any(-1).sum()), "obs": obs, "inf": inf}
