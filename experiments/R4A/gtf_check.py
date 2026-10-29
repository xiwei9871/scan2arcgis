"""R4-A stage GeoTIFF: can GSJ's own GeoTIFF supply pixel labels without our frame detection?

For one sheet:
  1. read the GeoTIFF georeferencing as published (CRS, affine, GCPs, size). NO parameter is fitted
     or adjusted; H_lonlat_to_px is the exact inverse of the file's affine transform.
  2. write runs/r4a_gtf/<code>/frame_gtf.json in the R2 frame format, then run the UNCHANGED R2
     independent ink-line check (gsj_reg_independent.py) on the GeoTIFF image with geo_L.
  3. content check JPEG vs GeoTIFF (no geology): map the 200 dpi JPEG into the GeoTIFF grid with the
     old R2 homography (frame_reg.json, when it exists) and measure, on a 4x4 grid of tiles, the
     image shift by phase correlation of the grey images. Small shifts = same print and both
     registrations agree; this is reported, never used to change anything.
  4. pixel labels: rasterise geo_A (unit id) and geo_L contacts / faults directly on the GeoTIFF grid
     -> runs/r4a_gtf/<code>/labels_*.npy (local only), and count units / instances.
"""
import json, os, subprocess, sys
from pathlib import Path
import cv2, numpy as np, rasterio, rasterio.features, geopandas as gpd, warnings

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments" / "R2_real_map"))
from gsj_gt import lines, to_px  # noqa: E402
warnings.filterwarnings("ignore")

SHEETS = {"05030": ("2004", "data/raw/gsj_r4a/norm/05030/shp", "runs/r4a/05030/frame_reg.json"),
          "06061": ("2002", "data/raw/gsj_r4a/norm/06061/shp", "runs/r4a/06061/frame_reg.json"),
          "08004": ("2012", "data/raw/gsj/08004/shp", "runs/r2_gsj/08004/frame_reg.json")}


