# RECOVERY_GUIDE — 新机器恢复 StitchVector (archive V1, 2026-11-02)

场景：当前 Mac 完全损坏。目标：在新 Mac(arm64，示例路径 `~/geomap2arcgis`）恢复可运行的
Studio V0.1 并能重跑 U2。**未做的部分见文末"不能宣称"清单**——受保护数据当前无远端备份。

## 0. 前置

```bash
# 需要: git(SSH 已配 github.com:xiwei9871 密钥)、Python 3.11(brew install python@3.11)、node(可选,仅浏览器 E2E)
git clone git@github.com:xiwei9871/scan2arcgis.git ~/geomap2arcgis
cd ~/geomap2arcgis
git checkout feature/stitchvector-studio-v01   # 当前开发 tip, 含全部 Studio 代码
```

## 1. Studio 主环境（服务 + B2c + 编辑器）

```bash
/opt/homebrew/bin/python3.11 -m venv .venv-sv
.venv-sv/bin/pip install -U pip
.venv-sv/bin/pip install -r docs/archive/v1/env/requirements-.venv-sv.txt
# 关键包: numpy pillow shapely geopandas pyogrio rasterio pypdfium2 tifffile opencv-python-headless pytest
```

## 2. OCR 环境

```bash
# RapidOCR (回退)
/opt/homebrew/bin/python3.11 -m venv .venv-ocr
.venv-ocr/bin/pip install -r docs/archive/v1/env/requirements-.venv-ocr.txt   # rapidocr_onnxruntime 等

# PaddleOCR (默认) — 独立 venv, 插件 manifest 按相对 home 路径解析
/opt/homebrew/bin/python3.11 -m venv runs/ocr_poc01/venvs/paddle
runs/ocr_poc01/venvs/paddle/bin/pip install -r docs/archive/v1/env/requirements-runs_ocr_poc01_venvs_paddle.txt
# paddlepaddle 3.3.1 / paddleocr 3.7.0 / paddlex 3.7.2 (版本见 manifest packages_verified)
```

## 3. 模型缓存（可重新下载，~139M)

```bash
# PaddleOCR 模型由首次调用自动下载到 PADDLE_PDX_CACHE_HOME; 预热:
mkdir -p runs/ocr_poc01/cache/paddle
PADDLE_PDX_CACHE_HOME=$PWD/runs/ocr_poc01/cache/paddle PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True \
  runs/ocr_poc01/venvs/paddle/bin/python -c \
  "from paddleocr import PaddleOCR; PaddleOCR(lang='ch', use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=True, device='cpu')"
# 应生成 official_models/{PP-OCRv6_medium_det,PP-OCRv6_medium_rec,PP-LCNet_x1_0_textline_ori}
```

## 4. 受保护测试数据（B 类，当前 REMOTE_BACKUP_PENDING)

```bash
# 需要用户提供备份包(见 DATA_BACKUP_MANIFEST.json 的 bundle 划分); 校验:
#   shasum -a 256 <file> 对照 manifest items[].sha256
# 关键文件放置:
#   runs/stitchvector/u2_full/u2_map.png               (U2 原图, sha256 见 manifest)
#   runs/stitchvector/u2_full/u2_full_B2c.gpkg         (可选, 流水线可重算)
#   runs/stitchvector/studio_v01/samples/*             (可由 make_samples.py 重新生成)
# 重新生成格式测试样本:
.venv-sv/bin/python experiments/STITCHVECTOR/studio_v01/make_samples.py runs/stitchvector/studio_v01/samples
```

## 5. 启动 Studio

```bash
.venv-sv/bin/python -m tools.stitchvector_studio.server \
  --workspace ~/geomap2arcgis/runs/stitchvector/studio_v01/e2e_ws_devin --port 8830
# 打开 http://127.0.0.1:8830/ ; /api/studio/plugins 应显示 5 插件 available
```

## 6. 重跑 U2（浏览器 E2E)

```bash
# 占位符替换后由 playwright-cli 执行:
sed -e 's|__PORT__|8830|g' -e 's|__U2__|'"$HOME"'/geomap2arcgis/runs/stitchvector/u2_full/u2_map.png|g' \
    -e 's|__DL__|/tmp/svs_dl|g' tests/stitchvector_studio/e2e_studio_u2.js > /tmp/e2e.run.js
mkdir -p /tmp/svs_dl
playwright-cli -s=svstudio open http://127.0.0.1:8830/
playwright-cli -s=svstudio run-code --filename=/tmp/e2e.run.js
# 期望: {"fail":0,...} (30/30); 结果文件规范见 experiments/STITCHVECTOR/studio_v01/e2e_u2_browser_result.json
```

## 7. 无浏览器的最小验证（API 级)

```bash
PID=$(curl -s -X POST localhost:8830/api/studio/projects -d '{"name":"recovery"}' | python3 -c "import json,sys;print(json.load(sys.stdin)['project_id'])")
curl -s -X POST "localhost:8830/api/studio/projects/$PID/upload?filename=u2_map.png" \
  --data-binary @runs/stitchvector/u2_full/u2_map.png
curl -s -X POST "localhost:8830/api/studio/projects/$PID/normalise" -d '{"page":0}'
curl -s -X POST "localhost:8830/api/studio/projects/$PID/process" -d '{"profile_id":"legacy-b2c-v01"}'
# 轮询 GET .../jobs/<run_id> 至 COMPLETED; 然后 POST /adopt, /open, /save, /exports(GPKG/SHP/GEOJSON)
```

## 8. 不能宣称 / 依赖本地数据的部分

- **受保护数据**(u2_map.png、oracle 真值 GPKG、GSJ/U3 原图）当前**无远端备份** → 若未先拿到
  `DATA_BACKUP_MANIFEST.json` 所列备份，U2/GSJ/U3 相关验证无法在新机完成。
- **venv 与模型缓存不在 git**:requirements 已归档，pip 下载依赖网络；模型 139M 自动重下。
- **runs/ 下 ~20G 实验输出**不在 git 也无远端备份：多数可由已归档脚本重算（代价高）;
  一次性成果见 manifest。
- **audit/dev 旧产品线**不在 GitHub(含 legacy 历史，钩子设计）——恢复范围仅限公开线。
- 新机器**未实测**：本指南在本地隔离克隆上验证到"代码完整 + mock 管线 + B2c 插件可运行",
  见 `RECOVERY_TEST_REPORT.md`。
