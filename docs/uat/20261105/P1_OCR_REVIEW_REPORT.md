# P1 OCR 置信度审核报告 — STITCHVECTOR-V02 Phase 2

日期：2026-11-05 · 分支：`fix/stitchvector-v02-uat-remediation`（基于 P0 commit `c4425b9`）· 真实数据：U2 全图 219 条 OCR 草稿（`u2_ocr_full.json` → `add_text_drafts` 现行 schema，含 `candidate_texts`/`ocr_engine`）

## T06 置信度分级（PASS）

`classify_review(threshold)`（一次可撤销操作）：

- **REVIEW_REQUIRED**：`ocr_score < threshold`、无 `ocr_score`（`no_ocr_evidence`）、或命中硬性风险规则——无论分数多高。
- **AUTO_ACCEPTED_UNVERIFIED**：其余。永远不写成 `OCR_CONFIRMED`；`review_actor` 记录 `auto:classify@<th>`。
- 人工终态（`HUMAN_EDITED`/`OCR_CONFIRMED`/`TEXT_VECTOR_CREATED`/`TEXT_LAYER_COMPLETE`/`BACKGROUND_CLEAR_PENDING`）与 `source=manual` 不再重分类。

风险规则实现（hard，强制送审）：

| 规则 | 命中数（U2 219 条） | 说明 |
|---|---|---|
| `stratigraphic_or_lithology_code` | 86 | 地层/岩性代号首字符（Є/O/D/C/P/T/J/K/Q/N/E/Ar/Pt/希腊字母等） |
| `numeric_or_short` | 29 | 纯数字或≤2 位含数字 |
| `rotated_or_vertical` | 26 | \|angle\|>15° |
| `sub_or_superscript` | 25 | 上下标字符或字母数字混排 |
| `special_symbol` | 3 | CJK/拉丁/常用标点之外字符 |
| `text_differs_from_candidates` | — | 文本与候选集不一致 |
| `no_ocr_evidence` | 0（本数据全有分） | 无 OCR 分 |

**软规则**：`soft:crosses_boundary_line`（190 命中）——实测 U2 上 87% 注记压线，硬性处理会把队列放大到全图失去分流意义；保留为审核面板信息但不单独强制送审。已在 `P1_OCR_THRESHOLD_EVAL.csv` 记录，供阈值评审参考。

### 阈值评估（`P1_OCR_THRESHOLD_EVAL.csv`，真实 U2 实测）

| threshold | review_required | auto | 送审比例 |
|---|---|---|---|
| 0.80 | 151 | 68 | 69.0% |
| 0.85 | 156 | 63 | 71.2% |
| 0.90 | 160 | 59 | 73.1% |
| 0.95 | 171 | 48 | 78.1% |

风险规则贡献：86 条地层/岩性代号在任意阈值下强制送审（其中约半数同时低于阈值）。**0.90 是初始配置不是最优值**；错误捕获率与漏检率评估需要标注真值，当前 `NOT_EVALUATED`（无人工标注集），完全漏检文字无分数、本就不依赖阈值（T09 手工补字路径保留）。

## T07 地图审核模式（PASS，浏览器实测）

编辑器 UI 新增「OCR 审核」区：

- 「置信度+风险分流」按钮 → `review_classify` → 审核模式自动开启。
- 待审文字画布红虚框、已跳过橙框；「只看待审」过滤其余文字。
- 点击红框或分流完成自动打开审核面板：原图局部裁剪（像素放大）、文字/OCR 原文/置信度/命中原因/队列位置 `k/N`。
- 「确认正确」→ `OCR_CONFIRMED`；「修改并确认」→ 填入文字编辑区，`text_edit` 后 `HUMAN_EDITED` 自动出队；「暂时跳过」→ `REVIEW_SKIPPED`（仍标记、列队尾）。
- 每次决定后自动跳下一项；计数行显示 待审/跳过/自动放行（未核实）/已确认/人工改/总数。
- 地质面色不受审核模式影响（仅叠加文字框绘制）。

## T08 审核持久化（PASS）

`text_labels` 新增列：`review_reason`（JSON 原因列表）、`reviewed_at`（UTC ISO）、`review_actor`（`auto:classify@0.90` / `human`）。旧 GPKG 无列时按默认填充。`ocr_text`/`ocr_score` 原始模型数据不被覆盖（`text` 独立保存当前值）。GPKG 保存→重开，状态、原因、操作者一致（单测 `test_review_state_survives_save_reopen`）。

## T09 导出联动（PASS）

`save_as(path, draft=False)`：存在 `REVIEW_REQUIRED` 时正式保存被拒绝（`EditError`，含待审数量）；`draft=True` 明确草稿导出，结果与 `.edits.json` manifest 记录 `export_mode:draft` + `unreviewed` + 全量计数。浏览器实测：正式保存被拒信息→显式草稿导出成功。

## 测试证据

- 单测 `tests/stitchvector_editor/test_p1_review.py`：8 项 PASS（分流/伪装确认防护/队列排序/确认·改字·跳过出队/人工态保护/保存重开/草稿 manifest/撤销重做）。
- 全量 `tests/stitchvector_editor/` + `tests/stitchvector_studio/`：**59 项 PASS**（无删除/放宽断言）。
- 浏览器 `tests/stitchvector_editor/e2e_review.js`（真实 U2，219 草稿）：**19/19 PASS, fail=0**——分流 160 待审/59 放行、红框 160 个、面板原图裁剪+原因、确认/修改/跳过三路径、只看待审过滤、正式保存拒绝→草稿导出 manifest。截图：`/tmp/p1_eval/shots/20_review_mode_redboxes.png`、`21_review_panel.png`、`22_after_save.png`（本地会话证据；地图本体为受保护资产不入库）。

## 已知限制

- `#revCounters` 行在分流按钮处理中的读数偶发显示上一轮值（异步刷新时序），终态计数正确；影响仅限面板文案瞬间显示。
- 送审比例 73%@0.90 偏高，主因 U2 地层代号密度大（86/219）；若人工审核负担过重，可在技术评审后下调阈值或把部分代号规则降为软规则——当前保持保守（宁多审）。
- Studio 侧审核入口未做（编辑器已可打开 Studio 项目 GPKG 完成审核）；如需 Studio 内嵌入口另计工作量。

## 人工 UAT 检查点材料（按任务书要求提交）

1. 审核队列实测：219 条 → 待审 160 / 自动放行 59（未核实态）。
2. 浏览器截图 3 张（红框审核模式、审核面板+原图裁剪、草稿导出后状态）。
3. 阈值评估 CSV：`docs/uat/20261105/P1_OCR_THRESHOLD_EVAL.csv`。
4. 复现方式：`tools.stitchvector_editor.server --image u2_map.png --gpkg <drafts gpkg> --out-dir out --port 8792` → 「置信度+风险分流」→ 审核模式。

## 下一阶段建议

进入 P2（半自动修复 T10–T14）：碎面智能合并、文字残影清理、窄面恢复、辅助补线、处理范围保护，逐项记录 `time/clicks/objects_changed/manual_steps/undo_count` 并与旧流程对照。
