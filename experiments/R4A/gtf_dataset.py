"""R4-A2 dataset builder: walk the FROZEN draw order (sheet_draw.json, seed 20261028), skip the
pre-declared exclusions, and accept sheets whose GSJ GeoTIFF passes the unchanged Q1/Q2/Q3 rules.

Exclusions (declared before any new download, see docs/research/r4a/r4a2_plan.md):
  development sheets 05030, 06061, 08004, 08001 (used in method development)
  validation candidates 15061, 13068 (inspected during registration diagnosis)
  sealed holdout 08011, 08021 (never read; region 08 is not in either pool anyway)
Rules (experiments/R4A/sheet_qc_rules.md, unchanged):
  Q1 data complete: GeoTIFF + vector zip readable; geo_L has 地質境界線 and 図郭線
  Q2 standard 1:50k quadrangle (0.25 deg x 1/6 deg +-0.002; geo_A bounds == frame bounds)
  Q3 unchanged R2 ink check on the GeoTIFF image with the published affine in array-index convention
     (AREA_OR_POINT=Area -> -0.5 px; fixed, no fitting): residual<=2 px, z>=5, trusted>=12, cell median<=2
Every candidate visited is logged with its status, in order. The walk stops at the target count.
Usage: gtf_dataset.py <train|validation> <target> <out_json>
"""
import json, os, subprocess, sys, zipfile, hashlib, time
from pathlib import Path
import numpy as np, rasterio

ROOT = Path(__file__).resolve().parents[2]
EXCLUDE = {"05030": "development sheet", "06061": "development sheet", "08004": "development sheet",
           "08001": "development sheet", "15061": "inspected in registration diagnosis",
           "13068": "inspected in registration diagnosis", "08011": "sealed holdout", "08021": "sealed holdout"}
PY = str(ROOT / ".venv/bin/python")
RAW = ROOT / "data/raw/gsj_r4a"; GTF = ROOT / "data/raw/gsj_gtf"


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()


def fetch(url, dest):
    if dest.exists() and dest.stat().st_size > 0: return "cached"
    r = subprocess.run(["curl", "-sL", "--noproxy", "*", "-m", "900", "-A", "Mozilla/5.0", "-o", str(dest), "-w", "%{http_code}", url],
                       capture_output=True, text=True)
    return r.stdout.strip()


def frame_from_geotiff(tif, out_json):
    with rasterio.open(tif) as d:
        T = d.transform; W, H = d.width, d.height; aop = d.tags().get("AREA_OR_POINT")
        rgb = np.moveaxis(d.read([1, 2, 3]), 0, -1)
    inv = ~T
    Hm = np.array([[inv.a, inv.b, inv.c], [inv.d, inv.e, inv.f], [0, 0, 1.0]])
    if aop == "Area": Hm = np.array([[1, 0, -0.5], [0, 1, -0.5], [0, 0, 1.0]]) @ Hm
    b = [T.c, T.f + T.e * H, T.c + T.a * W, T.f]
    def px(lon, lat):
        p = Hm @ np.array([lon, lat, 1.0]); return [float(p[0] / p[2]), float(p[1] / p[2])]
    fr = {"size": [W, H], "bounds_lonlat": b, "H_lonlat_to_px": Hm.tolist(), "area_or_point": aop,
          "corners_px": {"tl": px(b[0], b[3]), "tr": px(b[2], b[3]), "br": px(b[2], b[1]), "bl": px(b[0], b[1])},
          "registration": {"method": "GSJ GeoTIFF affine as published, array-index convention (-0.5 px if Area); no fitting"}}
    json.dump(fr, open(out_json, "w"), indent=1)
    return rgb, fr


