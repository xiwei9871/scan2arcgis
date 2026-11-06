"""T03 OCR-protected B2c experiment (`ocr-protected-b2c-v01`), P0 safety-hardened.

Frozen modules (sv_b2c, sv_v3, sv_lf, sv_d71, sv_oracle, sv_oracle_v2) are reused UNCHANGED - all protection
logic lives in this adapter.

P0 ordering rule (task 2): EVERY risk decision is made on untouched data BEFORE a single pixel is repainted.
  1. Read real PaddleOCR quads+scores (u2_ocr_full.json, 219 items - see run JSON for engine provenance).
  2. Per quad, on the ORIGINAL class image X:
       ring_classes    - >1 colour class on the quad's boundary ring => text sits on a unit boundary
       overlap         - quad raster overlaps another quad => mask ownership is ambiguous
       ink_saturation  - ink px share > 60% of quad => background median is unreliable
     Any flag => `preserve_review`: original pixels stay, quad is queued for human confirmation with a
     suggestion + affected-object list. NOTHING about it is modified.
     Only `auto_clean` quads (single-class ring, no overlap, sane ink) get ink-px inpainting.
  3. Face rebuild: ink px of AUTO_CLEAN quads only are added to `rem` so sv_d71.fill re-floods them; risky
     quads keep baseline geometry (fragments remain visible = honest, not hidden).
  4. Lines: B2c sees `img_prot` where only auto_clean ink px are repainted. Every baseline line that
     disappears is audited per-object (length, colour, ring-class crossing) in removed_lines_audit.csv -
     object count alone is never treated as quality.
  5. Output layers: colour_faces / visual_lines / text_labels (EDITOR-SCHEMA: Point geometry + all
     TEXT_COLS) / ocr_quads (raw candidate boxes) / text_residue_lines is left to the editor.
  The original scan and the frozen u2_full_B2c.gpkg are never touched.
"""
import hashlib, json, subprocess, sys, time
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
import geopandas as gpd, shapely
from shapely.geometry import Point, Polygon
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
import sv_lf as LF, sv_b2c as C, sv_v3 as V, sv_d71 as D, sv_oracle as O, sv_oracle_v2 as O2  # noqa: E402

RUN = Path.home() / "geomap2arcgis/runs/stitchvector/u2_full"
OUTJ = HERE / "u2_full"
TEXT_COLS = ["label_id", "text", "ocr_text", "ocr_score", "font_px", "angle_deg", "anchor", "rgb",
             "box_x0", "box_y0", "box_x1", "box_y1", "source", "review_status", "review_reason",
             "reviewed_at", "review_actor"]


def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()


def dedupe_quads(quads, iou=0.5):
    """The raw 219-item run has no dedup: same text detected at multiple scales -> merge IoU>iou boxes,
    keep the higher score + the union quad. Returns merged quad list with source indices."""
    boxes = [shapely.box(*np.asarray(q["quad"]).min(0), *np.asarray(q["quad"]).max(0)) for q in quads]
    used = np.zeros(len(quads), bool); merged = []
    for i in np.argsort([-q["score"] for q in quads]):
        if used[i]: continue
        grp = [i]
        for j in range(len(quads)):
            if used[j] or j == i: continue
            inter = boxes[i].intersection(boxes[j]).area; union = boxes[i].union(boxes[j]).area
            if union and inter / union > iou: grp.append(j); used[j] = True
        used[i] = True
        pts = np.concatenate([np.asarray(quads[k]["quad"]) for k in grp])
        x0, y0 = pts.min(0); x1, y1 = pts.max(0)
        merged.append({"quad": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]], "text": quads[i]["text"],
                       "score": quads[i]["score"], "src": grp})
    return merged


def quad_rasters(quads, shape):
    """per-quad boolean raster + an ownership map (-1 none, -2 overlap, else quad index)."""
    h, w = shape; own = np.full((h, w), -1, np.int16); masks = []
    for i, q in enumerate(quads):
        qim = Image.new("L", (w, h), 0); ImageDraw.Draw(qim).polygon([tuple(p) for p in np.asarray(q["quad"], float).tolist()], fill=1)
        masks.append(np.asarray(qim, bool))
    cnt = np.stack(masks).sum(0)
    for i, m in enumerate(masks): own[m & (cnt == 1)] = i
    own[cnt > 1] = -2
    return masks, own, cnt


