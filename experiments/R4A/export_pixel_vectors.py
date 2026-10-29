"""R4-A stage C: export existing R1/R3 recognition results as editable, UNREFERENCED pixel vectors.

Coordinate convention (docs/research/r4a/architecture_coordinate_free.md, section 2):
  X = column, Y = -row, in ORIGINAL image pixels; origin = top-left corner of the top-left pixel;
  GDAL GeoTransform (0, 1, 0, 0, 0, -1). No CRS is written (GeoPackage: undefined SRS;
  Shapefile: no .prj). Work-scale label maps are mapped back with transform scale 1/s.

Outputs (out_dir):
  <stem>.gpkg          layers geologic_units, contacts, metadata          (primary)
  <stem>_units.shp     + <stem>_contacts.shp (compatibility, no .prj)     + <stem>_COORDS.txt
  <stem>_image.<ext>.wld / symlink to the source image for overlay       (local only)

Modes
  gsj   <code> <year> <out_dir>   R1 rf_selftrain regions + R3 A3 codes + V7 candidate sets
                                  + in-map OCR anchors (prediction-side files only; no GT read)
  synth <case_dir> <r1_case_dir> <out_dir>   public example from a synthetic map
review_status: CONFIRMED (code agrees with an OCR code label inside the region),
LOW_CONFIDENCE (code from colour only), REVIEW (no code, candidate set, or R3 review flag).
Scores are UNCALIBRATED; no probability is claimed.
"""
import json, hashlib, os, sys
from pathlib import Path
import numpy as np, geopandas as gpd, pandas as pd
import rasterio.features
from affine import Affine
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "src"))
from scan2arcgis.vector.polygonize import contacts_from_polygons  # noqa: E402

CONV = {"coord_space": "image_px_unreferenced", "x": "column", "y": "-row", "origin": "top-left corner of pixel (0,0)",
        "pixel_centre": "(c+0.5, -(r+0.5))", "gdal_geotransform": [0, 1, 0, 0, 0, -1], "crs": "none"}


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()


def regions_from_labels(labels, valid):
    reg = np.full(labels.shape, -1, np.int32); cls = []; k0 = 0
    import cv2
    for k in np.unique(labels[valid & (labels >= 0)]):
        n, cc = cv2.connectedComponents(((labels == k) & valid).astype(np.uint8), connectivity=4)
        m = cc > 0; reg[m] = cc[m] - 1 + k0; cls += [int(k)] * (n - 1); k0 += n - 1
    return reg, cls


def polygons(reg, scale):
    tr = Affine(1.0 / scale, 0, 0, 0, -1.0 / scale, 0)
    geoms = {}
    for g, v in rasterio.features.shapes(reg, mask=reg >= 0, connectivity=4, transform=tr):
        geoms.setdefault(int(v), []).append(shape(g))
    from shapely.ops import unary_union
    return {k: (v[0] if len(v) == 1 else unary_union(v)) for k, v in geoms.items()}, tr


