# P2 人工/半自动修复逐项验收报告

分支：`fix/stitchvector-v02-uat-remediation` · 日期：2026-11-05 · 依据：《问题20261105.docx》——验收对象 = A 类 11 项 + E10，共 12 项
操作成本实测/估算明细见 `P2_EDIT_COST_COMPARISON.csv`；本报告为逐项裁决。
测试口径：合成 GPKG 单元测试（无受保护数据）+ U2 真实数据只读核查；所有写操作经 `_do()` 撤销栈。

## 验收总表

| issue | 任务 | 修复路径 | 人工操作 | 状态 | 误伤检查 | 一致性 |
|---|---|---|---|---|---|---|
| A08 连续面误分 | T10 | 主面点选→同色邻接扩选→预览→一次确认 | 3–5 | SEMI_AUTO_PASS | 风险候选默认排除；混合代号需显式 opt-in | undo/save/reopen 已测 |
| A09 面内碎裂 | T10 | 同上 + `face_group` 逻辑归组（不改几何） | 2–4 | SEMI_AUTO_PASS | 不连通面永不并入 | `face_group` 随 GPKG 持久化 |
| A01 文字周边碎面 | T10+T11 | 选文字→残影候选→勾选→确认 | 3–4 | SEMI_AUTO_PASS | 压界线默认不选、隔离非删除 | 撤销即复原 |
| A02 文字残影面 | T11 | 同上：面残影归并组 | 3–4 | SEMI_AUTO_PASS | 仅候选框内 | 已测保存重开 |
| E10 文字残影线 | T11 | `isolate_lines`/`text_apply` 移残影层，可恢复 | 2–3 | SEMI_AUTO_PASS | boundary_risk 线默认保留 | `residue_of` 溯源 |
| A10 处理范围/背景 | T14 | 拖 ROI→域外审计→正式存域外拒写 | 2–3 | PASS | 跨界≠域外；合法多区域保留 | ROI 状态持久 |
| A05 窄面缺失 | T12 | 描轴线（端点/中段吸附）→`line_to_face`+代号 | 3–6 | SEMI_AUTO_PASS | coverage 非法即回滚 | 邻面 id 不变 |
| A06 误并大面 | T12 | 画切割线→`SPLIT`→预览→应用 | 4 | SEMI_AUTO_PASS | 只切目标面 | undo 已测 |
| A33 线旁窄面被吞 | T12 | 描绘被吞边界（T 形吸界）→`line_to_face` | 4–6 | SEMI_AUTO_PASS | 同上 | 同上 |
| A15 断线漏段 | T13 | 选段→`join_preview`（端点距）→`join_lines` | 3 | SEMI_AUTO_PASS | 缺口>阈值拒接、先补画 | 保存重开一致 |
| A20 虚线误连 | T13 | `regroup` 逻辑归组；几何接被禁 | 2 | PASS | dash 图例线禁止几何接 | 渲染仍按图例 |
| A24 编组错误 | T13 | `regroup`/`ungroup_lines`/`isolate_lines` | 2–3 | SEMI_AUTO_PASS | 移出=隔离非删除 | 撤销恢复组属 |

## 结论

- **12/12 项均有已验证的修复路径**（A 类 11 项 + E10）：PASS 2（A10、A20），SEMI_AUTO_PASS 10。
- **无 PASS_BY_AUTO**：按设计，凡触及地质语义的操作均需人工确认；这符合「不牺牲真实地质线面换自动率」原则。
- **真实 U2 观察**：T10 自动合并空间=0（B2c 已并完可并者），价值在批量归组面板而非自动并；
  T11 线候选 86/86 命中 boundary_risk 默认不选——线隔离保持人工确认，为有意保守。
- **几何安全**：所有合并沿边连通分量；覆盖面变更经 `coverage_report` 校验；ROI 域外对象无法正式导出；
  虚线几何接被门禁拒绝。未发现对正确地质信息的误伤路径。
- **一致性**：每个写入算子均有 undo 测试；`merged_from`/`face_group`/`residue_of`/`logical_id` 随 GPKG 保存重开。
- **未解决/限制**：A05/A33 依赖人工描绘精度（吸附辅助已加）；完全漏检文字不在本阶段范围（P3-E01/E02）。
- **总状态**：`P2_READY_FOR_HUMAN_UAT`——待人工按本表与 CSV 逐项复核 UAT。
