# ARCH-1 总报告：多证据有效性与窄地层可恢复性审计（2026-10-30）

**状态：ARCH1_READY_FOR_HUMAN_REVIEW。** 没有训练，没有修改 RAG τ，没有修改 M2_hybrid 和正式 GIS 输出，没有访问测试池或 08011、08021，没有合并 main。
起点：`0a570f9c45595bfc35c877fc79ddf7bc66a03a52`。预注册判据：`experiments/ARCH1/arch1_criteria.json`（`dc6469a`，在 Gate 1–5 运行前提交）。
图幅：10 幅训练图（预测为样本内）和已暴露的 13014、15076。官方标签只用于分类、Oracle 和评价。

## 交付清单

| 交付 | 报告 | 数据 |
|---|---|---|
| 0. 研究口径固化 | [gate0_scope.md](gate0_scope.md) | `experiments/ARCH1/gate0/d3_strict_recount.json` |
| 1. 证据独立价值报告 + 分宽度有效性与互补性矩阵 | [gate1_evidence_audit.md](gate1_evidence_audit.md) | `gate1/gate1_evidence_audit.json`、`gate1/gate1_matrix.csv` |
| 2. 完美证据 Oracle 消融 | [gate2_oracle_ablation.md](gate2_oracle_ablation.md) | `gate2/gate2_oracle_ablation.json` |
| 3. 墨带截面线宽验证 | [gate3_line_width.md](gate3_line_width.md) | `gate3/gate3_line_width.json` |
| 4. 分级公共细分复杂度与接口 | [gate4_subdivision.md](gate4_subdivision.md) | `gate4/gate4_subdivision.json` |
| 5. C-PAIR V0.1 设计与准入结论 | [gate5_cpair_design.md](gate5_cpair_design.md) | — |
| 6. 风险与下一阶段预注册建议 | 见 Gate 5 第 3、4 节 | — |

## 主要结论

1. **边界层面的证据已经足够；难点在小区域。** 判断"该不该合并"（防止错误合并、保持大单元完整）时，B2 边界强度的 AUC 是 0.97–0.99。区分"真实窄单元与墨带伪碎片"时，最好的单项证据也只有 0.84–0.89，保留 95% 真实单元时误报率仍有 49–66%。
2. **有三类可以组合的独立证据：** B2 边界强度、颜色差、预测宽度。按错误相关性实测，两两 φ 在 0.18–0.26 之间。M1 与 M2（φ 0.66）、M2 距离与宽度（φ 0.54）高度相关，各只能算一项。邻居数在训练图上过拟合，不能用。
3. **窄候选必须带保护。** 完美的窄候选把 ≤ 6 px 的初始区域上限提高到 1.00，但冻结合并仍吞掉其中 34–88%，合并后召回只有 0.48 / 0.44；配上完美的合并关系，≤ 6 px 和 6–10 px 都达到 1.00。
4. **合并关系是价值最大的单项证据**（总召回 0.89 → 0.97、0.75 → 0.91）。完美的地质单元代号效果接近，但主要靠"同单元强制合并"，现有 OCR 无法覆盖训练图。
5. **局部线宽不能用于判别**：截面测宽对 1.5 px 以上的孤立线是准的，图间也稳定，但在密集地质图上可靠样本只有 0.7–22%，判别 AUC 只有 0.68。按预注册判为不合格，没有重调。
6. **分级公共细分在计算上可行：** 区域数是只用 B2 时的 1.6–2.2 倍（全部叠加是 15–21 倍），合并不到 0.5 秒，峰值内存 3.6 GB。决策记录在 12 幅图上都能逐像素还原被合并的候选。
7. **口径更正：** 按严格位置，3–6 px 实例中两侧都被 B2 覆盖良好的只有 7%（训练图）和 18%（暴露图）；ARCH-0 中"B2 已看到大部分窄层两侧"的说法过于乐观。

## C-PAIR V0.1：有条件准入

三项预注册条件都满足。附带三项约束：
- 必须同时提供候选和**软保护**，因为目前没有误保护率 ≤ 0.10 的证据，不能设硬切割；
- 判别只用三项独立证据（B2 边界强度、颜色差、宽度）的组合，不用局部线宽，也不用邻居数；
- 阶段二的门槛要直接衡量**合并后**的 3–6 px 召回（比 RAG_BOUNDARY_ONLY 提高 ≥ 0.10），并报告误保护率，不能只看 Oracle 上限。

## 复现

```bash
cd experiments/ARCH1
../../.venv-ml/bin/python arch1_gate0.py gate0/d3_strict_recount.json
../../.venv-ml/bin/python arch1_gate1.py gate1
../../.venv-ml/bin/python arch1_gate2.py gate2
../../.venv-ml/bin/python arch1_gate3.py gate3
../../.venv-ml/bin/python arch1_gate4.py gate4
```

M1 在 13014、15076 上的推理（冻结权重）需要先运行：

```bash
cd experiments/R4A && ../../.venv-ml/bin/python r4a2_2_infer.py M1 ../../runs/r4a2/models/M1_formal/best.pt ../../runs/r4a2/13014/geotiff_rgb.png ../../runs/r4c0/pred_test/13014/M1
```
