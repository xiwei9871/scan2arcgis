"""R4-A stage C: re-read exported pixel vectors through GDAL (pyogrio) and check them.

Checks (all against prediction-side inputs only; no ground truth is read):
  crs_undefined        GeoPackage layers and Shapefiles carry no CRS; no .prj file exists
  y_negative           all unit geometries lie in Y <= 0 and X >= 0 (image is upright in GIS)
  extent_within_image  bounds within [0, W] x [-H, 0] of the ORIGINAL image
  half_pixel           a polygon vertex grid aligned to work-pixel edges: every vertex x*s, y*s is
                       an integer (no 0.5 shift), and the rasterised area equals the label count
  validity             fraction of valid geometries
  count_match          #units == #regions in the label map; ids unique
  area_match           sum of polygon areas * s^2 == number of labelled work pixels (per region too)
  roundtrip            edit one attribute in the GeoPackage, write a copy, re-read: geometry WKB and
                       all other attributes unchanged; Shapefile copy re-read with same counts
Usage: validate_pixel_vectors.py <gpkg> <label_npy|synth:case_dir> <work_scale> <out_json>
"""
import json, os, sys, shutil, tempfile
from pathlib import Path
import numpy as np, geopandas as gpd, pyogrio, cv2

sys.path.insert(0, str(Path(__file__).parent))
from export_pixel_vectors import regions_from_labels  # noqa: E402


