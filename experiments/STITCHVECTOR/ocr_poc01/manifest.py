"""Write results/engine_manifest.json and results/runtime_metrics.csv from local installs and raw run JSONs.
Weight files are hashed in place (runs/ocr_poc01/cache, .venv-ocr); nothing is copied into git."""
import csv, hashlib, json, subprocess
from pathlib import Path
HOME = Path.home() / "geomap2arcgis"; R = HOME / "runs/ocr_poc01"; RES = Path(__file__).parent / "results"


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()


def files(root, pats):
    return [{"path": str(p.relative_to(HOME)), "bytes": p.stat().st_size, "sha256": sha(p)} for pat in pats for p in sorted(Path(root).glob(pat)) if p.is_file()]


def pipver(py, pkgs):
    out = subprocess.run([str(py), "-m", "pip", "list", "--format", "json"], capture_output=True, text=True).stdout
    v = {d["name"].lower(): d["version"] for d in json.loads(out)}; return {k: v.get(k) for k in pkgs}


def main():
    hf = R / "cache/hf/hub"
    m = {
        "host": {"cpu": "Apple M4", "ram_gb": 16, "os": "macOS (Darwin 25.6.0)", "python": "3.11.15"},
        "engines": {
            "rapidocr": {"venv": ".venv-ocr (existing, untouched)", "packages": pipver(HOME / ".venv-ocr/bin/python", ["rapidocr", "onnxruntime"]),
                         "framework": "onnxruntime CPU", "models": ["ch_PP-OCRv4_det_infer (mobile)", "ch_PP-OCRv4_rec_infer (mobile)", "ch_ppocr_mobile_v2.0_cls_infer"],
                         "weights": files(HOME / ".venv-ocr/lib/python3.11/site-packages/rapidocr/models", ["*.onnx", "*.txt"]),
                         "license_code": "Apache-2.0", "license_weights": "Apache-2.0 (PaddleOCR PP-OCRv4 weights converted to ONNX)"},
            "paddleocr": {"venv": "runs/ocr_poc01/venvs/paddle (new)", "packages": pipver(R / "venvs/paddle/bin/python", ["paddleocr", "paddlex", "paddlepaddle"]),
                          "framework": "PaddlePaddle CPU (paddle inference)", "models": ["PP-OCRv6_medium_det", "PP-OCRv6_medium_rec", "PP-LCNet_x1_0_textline_ori"],
                          "model_note": "library default for lang=ch in paddleocr 3.7.0; PP-OCRv6 tiny/small and PP-OCRv5 server/mobile also listed but NOT_TESTED in this round",
                          "weights": files(R / "cache/paddle/official_models", ["*/inference.pdiparams", "*/inference.json"]),
                          "license_code": "Apache-2.0", "license_weights": "Apache-2.0 (model card README 'license: apache-2.0')"},
            "surya": {"venv": "runs/ocr_poc01/venvs/surya (new)", "packages": pipver(R / "venvs/surya/bin/python", ["surya-ocr", "torch", "transformers"]),
                      "framework": "torch CPU/MPS for detection; llama.cpp llama-server 0.8.0 (Homebrew, Metal) for recognition",
                      "models": ["text_detection 2025_05_07 (datalab s3)", "datalab-to/surya-ocr-2.5-gguf surya-2.5-Q8_0.gguf + surya-2.5-mmproj.gguf"],
                      "model_note": "Q8_0 quantised GGUF chosen over the 1.18 GB full GGUF for disk space; full-precision NOT_TESTED",
                      "weights": files(R / "cache/datalab", ["**/*.safetensors"]) + [{"path": str(p.relative_to(HOME)), "target": p.resolve().name, "bytes": p.resolve().stat().st_size, "sha256": sha(p.resolve())}
                                  for p in sorted(hf.glob("models--datalab-to--surya-ocr-2.5-gguf/snapshots/*/*.gguf"))],
                      "license_code": "Apache-2.0 (github datalab-to/surya)",
                      "license_weights": "AI Pubs Open RAIL-M (modified): free for research/personal use; commercial use barred if the user's organisation had > USD 5M revenue in the prior year, has raised > USD 5M, or competes with Datalab; share-alike clause covers Output; commercial licence from datalab.to"},
            "mapkurator": {"status": "NOT_TESTED", "reason": "research only per brief; LICENSE file not found at repo root (raw URL 404 on main and master; GitHub API rate-limited) -> license NOT_VERIFIED"},
        },
    }
    json.dump(m, open(RES / "engine_manifest.json", "w"), ensure_ascii=False, indent=1)
    rows = []
    for p in sorted((R / "raw").glob("*.json")):
        d = json.load(open(p)); rows.append({"run": p.stem, "engine": d["engine"], "mode": d["mode"], "image_id": d["image_id"], "scale": d["scale"],
                                             "n_out": len(d["detections"]), "seconds_incl_model_load": d["seconds"],
                                             "peak_rss_mb_python": d["peak_rss_mb_self"], "peak_rss_mb_children": d["peak_rss_mb_children"]})
    w = csv.DictWriter(open(RES / "runtime_metrics.csv", "w", newline=""), fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    for r in rows: print(r)


if __name__ == "__main__":
    main()
