"""Rasterize official GSJ vectors onto the printed sheet's pixel grid and measure alignment.

Inputs: frame.json (neatline corners + lon/lat->px homography), the sheet's shp/ directory.
Outputs (in out_dir):
  gt_units.npy      int32 label per pixel inside the neatline (-1 outside), index into units.json
  gt_contacts.npy   uint8 mask of official geologic boundaries (geo_L), 1 px wide
  gt_faults.npy     uint8 mask of official faults (geo_L rows typed as faults)
  units.json        MAJOR_CODE, legend names, pixel area, polygon count per unit
  align_check.jpg   official boundaries drawn over the image (visual alignment check)
  align.json        edge-distance between official boundaries and image colour edges (px)
"""
import json, sys
from pathlib import Path
import cv2, numpy as np, geopandas as gpd, warnings
warnings.filterwarnings("ignore")


def to_px(geom_xy, H):
    pts = np.asarray(geom_xy, np.float64)
    p = np.c_[pts, np.ones(len(pts))] @ H.T
    return p[:, :2] / p[:, 2:3]


def rings(geom):
    polys = [geom] if geom.geom_type == "Polygon" else list(geom.geoms)
    for p in polys:
        yield [np.asarray(p.exterior.coords)] + [np.asarray(r.coords) for r in p.interiors]


def lines(geom):
    if geom is None: return
    if geom.geom_type == "LineString": yield np.asarray(geom.coords)
    else:
        for g in geom.geoms: yield np.asarray(g.coords)


def main(img_path, frame_path, shp_dir, out):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    fr = json.load(open(frame_path)); H = np.array(fr["H_lonlat_to_px"])
    rgb = cv2.cvtColor(cv2.imread(str(img_path)), cv2.COLOR_BGR2RGB); h, w = rgb.shape[:2]
    A = gpd.read_file(Path(shp_dir) / "geo_A.shp", encoding="cp932")
    L = gpd.read_file(Path(shp_dir) / "geo_L.shp", encoding="cp932")
    codes = sorted(A.MAJOR_CODE.astype(str).unique())
    cid = {c: i for i, c in enumerate(codes)}
    lab = np.full((h, w), -1, np.int32)
    for _, r in A.iterrows():
        for rr in rings(r.geometry):
            ext = np.round(to_px(rr[0], H)).astype(np.int32)
            cv2.fillPoly(lab, [ext], int(cid[str(r.MAJOR_CODE)]))
            for hole in rr[1:]:
                # holes are filled by the other polygon drawn into them; GSJ polygons tile the sheet
                pass
    # second pass: draw smaller polygons last so holes get the inner unit (GSJ geo_A tiles the area)
    order = A.geometry.area.sort_values(ascending=False).index
    lab[:] = -1
    for i in order:
        r = A.loc[i]
        for rr in rings(r.geometry):
            cv2.fillPoly(lab, [np.round(to_px(rr[0], H)).astype(np.int32)], int(cid[str(r.MAJOR_CODE)]))
    # boundaries: classify geo_L by its first legend field. GSJ mixes the sheet frame (図郭線) and
    # key beds (鍵層) into geo_L; they are neither contacts nor faults and are excluded from both.
    tcol = "LEGEND01"
    kind = []
    for v in L[tcol].astype(str):
        if "図郭" in v: kind.append("frame")
        elif "断層" in v or "fault" in v.lower(): kind.append("fault")
        elif "地質境界" in v: kind.append("contact")
        else: kind.append("other")
    kind = np.array(kind); is_fault = kind == "fault"
    con = np.zeros((h, w), np.uint8); flt = np.zeros((h, w), np.uint8)
    for k, g in enumerate(L.geometry):
        for ln in lines(g):
            p = np.round(to_px(ln, H)).astype(np.int32).reshape(-1, 1, 2)
            if kind[k] in ("contact", "fault"):
                cv2.polylines(flt if is_fault[k] else con, [p], False, 1, 1)
    np.save(out / "gt_units.npy", lab); np.save(out / "gt_contacts.npy", con); np.save(out / "gt_faults.npy", flt)
    units = []
    for c in codes:
        rows = A[A.MAJOR_CODE.astype(str) == c].iloc[0]
        units.append({"id": cid[c], "major_code": c,
                      "legend": {k: (None if str(rows[k]) == "None" else str(rows[k])) for k in A.columns if k.startswith("LEGEND")},
                      "area_px": int((lab == cid[c]).sum()), "n_polygons": int((A.MAJOR_CODE.astype(str) == c).sum())})
    json.dump(units, open(out / "units.json", "w"), ensure_ascii=False, indent=1)
    # alignment: distance from each official boundary pixel to the nearest strong colour edge
    lab_img = cv2.cvtColor(cv2.GaussianBlur(rgb, (5, 5), 0), cv2.COLOR_RGB2LAB).astype(np.float32)
    gx = cv2.Sobel(lab_img, cv2.CV_32F, 1, 0); gy = cv2.Sobel(lab_img, cv2.CV_32F, 0, 1)
    mag = np.sqrt((gx ** 2 + gy ** 2).sum(2))
    edges = (mag > np.percentile(mag[lab >= 0], 90)).astype(np.uint8)
    dist = cv2.distanceTransform(1 - edges, cv2.DIST_L2, 3)
    bd = (con > 0) & (lab >= 0)
    d = dist[bd]
    # systematic offset: try integer shifts and report the best one (evidence of residual misregistration)
    best = None
    for dy in range(-8, 9, 2):
        for dx in range(-8, 9, 2):
            ys, xs = np.nonzero(bd); ys2 = np.clip(ys + dy, 0, h - 1); xs2 = np.clip(xs + dx, 0, w - 1)
            m = float(np.median(dist[ys2, xs2]))
            if best is None or m < best[0]: best = (m, dx, dy)
    al = {"n_boundary_px": int(bd.sum()), "median_px": float(np.median(d)), "p90_px": float(np.percentile(d, 90)),
          "frac_within_3px": float((d <= 3).mean()), "best_shift": {"median_px": best[0], "dx": best[1], "dy": best[2]},
          "n_units": len(codes), "line_kinds": {k: int((kind == k).sum()) for k in np.unique(kind)},
          "line_kind_values": {str(v): str(kd) for v, kd in zip(L[tcol].astype(str), kind)},
          "line_type_column": tcol}
    json.dump(al, open(out / "align.json", "w"), indent=1)
    vis = rgb.copy(); vis[con > 0] = (255, 0, 0); vis[flt > 0] = (0, 0, 255)
    vis = cv2.dilate(vis, np.ones((1, 1), np.uint8))
    x0, y0 = [int(v) for v in fr["corners_px"]["tl"]]
    crop = vis[y0 + 900:y0 + 1700, x0 + 1300:x0 + 2300]
    s = 1600 / max(vis.shape[:2])
    cv2.imwrite(str(out / "align_overview.jpg"), cv2.cvtColor(cv2.resize(vis, None, fx=s, fy=s, interpolation=cv2.INTER_AREA), cv2.COLOR_RGB2BGR))
    cv2.imwrite(str(out / "align_check.jpg"), cv2.cvtColor(crop, cv2.COLOR_RGB2BGR))
    print(json.dumps(al))


if __name__ == "__main__":
    main(*sys.argv[1:5])
