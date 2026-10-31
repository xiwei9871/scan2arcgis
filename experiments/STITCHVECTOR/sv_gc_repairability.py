"""Read-only repairability check of existing u2 GPKGs (no new run, no algorithm change).
Question: for the Oracle narrow bands PN1 / PN2, what geometry is left in each GPKG, and how much could be recovered
by recolouring existing faces or by recolouring / re-widening existing line objects, without adding or moving vertices?
Band geometry = Oracle protected axis + radius (evaluation only). Usage: sv_gc_repairability.py <json_out>  (.venv-sv)"""
import json, sys
from pathlib import Path
import numpy as np, shapely, pyogrio
from shapely.geometry import LineString

ROOT = Path(__file__).resolve().parents[2]; R = ROOT / "runs/stitchvector"
ORA = json.load(open(Path(__file__).with_name("oracle") / "u2_300_oracle.json"))
FILES = {"F0": R / "v3_u2_real/gpkg/u2_F0.gpkg", "B0": R / "v3_u2_real/gpkg/u2_B0.gpkg", "B2c": R / "v3_u2_real/gpkg/u2_B2c.gpkg",
         "Oracle_class_tol0": R / "oracle_u2_300_v2/O1_class_tol0.gpkg"}
INSIDE = 0.8          # a face counts as band geometry if >= 80% of its area lies within band + 1.5 px


def band_check(q, F, L):
    g = LineString(q["axis"]); band = g.buffer(q["radius"]); core = g.buffer(max(q["radius"] - 1, 0.75)); near = g.buffer(q["radius"] + 1.5)
    hit = F[F.intersects(core)]; inside = []; spill = 0.0
    for geom, rgb, lab in zip(hit.geometry, hit["rgb"], hit["label"]):
        c = shapely.intersection(geom, core).area; share = shapely.intersection(geom, near).area / geom.area
        if share >= INSIDE: inside.append((c, geom.area, rgb, int(lab)))
        else: spill = max(spill, c)
    cov_faces = sum(c for c, _, _, _ in inside) / core.area
    labs = sorted({l for _, _, _, l in inside})
    same_label_outside = int(sum(1 for geom, lab in zip(F.geometry, F["label"]) if int(lab) in labs and shapely.intersection(geom, near).area / geom.area < INSIDE))
    pts = shapely.line_interpolate_point(g, np.linspace(0, g.length, int(g.length) + 1)); out = {
        "axis_length": float(g.length), "core_area": float(core.area),
        "faces_touching_core": int(len(hit)), "band_faces": len(inside), "band_face_labels": labs, "band_face_colours": sorted({r for _, _, r, _ in inside}),
        "core_covered_by_band_faces": float(cov_faces), "largest_outside_face_core_share": float(spill / core.area),
        "faces_with_same_label_outside_band": same_label_outside}
    if L is not None and len(L):
        on = L[L.intersects(band)]; parts = [shapely.intersection(x, band) for x in on.geometry]; parts = [p for p in parts if p.length >= 3]
        if parts:
            U = shapely.union_all(parts); d = shapely.distance(pts, U); cover = d <= 1.5
            widths = [float(w) for x, w in zip(on.geometry, on["width_px"]) if shapely.intersection(x, band).length >= 3]
            fat = shapely.union_all([p.buffer(q["radius"]) for p in parts])
            out["lines"] = {"objects": len(parts), "logical_ids": sorted(set(on["logical_id"])), "length_in_band": float(U.length), "widths_px": widths,
                            "band_width_px": 2 * q["radius"], "axis_share_within_1p5px": float(cover.mean()),
                            "mean_offset_of_line_from_axis_px": float(np.mean(shapely.distance(shapely.get_parts(shapely.points(shapely.get_coordinates(U))), g))),
                            "core_share_if_rewidened_to_band_width": float(shapely.intersection(fat, core).area / core.area)}
        else: out["lines"] = {"objects": 0}
    covered = cov_faces
    if "lines" in out and out["lines"].get("objects"): covered = max(cov_faces, min(1.0, cov_faces + out["lines"]["core_share_if_rewidened_to_band_width"]))
    out["redraw_axis_length_estimate_px"] = float(g.length * max(0.0, 1 - covered))
    return out


def main(out):
    res = {"inside_rule": f"face counted as band geometry if >= {INSIDE:.0%} of its area is within band radius + 1.5 px", "files": {}, "bands": {}}
    for m, f in FILES.items():
        F = pyogrio.read_dataframe(f, layer="colour_faces"); layers = [l[0] for l in pyogrio.list_layers(f)]
        L = pyogrio.read_dataframe(f, layer="visual_lines") if "visual_lines" in layers else None
        res["files"][m] = {"path": str(f.relative_to(ROOT)), "faces": len(F), "lines": 0 if L is None else len(L)}
        for q in ORA["protected"]: res["bands"].setdefault(q["id"], {})[m] = band_check(q, F, L if m != "Oracle_class_tol0" else None)
    json.dump(res, open(out, "w"), indent=1, default=float)
    for b, v in res["bands"].items():
        for m, x in v.items():
            ln = x.get("lines", {})
            print(b, m.ljust(18), "band faces", x["band_faces"], "core by band faces", round(x["core_covered_by_band_faces"], 2), "labels", x["band_face_labels"], x["band_face_colours"],
                  "same-label faces elsewhere", x["faces_with_same_label_outside_band"], "| lines", ln.get("objects", "-"), "axis cov", round(ln.get("axis_share_within_1p5px", 0), 2),
                  "widths", ln.get("widths_px"), "rewiden core", round(ln.get("core_share_if_rewidened_to_band_width", 0), 2), "| redraw px", round(x["redraw_axis_length_estimate_px"], 1))


if __name__ == "__main__":
    main(sys.argv[1])
