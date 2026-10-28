"""Local-only S1 visual check: legend OCR, in-map code anchors, R1 vs S1-A3 code map, review regions.
Writes runs/r3/<sheet>/vis_s1/*.jpg (git-ignored; derived from licensed sheet images)."""
import json, sys
from pathlib import Path
import cv2, numpy as np


def main(img, r1_dir, s1_dir, legend_ocr, spot, out_dir, crop):
    ev = json.load(open(Path(r1_dir) / "r1_eval.json")); s = ev["scale"]; out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    full = cv2.cvtColor(cv2.imread(str(img)), cv2.COLOR_BGR2RGB)
    rgb = cv2.resize(full, tuple(ev["work_size"]), interpolation=cv2.INTER_AREA)
    z = np.load(Path(s1_dir) / "s1_maps.npz"); meta = json.load(open(Path(s1_dir) / "s1_meta.json"))
    x, y, w, h = [int(v) for v in crop.split(",")]
    leg = json.load(open(legend_ocr))["swatches"]; boxes = {sw["id"]: sw["box"] for sw in ev["swatches"]}
    v = rgb.copy()
    for r in leg:
        bx, by, bw, bh = boxes[r["swatch"]]; cv2.rectangle(v, (bx, by), (bx + bw, by + bh), (255, 0, 0), 1)
        cv2.putText(v, str(r["tess_sub_case"]["code"]), (bx + bw + 3, by + bh - 4), 0, 0.45, (255, 0, 0), 1)
    xs = [b[0] for b in boxes.values()]; ys = [b[1] for b in boxes.values()]
    cv2.imwrite(str(out / "1_legend_ocr.jpg"), cv2.cvtColor(v[max(min(ys) - 10, 0):max(ys) + 60, max(min(xs) - 10, 0):max(xs) + 160], cv2.COLOR_RGB2BGR))
    v = rgb.copy()
    for c in json.load(open(spot))["candidates"]:
        if c["reader"] != "rapid": continue
        bx, by, bw, bh = [t * s for t in c["box_px"]]; col = (0, 160, 0) if c["code"] else (160, 160, 160)
        cv2.rectangle(v, (int(bx), int(by)), (int(bx + bw), int(by + bh)), col, 1)
        if c["code"]: cv2.putText(v, c["code"], (int(bx), int(by) - 2), 0, 0.4, (0, 120, 0), 1)
    cv2.imwrite(str(out / "2_map_code_anchors.jpg"), cv2.cvtColor(v[y:y + h, x:x + w], cv2.COLOR_RGB2BGR))
    a3 = z["A3"].astype(np.int32); reg = z["regions"]
    rng = np.random.default_rng(0); pal = rng.integers(40, 255, (len(meta["codes"]) + 1, 3)).astype(np.uint8)
    col = np.where(a3[..., None] >= 0, pal[np.clip(a3, 0, None)], 0).astype(np.uint8)
    v = (0.45 * rgb + 0.55 * col).astype(np.uint8); v[a3 < 0] = (255, 255, 255)
    cv2.imwrite(str(out / "3_s1_A3_codes.jpg"), cv2.cvtColor(v[y:y + h, x:x + w], cv2.COLOR_RGB2BGR))
    v = (0.5 * rgb + 127).astype(np.uint8)
    cmap = {"MULTI_CODE": (255, 0, 0), "ANCHOR_COLOUR_CONFLICT": (255, 140, 0), "SAME_COLOUR_NO_ANCHOR": (160, 0, 200),
            "NO_LEGEND_CODE": (0, 0, 0), "METHOD_DISAGREE": (0, 120, 255)}
    for rc in meta["review_candidates"]: v[reg == rc["region"]] = cmap[rc["reasons"][0]]
    cv2.imwrite(str(out / "4_review_regions.jpg"), cv2.cvtColor(v[y:y + h, x:x + w], cv2.COLOR_RGB2BGR))
    cv2.imwrite(str(out / "0_original.jpg"), cv2.cvtColor(rgb[y:y + h, x:x + w], cv2.COLOR_RGB2BGR))
    print("wrote", sorted(p.name for p in out.glob("*.jpg")))


if __name__ == "__main__":
    main(*sys.argv[1:8])
