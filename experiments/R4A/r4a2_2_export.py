"""R4-A2.2 P5: export M0/M1/M2 region maps through the stage-C vector rules (export_pixel_vectors.py).

Same conventions as stage C: X = column, Y = -row of the GeoTIFF-grid image, no CRS, GeoPackage
(geologic_units, contacts, metadata) + Shapefiles without .prj. Work scale 1.0 (regions are already on the
GeoTIFF grid). Each predicted region is split into 4-connected parts (regions_from_labels) so every exported
unit is one connected polygon; validate_pixel_vectors.py recomputes the same split.
Fields: code = None (no semantic naming in R4-A2), review_status from build() (REVIEW without a code),
confidence = UNCALIBRATED region score: M0 mean R1 margin, M1/M2 mean (1 - boundary probability) in the region.
Usage: r4a2_2_export.py <code> <method> <regions.npy> <out_dir> [score.npy] [score_kind: margin|prob]
"""
import json, sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from export_pixel_vectors import CONV, sha, regions_from_labels, build, write_all  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def main(code, method, regions, out_dir, score=None, kind="prob"):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    img = ROOT / "runs/r4a2" / code / "geotiff_rgb.png"
    r = np.load(regions).astype(np.int32)
    valid = (np.load(ROOT / "runs/r4a2" / code / "ignore.npy") == 0) & (r > 0)   # same valid area as the evaluation
    lab = np.where(valid, r - 1, -1).astype(np.int32)
    reg, reg_cls = regions_from_labels(lab, valid)
    np.save(out / "labels.npy", lab); np.save(out / "map_mask.npy", valid)          # inputs for validate_pixel_vectors.py
    n = int(reg.max()) + 1
    if score is not None:
        sc = np.load(score).astype(np.float32); sc = sc if kind == "margin" else 1 - sc
        m = reg >= 0
        conf = np.bincount(reg[m], weights=sc[m], minlength=n) / np.maximum(np.bincount(reg[m], minlength=n), 1)
    else:
        conf = np.full(n, np.nan)
    units, contacts, tr = build(reg, reg_cls, 1.0, lambda k: None, lambda k: None, lambda k: [], lambda k: ["no_semantic_code"],
                                f"R4-A2.2 {method} regions")
    units["confidence"] = [None if np.isnan(conf[k]) else round(float(conf[k]), 4) for k in units["unit_id"]]
    H, W = reg.shape
    meta = {**CONV, "image": img.name, "image_sha256": sha(img), "image_size_px": [W, H], "work_scale": 1.0,
            "work_to_original_transform": list(tr)[:6], "generator": "experiments/R4A/r4a2_2_export.py", "method": method,
            "confidence_definition": "M0: mean R1 classifier margin; M1/M2: mean (1 - boundary probability); UNCALIBRATED",
            "licence": "INTERNAL_RESEARCH_APPROVED_BY_PROJECT_OWNER / THIRD_PARTY_LICENSE_UNCONFIRMED; local only", "scores": "UNCALIBRATED"}
    stem = f"{code}_{method}"
    write_all(out, stem, units, contacts, meta, None)
    s = {"units": len(units), "contacts": len(contacts), "regions_in": int(r.max()), "connected_parts": n,
         "review_status": units["review_status"].value_counts().to_dict(), "confidence_filled": int(units["confidence"].notna().sum())}
    json.dump(s, open(out / f"{stem}_export_summary.json", "w"), indent=1)
    print(stem, s, flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:5], *sys.argv[5:7])
