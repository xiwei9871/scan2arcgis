"""Local-only visual check for S2 (original crop, R1 boundaries, L0 lines, B1 changes, review signals).
Writes runs/r3/<sheet>/vis/*.jpg (git-ignored; derived from licensed sheet images)."""
import json, sys
from pathlib import Path
import cv2, numpy as np


def edges(lab, mm):
    b = np.zeros(lab.shape, bool); b[:, 1:] |= lab[:, 1:] != lab[:, :-1]; b[1:, :] |= lab[1:, :] != lab[:-1, :]
    return b & mm


def main(img, r1_dir, s2_dir, out_dir, crop):
    ev = json.load(open(Path(r1_dir) / "r1_eval.json")); out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    rgb = cv2.resize(cv2.cvtColor(cv2.imread(str(img)), cv2.COLOR_BGR2RGB), tuple(ev["work_size"]), interpolation=cv2.INTER_AREA)
    mm = np.load(Path(r1_dir) / "map_mask.npy"); r1 = np.load(Path(r1_dir) / "pred_legend_rf_selftrain.npy").astype(np.int32)
    z = np.load(Path(s2_dir) / "s2_maps.npz"); b1 = z["B1"].astype(np.int32)
    x, y, w, h = [int(v) for v in crop.split(",")]
    def save(name, im): cv2.imwrite(str(out / name), cv2.cvtColor(im[y:y + h, x:x + w], cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 88])
    save("0_original.jpg", rgb)
    v = rgb.copy(); v[edges(r1, mm)] = (255, 0, 0); save("1_r1_boundaries.jpg", v)
    v = (0.5 * rgb + 127).astype(np.uint8); v[z["l0"]] = (0, 0, 0); v[z["l0_long"]] = (0, 90, 255); save("2_l0_lines.jpg", v)
    v = rgb.copy(); v[edges(b1, mm)] = (255, 0, 0); v[(r1 != b1) & mm] = (255, 0, 255); save("3_b1_changes.jpg", v)
    v = (0.5 * rgb + 127).astype(np.uint8); v[cv2.dilate(z["review_line_inside"].astype(np.uint8), np.ones((3, 3))) > 0] = (255, 120, 0)
    v[z["review_boundary_no_ink"]] = (200, 0, 200); save("4_review_signals.jpg", v)
    print("wrote", sorted(p.name for p in out.glob("*.jpg")))


if __name__ == "__main__":
    main(*sys.argv[1:6])
