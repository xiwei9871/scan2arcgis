# P2 半自动修复 — 阶段进展（T10 核心 + UI 通路）

分支：`fix/stitchvector-v02-uat-remediation` · 基线：`70bb064`（P1）

## 已实现（本增量）

- `Document.merge_suggest(ids, de, roi)`：从种子面向外生长同色(dE)边相邻候选；每个候选附风险标记——
  `crosses_split_line`（跨 SPLIT/UNKNOWN 线=可能真实分界）、`narrow_band`（短边<2px 碎条）、
  `mixed_label`（不同地质代号）、`not_connected_to_seed`（在建议集内与种子不边连通，合并会成 multipart）。
  带前两类风险的候选不进默认建议集；建议集进一步收敛为种子连通分量——`merge()` 的多部分保护在建议阶段就预先对齐。
- `group_faces` / `ungroup_faces`：`LOGICAL_GROUP`——写 `face_group` 列、不动几何、可撤销、随 GPKG 持久化（`face_group` 在 `attrs` 回读）。
- `set_roi`/`roi`：用户处理范围约束，`merge_suggest` 候选裁剪到 ROI 内（centre 规则）。
- server ops：`merge_suggest` / `group_faces` / `ungroup_faces` / `set_roi`。
- UI：「智能合并建议」按钮 + 候选面板（checkbox、⚠风险项默认不勾）+ 「逻辑归组」/「几何合并」执行钮；画布蓝实线=建议、橙虚线=风险候选。
- 测试：`test_p2_semiauto.py` 6 例（合成 GPKG）；全套 `65 passed, 97 warnings`。

## 真实 U2 数据验证（浏览器,`u2_B2c.gpkg` 665 面）

| 检查 | 结果 |
|---|---|
| `merge_suggest` 返回 + 风险标记 | PASS：seed54 → 7 候选；55/63/71 标 `mixed_label`/`narrow_band` 不进建议 |
| 建议集连通收敛 | PASS：54 的建议集收敛为 `{54}`（62/78/84 隔着风险面，合并本会 multipart） |
| `group_faces` 归组/拆组 | PASS：`FG2` 写入 `attrs.face_group`，拆组后清空 |
| 自动建议产出 | **诚实为零**：全图 1,305 个边相邻面对中同 rgb / 同 label 对数 = **0**——B2c 已把可自动合并的都合并了，剩下的边界全是真实颜色/代号分界。工具如实不报建议，而非硬凑 |
| `int64`/`str label` 序列化缺陷 | 已修（`eid` 转 int、`label` 转 str；"K1" 标签曾 ValueError） |

结论：T10 在 U2 上的真实形态是**半自动**——面板一次性列出邻接候选+风险原因，用户勾选（含风险项）后「逻辑归组」；
几何合并只在该组确为同单元时由用户显式发起，`merge()` 连通性/混合代号保护兜底。

## 复现

- 单测：`.venv-sv/bin/pytest tests/stitchvector_editor/test_p2_semiauto.py`
- 服务：`python -m tools.stitchvector_editor.server --image <png> --gpkg <gpkg> --out-dir <dir> --port 8793`
- API：`POST /api/merge_suggest {"ids":[<face>],"de":15}`；`POST /api/group_faces {"ids":[...]}`

## 未完成

T11（残影清理）、T12（窄面/误并拆分）、T13（补线/编组）、T14（背景保护）依赖既有算子
（residue 线隔离/恢复、`line_to_face`、`split_face_*`、`add_line` 吸附、`regroup`），
逐项 A 类问题的人工修复成本对照（`P2_EDIT_COST_COMPARISON.csv`）与 `P2_MANUAL_REPAIR_REPORT.md` 未做：**NOT_EVALUATED**。

---

## T10 验收补充（P1.1 后，2026-11-05 下午）

**修复**：`group_faces` 的 `next_fg` 自增移入可撤销操作体内——undo/redo 不再复用旧组号（原实现 redo 后 `next_fg` 不自增，后续归组会撞号）。

**真实 U2 量化（400 面抽样，`merge_suggest` de=15）**：

| 指标 | 值 |
|---|---|
| 有同色邻接候选的种子 | 22 / 400（5.5%） |
| 建议集 >1（真自动扩并可省点击） | **0 / 400** |
| 风险标记候选占比 | 779 / 1179（66%，多为 `crosses_split_line`/`mixed_label`=真实地质边界） |
| 同 rgb+同 label 边相邻面对（前 200 面） | 0 / 1396 |

