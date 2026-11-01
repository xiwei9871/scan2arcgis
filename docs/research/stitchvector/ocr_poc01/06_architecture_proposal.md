# 06 集成技术设计（T6）

本轮不改生产代码。下面是建议的接口；适配器原型在 `experiments/STITCHVECTOR/ocr_poc01/adapters/`（RapidOCR / PaddleOCR / Surya 已按同一 CLI 和输出格式实现）。

## 1. 结构

```text
StitchVector OCR Interface        ocr.run(image, mode=e2e|fixed_box, scale) -> [OcrObject]
  +-- RapidOCR Adapter            .venv-ocr，保留为快速基线
  +-- PaddleOCR Adapter           主引擎（检测 + 中文识别）
  +-- Surya Adapter               可选复读器（仅研究/个人用途，见许可证）
  +-- Geological Text Postprocessor   GENERIC 规则 + 地图图例词典 -> candidate_texts（不改 raw_text）
  +-- Human Review Gate           编辑器中确认文字、处理 PENDING_HUMAN 框
  +-- Text Layer Export           写 GPKG text_labels + 状态字段
```

每个引擎在独立进程/虚拟环境中运行，通过 JSON 交换结果（与本轮适配器相同），主程序不依赖 paddle 或 torch。

## 2. 统一对象字段

| 字段 | 说明 |
|---|---|
| `object_id` | 稳定 ID |
| `polygon` | 原图像素坐标多边形 |
| `raw_text` | 引擎原始输出，永不改写 |
| `normalized_text` | NFC 规范化，不做纠正 |
| `candidate_texts` | `[{text, reason, source}]`，来自后处理和其他引擎 |
| `engine`, `model_version` | 如 `paddleocr-3.7.0/PP-OCRv6_medium` |
| `confidence` | 引擎原始置信度，只在引擎内比较 |
| `text_category` | 地名 / 地层代号 / 产状 / 标签 / 其他 |
| `review_status` | 见下 |
| `source_image_id`, `source_run_id` | 追溯 |

## 3. 状态

| 状态 | 进入条件 | 允许的几何操作 |
|---|---|---|
| `OCR_CANDIDATE` | 模型输出 | 无 |
| `OCR_CONFIRMED` | 人工确认内容（或选定候选） | 无 |
| `TEXT_VECTOR_CREATED` | 写入 `text_labels` | 无（原图残影仍在） |
| `BACKGROUND_CLEAR_PENDING` | 框内有线/碎面待处理；穿框线、跨多底面一律在此 | 只在副本上预览 |
| `TEXT_LAYER_COMPLETE` | 残影处理经人工确认、严格拓扑检查通过 | 写回 |

OCR 找到文字不等于文字图层完成，三个阶段之间都要人工或检查关口。

## 4. 与现有 GPKG / 编辑器对接

编辑器已有 `text_labels`（`label_id, text, ocr_text, ocr_score, font_px, angle_deg, anchor, rgb, box_x0..box_y1, source`）。建议增加字段而不是新建图层：`engine, model_version, candidate_texts(JSON), text_category, review_status, source_run_id, polygon_wkt`。`text` 存确认后的内容，`ocr_text` 存 `raw_text`。

编辑器改动建议（下一阶段）：

1. 导入 OCR JSON 时只生成 `OCR_CANDIDATE`，不自动清除；这样全图打开就能看到"文字 N（候选）"而不是 0。
2. 选中文字时显示 `candidate_texts` 下拉。
3. "框文字 → 清理"只对 `OCR_CONFIRMED` 生效；穿框线不切。
4. 全图交互时避免每个框都做全层严格覆盖检查（U2 全图验证中已发现 8–9 s/次）。
5. 大幅面图需要切块 + 重叠 + 拼接去重（参考 mapKurator `m0`/`m3`）。
