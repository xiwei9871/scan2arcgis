"""R4-B2 full-image inference (prediction side: image only; no label is read).

Tiling as experiments/R4A/r4a2_2_infer.predict (512 px tiles, stride 384, triangular blending).
Outputs: prob_right.npy, prob_down.npy, dist_px.npy (float16) and regions_B2.npy from the FROZEN rule
r4b2_edges.regions_from_probs(pr, pd) with domain=None (full image).
Usage: r4b2_infer.py <best.pt> <image.png> <out_dir>   (.venv-ml)
"""
import json, sys, time
from pathlib import Path
import cv2, numpy as np, torch

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "R4A"))
import r4b2_edges as E  # noqa: E402
from r4a2_train import UNet  # noqa: E402
from r4a2_2_infer import predict  # noqa: E402


def main(ckpt, image, out_dir):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    dev = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    model = UNet(3).to(dev); model.load_state_dict(torch.load(ckpt, map_location=dev, weights_only=True))
    rgb = cv2.cvtColor(cv2.imread(str(image)), cv2.COLOR_BGR2RGB)
    t0 = time.time(); o = predict(model, rgb, dev, 3); t_inf = time.time() - t0
    pr, pd, dist = o[0], o[1], o[2] * 32
    for k, v in (("prob_right", pr), ("prob_down", pd), ("dist_px", dist)): np.save(out / f"{k}.npy", v.astype(np.float16))
    t0 = time.time(); reg, merged = E.regions_from_probs(pr, pd); t_pp = time.time() - t0
    np.save(out / "regions_B2.npy", reg.astype(np.int32))
    meta = {"ckpt": str(ckpt), "image": str(image), "size": list(rgb.shape[:2]), "device": str(dev), "inference_s": round(t_inf, 1),
            "reconstruction_s": round(t_pp, 1), "regions": int(reg.max()), "cleanup_merges": int(merged), "domain": "full image (frozen rule)"}
    json.dump(meta, open(out / "infer_meta.json", "w"), indent=1); print(json.dumps(meta), flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:4])
