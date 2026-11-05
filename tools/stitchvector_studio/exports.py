"""GIS export of a Studio working GPKG: GeoPackage, ESRI Shapefile (zip), GeoJSON.

Layers (Studio name -> GPKG layer in the working file):
  geological_faces  <- colour_faces          (Polygon)
  geological_lines  <- visual_lines          (LineString)
  text_confirmed    <- text_labels with review_status == OCR_CONFIRMED / TEXT_VECTOR_CREATED (Point)
  text_unconfirmed  <- the other text_labels rows (Point), only when selected, always in its own layer
  isolated_lines    <- text_residue_lines    (LineString), only when selected
Coordinates:
  GEOREFERENCED : pixel (col,row) -> map via the source affine; CRS written (.prj for Shapefile)
  PIXEL_SPACE   : pixel coordinates kept, no CRS written, never a fake EPSG; GeoJSON is refused (RFC 7946 needs WGS84
                  lon/lat) and a clearly named pixel-space JSON ("*.pixel.json") is offered instead.
Every export is re-read from disk and compared (feature count, geometry type, key attributes, validity, bounds).
"""
import json, os, shutil, tempfile, zipfile
from pathlib import Path
import numpy as np, pyogrio, shapely, geopandas as gpd
from shapely import affinity
from .contracts import sha256_file, write_json_atomic
from tools.stitchvector_editor.core import REVIEW_DELIVERABLE, review_status_series, review_pending, review_status_counts

LAYERS = {"geological_faces": "colour_faces", "geological_lines": "visual_lines", "text_confirmed": "text_labels",
          "text_unconfirmed": "text_labels", "isolated_lines": "text_residue_lines"}
DEFAULT_LAYERS = ("geological_faces", "geological_lines", "text_confirmed")
FORMATS = ("GPKG", "SHP", "GEOJSON")
# same deliverable judgement as the editor save gate: pipeline states (TEXT_VECTOR_CREATED, BACKGROUND_CLEAR_PENDING)
# and incomplete review states are NOT confirmations and go to the unconfirmed layer / block a formal export.
CONFIRMED = REVIEW_DELIVERABLE


class ExportError(Exception):
    pass


def _text_status(T): return review_status_series(T).astype(str)


def collect(gpkg, layers):
    have = [l[0] for l in pyogrio.list_layers(gpkg)]; out = {}
    for name in layers:
        if name not in LAYERS: raise ExportError(f"unknown layer {name}")
        src = LAYERS[name]
        if src not in have: out[name] = None; continue
        D = pyogrio.read_dataframe(gpkg, layer=src)
        if name.startswith("text_"):
            st = _text_status(D); keep = st.isin(CONFIRMED) if name == "text_confirmed" else ~st.isin(CONFIRMED)
            D = D.loc[keep].copy(); D["review_status"] = st[keep].values
        D = D[[c for c in D.columns if not c.startswith("_")]]
        out[name] = D
    return out


def _to_map(D, doc):
    if doc.get("coordinate_mode") != "GEOREFERENCED": return D
    a, b, c, d, e, f = doc["transform"]          # rasterio Affine order: x = a*col + b*row + c ; y = d*col + e*row + f
    D = D.copy(); D["geometry"] = [affinity.affine_transform(g, [a, b, d, e, c, f]) for g in D.geometry]; return D


def _crs(doc): return doc["crs"] if doc.get("coordinate_mode") == "GEOREFERENCED" else None


def _shp_safe(D):
    """Shapefile limits: 10-char field names (unique), no list types. Returns renamed frame + mapping."""
    m, used = {}, set()
    for c in D.columns:
        if c == "geometry": continue
        n = "".join(ch for ch in c if ch.isalnum() or ch == "_")[:10] or "f"; k = n; i = 1
        while k.lower() in used: s = str(i); k = n[:10 - len(s)] + s; i += 1
        used.add(k.lower()); m[c] = k
    return D.rename(columns=m), m


