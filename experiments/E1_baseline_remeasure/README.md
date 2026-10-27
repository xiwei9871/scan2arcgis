# E1 现有算法真实能力复测 + D0 评估框架落地

状态：DESIGN（未实施）。依赖：`docs/design/D0_dataset_spec.md`、`docs/design/evaluation_framework.md`。

## 1. 目标

1. **主要交付**：可长期复用的 D0 数据规范实现与评估工具（任何识别器都能接入）。
2. **次要交付**：旧算法在 D0 上的客观现状报告，以及错误的归因分布。

E1 不改进旧算法，不训练模型。

## 2. 假设

- H1：旧 baseline 指标（界线 F1 0.12、地层 mIoU 0.38）因标注极少而不可信，真实值可能偏高或偏低。
- H2：旧算法的错误中有可观比例属于 `IMPLEMENTATION` / `POSTPROCESS`（例如坐标换算），修复成本远低于换算法。
- H3：旧算法的原始分数（如 `confidence`、`line_style_confidence`、`fault_score`）与对错之间存在可测的区分能力（AUROC > 0.5），可作为将来误差预测模型的特征。

## 3. 输入

| 数据 | 层 | 状态 |
|---|---|---|
| `gm1`、`gm2` 样图 | L0 | 已有，本地 |
| 旧 baseline 局部标注（5 条线、7 个面、3 条等高线） | L0 | 迁移为 D0，`label_status=draft` |
| 两张样图上的新增局部 ROI 标注（近色地层、经纬网/图框、断层、矿种） | L1 | 需地质人员标注 |
| 2–3 张全幅标注 | L2 | 需新图幅或已有矢量 |
| 新图幅 | L3 | E1 不使用；E1 不读取任何 `holdout` |

## 4. 实施步骤

| 步骤 | 内容 | 产物 | 验收 |
|---|---|---|---|
| E1.1 | D0 schema、校验器、门槛注册表 | `schemas/d0/`、`src/scan2arcgis/d0/validate.py`、`configs/thresholds.yaml` | 单元测试通过（本分支已完成初版） |
| E1.2 | GeoPackage 读写；L0 旧标注迁移脚本 | `src/scan2arcgis/d0/io.py`、`tools/migrate_legacy_baseline.py` | 迁移结果通过 V1–V8；几何与旧文件逐点一致 |
| E1.3 | 评估器：面/线/点匹配、指标、cluster bootstrap、置信度分析 | `src/scan2arcgis/eval/` | 合成已知答案样例的测试全部通过；与手工计算的小例子一致 |
| E1.4 | 旧算法适配器：在 `legacy/`（`git worktree add legacy dev`）中运行旧流水线，把输出转为 D0 预测 | `adapters/legacy/` | 输出通过校验；`producer_kind=legacy_rule`、`calibration_status=UNCALIBRATED`；坐标空间逐一核对并有测试 |
| E1.5 | 运行与评估：L0 + L1（+ 可用的 L2） | `runs/`（不入库）、`experiments/E1_baseline_remeasure/results/report.md` | 报告结构符合框架 §7 |
| E1.6 | 错误归因：自动预判 + 地质人员抽样复核（每类要素抽样 ≥ 30 个错误对象或全部） | 归因表 | 抽样复核与自动预判一致率写入报告 |

旧流水线的运行方式：通过 `RecognitionPipeline.run_image_recognition`（`legacy/backend/core/recognition/pipeline.py`）直接调用，绕过 Web API；Linux 下需审计时使用的 `msvcrt` shim 与 `matplotlib`。全分辨率图在审计环境中超过 3 分钟未完成，E1 需在有足够内存的机器上运行，或在本地 Mac 上运行并记录耗时。

## 5. 指标

按 `evaluation_framework.md` §2：面（对象 F1、mIoU、图例绑定准确率）、接触界线与断层（缓冲 F1、对象 F1）、矿种点（对象 F1）。所有数据集级指标附图幅 bootstrap 区间；图幅 < 5 时只出逐图结果。

置信度：旧原始分数的 AUROC 与可靠性图，标注 `UNCALIBRATED`，**不做 Risk–Coverage 的自动接受结论**。

## 6. 成功标准

E1 的成功不以旧算法分数高低衡量：

1. 评估器在合成测试上 100% 正确。
2. 旧算法在 L0+L1 上的完整报告可一条命令复现（同一输入两次运行，指标完全一致）。
3. 每类要素的错误都有归因分布，抽样复核完成。
4. 报告中所有判定引用门槛注册表；没有已批准门槛时结论为 `NO_THRESHOLD`。

## 7. 资源假设

1 名开发约 2–3 周；1 名地质标注人员约 5–8 个工作日（L1 ROI）；CPU 机器，内存 ≥ 16 GB 以运行全分辨率图（推断）。

## 8. 结果对后续决策的影响

| E1 结果 | 后续决策 |
|---|---|
| 错误以 IMPLEMENTATION / POSTPROCESS 为主 | 先修复旧算法中对应部分作为 E2 的强基线 |
| 错误以 ALGORITHM 为主（尤其线要素） | E2 优先引入深度模型候选 |
| 旧分数 AUROC 明显 > 0.5 | 保留为误差预测特征 |
| 指标置信区间过宽 | 先扩充 L1/L2，再做 E2 |
