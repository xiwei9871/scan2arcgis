"""R4-C0.1b label-free GIS export (replaces the ignore.npy clipping of experiments/R4A/r4a2_2_export.py for products).

Why: ignore.npy is built from official geo_A coverage, so clipping the export with it reads official labels.
GSJ GeoTIFFs have no NoData / alpha (rasterio dataset_mask is all valid), and real geological units can be pure
white (13014: 27,411 pure-white blobs inside labelled units, largest 4,309 px), so an image white/black mask
would delete real units and erode thin ones.
Rule (image + prediction only, nothing is deleted):
  domain     the full image; every predicted region is exported
  margin_candidate  a region that touches the image border AND has >= 90% near-white pixels (all channels > 245)
             is flagged review = "REVIEW_MARGIN" (probable map margin / outside the neatline); it is kept
Region ids, polygons, shared boundaries and attributes otherwise follow experiments/R4A/export_pixel_vectors.build.
Usage: r4c0_1b_export.py <code> <method> <regions.npy> <out_dir> [<score.npy> <prob|margin>]   (.venv)
"""
import json, sys
from pathlib import Path
import cv2, numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "R4A"))
from export_pixel_vectors import CONV, sha, regions_from_labels, build, write_all  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
WHITE, MARGIN_SHARE = 245, 0.9


def margin_flags(reg, rgb):
    n = int(reg.max()) + 1
    white = (rgb > WHITE).all(-1)
    w = np.bincount(reg.ravel(), weights=white.ravel(), minlength=n); a = np.bincount(reg.ravel(), minlength=n)
    border = np.zeros(n, bool)
    for e in (reg[0], reg[-1], reg[:, 0], reg[:, -1]): border[np.unique(e)] = True
    return border & (w / np.maximum(a, 1) >= MARGIN_SHARE)


def main(code, method, regions, out_dir, score=None, kind="prob"):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    img = ROOT / "runs/r4a2" / code / "geotiff_rgb.png"; bgr = cv2.imread(str(img))
    r = np.load(regions).astype(np.int32)
    valid = r > 0                                                   # prediction-defined: every labelled pixel
    lab = np.where(valid, r - 1, -1).astype(np.int32)
    reg, reg_cls = regions_from_labels(lab, valid)
    np.save(out / "labels.npy", lab); np.save(out / "map_mask.npy", valid)
    n = int(reg.max()) + 1
    flag = margin_flags(np.where(reg >= 0, reg, n), bgr)[:n]
    if score is not None:
        sc = np.load(score).astype(np.float32); sc = sc if kind == "margin" else 1 - sc
        m = reg >= 0; conf = np.bincount(reg[m], weights=sc[m], minlength=n) / np.maximum(np.bincount(reg[m], minlength=n), 1)
    else:
        conf = np.full(n, np.nan)
    units, contacts, tr = build(reg, reg_cls, 1.0, lambda k: None, lambda k: None, lambda k: [],
                                lambda k: ["no_semantic_code"] + (["margin_candidate"] if flag[k] else []), f"R4-C0.1b {method} regions")
    units["confidence"] = [None if np.isnan(conf[k]) else round(float(conf[k]), 4) for k in units["unit_id"]]
    units.loc[[bool(flag[k]) for k in units["unit_id"]], "review_status"] = "REVIEW_MARGIN"
    H, W = reg.shape
    meta = {**CONV, "image": img.name, "image_sha256": sha(img), "image_size_px": [W, H], "work_scale": 1.0,
            "work_to_original_transform": list(tr)[:6], "generator": "experiments/R4C0/r4c0_1b_export.py", "method": method,
            "domain": "full image, label-free; margin candidates flagged REVIEW_MARGIN, never deleted",
            "licence": "INTERNAL_RESEARCH_APPROVED_BY_PROJECT_OWNER / THIRD_PARTY_LICENSE_UNCONFIRMED; local only", "scores": "UNCALIBRATED"}
    stem = f"{code}_{method}"; write_all(out, stem, units, contacts, meta, None)
    s = {"units": len(units), "contacts": len(contacts), "margin_candidates": int(flag.sum()),
         "margin_candidate_px": int(np.isin(reg, np.flatnonzero(flag)).sum()), "exported_px": int(valid.sum()), "image_px": int(valid.size)}
    json.dump(s, open(out / f"{stem}_export_summary.json", "w"), indent=1)
    print(stem, s, flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:5], *sys.argv[5:7])