def export(gpkg, doc, fmt, layers, out_dir, base="stitchvector_export", allow_pixel_space=False, draft=False):
    fmt = fmt.upper()
    if fmt not in FORMATS: raise ExportError(f"format must be one of {FORMATS}")
    layers = list(layers or DEFAULT_LAYERS); mode = doc.get("coordinate_mode", "PIXEL_SPACE")
    if mode == "PIXEL_SPACE" and fmt in ("SHP",) and not allow_pixel_space:
        raise ExportError("project is not georeferenced: confirm pixel-space Shapefile export (no .prj is written)")
    # shared review gate with the editor: incomplete review/pipeline states may not pass a formal export silently
    if "text_labels" in [l[0] for l in pyogrio.list_layers(gpkg)]:
        T_all = pyogrio.read_dataframe(gpkg, layer="text_labels"); pend = review_pending(T_all)
        if pend and not draft:
            raise ExportError(f"{pend} OCR texts are not in a deliverable state; confirm them in review or export with draft=true")
        if pend and draft and "text_unconfirmed" not in layers: layers = layers + ["text_unconfirmed"]
    else:
        pend = 0
    data = {k: v for k, v in collect(gpkg, layers).items() if v is not None and len(v)}
    if not data: raise ExportError("selected layers are empty")
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    tmpd = Path(tempfile.mkdtemp(dir=out_dir, prefix=".exp_")); crs = _crs(doc)
    meta = {"format": fmt, "coordinate_mode": mode, "crs": crs, "layers": {}, "source_gpkg_sha256": sha256_file(gpkg),
            "export_mode": "draft" if (pend and draft) else "formal", "unreviewed": pend,
            "review": review_status_counts(T_all) if pend else {},
            "note": None if mode == "GEOREFERENCED" else "成果未进行地理配准: coordinates are image pixels (x right, y down); no CRS"}
    try:
        if fmt == "GPKG":
            f = tmpd / f"{base}.gpkg"
            for k, D in data.items():
                G = gpd.GeoDataFrame(_to_map(D, doc), geometry="geometry", crs=crs); G.to_file(f, layer=k, driver="GPKG", engine="pyogrio")
                meta["layers"][k] = {"features": len(G), "geom_type": sorted(set(G.geom_type))}
            final = out_dir / f.name
        elif fmt == "SHP":
            sd = tmpd / base; sd.mkdir(); fmap = {}
            for k, D in data.items():
                G = gpd.GeoDataFrame(_to_map(D, doc), geometry="geometry", crs=crs); G, mp = _shp_safe(G); fmap[k] = mp
                G.to_file(sd / f"{k}.shp", driver="ESRI Shapefile", engine="pyogrio", encoding="UTF-8")
                (sd / f"{k}.cpg").write_text("UTF-8")
                meta["layers"][k] = {"features": len(G), "geom_type": sorted(set(G.geom_type))}
            write_json_atomic(sd / "field_mapping.json", fmap); write_json_atomic(sd / "export_manifest.json", meta)
            f = tmpd / f"{base}_shp.zip"
            with zipfile.ZipFile(f, "w", zipfile.ZIP_DEFLATED) as z:
                for p in sorted(sd.iterdir()): z.write(p, p.name)
            final = out_dir / f.name
        else:  # GEOJSON
            if mode != "GEOREFERENCED":
                f = tmpd / f"{base}.pixel.json"
                obj = {"type": "StitchVectorPixelExchange", "coordinate_space": "PIXEL_SPACE (x right, y down)", "crs": None,
                       "warning": "not GeoJSON: no geographic coordinates", "layers": {}}
                for k, D in data.items():
                    obj["layers"][k] = json.loads(gpd.GeoDataFrame(D, geometry="geometry").to_json(drop_id=True))
                    meta["layers"][k] = {"features": len(D), "geom_type": sorted(set(D.geom_type))}
                f.write_text(json.dumps(obj, ensure_ascii=False))
            else:
                f = tmpd / f"{base}_geojson.zip"; gd = tmpd / "gj"; gd.mkdir()
                for k, D in data.items():
                    G = gpd.GeoDataFrame(_to_map(D, doc), geometry="geometry", crs=crs).to_crs(4326)   # RFC 7946: WGS84
                    G.to_file(gd / f"{k}.geojson", driver="GeoJSON", engine="pyogrio")
                    meta["layers"][k] = {"features": len(G), "geom_type": sorted(set(G.geom_type)), "written_crs": "EPSG:4326"}
                write_json_atomic(gd / "export_manifest.json", meta)
                with zipfile.ZipFile(f, "w", zipfile.ZIP_DEFLATED) as z:
                    for p in sorted(gd.iterdir()): z.write(p, p.name)
            final = out_dir / f.name
        if final.exists(): raise ExportError(f"{final.name} already exists")
        meta["readback"] = readback(f, fmt, data, doc)
        if not meta["readback"]["ok"]: raise ExportError(f"export failed its read-back check: {meta['readback']}")
        os.replace(f, final)
    finally:
        shutil.rmtree(tmpd, ignore_errors=True)
    meta.update(file=final.name, path=str(final), bytes=final.stat().st_size, sha256=sha256_file(final))
    write_json_atomic(final.with_name(final.name + ".manifest.json"), meta); return meta


