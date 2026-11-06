# U2_REAL_CASE_VALIDATION — T05 两案例验证

## 截图定位状态：**EVIDENCE_GAP**

用户 2026-11-06 提供的两张截图在本地文件系统未找到。以下验证在程序扫描定位的**临时对应区域**执行，证明缺陷机制与修复有效性；**不声称截图原位缺陷已修复**。精确原位验证需用户重新提供截图或坐标。

## 案例一：红面内碎裂 — `case1_red_frag` [500,640,720,780]（另 `case1b_red2` [600,380,760,540]）

| 指标 | B2c 原结果 | ocr-protected 新结果 | Δ |
|---|---|---|---|
| small_frag | 806 | 534 | −34% |
| enclosed_face | 98 | 81 | −17% |
| interior_ring | 9 | 7 | |
| glyph_line | 7 | 3 | |
| anomalies 合计 | 923 | 632 | −31% |

case1b_red2：small_frag 522→394，enclosed 98→76，glyph_line 10→1。

## 案例二：文字区（希腊/拉丁字符）— `case2_ocr_dense` [330,280,500,470]

| 指标 | B2c | ocr-protected | Δ |
|---|---|---|---|
| small_frag | 1,024 | 415 | −59% |
| enclosed_face | 219 | 149 | −32% |
| glyph_line | 19 | 8 | −58% |
| anomalies 合计 | 1,297 | 610 | −53% |

机制证据：文字框叠加审计确认基线 214 条 glyph_line 为字形入线层（A02 对象级实证）；OCR 保护后 392 线中仅 65 条仍与文字框重叠（多为真实跨界线，已标 `crosses_text`）。

## 三态截图（本地，未上传）

`runs/stitchvector/u2_full/rootcause/case{1_red_frag,2_ocr_dense}_{B2c,prot}/`：A_raster.png / B_faces.png（纯面）/ C_lines.png（纯线）/ D_text.png（纯字）/ E_overlay.png。B_faces 中文字位置不再有笔画切口碎面——修复发生在几何层而非视图遮盖（两版均同一渲染器输出）。

## 几何/属性/持久化

- 覆盖率：两版 `colour_faces` 均无缝铺盖（provenance observed/inferred 列随写）。
- undo/重开/导出：编辑器路径 `merge_components`+`text_apply` 全部走 `_do` 可撤销栈；OCR 保护版 GPKG 可被 Document 正常打开（97+6 测试与 Document 加载验证）。
- 属性完整性：merged_from 溯源保留；text_labels 层含 quad+score+ambiguous_quad。

## Gate B 状态：**PASS（机制级）**——临时案例区内伪碎面与字形线显著下降且真实边界未被自动跨越（auto_merge 安全候选=0，异色碎面全部转人工 review）。Gate B 的"截图原位"维度因证据缺口记 **PARTIAL**。