**结论（诚实）**：U2 上 B2c 已把可安全自动合并的面对全部并掉，残留的边相邻几乎都是真实分界——
`merge_suggest` 的自动扩展在本图**不产生任何安全自动建议**，如实返回仅含种子的建议集。
T10 在 U2 的实际形态确认为**半自动**：
- 价值点 1——候选面板把"逐个 Ctrl 点击几十碎面"变成"点主面→看候选+风险原因→勾选"；
- 价值点 2——`LOGICAL_GROUP` 先归组不破坏几何，几何合并在确认后走 E31 溯源路径；
- 风险项默认不勾选，`crosses_split_line`/`mixed_label` 把真实界线挡在自动建议之外。

**状态**：`PARTIAL_AUTO / SEMI_AUTO_PASS`——自动扩选路径在 U2 无安全产出（数据特性非缺陷）；
半自动通路（建议→预览→归组/合并→撤销）单测+真实数据验证通过。
成本对照记入 `P2_EDIT_COST_COMPARISON.csv`。

---

## T11 文字残影半自动清理（A01/A02/E10）

**实现**（`text_residue` + `text_apply(line_ids=)`，隔离非删除、可恢复、可撤销）：

- `Document.text_residue(ids)`：对每个**已有文字对象**按其显示框（+pad）跑残影预案——小面并入候选按既有
  text_preview 分组规则（merge/uncertain），线候选=框内线长占比≥90%；`line_info` 逐线给出
  `inside_share/length/role/risks/suggested`。只读，不落任何修改。
- 风险规则：`line_role∈{SPLIT,UNKNOWN}`→`boundary_risk`（疑似真实界线，默认不勾）；
  端点贴框边→`may_continue_outside`。
- `text_apply(..., line_ids=[...])`：仅隔离用户勾选的线子集到 `text_residue_lines`（记录
  `source=text_residue` + `residue_of=text#<id>` 溯源），未勾线一律保留在 `visual_lines`；
  面并入沿用 coverage 校验；`restore_residue_lines` 恢复原样。
- UI：「选中文字→查残影」按钮 + 逐线勾选面板（⚠风险默认不勾）；应用走现有 textApply 确认路径。

**真实 U2 验证（40 文字样本）**：37/40 有框内线候选（共 86 条），**86/86 全部命中 `boundary_risk`**——
U2 注记大多压在真实界线上，默认隔离零条线、面并入照常建议：保守行为正确，真实界线零误删风险。
3 个无框内线文字为纯面残影。

**单测**（合成，新增 3 例共 9 例）：建议只读/风险标记/子集隔离+溯源/恢复/撤销/保存重开。

**状态**：`SEMI_AUTO_PASS`——A01/A02 修复路径为「点文字→查残影→勾线→确认」≤4 步/处；
E10 线残影默认保守（U2 上几乎全是真界线），留人工勾选决定。

---

## T14 ROI 与背景保护（A10）

**实现**（ROI 声明 → 候选标记 → 审计 → 导出约束）：

- `set_roi`（已有）+ 新 `roi_report()`：按层面/线/字分别统计 完全域内/跨边界/完全域外（边界相触计"跨"不计"外"）。
- `merge_suggest`：出域候选不再静默丢弃，标 `outside_roi` 风险 + 默认不建议——背景/图例区同色面不会被带进建议集。
- `save_as`：ROI 已设且存在**完全域外**对象 → 正式导出拒绝（可草稿导出兜底）；manifest 记 `roi` + `outside_roi` 数。
- 合法多区域区分：合并只沿边连通分量进行（`merge_components` 对无公共边选择直接报错），
  不连通同代号面永不并成一面；`face_group` 逻辑归组才是多区域合法表达。
- UI:「框ROI」工具拖框设域（紫色虚线框）+「域外审计」按钮 + ROI 区面板。

**单测**（合成，+3 例共 12 例）：审计计数（跨/外区分）、域外对象阻止正式存、不连通面永不合并但可逻辑归组。

**状态**：`PASS`——A10 的三类要求（合法多区域保留、跨界合并拒绝、域外成果约束）均有测试与导出门禁。