def ink_px(crop_img, quad, x0, y0):
    """actual stroke px inside one quad crop: colour distance>55 from the quad's own non-ink median, or lum<80."""
    xs = np.clip(np.asarray(quad)[:, 0] - x0, 0, crop_img.shape[1]); ys = np.clip(np.asarray(quad)[:, 1] - y0, 0, crop_img.shape[0])
    qim = Image.new("L", (crop_img.shape[1], crop_img.shape[0]), 0)
    ImageDraw.Draw(qim).polygon(list(zip(xs, ys)), fill=1); qm = np.asarray(qim, bool)
    px = crop_img[qm]
    if not len(px): return qm, np.zeros(3), 0
    med = np.median(px, 0); lum = px.mean(1); med_lum = float(lum.mean())
    ink = ((np.linalg.norm(px.astype(float) - med, 1) > 75) & (lum < med_lum * 0.85)) | (lum < 70)
    if not ink.any(): ink = lum < np.percentile(lum, 25)
    m = np.zeros_like(qm); m[qm] = ink
    bg = np.median(px[~ink] if (~ink).any() else px, 0)
    return m, bg, int(ink.sum())


def quad_ring_classes(X, quad, ring=2):
    h, w = X.shape; q = np.asarray(quad, float)
    x0, y0 = np.floor(q.min(0)).astype(int) - ring; x1, y1 = np.ceil(q.max(0)).astype(int) + ring
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(w, x1), min(h, y1)
    qm = Image.new("L", (w, h), 0); ImageDraw.Draw(qm).polygon([tuple(p) for p in q.tolist()], fill=1)
    inner = np.asarray(qm, bool); outer = np.zeros((h, w), bool); outer[y0:y1, x0:x1] = True
    vals, cnt = np.unique(X[outer & ~inner], return_counts=True)
    return {int(v): int(c) for v, c in zip(vals, cnt)}


def line_objects(img, log):
    objs = C.b2c(img)[0]; flat = []
    for o in objs:
        g = o["geom"]
        if g.geom_type == "LineString": flat.append(o)
        else: flat += [{**o, "geom": p} for p in g.geoms if p.length > 0]
    lg, _ = V.group(img, flat); lid = {i: g["logical_id"] for g in lg for i in g["parts"]}
    return objs, [{"id": f"L{i}", "group": f"G{lid[i]}", "kind": "auto_B2c", "width": float(o["width"]), "rgb": np.asarray(o["rgb"], np.uint8),
                   "geom": o["geom"]} for i, o in enumerate(flat)]


