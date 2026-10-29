"""R4-A2.2 M0 baseline on a sheet's GeoTIFF grid (freeze_config.json models.M0, unchanged R1 code).

R1 legend_rf_selftrain as shipped. Legend swatches are detected automatically (R1 detect_swatches) on the
sheet's own legend JPEGs from the same GSJ GeoTIFF package (<pkg>/*_L*.jpg, ~200 dpi; for 15023/15041 the
package has no single full-sheet JPEG, the legend is published as separate L*.jpg strips). Classification
runs on a composite: GeoTIFF map (0.5x) | 8 px white gap | legend strips stacked vertically (0.5x).
Map mask = valid GeoTIFF content (not ignore.npy, which is label-derived): pixels that are not pure
white/black padding, eroded 9 px at 0.5x (as gsj_run_r1). Labels upsampled (nearest) to the GeoTIFF grid.
Regions = 4-connected components of the class map (postprocess_fixed.M0). No official vector is read.
Usage: r4a2_2_m0.py <code> <out_dir>   (.venv-ml)
"""
import glob, json, sys, time
from pathlib import Path
import cv2, numpy as np

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "src"))
from scan2arcgis.recog.legend_classifier import LegendClass, classify  # noqa: E402
from scan2arcgis.recog.legend_swatches import detect_swatches  # noqa: E402

S = 0.5


def content_mask(rgb):
    g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    m = ~(((rgb > 250).all(-1)) | ((rgb < 5).all(-1)))
    n, cc, st, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8), connectivity=4)
    if n > 1: m = cc == 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    return cv2.erode(m.astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool)


def main(code, out_dir):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    full = cv2.cvtColor(cv2.imread(str(ROOT / "runs/r4a2" / code / "geotiff_rgb.png")), cv2.COLOR_BGR2RGB)
    H, W = full.shape[:2]
    mp = cv2.resize(full, None, fx=S, fy=S, interpolation=cv2.INTER_AREA)
    legs = sorted(glob.glob(str(ROOT / f"data/raw/gsj_gtf/GSJ_MAP_G050_{code}_*/*_L*.jpg")))
    strips = [cv2.resize(cv2.cvtColor(cv2.imread(f), cv2.COLOR_BGR2RGB), None, fx=S, fy=S, interpolation=cv2.INTER_AREA) for f in legs]
    lw = max(s.shape[1] for s in strips); lh = sum(s.shape[0] for s in strips) + 8 * (len(strips) - 1)
    Hc, ox = max(mp.shape[0], lh), mp.shape[1] + 8
    comp = np.full((Hc, ox + lw, 3), 255, np.uint8); comp[:mp.shape[0], :mp.shape[1]] = mp
    y = 0
    for s in strips: comp[y:y + s.shape[0], ox:ox + s.shape[1]] = s; y += s.shape[0] + 8
    mm = np.zeros(comp.shape[:2], bool); mm[:mp.shape[0], :mp.shape[1]] = content_mask(mp)
    sw = detect_swatches(comp, (ox, 0, lw, lh), min_side=18, max_side=int(400 * S))
    classes = [LegendClass(i, d["legend_entry_id"], tuple(d["box"]), d["legend_entry_id"]) for i, d in enumerate(sw)]
    t0 = time.time(); ar = classify(comp, mm, classes, self_train=True); dt = time.time() - t0
    lab = ar.labels[:mp.shape[0], :mp.shape[1]].astype(np.int32)
    lab_full = cv2.resize(lab, (W, H), interpolation=cv2.INTER_NEAREST)
    valid = cv2.resize(mm[:mp.shape[0], :mp.shape[1]].astype(np.uint8), (W, H), interpolation=cv2.INTER_NEAREST) > 0
    lab_full[~valid] = -1
    reg = np.zeros((H, W), np.int32); k0 = 0
    for k in np.unique(lab_full[lab_full >= 0]):
        n, cc = cv2.connectedComponents((lab_full == k).astype(np.uint8), connectivity=4)
        m = cc > 0; reg[m] = cc[m] + k0; k0 += n - 1
    mg = cv2.resize(ar.margin[:mp.shape[0], :mp.shape[1]].astype(np.float32), (W, H), interpolation=cv2.INTER_NEAREST)
    np.save(out / "margin.npy", mg.astype(np.float16))                # R1 classifier margin (uncalibrated)
    np.save(out / "class_map.npy", lab_full.astype(np.int16)); np.save(out / "regions_M0.npy", reg)
    meta = {"code": code, "legend_jpegs": [Path(f).name for f in legs], "n_swatches": len(sw), "scale": S,
            "classify_s": round(dt, 1), "n_regions": int(k0), "map_valid_frac": float(valid.mean()),
            "swatches": [{"id": d["legend_entry_id"], "box": d["box"], "fill_rgb": d["fill_rgb"]} for d in sw]}
    json.dump(meta, open(out / "m0_meta.json", "w"), indent=1, default=float)
    print(code, {k: v for k, v in meta.items() if k != "swatches"}, flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:3])
