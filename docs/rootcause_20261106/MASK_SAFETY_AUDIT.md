# MASK_SAFETY_AUDIT — 任务二：OCR 掩膜 P0 安全补强

文件：`experiments/STITCHVECTOR/sv_u2_ocr_protected_build.py`（冻结模块未改）。

## 修正前缺陷（如实）

1. `ambiguous_quad` 在掩膜重绘与填色**之后**才计算 → 风险判定不构成保护。
2. 219 条原始 OCR 未去重 → 多尺度重复框互相触发 `overlaps_other_quad`（201/219），且重叠像素归属不清。
3. 墨迹阈值过松（L1>55 或 lum<80）→ `ink_saturated` 219/219 全部误伤。
4. 环带判定只看"类数>1"→ 几乎所有框判 ambiguous → 全量保守=零自动清理（上一轮实测 0 auto/219 review）。

## 修正后机制（先判定、后动像素）

顺序：`LF.labels` → `dedupe_quads`（IoU>0.5 合并多尺度重复，219→**131**）→ 逐框在未修改的 X 上计算：
- `spans_unit_boundary`：环带主类占比<60% 且次类≥10%；
- `overlaps_other_quad`：像素级 `own` 归属图，重叠 px 记 -2，**不属于任何框**，绝不互覆；
- `ink_saturated`：墨迹占框>75%（新阈值 L1>75 且 lum<中值亮度85%，或 lum<70）。

任一标记 → `preserve_review`：**原始像素与几何全部保留**，仅输出建议+影响范围进复核队列。仅 `auto_clean` 框（无标记）做墨迹像素重绘+并入 rem 重漫。

## 真实 U2 实测（本轮 run）

| 指标 | 值 |
|---|---|
| 原始/去重后 OCR 框 | 219 / 131 |
| auto_clean / preserve_review | **66 / 65** |
| 清理墨迹像素 | 8,333 px（仅为安全框内确证笔画） |
| faces 17,047→14,894；lines 606→523 | 保守幅度（基线 9,638 版曾过度清理至 −43%） |
| 被移除线逐条审计 `removed_lines_audit.csv` | 94 条触清理框：38 判 `glyph_stroke_removed`、**56 判 `possible_real_geology_REVIEW`**（长度>30px 或端点跨色类） |

判定"地质信息"不靠数量：每条消失线带长度/色类端点/清理框占比证据；56 条存疑线如实进复核而非宣称全是笔画。基线 `u2_full_B2c.gpkg` 与原图 sha256 未变（run JSON 记录 `input_sha256`）。