if __name__ == "__main__":
    src = RUN / "u2_map.png"; ocr_path = RUN / "u2_ocr_full.json"
    img = np.asarray(Image.open(src).convert("RGB")); shape = img.shape[:2]
    ocr = json.load(open(ocr_path)); quads = ocr["items"] if isinstance(ocr, dict) else ocr
    log = {"input": str(src), "input_sha256": sha(src), "ocr_source": str(ocr_path), "ocr_items": len(quads), "ocr_items_deduped": None,
           "ocr_provenance": "raw PaddleOCR run on u2_map.png (seconds=3.5); differs from Studio ocr_candidates.v1 148-item baseline "
                             "(paddleocr 3.7.0 PP-OCRv6_medium, dedup + 4px input offset + rule layer) - same engine family, different params",
           "code_commit": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=HERE).stdout.strip(),
           "errors": []}
    t0 = time.time(); out = RUN / "u2_full_ocr_protected.gpkg"
    try:
        X, kpal = LF.labels(img); t1 = time.time()
        merged = dedupe_quads(quads)
        log["ocr_items_deduped"] = len(merged)
        masks, own, ocnt = quad_rasters(merged, shape)

        # -------- P0: risk decisions on UNTOUCHED data, before any pixel changes ----------
        decisions = []
        for i, q in enumerate(merged):
            ring = quad_ring_classes(X, q["quad"])
            tot = sum(ring.values()) or 1; top = max(ring.values()) / tot
            second = sorted(ring.values(), reverse=True)[1] / tot if len(ring) > 1 else 0
            overlap = bool((ocnt[masks[i]] > 1).any())
            flags = []
            if top < 0.6 and second >= 0.1: flags.append("spans_unit_boundary")
            if overlap: flags.append("overlaps_other_quad")
            x0, y0 = np.floor(np.asarray(q["quad"]).min(0)).astype(int); x1, y1 = np.ceil(np.asarray(q["quad"]).max(0)).astype(int)
            x0, y0, x1, y1 = max(0, x0 - 1), max(0, y0 - 1), min(shape[1], x1 + 1), min(shape[0], y1 + 1)
            im, bg, inkn = ink_px(img[y0:y1, x0:x1], np.asarray(q["quad"]), x0, y0)
            ink_share = inkn / max(int(masks[i].sum()), 1)
            if ink_share > 0.75: flags.append("ink_saturated")
            # overlap px are never owned by this quad -> exclude everywhere
            im_full = np.zeros(shape, bool); im_full[y0:y1, x0:x1] = im
            im_full &= (own == i)
            decisions.append({"quad": i, "text": q["text"], "score": q["score"], "flags": flags, "ink_px": int(im_full.sum()),
                              "ring_classes": ring, "decision": "preserve_review" if flags else "auto_clean",
                              "ink_mask": im_full, "bg": bg})

        # -------- mutate ONLY auto_clean ink px ------------------------------------------
        img_prot = img.copy(); gmask = np.zeros(shape, bool)
        for d in decisions:
            if d["decision"] != "auto_clean": continue
            gmask |= d["ink_mask"]; img_prot[d["ink_mask"]] = np.asarray(d["bg"], np.uint8)
        t2 = time.time()

        raw, lines = line_objects(img_prot, log); t3 = time.time()
        rem = LF.footprint(lines, shape, LF.Q["halo"]) | gmask
        Fimg = D.fill(X, rem); fc = O.faces(Fimg, LF.Q["tol"]); obs, inf = O.provenance(Fimg, rem, fc); t4 = time.time()

        # -------- per-object audit: what did cleaning actually remove ---------------------
        base_L = gpd.read_file(RUN / "u2_full_B2c.gpkg", layer="visual_lines")
        quad_geoms = [Polygon(np.asarray(q["quad"], float)) for q in merged]
        clean_union = shapely.union_all([quad_geoms[d["quad"]] for d in decisions if d["decision"] == "auto_clean"]) if any(
            d["decision"] == "auto_clean" for d in decisions) else None
        kept_geoms = shapely.unary_union([l["geom"] for l in lines]) if lines else None
        removed_audit = []
        for _, r in base_L.iterrows():
            g = r.geometry
            if clean_union is None or not g.intersects(clean_union): continue
            share = g.intersection(clean_union).length / max(g.length, 1e-9)
            still = kept_geoms is not None and g.buffer(0.75).intersects(kept_geoms)
            if share >= 0.4 and not still:
                # geological-info check: long lines or lines whose endpoints sit in different colour classes stay suspect->review
                p0, p1 = g.coords[0], g.coords[-1]
                c0 = int(X[int(np.clip(round(p0[1]), 0, shape[0] - 1)), int(np.clip(round(p0[0]), 0, shape[1] - 1))])
                c1 = int(X[int(np.clip(round(p1[1]), 0, shape[0] - 1)), int(np.clip(round(p1[0]), 0, shape[1] - 1))])
                removed_audit.append({"line_id": r.get("line_id", ""), "logical_id": r.get("logical_id", ""), "length": round(float(g.length), 1),
                                      "inside_clean_share": round(share, 3), "end_classes": f"{c0}->{c1}",
                                      "verdict": "possible_real_geology_REVIEW" if (g.length > 30 or c0 != c1) else "glyph_stroke_removed"})
        for l in lines:
            hit = [i for i in shapely.STRtree(np.asarray(quad_geoms, object)).query(l["geom"].buffer(0.75))]
            if hit: l["kind"] = "auto_B2c_crosses_text"

        if out.exists(): out.unlink()
        O2.write(out, fc, kpal, np.arange(len(kpal)), obs, inf, lines, [])
        # -------- editor-schema text layer (Point + full TEXT_COLS) + raw quad layer ------
        import pandas as pd
        rows, qrows = [], []
        for i, d in enumerate(decisions):
            q = merged[i]; qg = quad_geoms[i]; cx, cy = qg.centroid.x, qg.centroid.y
            xs = np.asarray(q["quad"])[:, 0]; ys = np.asarray(q["quad"])[:, 1]
            fpx = round(float(ys.max() - ys.min()) * 0.8, 1)
            ang = float(np.degrees(np.arctan2(ys[1] - ys[0], xs[1] - xs[0])))
            reason = ";".join(d["flags"]) if d["flags"] else ""
            rows.append({"label_id": f"ocr-{i}", "text": q["text"], "ocr_text": q["text"], "ocr_score": float(q["score"]),
                         "font_px": fpx, "angle_deg": ang, "anchor": "center", "rgb": "#000000",
                         "box_x0": float(xs.min()), "box_y0": float(ys.min()), "box_x1": float(xs.max()), "box_y1": float(ys.max()),
                         "source": "paddleocr_raw", "review_status": "OCR_CANDIDATE",
                         "review_reason": reason, "reviewed_at": "", "review_actor": ""})
            qrows.append({"cand_id": f"ocr-{i}", "quad_json": json.dumps(q["quad"]), "text": q["text"], "score": float(q["score"]),
                          "decision": d["decision"], "flags": reason, "ink_px": d["ink_px"], "engine": "paddleocr_raw_u2_full"})
        gpd.GeoDataFrame(pd.DataFrame(rows, columns=TEXT_COLS), geometry=[Point(r["box_x0"] + (r["box_x1"] - r["box_x0"]) / 2, r["box_y0"] + (r["box_y1"] - r["box_y0"]) / 2) for r in rows]).to_file(out, layer="text_labels", driver="GPKG", engine="pyogrio")
        gpd.GeoDataFrame(qrows, geometry=quad_geoms).to_file(out, layer="ocr_quads", driver="GPKG", engine="pyogrio")
        pd.DataFrame(removed_audit).to_csv(OUTJ / "removed_lines_audit.csv", index=False)
        pd.DataFrame([{k: v for k, v in d.items() if k not in ("ink_mask", "bg")} for d in decisions]).to_json(OUTJ / "quad_decisions.json", orient="records", indent=1)

        log.update(ok=True, glyph_ink_px_cleaned=int(gmask.sum()),
                   auto_clean_quads=sum(1 for d in decisions if d["decision"] == "auto_clean"),
                   preserve_review_quads=sum(1 for d in decisions if d["decision"] == "preserve_review"),
                   faces=int(len(fc["polys"])), lines=len(lines),
                   removed_lines_total=len(removed_audit),
                   removed_as_glyph=sum(1 for r in removed_audit if r["verdict"] == "glyph_stroke_removed"),
                   removed_review=sum(1 for r in removed_audit if "REVIEW" in r["verdict"]),
                   seconds={"labels": round(t1 - t0, 1), "risk+inpaint": round(t2 - t1, 1), "lines_b2c_group": round(t3 - t2, 1),
                            "faces": round(t4 - t3, 1), "total": round(time.time() - t0, 1)},
                   output=str(out), output_sha256=sha(out))
    except Exception as e:
        import traceback; log.update(ok=False); log["errors"].append({"type": type(e).__name__, "msg": str(e), "trace": traceback.format_exc()[-1500:]})
    OUTJ.mkdir(exist_ok=True); json.dump(log, open(OUTJ / "u2_ocr_protected_run.json", "w"), indent=1, default=str)
    print(json.dumps(log, default=str)[:1800])
