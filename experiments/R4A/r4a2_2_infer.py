"""R4-A2.2 full-image inference and frozen post-processing for M1/M2 (prediction side: image only).

Inference: 512 px tiles, stride 384, outputs blended with a separable triangular weight (no test-time
augmentation, no threshold or parameter chosen on validation sheets).
Post-processing (freeze_config.json postprocess_fixed + freeze_config_v2.json postprocess_v2):
  M1          watershed on boundary probability; markers = CC(p < 0.3) with area >= 50 px
  M2_oldseed  watershed on -dist_pred; markers = CC(dist_pred_px >= 3) with area >= 50 px
  M2_hybrid   watershed on -dist_pred; markers = r4a2_1_seeds.hybrid_markers(dist_pred_px)
Usage: r4a2_2_infer.py <M1|M2> <best.pt> <image.png|jpg> <out_dir> [x,y,w,h crop]   (.venv-ml)
Writes prob.npy (float16), dist_px.npy (M2), and region maps regions_<rule>.npy (int32) to out_dir.
"""
import json, sys, time
from pathlib import Path
import cv2, numpy as np, torch

sys.path.insert(0, str(Path(__file__).parent))
from r4a2_train import UNet  # noqa: E402
from r4a2_1_seeds import old_markers, hybrid_markers, segment  # noqa: E402
from skimage.segmentation import watershed  # noqa: E402

TILE, STRIDE = 512, 384


def _starts(n):
    if n <= TILE: return [0]
    s = list(range(0, n - TILE + 1, STRIDE))
    return s if s[-1] == n - TILE else s + [n - TILE]


def predict(model, rgb, dev, heads):
    H, W = rgb.shape[:2]
    ph, pw = max(0, TILE - H), max(0, TILE - W)
    img = np.pad(rgb, ((0, ph), (0, pw), (0, 0)), mode="reflect") if ph or pw else rgb
    Hp, Wp = img.shape[:2]
    acc = np.zeros((heads, Hp, Wp), np.float32); wsum = np.zeros((Hp, Wp), np.float32)
    r = 1 - np.abs(np.linspace(-1, 1, TILE)); w2 = np.outer(r, r).astype(np.float32) + 1e-3
    model.eval()
    with torch.no_grad():
        for y in _starts(Hp):
            for x in _starts(Wp):
                t = torch.from_numpy(np.ascontiguousarray(img[y:y + TILE, x:x + TILE])).permute(2, 0, 1)[None].contiguous().float().div_(255).sub_(0.5)
                o = torch.sigmoid(model(t.to(dev))[0]).float().cpu().numpy()
                acc[:, y:y + TILE, x:x + TILE] += o * w2; wsum[y:y + TILE, x:x + TILE] += w2
    out = acc / wsum
    return out[:, :H, :W]


def m1_regions(prob):
    n, cc, st, _ = cv2.connectedComponentsWithStats((prob < 0.3).astype(np.uint8), connectivity=8)
    keep = np.zeros(n, bool); keep[1:] = st[1:, cv2.CC_STAT_AREA] >= 50
    mk = (np.cumsum(keep) * keep)[cc].astype(np.int32)
    return watershed(prob.astype(np.float32), mk)


def regions_for(model_name, prob, dist_px):
    if model_name == "M1": return {"M1": m1_regions(prob)}
    return {"M2_oldseed": segment(dist_px, old_markers(dist_px)), "M2_hybrid": segment(dist_px, hybrid_markers(dist_px))}


def main(model_name, ckpt, image, out_dir, crop=None):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    dev = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    heads = 1 if model_name == "M1" else 2
    model = UNet(heads).to(dev); model.load_state_dict(torch.load(ckpt, map_location=dev, weights_only=True))
    rgb = cv2.cvtColor(cv2.imread(str(image)), cv2.COLOR_BGR2RGB)
    if crop:
        x, y, w, h = map(int, crop.split(",")); rgb = rgb[y:y + h, x:x + w]
    t0 = time.time(); o = predict(model, rgb, dev, heads); t_inf = time.time() - t0
    prob = o[0]; dist_px = o[1] * 32 if heads == 2 else None
    np.save(out / "prob.npy", prob.astype(np.float16))
    if dist_px is not None: np.save(out / "dist_px.npy", dist_px.astype(np.float16))
    t0 = time.time(); regs = regions_for(model_name, prob, dist_px); t_pp = time.time() - t0
    for k, r in regs.items(): np.save(out / f"regions_{k}.npy", r.astype(np.int32))
    meta = {"model": model_name, "ckpt": str(ckpt), "image": str(image), "crop": crop, "size": list(rgb.shape[:2]),
            "device": str(dev), "inference_s": round(t_inf, 1), "postprocess_s": round(t_pp, 1),
            "regions": {k: int(r.max()) for k, r in regs.items()}}
    json.dump(meta, open(out / "infer_meta.json", "w"), indent=1)
    print(json.dumps(meta), flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:5], *(sys.argv[5:6] or []))
