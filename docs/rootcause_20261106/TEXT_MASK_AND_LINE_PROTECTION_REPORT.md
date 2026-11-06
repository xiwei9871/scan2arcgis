# TEXT_MASK_AND_LINE_PROTECTION_REPORT — T03/T04

实验管线：`ocr-protected-b2c-v01` = `experiments/STITCHVECTOR/sv_u2_ocr_protected_build.py`（冻结模块 sv_b2c/sv_v3/sv_lf/sv_d71/sv_oracle/sv_oracle_v2 **未改一行**，全部为适配层新增代码）。冻结基线 `u2_full_B2c.gpkg` 保持原样。

## 处理顺序与机制

1. **OCR**：复用真实 PaddleOCR 输出 `u2_ocr_full.json`（219 项，quad+score，例：`"C-P" score 0.967`）。
2. **字形掩膜**：每个 quad 内，仅取与本框背景中值色差>55 或亮度<80 的**实际笔画像素**——共 77,098 px（占全图 12.3%），绝不整框删除，笔画间隙底色保留。
3. **底面重建**：glyph px 并入 `rem` 交给 `sv_d71.fill` 由边界向内重漫；每 quad 周边环带若含 >1 个色彩类 → 标 `ambiguous_quad` 进人工复核（186/219，本图文字多在界线处，如实偏保守），**不做跨单元盲目填充**。
4. **线隔离**：B2c 在"仅笔画像素被本框背景中值重绘"的 `img_prot` 上运行 → 字形对线提取不可见（A02 预防而非后删）。仍穿过文字区的线（`auto_B2c_crosses_text`，104 条）保留并标记复核。
5. **输出层**：`colour_faces`(9,638) / `visual_lines`(392) / `text_labels`(219, OCR_DRAFT+ambiguous_quad 标志)。原图未动。

## 实测指标（真实 U2 全图）

| 项 | B2c 基线 | ocr-protected | Δ |
|---|---|---|---|
| faces | 17,047 | 9,638 | −43.5%（文字诱导碎面被底面重建吸收） |
| lines | 606 | 392 | −214 |
| glyph_line（>60% 框内） | 214 | 65 | −70%（残留 65 条为跨框长线，复核队列） |
| small_frag / enclosed / ring | 14,568 / 2,313 / 172 | 7,866 / 1,623 / 103 | −46% / −30% / −40% |
| 运行时间 | ~同量级 | 12.3s（含 3.9s 线提取） | — |

## T04 后处理规则修复（core.py，向后兼容，97+6 测试过）

- `text_preview` 新增 `max_area_review=240`：(60,240]px² 残面纳入候选但强制 `uncertain`（size risk），绝不自动合并。
- `line_candidate_share=0.4`：跨出 OCR 框、share≥0.4 且短于框对角线的线纳入候选，标 `partially_outside`，默认不勾选。
- `ink_lum` 证据：UNKNOWN/SPLIT 角色线若笔画亮度<100 追加 `probable_glyph_ink` 提示（仍保守不默认勾选）。
- `text_residue(boxes=…)`：OCR 漏检区可由用户框选直接产生预览（`missed_text_region`），无需先有文字对象。
- 风险保护未放松：boundary_risk / may_continue_outside 依旧使 suggested=False。

## 已知限制（如实）

- 186 个 ambiguous_quad 跨界线文字下的底面分类需人工确认；未做自动跨界线恢复（spec 禁止盲目填）。
- 保护版 glyph_line 残留 65 条：多为长真线局部穿字，已标记非删除。
- 面数大降同时需警惕真实小透镜体被一并吸收——T02 keep 规则（地质代号/线证据/细长形状）+ review 队列兜底，最终取舍须 UAT 确认。
