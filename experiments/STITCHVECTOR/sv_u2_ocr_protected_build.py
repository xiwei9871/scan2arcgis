"""T03 OCR-protected B2c experiment (`ocr-protected-b2c-v01`). Frozen pipeline modules are reused UNCHANGED
(sv_b2c, sv_v3, sv_lf, sv_d71, sv_oracle, sv_oracle_v2); the only new code is this adapter + mask/review logic.

Order of operations (per task spec):
  1. OCR quads + confidence come from runs/stitchvector/u2_full/u2_ocr_full.json (real PaddleOCR output).
  2. glyph_mask = actual INK pixels inside each quad (colour distance from the quad's own background median),
     never the whole rectangle -> the underlying face colour survives between strokes.
  3. Face rebuild: glyph px are added to `rem` so sv_d71.fill re-floods them from surrounding classes; every quad
     whose boundary ring mixes >1 colour class is flagged `ambiguous_quad` (spans a unit boundary) for review -
     we never blindly fill across two geological units.
  4. Line isolation: B2c runs on `img_prot` where ONLY the ink px are repainted with the quad background median,
     so glyph strokes are invisible to line extraction (A02 prevention). Lines still intersecting dilated quads
     are real geology crossing text -> kept, flagged `crosses_text` for human confirmation.
  5. Writes colour_faces / visual_lines / text_residue_lines (isolated suspects) / text_labels layers + a metrics
     JSON comparing against the frozen u2_full_B2c.gpkg baseline. Original scan is never touched.
"""
import hashlib, json, subprocess, sys, time
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
import geopandas as gpd, shapely
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
import sv_lf as LF, sv_b2c as C, sv_v3 as V, sv_d71 as D, sv_oracle as O, sv_oracle_v2 as O2  # noqa: E402

RUN = Path.home() / "geomap2arcgis/runs/stitchvector/u2_full"
OUTJ = HERE / "u2_full"


def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()


def glyph_mask_and_bg(img, quads, pad=1):
    """Actual ink px inside each quad only. Ink = colour distance > 55 from the quad's own non-ink median
    (or very dark, lum < 80). Returns mask, per-quad bg colour, per-quad ink px count."""
    h, w = img.shape[:2]; mask = np.zeros((h, w), bool); bg = []; ink_counts = []
    for q in quads:
        quad = np.asarray(q["quad"], float); x0, y0 = np.floor(quad.min(0)).astype(int); x1, y1 = np.ceil(quad.max(0)).astype(int)
        x0, y0, x1, y1 = max(0, x0 - pad), max(0, y0 - pad), min(w, x1 + pad), min(h, y1 + pad)
        crop = img[y0:y1, x0:x1]
        qim = Image.new("L", (x1 - x0, y1 - y0), 0); ImageDraw.Draw(qim).polygon([tuple(p) for p in (quad - [x0, y0]).tolist()], fill=1)
        qm = np.asarray(qim, bool)
        px = crop[qm]
        if not len(px): bg.append(np.zeros(3)); ink_counts.append(0); continue
        med = np.median(px, 0); lum = px.mean(1)
        ink = (np.linalg.norm(px.astype(float) - med, 1) > 55) | (lum < 80)
        if not ink.any(): ink = lum < np.percentile(lum, 30)
        m = np.zeros((y1 - y0, x1 - x0), bool); m[qm] = ink
        real_bg = np.median(px[~ink] if (~ink).any() else px, 0)
        mask[y0:y1, x0:x1] |= m; bg.append(real_bg); ink_counts.append(int(ink.sum()))
    return mask, bg, ink_counts


def quad_ring_classes(X, quad, ring=2):
    """Distinct fill-classes on the quad's surrounding ring (excluding glyph px already masked)."""
    h, w = X.shape; q = np.asarray(quad, float)
    x0, y0 = np.floor(q.min(0)).astype(int) - ring; x1, y1 = np.ceil(q.max(0)).astype(int) + ring
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(w, x1), min(h, y1)
    inner = np.zeros((h, w), bool); qm = Image.new("L", (w, h), 0); ImageDraw.Draw(qm).polygon([tuple(p) for p in q.tolist()], fill=1)
    inner = np.asarray(qm, bool); outer = np.zeros((h, w), bool); outer[y0:y1, x0:x1] = True
    ring_px = X[outer & ~inner]; vals, cnt = np.unique(ring_px, return_counts=True)
    return {int(v): int(c) for v, c in zip(vals, cnt)}


