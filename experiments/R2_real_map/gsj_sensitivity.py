"""Registration sensitivity: hold R1 predictions fixed, perturb only the ground-truth registration.

R1 predictions (pred_*.npy from gsj_run_r1.py) do not depend on registration, so any change in
the metrics below comes from the reference alone. Perturbations are applied in pixel space after
the lon/lat->px homography: pure shifts, isotropic scale about the sheet centre, and rotation.
Also reports interior-only metrics that ignore pixels within 2 or 4 work-px (4 / 8 px at 200 dpi)
of any official unit boundary, so boundary-placement effects can be separated from interior
classification errors. These are additional metrics; the standard ones are unchanged.
"""
import json, sys
from pathlib import Path
import cv2, numpy as np, geopandas as gpd, warnings

sys.path.insert(0, str(Path(__file__).parent))
from gsj_gt import rings, lines, to_px  # noqa: E402
from gsj_run_r1 import evaluate, line_prf, boundary  # noqa: E402
warnings.filterwarnings("ignore")


def rasterize(A, L, H, shape, cid):
    lab = np.full(shape, -1, np.int32)
    for i in A.geometry.area.sort_values(ascending=False).index:
        r = A.loc[i]
        for rr in rings(r.geometry):
            cv2.fillPoly(lab, [np.round(to_px(rr[0], H)).astype(np.int32)], int(cid[str(r.MAJOR_CODE)]))
    con = np.zeros(shape, np.uint8)
    for g, k in zip(L.geometry, L["LEGEND01"].astype(str)):
        if "地質境界" not in k: continue
        for ln in lines(g):
            cv2.polylines(con, [np.round(to_px(ln, H)).astype(np.int32).reshape(-1, 1, 2)], False, 1, 1)
    return lab, con > 0


def perturb(H, kind, v, centre):
    cx, cy = centre
    T = lambda tx, ty: np.array([[1, 0, tx], [0, 1, ty], [0, 0, 1.0]])
    if kind == "shift": P = T(v, 0) if v >= 0 else T(0, -v)   # +v: shift x, -v: shift y (keeps a 1-D sweep)
    elif kind == "shift_diag": P = T(v / np.sqrt(2), v / np.sqrt(2))
    elif kind == "scale": P = T(cx, cy) @ np.diag([1 + v, 1 + v, 1]) @ T(-cx, -cy)
    elif kind == "rotate":
        a = np.deg2rad(v); P = T(cx, cy) @ np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]]) @ T(-cx, -cy)
    else: P = np.eye(3)
    return P @ H


def main(frame_json, shp_dir, r1_dir, out_json, method="legend_rf_selftrain"):
    d = Path(r1_dir); ev = json.load(open(d / "r1_eval.json")); s = ev["scale"]
    w, h = ev["work_size"]
    pred = np.load(d / f"pred_{method}.npy").astype(np.int32); mm = np.load(d / "map_mask.npy")
    fr = json.load(open(frame_json)); H = np.diag([s, s, 1.0]) @ np.array(fr["H_lonlat_to_px"])
    A = gpd.read_file(Path(shp_dir) / "geo_A.shp", encoding="cp932"); L = gpd.read_file(Path(shp_dir) / "geo_L.shp", encoding="cp932")
    codes = sorted(A.MAJOR_CODE.astype(str).unique()); cid = {c: i for i, c in enumerate(codes)}
    units = [{"major_code": c, "legend": {"LEGEND01": None}} for c in codes]
    centre = np.array(np.nonzero(mm)).mean(1)[::-1]
    tol = 1.5
    cb = boundary(np.where(mm, pred, -1)) & mm
    rows = []
    # work px = 2 px at 200 dpi
    sweep = [("none", 0)] + [("shift_diag", v) for v in (0.5, 1, 2, 4, 8)] + [("shift", v) for v in (2, -2, 4, -4)] \
            + [("scale", v) for v in (0.0005, 0.001, 0.002)] + [("rotate", v) for v in (0.02, 0.05, 0.1)]
    for kind, v in sweep:
        gt, gtc = rasterize(A, L, perturb(H, kind, v, centre), (h, w), cid)
        e = evaluate(pred, gt, mm, units, tol)
        gb = boundary(np.where(mm, gt, -1)) & mm & (gt >= 0)
        r = {"kind": kind, "value": v, "value_px200": (v * 2 if kind.startswith("shift") else None),
             "pixel_acc": e["pixel_acc_matched"], "miou": e["miou_matched_all_units"], "fw_iou": e["fw_iou_matched"],
             "contact_f1": line_prf(cb, gtc, mm, tol)["f1"], "boundary_from_areas_f1": e["boundary_from_areas"]["f1"]}
        for band in (2, 4):
            far = cv2.distanceTransform((~gb).astype(np.uint8), cv2.DIST_L2, 3) > band
            ei = evaluate(pred, gt, mm & far, units, tol)
            r[f"interior{band}_pixel_acc"] = ei["pixel_acc_matched"]; r[f"interior{band}_miou"] = ei["miou_matched_all_units"]
            r[f"interior{band}_px_frac"] = float((mm & far & (gt >= 0)).sum() / max((mm & (gt >= 0)).sum(), 1))
        rows.append(r)
        print(json.dumps({k: (round(x, 4) if isinstance(x, float) else x) for k, x in r.items()}), flush=True)
    base = rows[0]
    json.dump({"method": method, "work_scale": s, "note": "predictions fixed; only GT registration perturbed",
               "rows": rows,
               "delta_vs_none": [{"kind": r["kind"], "value": r["value"],
                                  "d_miou": r["miou"] - base["miou"], "d_contact_f1": r["contact_f1"] - base["contact_f1"],
                                  "d_pixel_acc": r["pixel_acc"] - base["pixel_acc"]} for r in rows[1:]]},
              open(out_json, "w"), indent=1, default=float)


if __name__ == "__main__":
    main(*sys.argv[1:5], *(sys.argv[5:6] or []))
