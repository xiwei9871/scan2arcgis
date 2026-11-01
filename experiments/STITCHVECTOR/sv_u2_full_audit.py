"""U2 full-sheet audit (read-only on B2c; text clearing runs on a copy through the editor core).

Inputs (local, not in git): runs/stitchvector/u2_full/{u2_map.png, u2_full_B2c.gpkg, u2_ocr_full.json}
Truth available: ONLY the 300x300 Oracle crop (offset y240 x711 in work.png). Inside the map box (805x780) that is
x 711-805, y 240-540 = 94 x 300 px (4.5 % of the map). Everything outside is PENDING_REVIEW / NOT_EVALUATED.
Text clearing uses the AUTOMATIC OCR strings (no human text). Uncertain residue groups are never merged.
Outputs: experiments/STITCHVECTOR/u2_full/*.csv|json (public), runs/stitchvector/u2_full/* (local GPKG/PNG).
"""
import csv, hashlib, json, shutil, sys, time
from pathlib import Path
import numpy as np, pyogrio, shapely, shapely.affinity
from shapely.geometry import LineString, box as sbox
from PIL import Image, ImageDraw
from skimage.color import rgb2lab
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from tools.stitchvector_editor.core import Document, coverage_report  # noqa: E402

RUN = Path.home() / "geomap2arcgis/runs/stitchvector/u2_full"; OUT = ROOT / "experiments/STITCHVECTOR/u2_full"
IMG, GP, OCR = RUN / "u2_map.png", RUN / "u2_full_B2c.gpkg", RUN / "u2_ocr_full.json"
B2C_300 = Path.home() / "geomap2arcgis/runs/stitchvector/editor_v01/inputs/u2_B2c.gpkg"
WORK_JSON = Path.home() / "geomap2arcgis/runs/real/u2/work.json"
ORA = ROOT / "experiments/STITCHVECTOR/oracle/u2_300_oracle.json"
OX, OY = 711, 240                                        # oracle crop offset in work.png == map coordinates (map box starts at 0,0)
SMALL = 5.0


def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()
def lab(rgbs): return rgb2lab(np.asarray(rgbs, float).reshape(-1, 1, 3) / 255).reshape(-1, 3)
def hexrgb(s): return [int(s[i:i + 2], 16) for i in (1, 3, 5)]
def wcsv(name, rows):
    with open(OUT / name, "w", newline="") as f:
        if not rows: f.write(""); return
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)


def ocr_boxes(items, W, H):
    """dedupe the two OCR scales by IoU > 0.3 (keep the higher score); axis-aligned boxes, clipped to the map."""
    bx = []
    for it in items:
        q = np.asarray(it["quad"]); x0, y0 = q.min(0); x1, y1 = q.max(0)
        x0, y0, x1, y1 = max(0, x0), max(0, y0), min(W, x1), min(H, y1)
        if x1 - x0 < 2 or y1 - y0 < 2: continue
        bx.append({"text": it["text"], "score": it["score"], "scale": it["scale"], "box": [float(x0), float(y0), float(x1), float(y1)]})
    bx.sort(key=lambda b: -b["score"]); keep = []
    for b in bx:
        g = sbox(*b["box"])
        if all(g.intersection(sbox(*k["box"])).area / g.union(sbox(*k["box"])).area <= 0.3 for k in keep): keep.append(b)
    for i, b in enumerate(sorted(keep, key=lambda b: (b["box"][1], b["box"][0]))): b["tid"] = f"T{i:03d}"
    return sorted(keep, key=lambda b: b["tid"])



def _ora_crop():
    """the 300x300 centre crop of work.png the Oracle waypoints were drawn on (offset y240 x711)."""
    import sv_common as Cm
    full = np.asarray(Image.open(Path.home() / "geomap2arcgis/runs/real/u2/work.png").convert("RGB"))   # read-only
    a, off = Cm.centre_crop(full, 300, 300); assert tuple(off) == (OY, OX), off
    return a

