"""Text Layer V0.1 human-UAT pack (read-only analysis of existing outputs; nothing is merged or edited).

Inputs : runs/stitchvector/editor_v01/inputs/u2_B2c.gpkg (original B2c), u2_original.png,
         runs/stitchvector/editor_text/demo/u2_text_demo.gpkg (demo built by sv_text_demo.py).
Outputs: experiments/STITCHVECTOR/text_layer/uat_metrics.json, ar2e_pending_fragments.csv / .json
The 'suggested' target for each Ar2E pending fragment is a hint (nearest original-scan colour of the candidate
ground faces); it is NOT applied and NOT a geological decision.
"""
import csv, hashlib, json, sys
from pathlib import Path
import numpy as np, shapely
from PIL import Image
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from tools.stitchvector_editor.core import Document, coverage_report, _lab_px  # noqa: E402

RUNS = Path.home() / "geomap2arcgis/runs/stitchvector"
SRC = RUNS / "editor_v01/inputs/u2_B2c.gpkg"; IMG = RUNS / "editor_v01/inputs/u2_original.png"
DEMO = RUNS / "editor_text/demo/u2_text_demo.gpkg"
BOXES = {"Є-O": (3, 25, 35, 42), "Ar₂E": (0, 196, 52, 225), "云": (24, 59, 41, 76)}
OUT = ROOT / "experiments/STITCHVECTOR/text_layer"


