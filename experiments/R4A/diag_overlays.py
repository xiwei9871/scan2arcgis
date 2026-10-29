"""R4-A registration diagnosis: local-only overlays of official geo_L on the printed sheet.

For each sheet and each available homography (frame-only, colour-refined, and optional extra
candidates name=path), draws geo_L contacts (frame-only: cyan, colour-refined: magenta, extra:
yellow) and the projected 図郭線 on two crops:
  * the densest-contact 600x600 window inside the neatline (where residuals are judged)
  * the top-left neatline corner (frame placement)
Images go to runs/r4a_diag/vis/<code>_*.jpg (git-ignored: derived from licensed sheets).
Also reports per sheet: share of the map area that geo_A codes as water/sea, contact length,
and the frame-line corner positions under each homography.
"""
import json, os, sys, glob, warnings
from pathlib import Path
import cv2, numpy as np, geopandas as gpd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "R2_real_map"))
from gsj_gt import lines, to_px  # noqa: E402
warnings.filterwarnings("ignore")
COL = {"frame_only": (255, 255, 0), "colour_refined": (255, 0, 255), "extra": (0, 255, 255)}


def draw(im, G, H, col, kinds=("地質境界", "断層"), w=1):
    for g, k in zip(G.geometry, G["LEGEND01"].astype(str)):
        if not any(s in k for s in kinds): continue
        for ln in lines(g):
            cv2.polylines(im, [np.round(to_px(ln, H)).astype(np.int32).reshape(-1, 1, 2)], False, col, w)


def main(code, year, *extra):
    img = f"data/raw/gsj_r4a/GSJ_MAP_G050_{code}_{year}_200dpi.jpg"
    shp = f"data/raw/gsj_r4a/norm/{code}/shp"
    out = Path("runs/r4a_diag/vis"); out.mkdir(parents=True, exist_ok=True)
    im = cv2.imread(img); h, w = im.shape[:2]
    G = gpd.read_file(f"{shp}/geo_L.shp", encoding="cp932"); A = gpd.read_file(f"{shp}/geo_A.shp", encoding="cp932")
    Hs = {}
    for name in ("frame_only", "colour_refined"):
        p = f"runs/r4a/{code}/{'frame.json' if name == 'frame_only' else 'frame_reg.json'}"
        if os.path.exists(p):
            H = np.array(json.load(open(p))["H_lonlat_to_px"], float)
            if np.isfinite(H).all(): Hs[name] = H
    for e in extra:
        n, p = e.split("="); Hs[n] = np.array(json.load(open(p))["H_lonlat_to_px"], float)
    info = {"code": code, "size": [w, h], "homographies": list(Hs)}
    # water share from geo_A legend text (evaluation-free: used only to describe the sheet)
    leg = (A.get("LEGEND01", A.iloc[:, 1]).astype(str))
    water = leg.str.contains("水|海|湖|Water|water|sea")
    info["water_area_frac"] = float(A[water].area.sum() / A.area.sum()) if len(A) else None
    info["contact_len_deg"] = float(G[G["LEGEND01"].astype(str).str.contains("地質境界")].length.sum())
    if not Hs:
        c = im[:min(900, h), :min(1400, w)]
        cv2.imwrite(str(out / f"{code}_topleft_nofr.jpg"), c, [cv2.IMWRITE_JPEG_QUALITY, 85])
        print(json.dumps(info, ensure_ascii=False)); return info
    ref = Hs.get("colour_refined", next(iter(Hs.values())))
    # densest contact window (judged on the reference homography)
    m = np.zeros((h, w), np.uint8); draw_m = m.copy()
    for g, k in zip(G.geometry, G["LEGEND01"].astype(str)):
        if "地質境界" not in k: continue
        for ln in lines(g): cv2.polylines(draw_m, [np.round(to_px(ln, ref)).astype(np.int32).reshape(-1, 1, 2)], False, 1, 1)
    dens = cv2.boxFilter(draw_m.astype(np.float32), -1, (600, 600), normalize=False)
    cy, cx = np.unravel_index(np.argmax(dens), dens.shape)
    y0, x0 = int(np.clip(cy - 300, 0, h - 600)), int(np.clip(cx - 300, 0, w - 600))
    vis = im.copy()
    for n, H in Hs.items():
        draw(vis, G, H, COL.get(n, COL["extra"]))
        draw(vis, G, H, COL.get(n, COL["extra"]), kinds=("図郭",), w=3)
    cv2.imwrite(str(out / f"{code}_dense.jpg"), vis[y0:y0 + 600, x0:x0 + 600], [cv2.IMWRITE_JPEG_QUALITY, 88])
    q = np.array([[0, 0]], float)
    fr = G[G["LEGEND01"].astype(str).str.contains("図郭")]
    if len(fr):
        b = fr.total_bounds; tl = np.array([[b[0], b[3]]])
        info["frame_tl_px"] = {n: [round(float(v), 1) for v in to_px(tl, H)[0]] for n, H in Hs.items()}
        tx, ty = [int(v) for v in to_px(tl, ref)[0]]
        cv2.imwrite(str(out / f"{code}_corner.jpg"), vis[max(ty - 200, 0):ty + 200, max(tx - 200, 0):tx + 200], [cv2.IMWRITE_JPEG_QUALITY, 88])
    info["dense_window"] = [x0, y0, 600, 600]
    print(json.dumps(info, ensure_ascii=False))
    return info


if __name__ == "__main__":
    main(*sys.argv[1:])
