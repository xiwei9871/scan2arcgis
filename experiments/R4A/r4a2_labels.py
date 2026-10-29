"""R4-A2 label builder (offline, uses official vectors; never imported by prediction code).

On each accepted sheet's GeoTIFF grid (runs/r4a2/<code>/frame_gtf.json, array-index convention):
  unit.npy            int16 official geo_A unit index (-1 outside)            [evaluation + training]
  instance.npy        int32 connected instance id of each unit (4-connected)  [evaluation]
  unit_boundary.npy   uint8 1 px boundary between different units (geo_A)     UNIT_BOUNDARY (raw thin)
  printed_contact.npy uint8 1 px geo_L contacts                               PRINTED_CONTACT (raw thin)
  fault.npy           uint8 1 px geo_L faults                                 FAULT (kept; no output head)
  low_ink_boundary.npy uint8 unit-boundary px with no printed ink within 2 px (candidate, audited)
  ignore.npy          uint8 IGNORE: outside the map, 2 px band at the image edge, and ink-free
                      boundary pixels further than 3 px from any geo_L line (possible vector/print
                      mismatch) are NOT ignored for evaluation but flagged in the audit
  train_boundary.npy  float32 soft training target: exp(-d^2 / 2 sigma^2), sigma = 1.0 px, of the
                      distance to the nearest unit-boundary pixel; band |d| <= 3 px kept, 3 < d <= 5 px
                      set to IGNORE_TRAIN: positive band <= 2 px, uncertainty band 2-8 px (approved rule; covers the 1-2 px residual offset)
  dist.npy            float32 distance (px) to the nearest unit boundary, clipped at 32 (M2 target)
Raw thin labels are kept unchanged for evaluation; widened / soft labels are for training only.
"""
import json, sys
from pathlib import Path
import cv2, numpy as np, rasterio.features, geopandas as gpd, warnings
from affine import Affine

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "experiments" / "R2_real_map"))
from gsj_gt import lines, to_px  # noqa: E402
warnings.filterwarnings("ignore")
SIGMA, BAND, UNC = 1.0, 2.0, 8.0   # positive band <=2 px, IGNORE 2-8 px (approved rule), negatives beyond 8 px