def main(gpkg, labels_spec, scale, out_json):
    s = float(scale); gp = Path(gpkg); stem = gp.stem; d = gp.parent
    meta = gpd.read_file(gp, layer="metadata", engine="pyogrio")
    md = {k: v for k, v in zip(meta["key"], meta["value"])}
    W, H = json.loads(md["image_size_px"])
    if labels_spec.startswith("synth:"):
        case = Path(labels_spec[6:]); g = json.load(open(case / "gt.json"))
        lab = np.load(labels_spec_r1(case)).astype(np.int32)
        x, y, w, h = g["map_box"]; mm = np.zeros(lab.shape, bool); mm[y:y + h, x:x + w] = True
    else:
        lab = np.load(labels_spec).astype(np.int32); mm = np.load(Path(labels_spec).parent / "map_mask.npy")
    reg, _ = regions_from_labels(lab, mm)
    n_reg = int(reg.max()) + 1
    res = {"gpkg": gp.name, "checks": {}}
    U = gpd.read_file(gp, layer="geologic_units", engine="pyogrio"); C = gpd.read_file(gp, layer="contacts", engine="pyogrio")
    info = {l[0]: pyogrio.read_info(gp, layer=l[0]) for l in pyogrio.list_layers(gp)}
    shp_u, shp_c = d / f"{stem}_units.shp", d / f"{stem}_contacts.shp"
    res["checks"]["crs_undefined"] = {"gpkg_units_crs": info["geologic_units"]["crs"], "gpkg_contacts_crs": info["contacts"]["crs"],
                                      "shp_units_crs": pyogrio.read_info(shp_u)["crs"], "prj_files": sorted(p.name for p in d.glob(f"{stem}*.prj")),
                                      "pass": info["geologic_units"]["crs"] is None and info["contacts"]["crs"] is None
                                              and pyogrio.read_info(shp_u)["crs"] is None and not list(d.glob(f"{stem}*.prj"))}
    b = U.total_bounds
    res["checks"]["y_negative"] = {"bounds": [float(v) for v in b], "pass": bool(b[3] <= 1e-9 and b[0] >= -1e-9)}
    res["checks"]["extent_within_image"] = {"image_wh": [W, H], "pass": bool(b[0] >= -1e-6 and b[2] <= W + 1e-6 and b[1] >= -H - 1e-6 and b[3] <= 1e-6)}
    # half-pixel: vertices scaled back to work pixels must be integers
    xy = np.concatenate([np.asarray(g.exterior.coords) for geom in U.geometry for g in getattr(geom, "geoms", [geom])])
    frac = np.abs(xy * s - np.round(xy * s)).max()
    res["checks"]["half_pixel"] = {"max_vertex_fraction_work_px": float(frac), "pass": bool(frac < 1e-6)}
    res["checks"]["validity"] = {"valid_frac": float(U.geometry.is_valid.mean()), "contacts_valid_frac": float(C.geometry.is_valid.mean()) if len(C) else None,
                                 "pass": bool(U.geometry.is_valid.all())}
    ids = U["unit_id"].astype(int)
    res["checks"]["count_match"] = {"units": len(U), "regions": n_reg, "unique_ids": bool(ids.is_unique), "pass": bool(len(U) == n_reg and ids.is_unique)}
    px = np.bincount(reg[reg >= 0], minlength=n_reg)
    ar = np.zeros(n_reg); ar[ids.values] = U.geometry.area.values * s * s
    err = np.abs(ar - px)
    res["checks"]["area_match"] = {"labelled_work_px": int(px.sum()), "polygon_area_work_px": float(ar.sum()),
                                   "max_abs_region_error_px": float(err.max()), "pass": bool(err.max() < 1e-6)}
    # spot check: rasterise polygons back onto the work grid and compare with the label map
    back = np.full(reg.shape, -1, np.int32)
    import rasterio.features
    from affine import Affine
    tr = Affine(1.0 / s, 0, 0, 0, -1.0 / s, 0)
    back = rasterio.features.rasterize(((g, int(i)) for g, i in zip(U.geometry, ids)), out_shape=reg.shape, transform=tr, fill=-1, dtype="int32")
    res["checks"]["rasterise_back"] = {"pixel_agreement": float((back == reg).mean()), "pass": bool((back == reg).all())}
    # round trip
    tmp = Path(tempfile.mkdtemp())
    U2 = U.copy(); U2.loc[U2.index[0], "review_status"] = "CONFIRMED_BY_EDIT_TEST"
    p2 = tmp / "rt.gpkg"; U2.to_file(p2, layer="geologic_units", driver="GPKG", engine="pyogrio")
    U3 = gpd.read_file(p2, layer="geologic_units", engine="pyogrio")
    same_geom = bool((U3.geometry.to_wkb() == U.geometry.to_wkb()).all())
    other = [c for c in U.columns if c not in ("geometry", "review_status")]
    same_attr = bool(U3[other].fillna("∅").astype(str).equals(U[other].fillna("∅").astype(str)))
    edited = U3.loc[U3.index[0], "review_status"] == "CONFIRMED_BY_EDIT_TEST"
    S = gpd.read_file(shp_u, engine="pyogrio"); S.to_file(tmp / "rt.shp", engine="pyogrio"); S2 = gpd.read_file(tmp / "rt.shp", engine="pyogrio")
    res["checks"]["roundtrip"] = {"gpkg_geometry_identical": same_geom, "gpkg_other_attrs_identical": same_attr, "edit_persisted": bool(edited),
                                  "shp_units": len(S), "shp_reimport_units": len(S2), "crs_after_reexport": pyogrio.read_info(p2, layer="geologic_units")["crs"],
                                  "pass": same_geom and same_attr and bool(edited) and len(S) == len(S2) == len(U)
                                          and pyogrio.read_info(p2, layer="geologic_units")["crs"] is None}
    shutil.rmtree(tmp)
    rs = U["review_status"].value_counts().to_dict()
    res["summary"] = {"units": len(U), "contacts": len(C), "review_status": rs,
                      "contacts_kind": C["kind"].value_counts().to_dict() if len(C) else {},
                      "units_with_code": int(U["code"].notna().sum()), "units_with_candidates": int(U["code_candidates"].notna().sum()),
                      "gdal": pyogrio.__gdal_version_string__, "all_pass": all(v["pass"] for v in res["checks"].values())}
    json.dump(res, open(out_json, "w"), ensure_ascii=False, indent=1, default=str)
    print(json.dumps({k: v["pass"] for k, v in res["checks"].items()}), res["summary"]["all_pass"])


def labels_spec_r1(case):
    return Path("runs/mac_r1/r1_synth") / case.name / "labels_legend_rf_selftrain.npy"


if __name__ == "__main__":
    main(*sys.argv[1:5])
