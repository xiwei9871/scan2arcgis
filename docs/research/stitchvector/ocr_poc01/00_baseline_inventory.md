# 00 基线清点（T0）

分支 `research/stitchvector-ocr-poc01`，起点 `research/stitchvector-u2-full-validation @ 988699ef482657655ccf0660ae8f679423f072c2`。本轮只读取现有代码和数据，没有改 B2c、M2、现有 OCR 或编辑器。

## 1. 相关代码

| 内容 | 位置 | 说明 |
|---|---|---|
| 全图 RapidOCR 调用 | `experiments/STITCHVECTOR/sv_u2_full_ocr.py` | `RapidOCR()` 默认配置，1× 和 2× 各跑一次，坐标除以倍数回到原图；输出 `u2_ocr_full.json` |
| 去重与审计 | `experiments/STITCHVECTOR/sv_u2_full_audit.py` `ocr_boxes()` | 两个尺度 IoU > 0.3 视为同一框，保留高分；轴对齐框，裁到地图内 → 127 个框 |
| B2c 全图构建 | `experiments/STITCHVECTOR/sv_u2_full_build.py` | 输出 `u2_full_B2c.gpkg`（`colour_faces` 17,047 / `visual_lines` 606） |
| 编辑器文字层 | `feature/stitchvector-editor-text-layer` 的 `tools/stitchvector_editor/core.py` | 图层 `text_labels`，字段 `label_id, text, ocr_text, ocr_score, font_px, angle_deg, anchor, rgb, box_x0..box_y1, source` |
| 编辑器顶栏计数 | 同分支 `static/app.js:20` | `文字 ${S.texts.length}`，即 `text_labels` 图层的行数 |

RapidOCR 环境：`.venv-ocr`，rapidocr 3.4.5、onnxruntime 1.23.2，默认模型 `ch_PP-OCRv4_det/rec_infer.onnx`（mobile）+ `ch_ppocr_mobile_v2.0_cls`。

## 2. 数据（本地，不在 git）

| 文件 | SHA-256 |
|---|---|
| `runs/stitchvector/u2_full/u2_map.png`（805×780，= `runs/real/u2/work.png` 地图框 [0,0,805,780]） | `05cdada47beed21363e7d1bf11bfa308ec3d02d6b270d06b4074906c6dcd64c7` |
| `runs/real/u2/work.png`（1722×780，右侧 805–1722 是图例） | `0deab1ffac1bada4748e98ee540b640929e580c70b26ae676d2e7ab8e6d2e0b1` |
| `runs/stitchvector/u2_full/u2_full_B2c.gpkg` | `988df621966d1b3ea25843c51a27ee0b3d691c6b3bb83f979ebff654fa9a6fd7`（本轮前后一致） |
| `runs/stitchvector/u2_full/u2_ocr_full.json` | 219 条（1× 107 + 2× 112），3.5 s |

已有真值：

- Oracle 线稿 `experiments/STITCHVECTOR/oracle/u2_300_oracle.json`：18 条线，窗口 x711–805、y240–540，占地图 4.5%，不描文字。
- 人工确认文字：3 个（Є-O、Ar₂E、云），都在 Oracle 窗口内。
- 地质单元真值：无。

## 3. 为什么全图显示"文字 0"

这是两个不同的数量：

| 数量 | 值 | 来源 |
|---|---|---|
| OCR 原始候选 | 219 | `u2_ocr_full.json`，两个尺度合计 |
| 去重后文字框 | 127 | 审计脚本内存中的框，没有写进 B2c GPKG |
| B2c GPKG 中的矢量文字对象 | **0** | `u2_full_B2c.gpkg` 只有 `colour_faces` 和 `visual_lines`，没有 `text_labels` 表 |
| 文字清除副本中的文字对象 | 126 | `u2_full_text_cleared.gpkg` 的 `text_labels`（`source=edited_text_box`）；比 127 少 1 个，原因本轮没查，NOT_VERIFIED |

编辑器打开 `u2_full_B2c.gpkg` 时读不到 `text_labels`，所以显示 `文字 0`。OCR 结果从来没有进入 B2c 文件；只有在副本上执行"框文字 → 清理"后才生成文字对象。

## 4. 本轮新增（没有改动已有文件）

- `experiments/STITCHVECTOR/ocr_poc01/`：适配器、评测、后处理、安全审计、可视化、测试、真值草稿、结果 CSV/JSON
- `docs/research/stitchvector/ocr_poc01/`：本目录 8 份文档
- 本地（git 忽略）：`runs/ocr_poc01/`（新 venv、模型缓存、原始输出、可视化页面）

新环境放在 `runs/ocr_poc01/venvs/{paddle,surya,eval}`，没有碰 `.venv-ocr`、`.venv-sv`。Surya 识别需要的 `llama-server` 用 Homebrew 装在系统里（llama.cpp 0.8.0，`/opt/homebrew/bin/llama-server`），这是本轮唯一的系统级改动。
