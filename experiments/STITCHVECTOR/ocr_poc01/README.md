# StitchVector OCR POC-01

Reports: `docs/research/stitchvector/ocr_poc01/00..07_*.md`. Truth is `AGENT_DRAFT` (not human verified).

Local, git-ignored: `~/geomap2arcgis/runs/ocr_poc01/` holds venvs (`venvs/{paddle,surya,eval}`), model caches, raw engine outputs (`raw/`), and the built viewer.

## Engine runs (writes raw/*.json)

```bash
R=~/geomap2arcgis/runs/ocr_poc01; IMG=~/geomap2arcgis/runs/stitchvector/u2_full/u2_map.png
# truth boxes for experiment B
~/geomap2arcgis/.venv-sv/bin/python -c "import json;t=json.load(open('truth/u2_text_truth.json'));json.dump({'boxes':[{'sample_id':o['sample_id'],'polygon':o['polygon']} for o in t['objects']]},open('$R/truth_boxes.json','w'))"
for k in 1 2; do
  ~/geomap2arcgis/.venv-ocr/bin/python adapters/rapidocr_adapter.py --image $IMG --out $R/raw/rapidocr_e2e_x$k.json --scale $k
  ~/geomap2arcgis/.venv-ocr/bin/python adapters/rapidocr_adapter.py --image $IMG --out $R/raw/rapidocr_fixed_x$k.json --scale $k --boxes $R/truth_boxes.json
  PADDLE_PDX_CACHE_HOME=$R/cache/paddle $R/venvs/paddle/bin/python adapters/paddleocr_adapter.py --image $IMG --out $R/raw/paddleocr_e2e_x$k.json --scale $k
  PADDLE_PDX_CACHE_HOME=$R/cache/paddle $R/venvs/paddle/bin/python adapters/paddleocr_adapter.py --image $IMG --out $R/raw/paddleocr_fixed_x$k.json --scale $k --boxes $R/truth_boxes.json
  HF_HOME=$R/cache/hf MODEL_CACHE_DIR=$R/cache/datalab SURYA_GGUF_MODEL_FILE=surya-2.5-Q8_0.gguf $R/venvs/surya/bin/python adapters/surya_adapter.py --image $IMG --out $R/raw/surya_e2e_x$k.json --scale $k
  HF_HOME=$R/cache/hf MODEL_CACHE_DIR=$R/cache/datalab SURYA_GGUF_MODEL_FILE=surya-2.5-Q8_0.gguf $R/venvs/surya/bin/python adapters/surya_adapter.py --image $IMG --out $R/raw/surya_fixed_x$k.json --scale $k --boxes $R/truth_boxes.json
done
```

Fusion needs `rapidocr_on_paddle_x2.json` / `surya_on_paddle_x2.json` (fixed-box runs on PaddleOCR's 1x+2x boxes) and legend runs `legend_{engine}_x2.json` on the legend crop `work.png[805:1722]`. Surya needs `llama-server` (Homebrew `llama.cpp`).

## Scoring

```bash
$R/venvs/eval/bin/python benchmark_runner.py   # results/detection_comparison.csv, recognition_comparison.csv, benchmark_summary.json
$R/venvs/eval/bin/python fusion_eval.py        # results/fusion_comparison.csv, geological_code_errors.csv, legend_dictionary.json
~/geomap2arcgis/.venv-sv/bin/python safety_audit.py   # results/safety_audit.csv, safety_summary.json (needs sv_oracle)
$R/venvs/eval/bin/python manifest.py           # results/engine_manifest.json, runtime_metrics.csv
$R/venvs/eval/bin/python viewer/build_viewer.py
$R/venvs/eval/bin/python -m pytest -q tests
```
