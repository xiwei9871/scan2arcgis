# STUDIO_SCHEMA_COMPATIBILITY_REPORT — 任务三：数据契约核查与端到端验证

## text_labels 契约（修复后）

| 要求 | 实现 |
|---|---|
| Point 几何 | ✅ 131 条全部 `Point`（原误写 Polygon 四边形，已改） |
| OCR 四边形独立保存 | ✅ `ocr_quads` 层（Polygon + cand_id/quad_json/score/decision/flags/engine） |
| 必要字段 | ✅ 全部 TEXT_COLS：label_id/text/ocr_text/ocr_score/font_px/angle_deg/anchor/rgb/box_x0..y1/source/review_status/review_reason/reviewed_at/review_actor |
| 原文/置信度/候选ID/模型/风险 | ✅ ocr-0..130、score、source=`paddleocr_raw`、review_reason=跨界/重叠/饱和标记 |
| 高风险不冒充已确认 | ✅ 全部 `review_status=OCR_CANDIDATE`（131/131），无一预设确认；ambiguous 标记进 review_reason |

`Document(PROT)` 直接打开：14,894 faces / 523 lines / 131 texts，review 计数 `OCR_CANDIDATE:131`。

## 219 vs 148 差异溯源

- `u2_ocr_full.json`（219 条）：**原始 PaddleOCR 全图 run**（seconds=3.5），无去重、无规则层、坐标原图系。
- Studio 基线 148 条：`ocr_candidates.v1`，`paddleocr 3.7.0 PP-OCRv6_medium_det+rec+PP-LCNet_x1_0_textline_ori`，含多尺度 dedup、4px 输入偏移、通用规则建议层。
- 差异本质：同引擎不同参数与后处理——219 含多尺度重复与低分候选；本实验新增 `dedupe_quads`（IoU>0.5）后 219→131，与 148 量级一致。run JSON 已记录该溯源说明。

## Studio 真实端到端（本轮实测，服务 :8830）

| 步骤 | 结果 |
|---|---|
| 创建项目 → upload u2_map.png → normalise → 放置 protected gpkg → `/open` | ✅ opened |
| `/api/review_queue` | ✅ 131 pending（OCR_CANDIDATE） |
| `/api/review_decide confirm id=0` | ✅ confirmed:1 |
| `/api/text_edit id=1` → `/api/undo` | ✅ 编辑生效并可撤销（"undone: edit text"） |
| `/save`（版本保存） | ✅ v001，`readback_matches_memory:true`，`input_sha256_unchanged:true` |
| 重开 v001 | ✅ confirmed:1 持久化 |
| `/exports` GPKG draft | ✅ geological_faces 14,894 / geological_lines 523 / **text_confirmed 1 + text_unconfirmed 130** 分流正确 |
| 正式导出门禁 | 草稿导出保留未审文字；未确认项不冒充已确认 |

## 结论

**STUDIO_INTEGRATION_VERIFIED**（API 级全链）。注意：Studio 项目入口仍是「上传原图→管线」流程，外部预建 GPKG 需按本轮方式放入 working 目录——这是平台既有契约，非缺陷；若需正式「导入外部成果」入口属后续产品需求。
