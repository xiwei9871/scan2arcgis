# 评估框架 v0.1

状态：DESIGN。适用于 E1–E4 以及所有后续识别器。评估工具只读 D0 文件（真值、预测、清单），不导入任何识别代码。

## 1. 评估粒度

| 粒度 | 回答的问题 | 用于 |
|---|---|---|
| 像素 | 面积上分得对不对 | 面要素 mIoU、混淆矩阵 |
| 对象 | 每个要素是否被找到且类别正确 | 所有要素的 P/R/F1；置信度校准的样本单位 |
| 图幅 | 整张图能否交付 | 完整性、拓扑、导出、端到端耗时 |
| 数据集 | 方法总体水平与不确定性 | 按图幅 bootstrap 的置信区间 |

**置信度校准与 Risk–Coverage 一律以“对象”为样本单位**，因为自动接受决策是对单个要素做的。

## 2. 各要素的对象级匹配与“正确”定义

容差统一用图上毫米表达，按扫描分辨率换算成像素：`tol_px = tol_mm × dpi / 25.4`。默认值只是开发用占位，正式值由业务方确定（见 §6 门槛注册表）。

| 要素 | 匹配方式 | 对象正确条件 | 错误类型 |
|---|---|---|---|
| 地层/侵入岩面 | 预测面与真值面按 IoU 做一对一最优匹配（Hungarian） | IoU ≥ τ_iou 且 `legend_code` 一致 | 类别错 / 边界差 / 漏检 / 多检 / 过分割 / 欠分割 |
| 接触界线 | 按长度切分为固定步长线段，在缓冲区 `tol_px` 内匹配 | 被匹配长度比例 ≥ τ_len，两侧面类别正确 | 漏段 / 多段 / 位置偏 / 两侧类别错 |
| 断层 | 同接触界线，额外比较线型 | 同上 + 线型一致 | 同上 + 线型错 |
| 矿种点 | 距离 ≤ `tol_px` 的一对一最优匹配 | 匹配且矿种代号一致 | 漏检 / 多检 / 类别错 |
| 图例项 | 与真值图例字典逐项比较 | 代号、名称、颜色（ΔE ≤ 阈值）全部正确 | 代号错 / 缺项 / 多项 |

像素/长度级汇总指标同时报告：面 mIoU、面积加权准确率；线缓冲 Precision / Recall / F1；点 P/R/F1。

错误按严重度分级，供置信度系统使用：

| 级别 | 示例 | 意义 |
|---|---|---|
| S1 严重 | 类别错、坐标错、虚构要素 | 自动接受中最不能容忍 |
| S2 中等 | 漏检、明显边界偏移 | 影响完整性 |
| S3 轻微 | 容差边缘的边界偏差 | 可容忍 |

## 3. 失败归因

E1 中每个错误对象再标一个原因（由脚本先自动预判，地质人员抽样复核）：

`ALGORITHM`（方法本身做不到） / `DATA`（缺少该图式样本或图例） / `IMPLEMENTATION`（坐标换算、裁剪、字段丢失等工程错误） / `POSTPROCESS`（分割对但合并、简化、拓扑处理出错） / `EVALUATION`（真值错误或匹配规则不合理）。

自动预判依据举例：预测几何整体平移且与图像尺寸比例相关 → `IMPLEMENTATION`；同一真值面被切成多个预测面且类别都对 → `POSTPROCESS`；真值标注状态为 `draft` 且双人标注不一致 → `EVALUATION`。

## 4. 置信度评估（对所有带分数的识别器适用）

1. **原始分数也要评估**，即使是 `UNCALIBRATED`：计算 AUROC（分数能否区分对错）与可靠性图。这回答“旧分数有没有可用信号”，但不允许把它当概率使用。
2. **校准**只在 `calib` 切分上拟合（isotonic / Platt / conformal），在 `holdout` 上报告 ECE、Brier。
3. **Risk–Coverage**：按 `p_error` 升序逐个接受对象，记录覆盖率与被接受集合的实际错误率（按 S1、S1+S2 分别计算）；报告 AURC，以及在给定 α 下的最大覆盖率和置信上界。
4. **置信上界**按图幅 cluster bootstrap 计算（错误按图幅成簇）。零错误时的二项上界作为下限参考：n 个被接受对象零错误时，95% 上界约为 3/n。
5. **自动接受实测错误率**只能用 `review_sampling = random_audit` 的样本估计。

## 5. 不确定性与样本量

- 所有数据集级指标报告点估计 + 95% 置信区间，方法为按图幅 cluster bootstrap（默认 2,000 次重采样）。图幅少于 5 张时只报告逐图结果，并标注“样本不足，不做总体结论”。
- 比较两个方法时，用**配对**图幅 bootstrap 计算差值的置信区间；区间不含 0 才算有差异。
- 扩充数据的停止条件：关键指标的置信区间半宽小于业务关心的最小改进量（由业务方给定，未给定前不做停止判断）。

## 6. 门槛注册表

门槛统一存放在 `configs/thresholds.yaml`，每一项必须包含：

```yaml
- id: unit.object_iou_min
  value: null            # 未确定为 null
  unit: ratio
  status: UNSET          # UNSET / PROPOSED / APPROVED
  source: ""             # 业务文件、规范条款或会议纪要
  approved_by_role: ""
```

规则：
- 报告中引用 `UNSET` 门槛时只输出数值，结论栏写 `NO_THRESHOLD`，不输出 PASS/FAIL。
- 开发期间允许使用 `PROPOSED` 值调试，但报告必须标明“非验收门槛”。
- **旧项目 `minimum_metrics.json` 中的阈值不迁移**。它们是贴着当时结果设定的防退步线，不代表业务要求。旧值只作为“历史参照数值”出现在 E1 报告中。

## 7. 报告结构（`report.json` / `report.md`）

```
meta:      eval_id, created_at, evaluator_commit, dataset_version, run_ids, holdout_accessed
inputs:    逐图 sha256 校验结果；D0 校验结果（V1–V8）
metrics:   按 要素 × 粒度 × 图幅 / style_group / 总体（含置信区间）
errors:    错误对象清单（类型、严重度、归因、位置），失败案例裁片路径（裁片不入库）
confidence: 原始分数 AUROC、可靠性图数据；如已校准：ECE、Brier、Risk–Coverage、α 下覆盖率
thresholds: 引用的门槛及状态；每项结论 PASS / FAIL / NO_THRESHOLD
limitations: 标注状态分布、样本量警告、未执行项
```

## 8. 实现计划（代码路径）

| 路径 | 内容 |
|---|---|
| `schemas/d0/feature_record.schema.json` | 要素记录 JSON Schema（本分支已提供） |
| `src/scan2arcgis/d0/validate.py` | V1–V8 校验器（本分支已提供） |
| `src/scan2arcgis/d0/io.py` | GeoPackage 读写（E1 实施时） |
| `src/scan2arcgis/eval/match_*.py` | 面/线/点匹配（E1 实施时） |
| `src/scan2arcgis/eval/bootstrap.py` | 图幅 cluster bootstrap（E1 实施时） |
| `src/scan2arcgis/eval/confidence.py` | AUROC、可靠性、Risk–Coverage（E1 实施时） |
| `src/scan2arcgis/eval/report.py` | 报告生成（E1 实施时） |
| `configs/thresholds.yaml` | 门槛注册表（本分支已提供，全部 UNSET） |

评估工具自身用合成小样例做单元测试：已知答案的面、线、点，确保匹配与指标计算正确。“评估器正确”必须先于“识别器好坏”被证明。
