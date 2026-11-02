"""Legend completeness audit for a GSJ sheet: why do detected swatches (36/38) not cover the
official units (42/45)? Uses the official legend table (xlsx LEGEND_POLY + RGB) only to audit.

Each official unit is put in exactly one category (first that applies):
  granularity    unit code appears in geo_A but not in the legend table, or vice versa
  no_swatch_kind unit has no symbol in the table or is a water/non-geologic area
                 (no independent coloured legend box is printed for these)
  same_colour    official RGB is within dE<3 of another unit's official RGB (same colour,
                 different code: colour alone cannot separate them)
  patterned      unit is printed with a pattern (in-map texture std > 2x sheet median);
                 R1's detector requires a uniform box and may reject it
  detected       a detected swatch is assigned to it (Hungarian on dE between detected swatch
                 fill and official RGB, accepted if dE < 15)
  missed         none of the above: a plain unit whose box was not found
Also reports detected swatches assigned to no unit (spurious detections).
"""
import json, sys
from pathlib import Path
import cv2, numpy as np, pandas as pd, geopandas as gpd, warnings
from scipy.optimize import linear_sum_assignment
warnings.filterwarnings("ignore")


def lab1(rgb):
    a = np.asarray(rgb, np.uint8).reshape(-1, 1, 3)
    L = cv2.cvtColor(a, cv2.COLOR_RGB2LAB).astype(np.float32).reshape(-1, 3)
    return L * np.array([100 / 255, 1, 1], np.float32) - np.array([0, 128, 128], np.float32)


def main(xlsx, shp_dir, r1_dir, errors_json, out_json):
    leg = pd.read_excel(xlsx, "LEGEND_POLY")
    raw = pd.read_excel(xlsx, "RGB", header=None).iloc[3:, :5]
    raw.columns = ["code", "sym", "R", "G", "B"]; raw = raw.dropna(subset=["code"])
    rgb = {float(r.code): (int(r.R), int(r.G), int(r.B)) for r in raw.itertuples()}
    A = gpd.read_file(Path(shp_dir) / "geo_A.shp", encoding="cp932")
    ev = json.load(open(Path(r1_dir) / "r1_eval.json")); er = json.load(open(errors_json))
    tex = {float(r["major_code"]): r["in_map_texture_std"] for r in er["per_unit"]}
    area = {float(u["major_code"]): u["gt_px"] for u in ev["methods"]["legend_rf_selftrain"]["per_unit"]}  # sheets store codes as "1" or "1.0"
    s_map = {float(c) for c in A.MAJOR_CODE.astype(float)}; s_leg = {float(c) for c in leg.MAJOR_CODE}
    units = sorted(s_map | s_leg)
    texv = np.array([t for t in tex.values() if t is not None]); tmed = float(np.median(texv))
    L_off = {c: lab1(rgb[c])[0] for c in units if c in rgb}
    sw = ev["swatches"]; L_sw = lab1([s["fill_rgb"] for s in sw])
    cand = [c for c in units if c in L_off]
    D = np.array([[np.linalg.norm(L_sw[i] - L_off[c]) for c in cand] for i in range(len(sw))])
    r, c = linear_sum_assignment(D)
    det = {cand[j]: (f"S{i:02d}", float(D[i, j])) for i, j in zip(r, c) if D[i, j] < 15}
    used = {v[0] for v in det.values()}
    rows = []
    for u in units:
        lr = leg[leg.MAJOR_CODE == u]
        sym = None if lr.empty or pd.isna(lr.symbol.iloc[0]) else str(lr.symbol.iloc[0])
        name = None if lr.empty else str(lr.LEGEND01.iloc[0])
        key = str(u)
        others = [np.linalg.norm(L_off[u] - L_off[o]) for o in L_off if o != u] if u in L_off else []
        near = min(others) if others else None
        t = tex.get(u)
        if (u in s_map) != (u in s_leg): cat = "granularity"
        elif sym is None or (name and ("水" in name or "Water" in name)) or u >= 88: cat = "no_swatch_kind"
        elif near is not None and near < 3: cat = "same_colour"
        elif u in det: cat = "detected"
        elif t is not None and t > 2 * tmed: cat = "patterned"
        else: cat = "missed"
        rows.append({"major_code": key, "symbol": sym, "name": name, "category": cat, "gt_px": area.get(u, 0),
                     "official_rgb": rgb.get(u), "nearest_official_dE": near, "texture_std": t,
                     "detected_swatch": det.get(u, (None, None))[0], "swatch_dE": det.get(u, (None, None))[1]})
    tot = sum(r["gt_px"] for r in rows) or 1
    cats = ["granularity", "no_swatch_kind", "same_colour", "patterned", "detected", "missed"]
    out = {"n_units": len(rows), "n_detected_swatches": len(sw), "texture_std_sheet_median": tmed,
           "counts": {k: sum(r["category"] == k for r in rows) for k in cats},
           "area_share": {k: sum(r["gt_px"] for r in rows if r["category"] == k) / tot for k in cats},
           "spurious_swatches": [s["id"] for s in sw if s["id"] not in used],
           "same_colour_pairs": sorted({tuple(sorted((a, b))) for a in L_off for b in L_off
                                        if a < b and np.linalg.norm(L_off[a] - L_off[b]) < 3}),
           "units": rows}
    json.dump(out, open(out_json, "w"), ensure_ascii=False, indent=1, default=float)
    print(json.dumps({k: out[k] for k in ("n_units", "n_detected_swatches", "counts", "area_share", "spurious_swatches", "same_colour_pairs")}, default=float))


if __name__ == "__main__":
    main(*sys.argv[1:6])