def write_all(out, stem, units, contacts, meta, image_path):
    out.mkdir(parents=True, exist_ok=True)
    gp = out / f"{stem}.gpkg"
    for p in [gp] + list(out.glob(f"{stem}_units.*")) + list(out.glob(f"{stem}_contacts.*")):
        if p.exists(): p.unlink()
    units.to_file(gp, layer="geologic_units", driver="GPKG", engine="pyogrio")
    contacts.to_file(gp, layer="contacts", driver="GPKG", engine="pyogrio")
    pd.DataFrame({"key": list(meta), "value": [json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v for v in meta.values()]}) \
        .pipe(lambda d: gpd.GeoDataFrame(d, geometry=[None] * len(d))).to_file(gp, layer="metadata", driver="GPKG", engine="pyogrio")
    ren = {"code_candidates": "code_cands", "confidence": "conf", "review_status": "review", "conf_status": "conf_stat",
           "review_reasons": "rv_reason", "anchor_codes": "anchors", "left_unit": "left_u", "right_unit": "right_u"}
    units.rename(columns=ren).to_file(out / f"{stem}_units.shp", engine="pyogrio")
    contacts.rename(columns=ren).to_file(out / f"{stem}_contacts.shp", engine="pyogrio")
    (out / f"{stem}_COORDS.txt").write_text(
        "Pixel coordinates, NOT geographic. X = column, Y = -row of the original image; origin = top-left corner of pixel (0,0).\n"
        "No CRS / no .prj on purpose. Do not assign EPSG:4326.\n" + json.dumps(meta, ensure_ascii=False, indent=1))
    if image_path:
        src = Path(image_path); link = out / f"{stem}_image{src.suffix}"
        if link.exists() or link.is_symlink(): link.unlink()
        link.symlink_to(src.resolve())
        # world file: pixel size, rotation, rotation, -pixel size, X and Y of the CENTRE of the top-left pixel
        wext = {".jpg": ".jgw", ".jpeg": ".jgw", ".png": ".pgw", ".tif": ".tfw"}.get(src.suffix.lower(), ".wld")
        (out / f"{stem}_image{wext}").write_text("1.0\n0.0\n0.0\n-1.0\n0.5\n-0.5\n")
    return gp


def build(reg, reg_cls, scale, code_of_region, cand_of_region, anchors_of_region, flags_of_region, source):
    geoms, tr = polygons(reg, scale)
    rows, gl = [], []
    for r, g in sorted(geoms.items()):
        code = code_of_region(r); cands = cand_of_region(r); anc = anchors_of_region(r); flags = flags_of_region(r)
        if code and code in anc: st = "CONFIRMED"
        elif code and not flags: st = "LOW_CONFIDENCE"
        else: st = "REVIEW"
        rows.append({"unit_id": int(r), "class_id": int(reg_cls[r]), "code": code, "code_candidates": json.dumps(cands) if cands else None,
                     "anchor_codes": json.dumps(sorted(set(anc))) if anc else None, "review_reasons": ",".join(flags) if flags else None,
                     "area_px": float(g.area), "confidence": None, "conf_status": "UNCALIBRATED", "review_status": st, "source": source})
        gl.append(g)
    units = gpd.GeoDataFrame(rows, geometry=gl, crs=None)
    cpolys = [(g, int(row["unit_id"])) for g, row in zip(gl, rows)]
    lines = contacts_from_polygons(cpolys)
    code_by_unit = {row["unit_id"]: row["code"] for row in rows}
    crow, cgeo = [], []
    for k, (ln, ui, uj, _, _) in enumerate(lines):
        crow.append({"line_id": k, "left_unit": int(ui), "right_unit": int(uj),
                     "kind": "contact" if code_by_unit.get(ui) != code_by_unit.get(uj) else "same_code_boundary",
                     "length_px": float(ln.length), "review_status": "REVIEW" if (code_by_unit.get(ui) is None or code_by_unit.get(uj) is None) else "LOW_CONFIDENCE",
                     "source": source})
        cgeo.append(ln)
    contacts = gpd.GeoDataFrame(crow, geometry=cgeo, crs=None)
    return units, contacts, tr