def process(rec):
    code, year = rec["code"], rec["year"]
    row = {"code": code, "year": year}
    gz = GTF / f"GSJ_MAP_G050_{code}_{year}.zip"; vz = RAW / f"GSJ_MAP_G050_{code}_{year}_V01.zip"
    vname = Path(rec["vct"]).name; vz = RAW / vname
    row["http_gtf"] = fetch(f"https://www.gsj.jp/data/50KGM/GTF/GSJ_MAP_G050_{code}_{year}.zip", gz)
    row["http_vct"] = fetch(f"https://www.gsj.jp/data/50KGM/{rec['vct']}", vz)
    try:
        for z, d in ((gz, GTF / gz.stem), (vz, RAW / code)):
            with zipfile.ZipFile(z) as f:
                if f.testzip() is not None: raise ValueError(f"bad zip {z.name}")
                f.extractall(d)
        tifs = list((GTF / gz.stem).glob("*_geotiff.tif"))
        if not tifs: raise ValueError("no *_geotiff.tif in GTF zip")
        row["sha256"] = {"gtf_zip": sha(gz), "vct_zip": sha(vz)}
    except Exception as e:
        row["status"] = "FAIL_Q1_data"; row["error"] = str(e)[:200]; return row
    r = subprocess.run([PY, str(ROOT / "experiments/R4A/prepare_sheet.py"), code], capture_output=True, text=True, cwd=ROOT)
    if r.returncode: row["status"] = "FAIL_Q1_vector"; row["error"] = r.stderr[-200:]; return row
    info = json.load(open(RAW / "norm" / code / "sheet_info.json"))
    lt = info["line_types"]; b = info["bounds_lonlat"]
    if not (any("地質境界" in x for x in lt) and any("図郭" in x for x in lt)):
        row["status"] = "FAIL_Q1_line_types"; row["line_types"] = lt; return row
    w, h = b[2] - b[0], b[3] - b[1]; row["quadrangle_deg"] = [round(w, 4), round(h, 4)]
    if not (abs(w - 0.25) <= 0.002 and abs(h - 1 / 6) <= 0.002):
        row["status"] = "FAIL_Q2_nonstandard_quadrangle"; return row
    out = ROOT / f"runs/r4a2/{code}"; out.mkdir(parents=True, exist_ok=True)
    import cv2
    rgb, fr = frame_from_geotiff(tifs[0], out / "frame_gtf.json")
    cv2.imwrite(str(out / "geotiff_rgb.png"), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    row.update(geotiff=tifs[0].name, size=fr["size"], area_or_point=fr["area_or_point"],
               bounds_offset_vs_frame_deg=float(max(abs(x - y) for x, y in zip(fr["bounds_lonlat"], b))))
    r = subprocess.run([PY, str(ROOT / "experiments/R2_real_map/gsj_reg_independent.py"), str(out / "geotiff_rgb.png"),
                        str(RAW / "norm" / code / "shp"), str(out / "reg_independent.json"), f"gtf={out / 'frame_gtf.json'}"],
                       capture_output=True, text=True, cwd=ROOT)
    if r.returncode: row["status"] = "FAIL_Q3_check_error"; row["error"] = r.stderr[-200:]; return row
    cr = json.load(open(out / "reg_independent.json"))["candidates"]["gtf"]; g = cr["global"]
    res = float(np.hypot(g["dx"], g["dy"])); med = cr["cell_offset_abs_median_px"]
    row["q3"] = {"dx": g["dx"], "dy": g["dy"], "residual_px": res, "z": g["contrast_z"], "cells_trusted": cr["cells_trusted"],
                 "cell_median_px": med, "cell_max_px": cr["cell_offset_abs_max_px"]}
    ok = res <= 2 and g["contrast_z"] >= 5 and cr["cells_trusted"] >= 12 and med is not None and med <= 2
    row["status"] = "PASS" if ok else "FAIL_Q3_registration"
    return row


def main(role, target, out_json):
    target = int(target)
    draw = json.load(open(ROOT / "experiments/R4A/sheet_draw.json"))
    order = draw["train_order" if role == "train" else "validation_order"]
    log, accepted = [], []
    for i, rec in enumerate(order):
        if len(accepted) >= target: break
        if rec["code"] in EXCLUDE:
            log.append({"order": i, "code": rec["code"], "status": "SKIP_EXCLUDED", "reason": EXCLUDE[rec["code"]]}); continue
        t0 = time.time(); row = process(rec); row["order"] = i; row["seconds"] = round(time.time() - t0, 1)
        log.append(row)
        if row["status"] == "PASS": accepted.append(rec["code"])
        q = row.get("q3", {})
        print(i, rec["code"], row["status"], {k: round(v, 2) for k, v in q.items() if isinstance(v, float)}, flush=True)
    res = {"role": role, "target": target, "accepted": accepted, "reached_target": len(accepted) >= target,
           "visited": len(log), "draw_seed": draw["seed"], "exclusions": EXCLUDE, "log": log}
    json.dump(res, open(out_json, "w"), ensure_ascii=False, indent=1, default=float)
    print(role, "accepted", len(accepted), accepted)


if __name__ == "__main__":
    main(*sys.argv[1:4])
