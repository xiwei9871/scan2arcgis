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
