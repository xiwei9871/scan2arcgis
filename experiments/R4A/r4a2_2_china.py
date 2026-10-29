"""R4-A2.2 China zero-shot qualitative check (freeze_config.json data_roles.china_qualitative).

Inputs: runs/real/<work>/work.png map part (work.json map_box_work), the same work images R1 used.
M1/M2 run unchanged (no fine-tuning, no parameter change). No reference labels exist: NO accuracy is
reported, only descriptive counts (regions, regions < 200 px, boundary-pixel share, M0 region count from
the existing R1 run for scale) and local overlays for visual review.
Usage: r4a2_2_china.py <M1.pt> <M2.pt> <out_dir>   (.venv-ml)
"""
import json, sys
from pathlib import Path
import cv2, numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import r4a2_2_infer as I  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
WORKS = ["gm2_roi", "u1", "u2", "u3"]


def bnd(lab):
    b = np.zeros(lab.shape, bool); b[:, 1:] |= lab[:, 1:] != lab[:, :-1]; b[1:] |= lab[1:] != lab[:-1]
    return b


def main(m1, m2, out_dir):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True); summary = {}
    for w in WORKS:
        wj = json.load(open(ROOT / f"runs/real/{w}/work.json")); x, y, ww, hh = wj["map_box_work"]
        img = ROOT / f"runs/real/{w}/work.png"; crop = f"{x},{y},{ww},{hh}"
        rgb = cv2.cvtColor(cv2.imread(str(img)), cv2.COLOR_BGR2RGB)[y:y + hh, x:x + ww]
        s = {"work": w, "size": [hh, ww], "scale_vs_original": wj.get("scale")}
        panels = [rgb]
        for name, ck in (("M1", m1), ("M2", m2)):
            od = out / w / name; I.main(name, ck, img, od, crop)
            prob = np.load(od / "prob.npy").astype(np.float32)
            s[f"{name}_boundary_px_share_p0.5"] = float((prob > 0.5).mean())
            for f in sorted(od.glob("regions_*.npy")):
                r = np.load(f); a = np.bincount(r.ravel())[1:]
                s[f.stem.replace("regions_", "")] = {"regions": int((a > 0).sum()), "regions_lt_200px": int(((a > 0) & (a < 200)).sum())}
                p = rgb.copy(); p[bnd(r)] = (220, 0, 0); panels.append(p)
        summary[w] = s
        cv2.imwrite(str(out / f"{w}_overlay.jpg"), cv2.cvtColor(np.hstack(panels), cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 80])
        print(w, s, flush=True)
    summary["note"] = "zero-shot, no reference labels: descriptive counts only, no accuracy"
    json.dump(summary, open(out / "china_zero_shot.json", "w"), indent=1)


if __name__ == "__main__":
    main(*sys.argv[1:4])
