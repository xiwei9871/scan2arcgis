# P2.1 加固报告（任务一）

基线：`fix/stitchvector-v02-uat-remediation @ e6010ba` → 本次三个独立小提交。

## 修复项

### 1. T11 text_apply 默认隔离范围（`cd77e1e`）

**问题**：`text_apply(line_ids=None)` 旧语义 = 隔离预览中**全部**候选线，包括 `boundary_risk` 标记线；
Python/API 调用方若不传 `line_ids`，风险线会被默认移出线层——与「压线默认不选」的 UI 语义不一致。

**修复**：默认仅隔离预览标记 `suggested`（零风险）的线；风险线必须显式 `line_ids` opt-in。
前端本就回传勾选集，语义自此三端一致。3 个旧测试改为显式传全量候选（它们本意即"全部隔离"），
新增 `test_text_apply_default_isolates_only_suggested_lines` 钉住新默认。

### 2. T14 ROI 持久化/撤销 + 三能力分离（`73fe47b`）

**问题**：ROI 仅存内存 `self.roi`——保存丢失、重开为空、不参与快照（撤销无法恢复）；
且「域外拒存」把审计、裁剪、跨域保护混为一个开关。

**修复**：
- `project_roi` GPKG 层：保存写入、打开恢复（实测 reopen 后 bounds 一致）；
- `set_roi` 走 `_do` 撤销栈（`_snap/_restore` 加入 roi）——undo/redo 正确恢复，设域标脏促保存；
- 三能力显式分离：
  - **审计** `roi_report`（非破坏计数，内/跨/外）；
  - **跨域保护** `merge_suggest` 的 `outside_roi` 风险 + 正式存域外门禁；
  - **裁剪导出** `save_as(roi_mode="keep"|"clip")`。

### 3. T14 范围约束导出（同提交）

**问题**：跨 ROI 对象此前只有「全部合法」或「域外拒存」两态，跨界对象无处置路径。

**修复**：
- `roi_clip_preview`：逐层列出 inside/crossing/outside **对象 id**，跨界处置前可预览；
- `roi_mode="keep"`：域外丢弃、跨界**整体保留**；`roi_mode="clip"`：跨界沿 ROI 边界裁切
  （MultiPolygon/ MultiLineString 自动拆分保证单层单类型）；
- 覆盖面校验随模式切换：clip=对 ROI 精确平铺（`within`），keep=并集覆盖 ROI（`covers`）；
- 裁剪导出**不修改文档本体**，readback 与写出子集比对；UI 保存被拒时提供 keep/clip 选择。

### 4. T13 虚线误并恢复测试（`cddbcea`）

新增 `test_dash_wrongly_joined_split_regap_regroup`：实线（B2c 误并的虚线）→ 间隔界点 split_line ×2
→ 误连段 `isolate_lines`（可恢复）→ 两段赋 L_DASH_RED → new_group 编组。
验证：渲染按图例为虚线、5px 间隔作为真实缺口保留、撤销恢复成员关系。

### 5. 统计口径修正（同提交）

`P2_MANUAL_REPAIR_REPORT.md` 验收对象明确为 **A 类 11 项 + E10 = 12 项**（此前行文混用"A 类11项/12项"）。

## 测试

- 编辑器全量：**96/96 PASS**（P2.1 新增 8 例：默认隔离、ROI 持久化/撤销/预览/keep/clip、虚线恢复链）。
- `test_line_repair` 一处 monkeypatch 签名适配（verify 新增 kwargs）。
- 未改 B2c 基线；提交相互独立：`cd77e1e` / `73fe47b` / `cddbcea`。