def build(code, out_root="runs/r4a2", shp=None):
    d = ROOT / out_root / code
    fr = json.load(open(d / "frame_gtf.json")); H = np.array(fr["H_lonlat_to_px"]); W, Hh = fr["size"]
    shp = Path(shp) if shp else ROOT / "data/raw/gsj_r4a/norm" / code / "shp"
    A = gpd.read_file(shp / "geo_A.shp", encoding="cp932"); L = gpd.read_file(shp / "geo_L.shp", encoding="cp932")
    codes = sorted(A.MAJOR_CODE.astype(str).unique()); cid = {c: i for i, c in enumerate(codes)}
    # rasterio uses pixel-corner transforms; H is array-index -> build the equivalent affine
    Hc = np.array([[1, 0, 0.5], [0, 1, 0.5], [0, 0, 1.0]]) @ H        # back to corner convention
    inv = Affine(Hc[0, 0], Hc[0, 1], Hc[0, 2], Hc[1, 0], Hc[1, 1], Hc[1, 2]); T = ~inv
    order = A.geometry.area.sort_values(ascending=False).index
    unit = rasterio.features.rasterize(((A.loc[i].geometry, cid[str(A.loc[i].MAJOR_CODE)]) for i in order),
                                       out_shape=(Hh, W), transform=T, fill=-1, dtype="int32")
    inst = np.full(unit.shape, -1, np.int32); k0 = 0
    for j in range(len(codes)):
        n, cc = cv2.connectedComponents((unit == j).astype(np.uint8), connectivity=4)
        m = cc > 0; inst[m] = cc[m] - 1 + k0; k0 += n - 1
    # boundary only between two LABELLED units (audit 2026-10-29: map-edge columns without geo_A
    # coverage produced spurious "boundaries" against -1)
    ub = np.zeros(unit.shape, bool)
    h_ = (unit[:, 1:] != unit[:, :-1]) & (unit[:, 1:] >= 0) & (unit[:, :-1] >= 0); ub[:, 1:] |= h_; ub[:, :-1] |= h_
    v_ = (unit[1:, :] != unit[:-1, :]) & (unit[1:, :] >= 0) & (unit[:-1, :] >= 0); ub[1:, :] |= v_; ub[:-1, :] |= v_
    con = np.zeros(unit.shape, np.uint8); flt = np.zeros(unit.shape, np.uint8)
    for g, k in zip(L.geometry, L["LEGEND01"].astype(str)):
        tgt = flt if "断層" in k else (con if "地質境界" in k else None)
        if tgt is None: continue
        for ln in lines(g): cv2.polylines(tgt, [np.round(to_px(ln, H)).astype(np.int32).reshape(-1, 1, 2)], False, 1, 1)
    rgb = cv2.imread(str(d / "geotiff_rgb.png")); g = cv2.cvtColor(rgb, cv2.COLOR_BGR2GRAY)
    bh = cv2.morphologyEx(g, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
    ink = cv2.dilate((bh > 40).astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
    low_ink = ub & ~ink
    dL = cv2.distanceTransform((con == 0).astype(np.uint8), cv2.DIST_L2, 3)
    dist = cv2.distanceTransform((~ub).astype(np.uint8), cv2.DIST_L2, 3).astype(np.float32)
    ignore = (unit < 0).astype(np.uint8)
    e = np.zeros_like(ignore); e[:2, :] = e[-2:, :] = 1; e[:, :2] = e[:, -2:] = 1; ignore |= e
    ub &= ignore == 0; low_ink &= ignore == 0
    soft = np.exp(-(dist ** 2) / (2 * SIGMA ** 2)).astype(np.float32); soft[dist > BAND] = 0
    ign_train = ignore.copy(); ign_train[(dist > BAND) & (dist <= UNC)] = 1
    np.save(d / "unit.npy", unit.astype(np.int16)); np.save(d / "instance.npy", inst)
    np.save(d / "unit_boundary.npy", ub.astype(np.uint8)); np.save(d / "printed_contact.npy", con); np.save(d / "fault.npy", flt)
    np.save(d / "low_ink_boundary.npy", low_ink.astype(np.uint8)); np.save(d / "ignore.npy", ignore)
    neg_cand = ink & (dist > UNC) & (dL > UNC) & (ignore == 0)       # ink far from any official line: negative CANDIDATES
    np.save(d / "neg_candidate.npy", neg_cand.astype(np.uint8))
    np.save(d / "train_boundary.npy", soft); np.save(d / "ignore_train.npy", ign_train); np.save(d / "dist.npy", np.minimum(dist, 32))
    areas = np.bincount(inst[inst >= 0])
    audit = {"code": code, "size": [W, Hh], "units": len(codes), "instances": int(k0),
             "instance_area_px": {"p10": float(np.percentile(areas, 10)), "median": float(np.median(areas)), "p90": float(np.percentile(areas, 90))},
             "small_instances_lt_5000px": int((areas < 5000).sum()), "small_instances_lt_1000px": int((areas < 1000).sum()),
             "unit_boundary_px": int(ub.sum()), "printed_contact_px": int(con.sum()), "fault_px": int(flt.sum()),
             "unit_boundary_with_geoL_within_3px": float((dL[ub] <= 3).mean()),
             "unit_boundary_with_ink_within_2px": float(ink[ub].mean()),
             "low_ink_boundary_px": int(low_ink.sum()), "low_ink_frac_of_unit_boundary": float(low_ink.mean() / max(ub.mean(), 1e-12)),
             "low_ink_and_far_from_geoL_px": int((low_ink & (dL > 3)).sum()),
             "labelled_frac": float((unit >= 0).mean()), "neg_candidate_ink_px": int(neg_cand.sum()),
             "train_positive_px_frac": float((soft > 0).mean()), "train_ignore_px_frac": float(ign_train.mean()), "params": {"sigma": SIGMA, "band": BAND, "uncertainty_band": UNC, "ink_blackhat_thr": 40}}
    json.dump(audit, open(d / "label_audit.json", "w"), indent=1)
    print(code, {k: (round(v, 3) if isinstance(v, float) else v) for k, v in audit.items() if k not in ("params", "instance_area_px")})
    return audit


if __name__ == "__main__":
    for c in sys.argv[1:]:
        code, _, shp = c.partition("=")
        build(code, shp=(ROOT / shp) if shp else None)