def readback(f, fmt, data, doc):
    """re-open the written file and compare with what was meant to be written."""
    res = {"layers": {}}; ok = True
    def chk(k, G, ref):
        nonlocal ok
        r = {"features": len(G), "expected": len(ref), "valid": bool(shapely.is_valid(np.asarray(G.geometry.values, object)).all()) if len(G) else True,
             "geom_types": sorted(set(G.geom_type))}
        if "rgb" in ref.columns and "rgb" in G.columns: r["rgb_equal"] = list(G["rgb"]) == list(ref["rgb"])
        if "text" in ref.columns and "text" in G.columns: r["text_equal"] = list(G["text"]) == list(ref["text"])
        r["ok"] = r["features"] == r["expected"] and r["valid"] and r.get("rgb_equal", True) and r.get("text_equal", True)
        ok &= r["ok"]; res["layers"][k] = r
    if fmt == "GPKG":
        for k, ref in data.items(): G = pyogrio.read_dataframe(f, layer=k); chk(k, G, ref); res["crs"] = None if G.crs is None else G.crs.to_wkt()[:60]
    elif fmt == "SHP":
        with tempfile.TemporaryDirectory() as td:
            zipfile.ZipFile(f).extractall(td)
            fmap = json.load(open(Path(td) / "field_mapping.json"))
            for k, ref in data.items():
                G = pyogrio.read_dataframe(Path(td) / f"{k}.shp", encoding="UTF-8").rename(columns={v: c for c, v in fmap[k].items()}); chk(k, G, ref)
                res.setdefault("prj", {})[k] = (Path(td) / f"{k}.prj").exists()
            if doc.get("coordinate_mode") != "GEOREFERENCED" and any(res.get("prj", {}).values()): ok = False; res["fake_prj"] = True
    else:
        if f.name.endswith(".pixel.json"):
            obj = json.loads(f.read_text())
            for k, ref in data.items(): G = gpd.GeoDataFrame.from_features(obj["layers"][k]["features"]); chk(k, G, ref)
        else:
            with tempfile.TemporaryDirectory() as td:
                zipfile.ZipFile(f).extractall(td)
                for k, ref in data.items():
                    G = pyogrio.read_dataframe(Path(td) / f"{k}.geojson"); chk(k, G, ref)
                    b = G.total_bounds; res["layers"][k]["lonlat_bounds"] = [round(float(x), 6) for x in b]
                    if not (-180 <= b[0] <= 180 and -90 <= b[1] <= 90): ok = False
    res["ok"] = bool(ok); return res
