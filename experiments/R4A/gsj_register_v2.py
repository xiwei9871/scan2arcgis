"""R4-A registration v2: neatline-only, image + sheet metadata only (no geo_A, no geo_L).

Why (diagnosis, docs/research/r4a/registration_diagnosis.md): GSJ 1:50k sheets print a double
border. The R2 detector takes the OUTERMOST long dark lines (often the thick outer border) and
relied on geo_A colour refinement to pull the frame onto the inner neatline; on other sheets that
refinement converged to wrong places, and a fixed grey threshold (<110) missed lighter borders.

Method
  1. black-hat (15 px) of grey -> long horizontal / vertical line masks (morphological opening
     with kernels of 30% of the nominal side length). Contrast-based, no absolute threshold.
  2. nominal neatline size from the quadrangle alone: 1:50,000 at 200 dpi
     height = dlat * 111132.954 m / 50 m-per-mm * 200/25.4 px; width uses cos(mid-lat).
  3. candidate top/bottom rows and left/right columns = peaks of the line masks; every
     (top,bottom) and (left,right) pair within +-10% of nominal is scored by
       |log(h/Hn)| + |log(w/Wn)| + 2*|log(h/Hn) - log(w/Wn)|
     (closeness to nominal print size, and isotropic scale between the two axes).
  4. each chosen side is refined by a robust line fit to its mask pixels; corners = intersections;
     homography from the 4 corners to the quadrangle bounds (same as R2 fit_geo).
Nothing here reads official vectors except the quadrangle bounds in sheet_info.json.
"""
import json, sys, time
from pathlib import Path
import cv2, numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "R2_real_map"))
from gsj_frame import fit_side, intersect, fit_geo  # noqa: E402

DPI, SCALE = 200.0, 50000.0


def nominal_px(b):
    lat = np.deg2rad((b[1] + b[3]) / 2)
    mm_per_m = 1000.0 / SCALE
    h = (b[3] - b[1]) * 111132.954 * mm_per_m / 25.4 * DPI
    w = (b[2] - b[0]) * 111319.49 * np.cos(lat) * mm_per_m / 25.4 * DPI
    return float(w), float(h)


def peaks(profile, thr, sep=6):
    idx = np.flatnonzero(profile > thr)
    if not len(idx): return []
    groups = np.split(idx, np.flatnonzero(np.diff(idx) > sep) + 1)
    return [int(g[np.argmax(profile[g])]) for g in groups]


def detect(rgb, bounds):
    g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    h, w = g.shape
    Wn, Hn = nominal_px(bounds)
    bh = cv2.morphologyEx(g, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15)))
    thr, _ = cv2.threshold(bh, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    m = (bh > max(thr, 20)).astype(np.uint8)
    hor = cv2.morphologyEx(m, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (int(0.3 * Wn), 1)))
    ver = cv2.morphologyEx(m, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, int(0.3 * Hn))))
    rows = peaks(hor.sum(1).astype(float), 0.4 * Wn); cols = peaks(ver.sum(0).astype(float), 0.4 * Hn)
    best = None
    for t in rows:
        for b_ in rows:
            hh = b_ - t
            if not (0.9 * Hn <= hh <= 1.1 * Hn): continue
            for l in cols:
                for r in cols:
                    ww = r - l
                    if not (0.9 * Wn <= ww <= 1.1 * Wn): continue
                    sh, sw = np.log(hh / Hn), np.log(ww / Wn)
                    s = abs(sh) + abs(sw) + 2 * abs(sh - sw)
                    if best is None or s < best[0]: best = (s, t, b_, l, r)
    info = {"nominal_wh_px": [round(Wn, 1), round(Hn, 1)], "row_peaks": rows, "col_peaks": cols,
            "blackhat_thr": float(max(thr, 20))}
    if best is None:
        return None, info
    s, t, b_, l, r = best
    info.update(score=float(s), chosen={"top": t, "bottom": b_, "left": l, "right": r},
                scale_h=float((b_ - t) / Hn), scale_w=float((r - l) / Wn))
    sides = {}
    for name, idx, mask, is_row in (("top", t, hor, True), ("bottom", b_, hor, True), ("left", l, ver, False), ("right", r, ver, False)):
        lo = max(idx - 4, 0)
        if is_row:
            sub = mask[lo:idx + 5, max(l - 20, 0):r + 21]; ys, xs = np.nonzero(sub)
            pts = np.stack([xs + max(l - 20, 0), ys + lo], 1)
        else:
            sub = mask[max(t - 20, 0):b_ + 21, lo:idx + 5]; ys, xs = np.nonzero(sub)
            pts = np.stack([xs + lo, ys + max(t - 20, 0)], 1)
        sides[name] = fit_side(pts)
    c = {"tl": intersect(sides["top"], sides["left"]), "tr": intersect(sides["top"], sides["right"]),
         "br": intersect(sides["bottom"], sides["right"]), "bl": intersect(sides["bottom"], sides["left"])}
    return {k: [float(v[0]), float(v[1])] for k, v in c.items()}, info


def main(img, sheet_info_json, out_json):
    t0 = time.time()
    rgb = cv2.cvtColor(cv2.imread(str(img)), cv2.COLOR_BGR2RGB)
    b = json.load(open(sheet_info_json))["bounds_lonlat"]
    corners, info = detect(rgb, b)
    res = {"image": Path(img).name, "method": "v2 neatline-only (image + quadrangle bounds; no geo_A/geo_L)",
           "bounds_lonlat": b, "detect": info, "seconds": None}
    if corners is None:
        res["status"] = "FRAME_NOT_FOUND"
    else:
        H = fit_geo(corners, b)
        res.update(status="OK", corners_px=corners, H_lonlat_to_px=H.tolist())
    res["seconds"] = round(time.time() - t0, 2)
    Path(out_json).parent.mkdir(parents=True, exist_ok=True)
    json.dump(res, open(out_json, "w"), indent=1)
    print(res["status"], {k: info.get(k) for k in ("nominal_wh_px", "chosen", "scale_h", "scale_w")}, res["seconds"], "s")


if __name__ == "__main__":
    main(*sys.argv[1:4])
