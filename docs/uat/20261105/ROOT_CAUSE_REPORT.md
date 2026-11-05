# ROOT_CAUSE_REPORT — 初步根因分析 (2026-11-05)

分级：**CODE_CONFIRMED**（代码已定位缺陷行）/ **MECHANISM_UNDERSTOOD**（机制明确、需复现定位）/ **NEEDS_REPRO**。

## P0 — 软件正确性（全部 CODE_CONFIRMED)

### E22 文字移动/字号/角度后显示与点击范围不同步 — CODE_CONFIRMED

- `tools/stitchvector_editor/core.py:852-876` `edit_text()`：仅更新 `text/font_px/angle_deg/rgb` 与
  `geometry` Point;**从不更新 `box_x0..y1`**。
- `tools/stitchvector_editor/static/app.js:255-256` `pickText()`：点击命中判定 `x∈[box_x0,box_x1] ∧
  y∈[box_y0,box_y1]`——用的是 stale box。
- 渲染用 `t.x,t.y`(Point)+`angle_deg` 旋转（app.js:63)→ 显示在新位、点击在旧位，与报告完全吻合
  （芽 显示(165.45,430.53) vs 点击范围 x295-316/y248-269)。
- 修复方向：`text`/`font_px`/`angle_deg`/`position` 任一变化即由 anchor+字号+文本度量重算 box_*；
  重算逻辑单一来源（server 端），前端只消费。回归：移动/改字号/改角度→新位可点、旧位不可点，
  含 save/reopen/undo/redo。

### E04 框选确认产生重复文字 — CODE_CONFIRMED

- `core.py:843-847` `text_apply()`：无论框内是否已有 text_labels 对象，都 `next_t` 新建一行 →
  "怀道" 同位 12px+18.4px 两份、对象数 152→153。
- 修复方向：`text_preview` 返回 `existing_text_ids`（与框相交的已有文字）;`text_apply` 在存在既有对象
  时默认进入"编辑现有"路径而非新建；明确区分 add vs edit。**不做距离去重**（不同文字可相邻）。
- 回归：同一框反复确认→对象数不变；框内已有人工文字→进入编辑。

### E31 面合并丢失来源属性 — CODE_CONFIRMED

- `core.py:254-265` `merge_faces()`、`618-630` `merge_components()`、`700-706` `heal_apply()`:
  只保留最大面属性，`source=edited_merge|edited_heal`，其余来源面 ID/rgb/label/面积全部丢弃。
- 报告实例：#6136 #fffffd label=0 + #2034 #dd5843 label=9 → 仅剩 #6136 属性。
- 修复方向：保留面新增 `merged_from` JSON 列（{eid,label_id,rgb,label,area,op} 列表）+ 合并历史可查；
  跨 label（不同地质类别）合并需显式警告确认；undo/save/export 后来源关系正确。
- GPKG 回读：属性列随层导出（新增列不破坏既有 schema,pyogrio 写入）。

### E09 OCR 字号/角度异常（超大文字遮挡地图）— CODE_CONFIRMED

- `tools/stitchvector_studio/projects.py:289-291` `add_text_drafts()`:
  `font_px = 0.8*(box_y1-box_y0)`——用的是旋转四边形的**轴对齐包围盒高**。旋转/竖排文字 AABB 高≈
  文字总长度 → font_px 严重偏大（报告显示的超大文字）。
- `angle_deg = -atan2(q1-q0)` 取 quad 首边方向；若 quad 首边为短边，角度差 90°。
- `core.py:816` `text_apply` 默认 `0.8*(y1-y0)` 同源缺陷（用户自画框场景）。
- 修复方向：字高 = quad 短边长（min(|q1-q0|,|q2-q1|))×系数；角度 = 长边方向；font_px 与 box 尺寸
  交叉钳制（不得超出 quad 合理范围）；不依赖单张图缩放系数。PaddleOCR rec_polys 点序已在插件
  记录（plugin.py:36-39)。

### E12 局部 OCR 空候选 / engine=none — CODE_CONFIRMED

- `core.py:718` `OCR_PY = Path.home()/"geomap2arcgis/.venv-ocr/bin/python"` —— **编辑器独立硬编码**
  （与 Studio 插件 manifest 是两套路径；任务书特别提示需一并核对）。
- `core.py:745-756` `ocr_box()`:`self.img is None or not OCR_PY.exists()` → `engine:"none"`；
  子进程任何异常 → `engine:"failed: {Type}"` 无 stderr/退出码；不先查框内已有文字对象。
- 修复方向：先复用框内已存在的独立文字对象（多数场景不必重 OCR)；运行时不可用时返回
  明确 `engine_unavailable` 原因；无检出/低置信度分别标识；手工输入始终可用。

## E 类其余（P1/P2 处理）

### E01 邻近符号并入文字 / E02 漏检与非文字误检 — MECHANISM_UNDERSTOOD

- PaddleOCR det/rec 对界线穿过文字、小字、旋转/竖排字存在漏检；邻近符号被纳入检测框。
- 走 P1 置信度+风险规则分流（低分与特殊符号强制送审）+ E02 漏检靠局部补识别与人工添加兜底
  （漏检无分数，不能用阈值兜底）。

### E10 文字残影未完全消除 — MECHANISM_UNDERSTOOD

- `text_apply` 清理范围仅：≤60px² 且 ≥50% 在框内的残面 + ≥90% 长度在框内的线。
  跨框笔画、大面积残面、底图原字形像素均不动 → 取消勾选/删字后残影仍在。
- 走 T11 半自动清理（候选→预览→确认，残影线可隔离可恢复）。

## A 类（P2 半自动修复 + P3 评估）— MECHANISM_UNDERSTOOD

- **A01/A02**：文字笔画进入面/线层（无文字预掩膜）→ T10/T11。
- **A05/A06/A08/A09/A33**：面分割错误（过分割/误合并/窄面吞并）→ T10 智能合并、T12 切割/窄面描绘。
  现有 `merge_preview`（含色彩冲突检测）与 `heal_preview/apply`(line_role 感知）可作为候选基础。
- **A10**：颜色连通把图外背景与图内白面连成一体 + 无 ROI 约束 → T14。
- **A15/A20/A24**：线漏检/断线/虚线误连/logical_id 错组 → T13 补线/编组/拆组；
  `experiments/STITCHVECTOR/sv_line_repair_uat.py` 与 line-repair 分支有既有 UAT 框架可复用。

所有 A 类修复均走"候选→预览→确认"路径并保留 undo/provenance，不做无人值守自动批改。