def mode_gsj(code, year, out_dir):
    img = ROOT / f"data/raw/gsj/GSJ_MAP_G050_{code}_{year}_200dpi.jpg"
    r1 = ROOT / f"runs/r2_gsj/{code}/r1"; s1 = ROOT / f"runs/r3/{code}/s1"; s1v2 = ROOT / f"runs/r3fix/s1v2/{code}"
    ev = json.load(open(r1 / "r1_eval.json")); s = ev["scale"]
    pred = np.load(r1 / "pred_legend_rf_selftrain.npy").astype(np.int32); mm = np.load(r1 / "map_mask.npy")
    z = np.load(s1 / "s1_maps.npz"); meta3 = json.load(open(s1 / "s1_meta.json")); codes = meta3["codes"]
    reg = z["regions"].astype(np.int32); a3 = z["A3"].astype(np.int32)
    reg2, reg_cls = regions_from_labels(pred, mm)
    assert reg2.shape == reg.shape and (reg2 == reg).all(), "R3 regions differ from R1 connected components"
    nR = int(reg.max()) + 1
    code_r = {}
    for r in range(nR):
        v = a3[reg == r]; code_r[r] = codes[int(v[0])] if len(v) and v[0] >= 0 else None
    cand = json.load(open(s1v2 / "s1v2_meta.json"))["candidates"]["V7_constr_cands"]
    flags = {rc["region"]: rc["reasons"] for rc in meta3["review_candidates"]}
    anchors = {}
    for c in json.load(open(ROOT / f"runs/r3fix/ocr/{code}/map_spot.json"))["candidates"]:
        if c["reader"] != "rapid" or not c["code"]: continue
        x, y = int(c["centre_px"][0] * s), int(c["centre_px"][1] * s)
        if 0 <= y < reg.shape[0] and 0 <= x < reg.shape[1] and reg[y, x] >= 0: anchors.setdefault(int(reg[y, x]), []).append(c["code"])
    units, contacts, tr = build(reg, reg_cls, s, lambda r: code_r[r], lambda r: cand.get(str(r)) if code_r[r] is None else None,
                                lambda r: anchors.get(r, []), lambda r: flags.get(r, []), "R1 rf_selftrain regions + R3 A3 codes + R3fix V7 candidates")
    from PIL import Image; Image.MAX_IMAGE_PIXELS = None
    W, H = Image.open(img).size
    meta = {**CONV, "image": img.name, "image_sha256": sha(img), "image_size_px": [W, H], "work_scale": s,
            "work_to_original_transform": list(tr)[:6], "generator": "experiments/R4A/export_pixel_vectors.py gsj",
            "licence": "INTERNAL_RESEARCH_APPROVED_BY_PROJECT_OWNER / THIRD_PARTY_LICENSE_UNCONFIRMED; local only",
            "scores": "UNCALIBRATED"}
    out = Path(out_dir); gp = write_all(out, code, units, contacts, meta, img)
    json.dump({"units": len(units), "contacts": len(contacts), "regions": nR}, open(out / f"{code}_export_summary.json", "w"))
    print(code, "units", len(units), "contacts", len(contacts), "->", gp)


def mode_synth(case_dir, r1_case_dir, out_dir):
    case, r1c = Path(case_dir), Path(r1_case_dir)
    gt = json.load(open(case / "gt.json"))                       # legend codes are printed on the synthetic map
    lab = np.load(r1c / "labels_legend_rf_selftrain.npy").astype(np.int32)
    x, y, w, h = gt["map_box"]; mm = np.zeros(lab.shape, bool); mm[y:y + h, x:x + w] = True
    reg, reg_cls = regions_from_labels(lab, mm)
    code_of_cls = {e["class_id"]: e["legend_code"] for e in gt["legend"]}
    units, contacts, tr = build(reg, reg_cls, 1.0, lambda r: code_of_cls.get(reg_cls[r]), lambda r: None, lambda r: [], lambda r: [],
                                "R1 rf_selftrain on synthetic map")
    img = case / "image.png"
    meta = {**CONV, "image": "synthetic " + case.name + "/image.png", "image_sha256": sha(img), "image_size_px": [lab.shape[1], lab.shape[0]],
            "work_scale": 1.0, "generator": "experiments/R4A/export_pixel_vectors.py synth", "licence": "synthetic, MIT (this repository)",
            "scores": "UNCALIBRATED"}
    gp = write_all(Path(out_dir), "synth_" + case.name, units, contacts, meta, None)
    print("synth units", len(units), "contacts", len(contacts), "->", gp)


if __name__ == "__main__":
    {"gsj": mode_gsj, "synth": mode_synth}[sys.argv[1]](*sys.argv[2:])
