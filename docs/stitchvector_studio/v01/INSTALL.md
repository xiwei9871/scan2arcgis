# StitchVector Studio V0.1 — 环境安装 / Installation

> 适用版本：基于 `feature/stitchvector-studio-v01` 的安装配置分支。2026-11-02。  
> 已有实测环境：macOS Apple Silicon (M4), Python **3.11**。其他系统、Python 版本及从零安装仍需要独立验证。  
> 所有原始地质图和实验 GPKG **无需下载**；用户可以导入自己的 PNG/JPG/PDF/TIFF/GeoTIFF。

## 0. 文件说明

| 文件 | 对应虚拟环境 | 用途 |
| --- | --- | --- |
| [`requirements.txt`](../../../requirements.txt) | `.venv-sv` | Studio 服务、B2c、编辑器、GIS 导入导出 |
| [`requirements-ocr-paddle.txt`](../../../requirements-ocr-paddle.txt) | `runs/ocr_poc01/venvs/paddle` | PaddleOCR，默认 OCR |
| [`requirements-ocr-rapid.txt`](../../../requirements-ocr-rapid.txt) | `.venv-ocr` | RapidOCR，可选回退 |

以上版本来自 2026-11-02 的**已运行环境 pip freeze 快照**，不是跨平台通用锁文件。三个环境之间有不同版本的 NumPy / OpenCV 等依赖，**不得把三个文件依次 pip install 到同一个环境**。安装它们需要联网，模型权重不在 GitHub 中。

## 1. 下载仓库与准备 Python

macOS Apple Silicon 示例：

```bash
# 先确保已安装 Git、Python 3.11（macOS 可通过 Homebrew 安装）
brew install python@3.11

git clone https://github.com/xiwei9871/scan2arcgis.git
cd scan2arcgis
# 安装文件当前位于这个分支；合并后可改用正式包含它的分支
git switch chore/stitchvector-requirements-install-v1

python3.11 --version
```

如没有 `brew`，请自行安装 Python 3.11，然后确保 `python3.11` 可用。Linux 可以尝试相同安装流程，但包轮子和底层库的兼容性尚未验证；Windows 环境路径尚未适配。

## 2. Studio 主环境（必需）

```bash
python3.11 -m venv .venv-sv
.venv-sv/bin/python -m pip install -r requirements.txt
.venv-sv/bin/python -m pip check
```

默认包含 `rasterio`、`pyogrio`、`geopandas`、`shapely`、`pypdfium2`、`tifffile`、`vtracer` 等；主环境通过 Python 包实现 GIS/PDF/TIFF 处理。某些系统可能还需适配系统级动态库，但**不要无依据把某一平台安装命令写成全平台必须执行**。

## 3. PaddleOCR 默认环境（推荐）

```bash
mkdir -p runs/ocr_poc01/venvs runs/ocr_poc01/cache/paddle
python3.11 -m venv runs/ocr_poc01/venvs/paddle
runs/ocr_poc01/venvs/paddle/bin/python -m pip install -r requirements-ocr-paddle.txt
runs/ocr_poc01/venvs/paddle/bin/python -m pip check
```

首次预热模型（需要联网；模型不提交 Git）：

```bash
PADDLE_PDX_CACHE_HOME="$PWD/runs/ocr_poc01/cache/paddle" \
PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True \
runs/ocr_poc01/venvs/paddle/bin/python -c \
'from paddleocr import PaddleOCR; PaddleOCR(lang="ch", use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=True, device="cpu")'
```

预期缓存有 `PP-OCRv6_medium_det`、`PP-OCRv6_medium_rec` 和 `PP-LCNet_x1_0_textline_ori`。模型下载地址/源的可用性依赖安装时网络条件。插件默认从**当前仓库** `runs/ocr_poc01/cache/paddle` 寻找模型，可用环境变量 `PADDLE_PDX_CACHE_HOME` 指定其他缓存目录；改变它时运行 Studio 的进程也应设置相同变量。