def line_objects(img, log):
    objs = C.b2c(img)[0]; flat = []
    for o in objs:
        g = o["geom"]
        if g.geom_type == "LineString": flat.append(o)
        else:
            flat += [{**o, "geom": p} for p in g.geoms if p.length > 0]
    lg, _ = V.group(img, flat); lid = {i: g["logical_id"] for g in lg for i in g["parts"]}
    return objs, [{"id": f"L{i}", "group": f"G{lid[i]}", "kind": "auto_B2c", "width": float(o["width"]), "rgb": np.asarray(o["rgb"], np.uint8),
                   "geom": o["geom"]} for i, o in enumerate(flat)]


if __name__ == "__main__":
    src = RUN / "u2_map.png"; ocr_path = RUN / "u2_ocr_full.json"
    img = np.asarray(Image.open(src).convert("RGB")); shape = img.shape[:2]
    ocr = json.load(open(ocr_path)); quads = ocr["items"] if isinstance(ocr, dict) else ocr
    log = {"input": str(src), "input_sha256": sha(src), "ocr_source": str(ocr_path), "ocr_items": len(quads),
           "code_commit": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=HERE).stdout.strip(),
           "errors": []}
    t0 = time.time(); out = RUN / "u2_full_ocr_protected.gpkg"
    try:
        X, kpal = LF.labels(img); t1 = time.time()
        gmask, bgs, ink_counts = glyph_mask_and_bg(img, quads)
        img_prot = img.copy()
        # repaint ink px only, each with its own quad's background median
        for i, q in enumerate(quads):
            qg = np.asarray(q["quad"], float); x0, y0 = np.floor(qg.min(0)).astype(int); x1, y1 = np.ceil(qg.max(0)).astype(int)
            x0, y0, x1, y1 = max(0, x0), max(0, y0), min(shape[1], x1), min(shape[0], y1)
            sub = gmask[y0:y1, x0:x1]; yy, xx = np.nonzero(sub); img_prot[y0 + yy, x0 + xx] = np.asarray(bgs[i], np.uint8)
        t2 = time.time()
        raw, lines = line_objects(img_prot, log); t3 = time.time()
        rem = LF.footprint(lines, shape, LF.Q["halo"]) | gmask
        Fimg = D.fill(X, rem); fc = O.faces(Fimg, LF.Q["tol"]); obs, inf = O.provenance(Fimg, rem, fc); t4 = time.time()
        # quad ambiguity + line/text crossing review flags
        amb = [i for i, q in enumerate(quads) if len(quad_ring_classes(X, q["quad"])) > 1]
        quad_geoms = [shapely.Polygon(np.asarray(q["quad"], float)) for q in quads]
        qtree = shapely.STRtree(np.asarray(quad_geoms, object))
        crosses = []
        for l in lines:
            hit = qtree.query(l["geom"].buffer(0.75))
            if len(hit): crosses.append(l["id"])
        for l in lines:
            if l["id"] in crosses: l["kind"] = "auto_B2c_crosses_text"
        if out.exists(): out.unlink()
        O2.write(out, fc, kpal, np.arange(len(kpal)), obs, inf, lines, []); t5 = time.time()
        # text layer: quads + confidence, as draft OCR candidates
        gpd.GeoDataFrame({"text": [q["text"] for q in quads], "score": [q["score"] for q in quads],
                          "status": "OCR_DRAFT", "ambiguous_quad": [i in amb for i in range(len(quads))]},
                         geometry=quad_geoms).to_file(out, layer="text_labels", driver="GPKG", engine="pyogrio")
        base = gpd.read_file(RUN / "u2_full_B2c.gpkg", layer="visual_lines")
        base_glyph = 0
        for g in base.geometry:
            b = g.buffer(0.75)
            if any(b.intersects(qg) and (b.intersection(qg).length / max(g.length, 1e-9)) > 0.6 for qg in quad_geoms): base_glyph += 1
        log.update(ok=True, glyph_ink_px=int(gmask.sum()), faces=int(len(fc["polys"])), lines=len(lines),
                   lines_crosses_text=len(crosses), ambiguous_quads=len(amb),
                   baseline_lines=len(base), baseline_glyph_like_lines=base_glyph,
                   seconds={"labels": round(t1 - t0, 1), "glyph_mask+inpaint": round(t2 - t1, 1),
                            "lines_b2c_group": round(t3 - t2, 1), "faces": round(t4 - t3, 1),
                            "write+metrics": round(t5 - t4, 1), "total": round(t5 - t0, 1)},
                   output=str(out), output_sha256=sha(out))
    except Exception as e:
        import traceback; log.update(ok=False); log["errors"].append({"type": type(e).__name__, "msg": str(e), "trace": traceback.format_exc()[-1500:]})
    OUTJ.mkdir(exist_ok=True); json.dump(log, open(OUTJ / "u2_ocr_protected_run.json", "w"), indent=1, default=str)
    print(json.dumps(log, default=str)[:1800])