def sha(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()


def box_residue(doc, B, lab, max_area=60.0):
    g = np.asarray(doc.F.geometry.values, object); a = shapely.area(g)
    m = (a <= max_area) & (a > 0) & (shapely.area(shapely.intersection(g, B)) >= 0.5 * a)
    fid = doc._face_pixels(); dark = 0; dark_area = 0.0
    for e, gg in zip(doc.F["_eid"][m], g[m]):
        px = fid == e
        if px.any() and np.median(lab[px][:, 0]) < 50: dark += 1; dark_area += float(gg.area)
    lines = sum(1 for ln in doc.L.geometry if ln.length > 0 and ln.intersection(B).length >= 0.9 * ln.length)
    return {"small_faces": int(m.sum()), "small_face_area": float(shapely.area(g[m]).sum()), "dark_glyph_faces": dark,
            "dark_glyph_area": dark_area, "lines_inside": lines}


def glyph_bbox(lab, b):
    x0, y0, x1, y1 = b; L = lab[y0:y1, x0:x1, 0]; ys, xs = np.nonzero(L < 50)
    if not len(xs): return None
    return [int(x0 + xs.min()), int(y0 + ys.min()), int(x0 + xs.max() + 1), int(y0 + ys.max() + 1)]


if __name__ == "__main__":
    s0 = sha(SRC); img = np.asarray(Image.open(IMG).convert("RGB")); lab = _lab_px(img)
    A = Document(SRC, (300, 300), img); D = Document(DEMO, (300, 300), img)
    R = {"inputs": {"b2c": str(SRC), "b2c_sha256": s0, "demo": str(DEMO), "demo_sha256": sha(DEMO)}, "boxes": {}}
    U = shapely.union_all([shapely.box(*b) for b in BOXES.values()])
    # 1) text clearance + 3) text reconstruction position/size
    for t, b in BOXES.items():
        B = shapely.box(*b); before, after = box_residue(A, B, lab), box_residue(D, B, lab)
        gb = glyph_bbox(lab, b); lbl = D.T[D.T["text"] == t].iloc[0]
        gc = None if gb is None else [(gb[0] + gb[2]) / 2, (gb[1] + gb[3]) / 2]
        R["boxes"][t] = {"box": b, "before": before, "after": after,
                         "dark_glyph_area_removed_share": round(1 - after["dark_glyph_area"] / before["dark_glyph_area"], 3) if before["dark_glyph_area"] else None,
                         "label": {"x": float(lbl.geometry.x), "y": float(lbl.geometry.y), "font_px": float(lbl["font_px"]), "ocr_text": lbl["ocr_text"]},
                         "scan_glyph_bbox": gb, "scan_glyph_centre": gc,
                         "label_centre_offset_px": None if gc is None else round(float(np.hypot(lbl.geometry.x - gc[0], lbl.geometry.y - gc[1])), 2),
                         "scan_glyph_height_px": None if gb is None else gb[3] - gb[1],
                         "font_px_over_glyph_height": None if gb is None else round(float(lbl["font_px"]) / (gb[3] - gb[1]), 2)}
    # 2) boundary fidelity outside the boxes
    fa, fb = A.F, D.F
    rgbs = set(fa["rgb"]) | set(fb["rgb"])
    def col_area(F, rgb, region): return float(shapely.area(shapely.intersection(shapely.union_all(list(F.loc[F["rgb"] == rgb, "geometry"])), region))) if (F["rgb"] == rgb).any() else 0.0
    win = shapely.box(0, 0, 300, 300)
    out0, out1 = win.difference(U), win.difference(U.buffer(1))
    R["boundary_fidelity"] = {
        "colour_area_change_outside_boxes_px2": round(sum(abs(col_area(fa, c, out0) - col_area(fb, c, out0)) for c in rgbs), 3),
        "colour_area_change_outside_boxes_plus1px_px2": round(sum(abs(col_area(fa, c, out1) - col_area(fb, c, out1)) for c in rgbs), 3),
        "lines_not_touching_boxes_changed": [r for r, g in zip(A.L["line_id"], A.L.geometry) if not g.intersects(U)
                                             and not any(g.equals_exact(h, 1e-9) for h in D.L.geometry)],
        "lines_moved_to_residue": sorted(D.Q["line_id"]), "coverage_valid": coverage_report(D.F, 300, 300)["accepted"]}
    # 4) Ar2E pending fragments
    pend = [p for p in D.pending_residue() if p["text"] == "Ar₂E"]
    fid = D._face_pixels(); geo = dict(zip(D.F["_eid"], D.F.geometry)); rgb = dict(zip(D.F["_eid"], D.F["rgb"])); rows = []
    ground_lab = {}
    for p in pend:
        for e in p["faces"]:
            g = geo[e]; px = fid == e; c = g.representative_point()
            own = np.median(lab[px], 0) if px.any() else lab[int(c.y), int(c.x)]
            nb = D._edge_neighbours(e); grounds = {k: v for k, v in nb.items() if geo[k].area > 60}
            opts = []
            for k, s in sorted(grounds.items(), key=lambda kv: -kv[1]):
                if k not in ground_lab:
                    m = (fid == k) & shapely.contains_xy(shapely.box(*BOXES["Ar₂E"]).buffer(6), *np.meshgrid(np.arange(300) + 0.5, np.arange(300) + 0.5))
                    ground_lab[k] = np.median(lab[m], 0) if m.any() else np.median(lab[fid == k], 0)
                opts.append({"face": int(k), "rgb": rgb[k], "area": float(geo[k].area), "shared_edge_px": float(s),
                             "scan_dE": round(float(np.linalg.norm(own - ground_lab[k])), 1)})
            sug = min(opts, key=lambda o: o["scan_dE"]) if opts else None
            rows.append({"fragment": f"P{len(rows) + 1:02d}", "face_id": int(e), "x": round(c.x, 1), "y": round(c.y, 1), "area_px2": float(g.area),
                         "rgb": rgb[e], "scan_L": round(float(own[0]), 1), "dark_glyph": bool(own[0] < 50),
                         "neighbours": [int(k) for k in nb], "ground_options": opts,
                         "suggested_face": None if sug is None else sug["face"], "suggested_rgb": None if sug is None else sug["rgb"],
                         "suggestion_basis": "nearest original-scan colour among candidate ground faces (hint only, not applied)",
                         "status": "PENDING_HUMAN"})
    R["ar2e_pending"] = {"count": len(rows), "area_px2": sum(r["area_px2"] for r in rows), "dark_glyph": sum(r["dark_glyph"] for r in rows)}
    json.dump(rows, open(OUT / "ar2e_pending_fragments.json", "w"), indent=1, ensure_ascii=False)
    with open(OUT / "ar2e_pending_fragments.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["fragment", "face_id", "x", "y", "area_px2", "rgb", "scan_L", "dark_glyph", "neighbours", "ground_options", "suggested_face", "suggested_rgb", "status"])
        for r in rows: w.writerow([r["fragment"], r["face_id"], r["x"], r["y"], r["area_px2"], r["rgb"], r["scan_L"], r["dark_glyph"], " ".join(map(str, r["neighbours"])),
                                   "; ".join(f"{o['face']}({o['rgb']},edge {o['shared_edge_px']:.0f},dE {o['scan_dE']})" for o in r["ground_options"]), r["suggested_face"], r["suggested_rgb"], r["status"]])
    # 5) regression
    R["regression"] = {"b2c_sha256_unchanged": sha(SRC) == s0 == "7d78a7111320c2da1ce18006d05c8ecb5c2fc89c8b97c325801fa5ddde310d26"}
    json.dump(R, open(OUT / "uat_metrics.json", "w"), indent=1, ensure_ascii=False, default=str)
    for t, x in R["boxes"].items(): print(t, x["before"], "->", x["after"], "| removed", x["dark_glyph_area_removed_share"], "| offset", x["label_centre_offset_px"], "font/glyph", x["font_px_over_glyph_height"])
    print("fidelity", R["boundary_fidelity"]); print("pending", R["ar2e_pending"]); print("regression", R["regression"])
    for r in rows: print(r["fragment"], r["face_id"], r["x"], r["y"], r["area_px2"], r["rgb"], r["dark_glyph"], [(o["face"], o["rgb"], o["scan_dE"]) for o in r["ground_options"]], "->", r["suggested_face"])