def main():
    t0 = time.time(); OUT.mkdir(parents=True, exist_ok=True)
    img = np.asarray(Image.open(IMG).convert("RGB")); H, W = img.shape[:2]
    F = pyogrio.read_dataframe(GP, layer="colour_faces"); L = pyogrio.read_dataframe(GP, layer="visual_lines")
    src_sha = sha(GP); b300 = sha(B2C_300)
    window = sbox(OX, OY, min(OX + 300, W), min(OY + 300, H))
    ora = json.load(open(ORA))
    for l in ora["lines"]:
        if isinstance(l.get("waypoints"), str): l["waypoints"] = json.loads(l["waypoints"])
    import sv_oracle as O
    olines = [shapely.affinity.translate(LineString(f["raw"]), OX, OY) for f in O.build_lines(_ora_crop(), ora, O.P, 0)[0]]
    olines = [g for g in olines if g.length > 0]; O_U = shapely.union_all(olines)
    o_in_map = shapely.intersection(O_U, sbox(0, 0, W, H)); oracle_len_in_map = float(o_in_map.length)
    T = ocr_boxes(json.load(open(OCR))["items"], W, H); TU = shapely.union_all([sbox(*b["box"]) for b in T])
    sw = json.load(open(WORK_JSON))["swatches"]; sw_lab = lab([s["fill_rgb"] for s in sw])

    # ---------------- T2 faces ----------------
    g = np.asarray(F.geometry.values, object); area = shapely.area(g); Lbuf = shapely.union_all([x.buffer(max(float(w) / 2, 0.71) + 1) for x, w in zip(L.geometry, L["width_px"])])
    near_line = shapely.intersects(g, Lbuf); in_text = shapely.area(shapely.intersection(g, TU)) >= 0.5 * area
    in_win = shapely.intersects(g, window); classes = F["rgb"].values; cls_lab = {c: lab([hexrgb(c)])[0] for c in set(classes)}
    cls_sw = {c: (sw[int(np.argmin(np.linalg.norm(sw_lab - v, axis=1)))]["legend_entry_id"], round(float(np.min(np.linalg.norm(sw_lab - v, axis=1))), 1)) for c, v in cls_lab.items()}
    face_rows = []
    for i, (gg, a, c) in enumerate(zip(g, area, classes)):
        small = a <= SMALL; cause = "text_box" if in_text[i] else ("line_footprint" if near_line[i] else "other")
        st = "PENDING_REVIEW" if (small or cls_sw[c][1] > 15) else ("PENDING_REVIEW" if not in_win[i] else "PENDING_REVIEW")
        pt = gg.representative_point()
        face_rows.append({"face_id": i, "x": round(pt.x, 1), "y": round(pt.y, 1), "area_px2": a, "rgb": c, "nearest_legend_swatch": cls_sw[c][0],
                          "swatch_dE": cls_sw[c][1], "small_le5px2": bool(small), "likely_source": cause if small else "", "in_truth_window": bool(in_win[i]),
                          "status": st})
    wcsv("u2_face_audit.csv", face_rows)
    per_class = {}
    for c in set(classes):
        m = classes == c; per_class[c] = {"faces": int(m.sum()), "area_px2": float(area[m].sum()), "small_faces": int((m & (area <= SMALL)).sum()),
                                          "largest_px2": float(area[m].max()), "nearest_swatch": cls_sw[c][0], "swatch_dE": cls_sw[c][1]}
    sm = area <= SMALL
    face_sum = {"faces": len(F), "colour_classes": len(per_class), "legend_swatches": len(sw), "per_class": per_class,
                "small_faces": int(sm.sum()), "small_face_area_px2": float(area[sm].sum()), "small_share_of_faces": round(float(sm.mean()), 3),
                "small_by_source": {k: int((sm & mm).sum()) for k, mm in (("text_box", in_text), ("line_footprint", near_line & ~in_text), ("other", ~near_line & ~in_text))},
                "area_quantiles": [float(x) for x in np.quantile(area, [0.5, 0.9, 0.99, 1.0])], "coverage": coverage_report(F, W, H),
                "semantic_truth": "none: no per-unit ground truth exists for u2; nearest legend swatch by colour only (candidate, not a classification)"}

    # ---------------- T3 lines ----------------
    line_rows = []; Lw = L.geometry.values
    for i, (ln, r) in enumerate(zip(Lw, L.itertuples())):
        win_part = ln.intersection(window); cov = None
        if win_part.length > 0: cov = round(float(win_part.intersection(O_U.buffer(2.5)).length / win_part.length), 3)
        inbox = float(ln.intersection(TU).length / ln.length) if ln.length else 0
        flags = []
        if ln.length < 10: flags.append("short_lt10px")
        if inbox >= 0.9: flags.append("inside_text_box")
        elif inbox > 0: flags.append("crosses_text_box")
        line_rows.append({"line_eid": i, "line_id": r.line_id, "logical_id": r.logical_id, "length_px": round(ln.length, 1), "width_px": r.width_px, "rgb": r.rgb,
                          "x0": round(ln.coords[0][0], 1), "y0": round(ln.coords[0][1], 1), "x1": round(ln.coords[-1][0], 1), "y1": round(ln.coords[-1][1], 1),
                          "share_in_text_boxes": round(inbox, 2), "flags": " ".join(flags), "in_truth_window": win_part.length > 0,
                          "oracle_cover_2p5px_in_window": cov, "status": "PENDING_REVIEW"})
    wcsv("u2_line_audit.csv", line_rows)
    # oracle recall inside the window: share of oracle length within 2.5 px of any B2c line
    LU = shapely.union_all(list(Lw)); o_rec = float(o_in_map.intersection(LU.buffer(2.5)).length / max(oracle_len_in_map, 1e-9))
    lw_in = shapely.intersection(LU, window); l_prec = float(lw_in.intersection(O_U.buffer(2.5)).length / max(lw_in.length, 1e-9))
    lens = np.array([x.length for x in Lw])
    line_sum = {"lines": len(L), "logical_groups": int(L["logical_id"].nunique()), "total_length_px": round(float(lens.sum()), 1),
                "short_lt10px": int((lens < 10).sum()), "inside_text_boxes": sum("inside_text_box" in r["flags"] for r in line_rows),
                "crossing_text_boxes": sum("crosses_text_box" in r["flags"] for r in line_rows),
                "truth_window": {"oracle_lines": len(olines), "oracle_length_in_map_px": round(oracle_len_in_map, 1),
                                 "recall_2p5px": round(o_rec, 3), "precision_2p5px_vs_oracle": round(l_prec, 3),
                                 "note": "Oracle traces only part of the linework (no text, no symbols) -> precision is a lower bound"}}

    # ---------------- T4 text ----------------
    known = {"Є-O": (3, 25, 35, 42), "Ar₂E": (0, 196, 52, 225), "云": (24, 59, 41, 76)}   # human-confirmed earlier (crop coords)
    truth = {k: sbox(b[0] + OX, b[1] + OY, b[2] + OX, b[3] + OY) for k, b in known.items()}
    text_rows = []; matched = set()
    for b in T:
        G = sbox(*b["box"]); m = [k for k, tb in truth.items() if G.intersection(tb).area > 0.3 * min(G.area, tb.area)]
        ok = None
        if m: matched |= set(m); ok = b["text"] == m[0]
        inwin = G.intersects(window)
        text_rows.append({"text_id": b["tid"], "ocr_text": b["text"], "ocr_score": b["score"], "ocr_scale": b["scale"], "x0": round(b["box"][0], 1), "y0": round(b["box"][1], 1),
                          "x1": round(b["box"][2], 1), "y1": round(b["box"][3], 1), "in_truth_window": inwin, "truth_text": m[0] if m else "",
                          "ocr_correct": "" if ok is None else ok,
                          "status": ("FAIL" if ok is False else "PASS" if ok else ("PENDING_REVIEW" if inwin else "PENDING_REVIEW"))})
    for k in truth:
        if k not in matched: text_rows.append({"text_id": "MISS", "ocr_text": "", "ocr_score": "", "ocr_scale": "", "x0": truth[k].bounds[0], "y0": truth[k].bounds[1],
                                               "x1": truth[k].bounds[2], "y1": truth[k].bounds[3], "in_truth_window": True, "truth_text": k, "ocr_correct": False, "status": "FAIL"})
    wcsv("u2_text_recognition_audit.csv", text_rows)
    sc = np.array([b["score"] for b in T])
    text_sum = {"ocr_raw_items": len(json.load(open(OCR))["items"]), "text_boxes_after_dedup": len(T), "score_lt_0p8": int((sc < 0.8).sum()),
                "truth_labels": len(truth), "truth_matched_by_box": len(matched), "truth_text_correct": sum(1 for r in text_rows if r["ocr_correct"] is True),
                "truth_missed": len(truth) - len(matched), "truth_note": "only 3 human-confirmed labels exist (all in the Oracle window); full-sheet precision/recall NOT_EVALUATED"}

    # ---------------- T5 automatic text clearing on a copy + change audit ----------------
    work = RUN / "u2_full_text_input_copy.gpkg"; shutil.copyfile(GP, work)
    doc = Document(work, (W, H), img); F0 = doc.F.set_index("_eid").copy(); L0 = doc.L.set_index("_eid").copy()
    tlog = []; tc = time.time()
    # Speed: text_apply() runs coverage_report() on the whole face layer after every box (8-9 s at 17k faces).
    # During the loop use a local check (merged faces valid single Polygons); the full strict coverage check runs
    # once on the final layer in save_as() and in the audit below. The editor core itself is not changed.
    import tools.stitchvector_editor.core as CORE
    _full_cov = CORE.coverage_report
    def _local_cov(F, W_, H_):
        g = np.asarray(F.loc[F["source"] == "edited_text_clean", "geometry"].values, object)
        ok = bool(len(g) == 0 or (shapely.is_valid(g).all() and all(x.geom_type == "Polygon" for x in g)))
        return {"accepted": ok, "coverage_is_valid": ok, "local_check": True}
    CORE.coverage_report = _local_cov
    for b in T:
        try:
            pv = doc.text_preview(b["box"], ocr=False)
            if not pv["counts"]["residue_faces"] and not pv["counts"]["residue_lines"]: tlog.append({"tid": b["tid"], "skipped": "no residue"}); continue
            r = doc.text_apply(pv["preview_id"], b["text"] or "?")
            tlog.append({"tid": b["tid"], "counts": pv["counts"], "groups": pv["groups"], "lines": pv["lines"], "applied": r})
        except Exception as e: tlog.append({"tid": b["tid"], "error": str(e)[:160]})
    CORE.coverage_report = _full_cov
    t_clear = round(time.time() - tc, 1)
    cleared = RUN / "u2_full_text_cleared.gpkg"
    if cleared.exists(): cleared.unlink()
    sv = doc.save_as(cleared)
    F1 = doc.F.set_index("_eid"); L1 = doc.L.set_index("_eid"); Qd = doc.Q
    allowed = shapely.union_all([sbox(*b["box"]).buffer(1) for b in T])
    topo_rows = []
    gid = {}
    for t in tlog:
        for gr in t.get("groups", []):
            for e in gr["faces"]: gid[e] = (t["tid"], gr["decision"], gr.get("target"))
    for e in F0.index:
        a = F0.at[e, "geometry"]
        if e not in F1.index:
            tid, dec, tgt = gid.get(e, ("", "", ""))
            topo_rows.append({"layer": "face", "object": e, "change": "merged_into_ground", "into": tgt, "text_id": tid, "x": round(a.centroid.x, 1), "y": round(a.centroid.y, 1),
                              "area_px2": a.area, "inside_allowed_zone": bool(a.within(allowed)), "status": "PENDING_REVIEW"})
        elif not a.equals_exact(F1.at[e, "geometry"], 1e-9):
            grow = F1.at[e, "geometry"].difference(a); out = grow.difference(allowed).area
            topo_rows.append({"layer": "face", "object": e, "change": "grew (absorbed residue)", "into": "", "text_id": "", "x": round(a.centroid.x, 1), "y": round(a.centroid.y, 1),
                              "area_px2": round(grow.area, 1), "inside_allowed_zone": out < 1e-6, "status": "PASS" if out < 1e-6 else "FAIL"})
    lid_parts = L0.groupby("logical_id").size().to_dict()
    for e in L0.index:
        if e in L1.index: continue
        ln = L0.at[e, "geometry"]; grp = L0.at[e, "logical_id"]; multi = lid_parts.get(grp, 1) > 1
        risk = "group has parts outside the box (possible real line)" if multi else ("long (>25 px)" if ln.length > 25 else "")
        topo_rows.append({"layer": "line", "object": e, "change": "moved_to_text_residue_lines (restorable)", "into": "", "text_id": "", "x": round(ln.centroid.x, 1), "y": round(ln.centroid.y, 1),
                          "area_px2": round(ln.length, 1), "inside_allowed_zone": bool(ln.within(allowed)), "status": "PENDING_REVIEW" + (f": {risk}" if risk else "")})
    wcsv("u2_topology_changes.csv", topo_rows)
    unc = [(t["tid"], gr) for t in tlog for gr in t.get("groups", []) if gr["decision"] == "uncertain"]
    # outside-zone pixel check on the face raster
    def raster(D):
        import rasterio.features as RF
        from affine import Affine
        code = {c: i + 1 for i, c in enumerate(sorted(set(F0["rgb"]) | set(F1["rgb"])))}
        return RF.rasterize([(gg, code[c]) for gg, c in zip(D.geometry, D["rgb"])], out_shape=(H, W), transform=Affine.identity(), dtype="int32")
    import rasterio.features as RF
    from affine import Affine
    zone = RF.rasterize([(allowed, 1)], out_shape=(H, W), transform=Affine.identity(), dtype="uint8") > 0
    diff = raster(F0) != raster(F1)
    lines_outside_changed = [e for e in L0.index if not L0.at[e, "geometry"].intersects(allowed) and (e not in L1.index or not L0.at[e, "geometry"].equals_exact(L1.at[e, "geometry"], 1e-9))]
    topo_sum = {"text_boxes_processed": len(T), "boxes_with_residue": sum(1 for t in tlog if "applied" in t), "errors": [t for t in tlog if "error" in t],
                "faces_before_after": [len(F0), len(F1)], "lines_before_after": [len(L0), len(L1)], "lines_moved_to_residue": len(Qd),
                "faces_merged": sum(1 for r in topo_rows if r["change"] == "merged_into_ground"), "uncertain_groups_left": len(unc),
                "uncertain_faces_left": sum(len(gr["faces"]) for _, gr in unc), "face_px_changed": int(diff.sum()),
                "face_px_changed_outside_allowed_zone": int((diff & ~zone).sum()), "lines_not_touching_boxes_changed": len(lines_outside_changed),
                "moved_lines_in_multi_part_groups": sum(1 for r in topo_rows if r["layer"] == "line" and "possible real line" in r["status"]),
                "coverage_after": coverage_report(doc.F, W, H), "save": {k: sv[k] for k in ("accepted", "readback_matches_memory", "input_sha256_unchanged")},
                "seconds": t_clear, "text_used": "automatic OCR strings (not human-confirmed)"}

    # ---------------- T6 review queue ----------------
    q = []
    for tid, gr in unc: q.append({"priority": 1, "kind": "uncertain_residue_group", "ref": f"{tid}:{gr['faces'][:6]}", "x": "", "y": "", "why": gr["reason"], "action": "assign to a ground face or skip"})
    for r in topo_rows:
        if r["layer"] == "line" and "possible real line" in r["status"]: q.append({"priority": 1, "kind": "isolated_line_in_group", "ref": f"line {r['object']}", "x": r["x"], "y": r["y"], "why": r["status"], "action": "restore if geological"})
    for r in text_rows:
        if r["ocr_score"] != "" and float(r["ocr_score"]) < 0.8: q.append({"priority": 2, "kind": "low_confidence_text", "ref": r["text_id"], "x": r["x0"], "y": r["y0"], "why": f"OCR '{r['ocr_text']}' {r['ocr_score']}", "action": "confirm or correct text"})
        if r["status"] == "FAIL": q.append({"priority": 1, "kind": "wrong_or_missed_text", "ref": r["text_id"], "x": r["x0"], "y": r["y0"], "why": f"OCR '{r['ocr_text']}' vs truth '{r['truth_text']}'", "action": "correct text"})
    for r in line_rows:
        if "short_lt10px" in r["flags"] and "inside_text_box" not in r["flags"]: q.append({"priority": 3, "kind": "short_line", "ref": f"line {r['line_eid']}", "x": r["x0"], "y": r["y0"], "why": f"{r['length_px']} px", "action": "connect, keep or delete"})
    # small faces clustered away from text and lines: one queue item per 20x20 cell
    cells = {}
    for r in face_rows:
        if r["small_le5px2"] and r["likely_source"] == "other": cells.setdefault((int(r["x"] // 20), int(r["y"] // 20)), []).append(r["face_id"])
    for (cx, cy), ids in sorted(cells.items(), key=lambda kv: -len(kv[1])):
        if len(ids) >= 10: q.append({"priority": 2, "kind": "small_face_cluster", "ref": f"{len(ids)} faces", "x": cx * 20 + 10, "y": cy * 20 + 10, "why": "<=5 px2 faces not under text or lines", "action": "heal brush / lasso merge"})
    q.sort(key=lambda r: r["priority"]); wcsv("u2_manual_review_queue.csv", q)

    # ---------------- problem map (local PNG) ----------------
    vis = Image.fromarray((img * 0.45 + 255 * 0.55).astype(np.uint8)); d = ImageDraw.Draw(vis)
    for r in face_rows:
        if r["small_le5px2"]: d.point((r["x"], r["y"]), fill={"text_box": (160, 0, 200), "line_footprint": (230, 120, 0), "other": (220, 0, 0)}[r["likely_source"]])
    for b in T: d.rectangle(b["box"], outline=(0, 90, 220))
    for r in topo_rows:
        if r["layer"] == "line": d.ellipse((r["x"] - 3, r["y"] - 3, r["x"] + 3, r["y"] + 3), outline=(0, 160, 0))
    d.rectangle(window.bounds, outline=(0, 0, 0), width=2); vis = vis.resize((W * 2, H * 2), Image.NEAREST); vis.save(RUN / "u2_problem_map_x2.png")

    # ---------------- summary + statuses ----------------
    S = {"inputs": {"map_png": str(IMG), "map_sha256": sha(IMG), "b2c_full_gpkg": str(GP), "b2c_full_sha256": src_sha, "b2c_full_sha256_after": sha(GP),
                    "b2c_300_editor_input_sha256_unchanged": sha(B2C_300) == b300, "ocr_json": str(OCR)},
         "truth_coverage": {"map_px": W * H, "oracle_window_px_in_map": int(window.area), "share": round(window.area / (W * H), 3),
                            "text_truth_labels": 3, "face_unit_truth": 0},
         "faces": face_sum, "lines": line_sum, "text": text_sum, "topology_text_clearing": topo_sum, "review_queue_items": len(q),
         "outputs_local": {"cleared_gpkg": str(cleared), "cleared_sha256": sha(cleared), "problem_map_png": str(RUN / "u2_problem_map_x2.png"),
                           "problem_map_sha256": sha(RUN / "u2_problem_map_x2.png")},
         "status": {
             "faces_geometry_validity": "PASS" if face_sum["coverage"]["accepted"] else "FAIL",
             "faces_semantic_classification": "NOT_EVALUATED (no unit truth; colour classes only)",
             "faces_fragmentation": f"FAIL ({face_sum['small_faces']} of {len(F)} faces are <= 5 px2)",
             "lines_vs_oracle_window": f"PENDING_REVIEW (recall {line_sum['truth_window']['recall_2p5px']} on 4.5% of the map; rest not evaluated)",
             "lines_outside_window": "NOT_EVALUATED",
             "text_detection_full_sheet": "NOT_EVALUATED (no full-sheet text truth)",
             "text_ocr_on_3_known_labels": f"{text_sum['truth_text_correct']} of 3 correct",
             "text_clearing_face_protection": "PASS" if topo_sum["face_px_changed_outside_allowed_zone"] == 0 else "FAIL",
             "text_clearing_line_protection": "PENDING_REVIEW" if topo_sum["lines_not_touching_boxes_changed"] == 0 else "FAIL",
             "joint_topology_after_clearing": "PASS" if topo_sum["coverage_after"]["accepted"] else "FAIL"},
         "seconds": round(time.time() - t0, 1)}
    json.dump(S, open(OUT / "u2_validation_summary.json", "w"), indent=1, ensure_ascii=False, default=str)
    json.dump(tlog, open(OUT / "u2_text_clearing_log.json", "w"), indent=1, ensure_ascii=False, default=str)
    print(json.dumps(S["status"], ensure_ascii=False, indent=1)); print("seconds", S["seconds"])


if __name__ == "__main__":
    main()