## 4. RapidOCR 回退环境（可选，但建议安装）

```bash
python3.11 -m venv .venv-ocr
.venv-ocr/bin/python -m pip install -r requirements-ocr-rapid.txt
.venv-ocr/bin/python -m pip check
```

工作台插件注册器会从**仓库相对路径**查找上述两个 OCR 虚拟环境，而不再假定项目放在 `~/geomap2arcgis`。

## 5. 依赖与插件自检

```bash
.venv-sv/bin/python - <<'PY'
from tools.stitchvector_studio import registry
for e in registry.discover():
    m = e["manifest"]
    print(m.get("plugin_id"), "AVAILABLE" if e["available"] else "UNAVAILABLE", e.get("problem") or "")
for name, profile in registry.profiles().items():
    print("PROFILE", name, "RUNNABLE" if registry.profile_status(profile)["runnable"] else "DISABLED")
PY
```

预期默认 `legacy-b2c-v01` 可运行、PaddleOCR 可用；`geology-aware-vnext` 仍按设计为 `NOT_IMPLEMENTED`。若提示 `runtime python not found`，先确认三个 venv 已建在仓库根目录的正确位置；若提示模型缓存缺失，检查第 3 步。

可生成无需受保护地质图的文件格式测试样本：

```bash
.venv-sv/bin/python experiments/STITCHVECTOR/studio_v01/make_samples.py \
  runs/stitchvector/studio_v01/samples
```

## 6. 启动 Studio

```bash
.venv-sv/bin/python -m tools.stitchvector_studio.server \
  --workspace "$PWD/runs/stitchvector/studio_v01/workspace" \
  --port 8830
```

打开 [http://127.0.0.1:8830/](http://127.0.0.1:8830/)，选择 **新建项目 → 选择文件 → 导入文件 → legacy-b2c-v01 → 开始矢量化 → 编辑 → 保存 → 导出**。

- `legacy-b2c-v01`：B2c + PaddleOCR（默认）。
- `legacy-b2c-v01-rapidocr`：RapidOCR 回退。
- `mock-swap-test`：插件测试数据，**不是真实地质矢量结果**。
- `geology-aware-vnext`：占位流程，尚不可运行。

数据保存在当前机器 `--workspace` 指定的目录内；原始图像和 GPKG 没有放进 GitHub。用户用自己的地图即可使用已实现的导入、处理、编辑和导出功能。普通图片未进行地理配准时，导出会明确标注 `PIXEL_SPACE`，不会假造 CRS。

## 7. 常见问题

- **插件不可用**：请在仓库根目录运行命令，并检查 `/api/studio/plugins` 列出的 `problem`。
- **PaddleOCR 无法加载**：检查 `runs/ocr_poc01/cache/paddle` 及模型预热是否成功、CPU 依赖是否能安装。OCR 阶段失败时请查看项目运行目录中该阶段的 `stage.log`。
- **系统内存或磁盘不足**：模型和临时图像会占用本地资源，大图处理不保证与 U2 小图速度相同。
- **只能找到 GitHub 代码，没有 U2 原图**：这是正常的；U2、GSJ 原始扫描图不随代码提供。请上传你自己拥有使用权的图片。
- **PaddleOCR 模型首次安装失败**：可先完成主环境安装，再选择 mock 流程验证界面与插件装配；真实 OCR 需要继续解决模型下载与兼容问题。
- **为什么三个 requirements？** 各算法隔离运行，避免 NumPy / OpenCV / PaddlePaddle 依赖相互冲突。

## 8. 当前验证范围

依赖版本来自已有 Mac 工作环境；2026-11-02 已有同机隔离 Git 克隆运行 U2 全链路的记录（参见 `chore/stitchvector-archive-v1` 的 `docs/archive/v1/RECOVERY_TEST_REPORT.md`），但没有执行“全新机器无缓存、从零 pip install”验收。以上安装指南与路径修正需要由另一台电脑独立复核后才能声明完全跨机可复现。
