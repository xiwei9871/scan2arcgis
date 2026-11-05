# P1.1 审核门禁加固报告

日期：2026-11-05 · 分支：`fix/stitchvector-v02-uat-remediation`（基于 P1 commit `70bb064`）
范围：评审指令 `P1_CONDITIONAL_PASS / P2_APPROVED` 的全部八项小范围补丁；不改算法、不调阈值。

## 1. 统一审核 Gate

`tools/stitchvector_editor/core.py` 新增共享判定（模块级，Editor 与 Studio 共用）：

| 状态集合 | 成员 | 含义 |
|---|---|---|
| `REVIEW_DELIVERABLE`（可正式交付） | `OCR_CONFIRMED`, `HUMAN_EDITED`, `TEXT_LAYER_COMPLETE`, `AUTO_ACCEPTED_UNVERIFIED` | 真正人工确认 / 显式非人工终态 |
| 阻塞正式交付 | `REVIEW_REQUIRED`, `REVIEW_SKIPPED`, `OCR_DRAFT`, `OCR_CANDIDATE`, `TEXT_VECTOR_CREATED`, `BACKGROUND_CLEAR_PENDING`，空值→`OCR_CANDIDATE` | 未完成态或几何管线状态，**一律不算人工确认** |

- `save_as(draft=False)` 现在用 `review_pending()` 计数（非仅 `REVIEW_REQUIRED`）；拒绝信息列出阻塞类别。
- `review_counters()["pending"]` 与门禁同口径。
- `AUTO_ACCEPTED_UNVERIFIED` 按既有设计放行但保持"未核实"标签；`TEXT_VECTOR_CREATED` 需经 `review_decide` 显式确认后方可正式交付（`review_decide` 资格已放宽为"非人工终态即可判"，确认→`OCR_CONFIRMED`）。

## 2. Studio 与 Editor 导出共用判定

- `tools/stitchvector_studio/exports.py` 直接 `from tools.stitchvector_editor.core import REVIEW_DELIVERABLE, review_pending, review_status_counts`——同一函数、同一集合，无双份逻辑。
- `export()` 增加统一门禁：`text_labels` 存在非交付态 → `ExportError`（除非 `draft=True`）；草稿导出自动附带 `text_unconfirmed` 层并在 manifest 记 `export_mode/unreviewed/review` 全状态计数。
- Studio `CONFIRMED` 元组同步为 `REVIEW_DELIVERABLE`：`TEXT_VECTOR_CREATED` 由此归入 `text_unconfirmed` 层（按评审指令，管线创建状态不再视为已确认）。
- 服务端：`POST /api/studio/projects/<id>/exports` 新增 `draft` 参数透传。
- 工作草稿保存（editor `save_as(draft=True)`、Studio `save_version`）不受影响，保持可用。

## 3. 人工确认语义

- `edit_text`：仅当 `text` 内容**真的改变**才置 `HUMAN_EDITED` 并记录 `reviewed_at`/`review_actor="human:edit_text"`；字号/角度/颜色/位置修改或重复提交原文不再触碰审核状态。
- `text_apply`（框选更新已有文字）：同上语义，仅在文本变化时记 `human:text_box`。
- `add_text`（手工补字）：内容为人工录入，保持 `HUMAN_EDITED` 并补记 `reviewed_at`/`review_actor="manual"`。
- `review_decide`：确认/跳过均记 UTC 时间戳与 actor；已人工确认的对象不能再次 decide（防回退）。

## 4. 审核计数刷新时序

`app.js::refreshQueue()` 计数改取 `review_queue` 响应体自带的 `r.review`（服务端同一时刻计算的计数，与队列原子一致），不再读异步链路中可能滞后一轮的 `S.review` 缓存；`S.review` 仅作兜底。

## 5. 两套 OCR 基线分别评估（不混用）

`P1_1_OCR_THRESHOLD_EVAL.csv`（真实 U2，同一 `classify_review` 实现）：

| engine | items | 0.80 | 0.85 | **0.90** | 0.95 | @0.90 送审率 |
|---|---|---|---|---|---|---|
| rapidocr | 219 | 151 | 156 | **160** | 171 | 73.1% |
| paddleocr | 148 | 98 | 99 | **99** | 100 | 66.9% |

- RapidOCR 基线复算与 P1 已发布结果一致（160/59），样本与管线未变。
- PaddleOCR 基线：`studio_v01` 项目真实运行的 `ocr_candidates.json`（paddleocr 3.7.0，PP-OCRv6_medium det+rec+ori），148 条与任务要求一致；送审率较低主要因该引擎对长词给分更集中，非阈值不同。
- 两套独立统计，`engine` 列区分，不合并。