def main(code):
    year, shp, r2frame = SHEETS[code]
    tif = ROOT / f"data/raw/gsj_gtf/GSJ_MAP_G050_{code}_{year}/GSJ_MAP_G050_{code}_{year}_F1_geotiff.tif"
    jpg = next((ROOT / "data/raw").glob(f"gsj*/GSJ_MAP_G050_{code}_{year}_200dpi.jpg"))
    out = ROOT / f"runs/r4a_gtf/{code}"; out.mkdir(parents=True, exist_ok=True)
    with rasterio.open(tif) as d:
        T = d.transform; W, Hh = d.width, d.height; crs = d.crs.to_wkt() if d.crs else None; gcps = len(d.gcps[0])
        rgb = np.moveaxis(d.read([1, 2, 3]), 0, -1)
    cv2.imwrite(str(out / "geotiff_rgb.png"), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    # pixel (col,row) <- lon/lat: inverse affine; corner-of-pixel convention as in the file
    inv = ~T
    H = np.array([[inv.a, inv.b, inv.c], [inv.d, inv.e, inv.f], [0, 0, 1.0]])
    b = [T.c, T.f + T.e * Hh, T.c + T.a * W, T.f]
    corners = {k: [float(v) for v in to_px(np.array([p]), H)[0]] for k, p in
               (("tl", (b[0], b[3])), ("tr", (b[2], b[3])), ("br", (b[2], b[1])), ("bl", (b[0], b[1])))}
    fr = {"image": "geotiff_rgb.png", "size": [W, Hh], "corners_px": corners, "bounds_lonlat": b, "H_lonlat_to_px": H.tolist(),
          "registration": {"method": "GSJ GeoTIFF affine as published (no fitting)"}}
    json.dump(fr, open(out / "frame_gtf.json", "w"), indent=1)
    # Convention: the GeoTIFF is AREA_OR_POINT=Area, so its affine maps pixel CORNERS; R2 drawing and the
    # ink check use array indices (pixel CENTRES). Index = affine pixel - 0.5. This is a fixed convention
    # conversion, not a fitted parameter. (Disclosure: noticed after the first run showed a ~-1.5 px bias.)
    Sx = np.array([[1, 0, -0.5], [0, 1, -0.5], [0, 0, 1.0]])
    fr_idx = dict(fr); fr_idx["H_lonlat_to_px"] = (Sx @ H).tolist()
    fr_idx["registration"] = {"method": "GSJ GeoTIFF affine as published, pixel-corner -> array-index (-0.5 px), no fitting"}
    json.dump(fr_idx, open(out / "frame_gtf_idx.json", "w"), indent=1)
    res = {"code": code, "geotiff": tif.name, "size": [W, Hh], "crs_wkt_head": (crs or "")[:80], "gcps": gcps,
           "affine": [T.a, T.b, T.c, T.d, T.e, T.f], "pixel_deg": [T.a, -T.e], "bounds_lonlat": b}
    # 2. unchanged R2 ink check
    r = subprocess.run([str(ROOT / ".venv/bin/python"), str(ROOT / "experiments/R2_real_map/gsj_reg_independent.py"),
                        str(out / "geotiff_rgb.png"), str(ROOT / shp), str(out / "reg_independent_gtf.json"), f"gtf={out / 'frame_gtf.json'}", f"gtf_idx={out / 'frame_gtf_idx.json'}"],
                       capture_output=True, text=True, cwd=ROOT)
    if r.returncode: res["ink_check_error"] = r.stderr[-400:]
    else:
        res["ink_check"] = {}
        for name in ("gtf", "gtf_idx"):
            cr = json.load(open(out / "reg_independent_gtf.json"))["candidates"][name]; g = cr["global"]
            resid = float(np.hypot(g["dx"], g["dy"])); med = cr["cell_offset_abs_median_px"]
            res["ink_check"][name] = {"dx": g["dx"], "dy": g["dy"], "residual_px": resid, "z": g["contrast_z"], "cells_trusted": cr["cells_trusted"],
                                      "cell_median_px": med, "cell_max_px": cr["cell_offset_abs_max_px"],
                                      "Q3_pass": bool(resid <= 2 and g["contrast_z"] >= 5 and cr["cells_trusted"] >= 12 and med is not None and med <= 2)}
        res["ink_check"]["note"] = "gtf = pixel-corner affine as published; gtf_idx = same affine in array-index convention. Q3 thresholds unchanged, in GeoTIFF px"
    # 3. JPEG vs GeoTIFF content via old R2 homography (no geology)
    if os.path.exists(ROOT / r2frame):
        Hj = np.array(json.load(open(ROOT / r2frame))["H_lonlat_to_px"])
        # GeoTIFF pixel centres -> lon/lat -> JPEG px
        cc, rr = np.meshgrid(np.arange(W) + 0.5, np.arange(Hh) + 0.5)
        lon = T.a * cc + T.b * rr + T.c; lat = T.d * cc + T.e * rr + T.f
        P = np.stack([lon, lat, np.ones_like(lon)], -1) @ Hj.T
        mx = (P[..., 0] / P[..., 2]).astype(np.float32); my = (P[..., 1] / P[..., 2]).astype(np.float32)
        J = cv2.imread(str(jpg))
        warped = cv2.remap(J, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255))
        cv2.imwrite(str(out / "jpeg_in_geotiff_grid_R2.png"), warped)
        g1 = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32); g2 = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY).astype(np.float32)
        tiles = []
        for a in range(4):
            for c_ in range(4):
                y0, y1 = int(Hh * a / 4) + 40, int(Hh * (a + 1) / 4) - 40; x0, x1 = int(W * c_ / 4) + 40, int(W * (c_ + 1) / 4) - 40
                A_, B_ = g1[y0:y1, x0:x1], g2[y0:y1, x0:x1]
                win = cv2.createHanningWindow(A_.shape[::-1], cv2.CV_32F)
                (dx, dy), resp = cv2.phaseCorrelate(A_, B_, win)
                ncc = float(np.corrcoef(A_.ravel(), B_.ravel())[0, 1])
                tiles.append({"tile": [a, c_], "dx": float(dx), "dy": float(dy), "response": float(resp), "ncc_unshifted": ncc})
        sh = np.array([np.hypot(t["dx"], t["dy"]) for t in tiles])
        res["jpeg_vs_geotiff_via_R2"] = {"tile_shift_median_px": float(np.median(sh)), "tile_shift_max_px": float(sh.max()),
                                         "ncc_median": float(np.median([t["ncc_unshifted"] for t in tiles])), "tiles": tiles,
                                         "note": "shift = how far the R2-registered JPEG content sits from the GeoTIFF content, GeoTIFF px"}
    # 4. pixel labels directly on the GeoTIFF grid
    A = gpd.read_file(ROOT / shp / "geo_A.shp", encoding="cp932"); L = gpd.read_file(ROOT / shp / "geo_L.shp", encoding="cp932")
    codes = sorted(A.MAJOR_CODE.astype(str).unique()); cid = {c: i for i, c in enumerate(codes)}
    order = A.geometry.area.sort_values(ascending=False).index
    unit = rasterio.features.rasterize(((A.loc[i].geometry, cid[str(A.loc[i].MAJOR_CODE)]) for i in order), out_shape=(Hh, W),
                                       transform=T, fill=-1, dtype="int32")
    con = np.zeros((Hh, W), np.uint8); flt = np.zeros((Hh, W), np.uint8)
    for g, k in zip(L.geometry, L["LEGEND01"].astype(str)):
        tgt = flt if "断層" in k else (con if "地質境界" in k else None)
        if tgt is None: continue
        for ln in lines(g): cv2.polylines(tgt, [np.round(to_px(ln, H) - 0.5).astype(np.int32).reshape(-1, 1, 2)], False, 1, 1)
    np.save(out / "labels_unit.npy", unit.astype(np.int16)); np.save(out / "labels_contact.npy", con); np.save(out / "labels_fault.npy", flt)
    n_inst = sum(cv2.connectedComponents((unit == j).astype(np.uint8), connectivity=4)[0] - 1 for j in range(len(codes)))
    res["labels"] = {"units": len(codes), "instances": int(n_inst), "labelled_px_frac": float((unit >= 0).mean()),
                     "contact_px": int(con.sum()), "fault_px": int(flt.sum()), "local_files": f"runs/r4a_gtf/{code}/labels_*.npy"}
    json.dump(res, open(out / "gtf_check.json", "w"), ensure_ascii=False, indent=1, default=float)
    show = {k: res.get(k) for k in ("size", "gcps", "pixel_deg")}
    show["ink"] = {n: {k: (round(v, 2) if isinstance(v, float) else v) for k, v in d.items()} for n, d in res.get("ink_check", {}).items() if n != "note"}
    if "jpeg_vs_geotiff_via_R2" in res:
        j = res["jpeg_vs_geotiff_via_R2"]; show["jpeg_vs_gtf"] = {k: round(j[k], 2) for k in ("tile_shift_median_px", "tile_shift_max_px", "ncc_median")}
    show["labels"] = res["labels"]
    print(code, json.dumps(show, default=float))


if __name__ == "__main__":
    for c in sys.argv[1:]: main(c)