## 6. 地层代号规则复核

- 逐条审计 RapidOCR 86 条命中：**全部为代号形对象**（`C-P`/`N-Q` 区间代号、`Pt3`/`J3t` 地层代号、`CHTA`/`PuiL`/`AreJ` 等 OCR 乱码代号），**0 条普通英文误判**；`PuiL`/`AreJ` 类乱码代号正是该规则应捕获的对象。
- 加固：`_era_like()` 在正则命中之外要求"代号形"——长度 ≤4 或含数字/符号，普通英文单词（`North`、`Ordovician`、`Tertiary` 等）即使首字母命中也不再误报。86 条命中数不变（全部仍为代号形）。
- `crosses_boundary_line` 保持软规则（`soft:` 前缀记因、不强制送审）；阈值 0.90 未调。

## 7. 人工真值小样本（探索性）

`P1_1_TRUTH_SAMPLE.csv`：24 条，三类各 8 条，逐条附 crop 文件索引（crops 存 `/tmp/p1_eval/truth_sample/`，受保护图幅内容不入库）。初核由执行代理对原图裁剪比对完成，**结论为探索性**，待人工复核后方可作依据。

| 类别 | 正确 | 错误 | 存疑 | 发现 |
|---|---|---|---|---|
| auto_accepted_high_conf | 6 | **2** | 0 | `上榆庄`漏"上"字(0.90)；`轩岗镇`误为"轩肉镇"(0.942)——**高置信度漏错确实存在** |
| review_low_conf | 3 | 2 | 3 | `C-O`漏C；民居点符号被误检为文字`。`；低分 `长梁沟镇` 实际正确（误报） |
| review_era_code | 7 | 0 | 1 | 多为正确读数但被合理强制送审（代号宁可多审） |

探索性结论：**0.90 阈值下自动放行样本中观察到 ~25% 错误率（2/8）**，含地名错字——支持"自动放行必须保留 UNVERIFIED 标签并允许抽查"的既有设计，也提示后续 UAT 应在人工检查点重点抽查 auto-accepted 组。样本量不足以下准确率结论。

## 8. 测试与验证

- 新增 `tests/stitchvector_editor/test_p1_1_gate.py`：9 项，覆盖——全跳过后正式导出仍被拒/草稿可出、四类非交付态逐一阻塞、`TEXT_VECTOR_CREATED`/`BACKGROUND_CLEAR_PENDING` 非确认、字号角度修改与重复原文不确认、真改字记状态+时间+actor、管线态可显式确认后放行、已确认不可二次 decide、英文单词不命中代号规则、Studio 导出同门禁+草稿层。
- 既有测试 3 处按新门禁语义适配（拒绝信息文案、`TEXT_VECTOR_CREATED` 需先确认再正式存）。
- 全量：`pytest tests/stitchvector_editor tests/stitchvector_studio` → **74 passed, 0 failed**。
- 浏览器端复审 UI 未重跑（计数修复为纯取数口径变化，e2e_review.js 仍适用）；NOT_VERIFIED 项见下。

## 9. 诚实声明 / 未解决项

- 真值样本为**代理初核的探索性结果**，需人工复核裁片确认后才可引用为漏审率证据。
- `TEXT_LAYER_COMPLETE` 列入可交付集合（工作流显式"完成"标记）；若评审认为也应阻塞，改动为一行集合调整。
- `AUTO_ACCEPTED_UNVERIFIED` 可过正式门但携带"未核实"状态交付——与 P1 设计一致；样本显示该组确有漏错，建议 UAT 抽查比例由人工定。
- 浏览器复审界面的计数修复未做真机复测（`NOT_VERIFIED`）；P1 e2e 用例逻辑未变。

## 交付物

- `docs/uat/20261105/P1_1_GATE_HARDENING_REPORT.md`（本文）
- `docs/uat/20261105/P1_1_OCR_THRESHOLD_EVAL.csv`（双引擎分档统计）
- `docs/uat/20261105/P1_1_TRUTH_SAMPLE.csv`（24 条真值样本 + 初核）
- `tests/stitchvector_editor/test_p1_1_gate.py`（9 项边界测试）
- 修改：`tools/stitchvector_editor/{core.py,static/app.js}`、`tools/stitchvector_studio/{exports.py,server.py}`、`tests/stitchvector_editor/{test_p0_fixes.py,test_p1_review.py,test_text_layer.py}`
