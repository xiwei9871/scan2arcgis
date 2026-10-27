# 实际对比实验（S2A-R1 任务 C）

所有数字由脚本从结果 JSON 生成或直接引用，未手工改写。完整表格：`experiments/R1_auto_vectorization/results/tables.md`。

## 1. 实验设置

| 项 | 内容 |
|---|---|
| 运行环境 | Ubuntu 22.04 VM，aarch64，4 核 CPU，约 3.9 GB 内存，无 GPU；Python 3.10.12，numpy 1.24.3，OpenCV 4.10，scikit-learn 1.7.2，onnxruntime 1.23.2，shapely 2.0.2 |
| 代码版本 | 新代码：本分支；旧代码：GitLab `dev` `7aad0c1`（只读 worktree） |
| C1 旧算法 | `StratigraphyPipeline`（地层面）、`BoundaryPipeline`（界线），经 `src/scan2arcgis/adapters/legacy.py` 调用 |
| C2 新候选 | (a) 图例最近色 `legend_nearest_color`；(b) 图例随机森林 `legend_rf`；(c) 加图面自训练 `legend_rf_selftrain`；(d) (c)+SAM 2.1-tiny 边界精修 |
| 接触线 | 新方法一律由面分区公共边导出，不单独检测 |
| 断层 | 新方法用规则版“深色墨迹骨架”候选（占位基线，非深度模型） |
| 输入一致性 | 同一图像、同一图例颜色输入两类方法；旧算法输入 BGR（其要求），新方法 RGB |

## 2. 数据

**合成基准（有精确真值）**：`src/scan2arcgis/synth/generate.py`，5 类难点 × 3 个随机种子 = 15 张 1024² 图，带图例面板、接触线、断层、注记、经纬网和侵入体花纹。难点：`clean`、`near_color`（近色地层）、`scan_jpeg`（噪声、模糊、JPEG、色偏）、`hillshade`（地形晕渲）、`thick_ink`（粗线条）。合成数据只用于隔离具体难点，**不能替代真实图验证**。

**真实图（无完整真值）**：

| map_id | 来源 | 处理区域 | 参考数据 |
|---|---|---|---|
| gm2 | 旧仓库样图（1:20 万） | 原图 ROI 3100×3500，缩放 0.5 | 旧项目 draft 局部标注：4 个面、3 条线（未审核，无图例代号） |
| u1 | 项目负责人提供（低分辨率截图） | 774×722 | 无 |
| u2 | 项目负责人提供 | 805×780 | 无 |
| u3 | 项目负责人提供 | 3357×2177，缩放 0.5 | 无 |

真实图像不入库，SHA-256 见 `data/manifests/maps.csv`。图例色块由 `recog/legend_swatches.py` 自动检测（gm2 33 个、u1 11 个、u2 12 个、u3 14 个），未人工修正。

## 3. 合成基准结果（15 张，均值 [95% 按图 bootstrap 区间]）

| 方法 | 面 mIoU | 面对象 F1 | 接触线 F1 | 全部线 F1 | 全部线 P / R | 耗时 s |
|---|---|---|---|---|---|---|
| 旧 地层面 | 0.609 [0.41, 0.80] (n=14) | 0.122 [0.08, 0.17] | 0.373 [0.22, 0.54] | — | — | 2.2 |
| 旧 界线 | — | — | — | 0.092 [0.05, 0.13] (n=14) | 0.535 / 0.053 | 6.9（1 例 >165 s） |
| 图例最近色 | 0.857 [0.78, 0.93] | 0.619 [0.46, 0.78] | 0.785 [0.66, 0.91] | 0.802 [0.68, 0.92] | 0.754 / 0.939 | 0.6 |
| 图例 RF | 0.861 [0.78, 0.94] | 0.658 [0.49, 0.81] | 0.811 [0.69, 0.92] | 0.824 [0.71, 0.93] | — | — |
| **图例 RF + 自训练** | **0.874 [0.80, 0.94]** | **0.681 [0.51, 0.84]** | **0.827 [0.71, 0.94]** | **0.831 [0.72, 0.93]** | 0.791 / 0.943 | 1.7 |
| + SAM 2.1-tiny 精修 | 0.877 [0.80, 0.94] | 0.706 [0.54, 0.86] | 0.820 [0.70, 0.94] | — | — | 3.4 |

n=14 处：旧地层在 `scan_jpeg_s2` 抛出 `IndexError`；旧界线在 `hillshade_s2` 超过 165 s 未完成，均计为缺失（对旧算法有利）。

按难点（mIoU / 对象 F1）：

| 难点 | 旧 地层面 | 图例 RF + 自训练 |
|---|---|---|
| clean | 0.922 / 0.205 | 0.972 / 0.968 |
| near_color | 0.943 / 0.234 | 0.973 / 0.937 |
| thick_ink | 0.725 / 0.099 | 0.945 / 0.790 |
| scan_jpeg | 0.347 / 0.048（1 例报错） | 0.826 / 0.570 |
| hillshade | 0.018 / 0.000 | 0.654 / 0.138（最弱） |

**结论（合成）**：新方法在面、接触线、全部线上均明显优于旧算法，区间不重叠。SAM 精修的提升（对象 F1 0.681 → 0.706）在区间内，**不显著**，耗时翻倍。地形晕渲是新方法最主要的弱点；在旧算法上，扫描噪声与晕渲都会导致几乎完全失效。

## 4. 线要素

- 接触线：由面导出后，F1 0.827；旧界线模块 0.092，召回 0.053。
- 断层：规则墨迹骨架候选 F1 0.656 [0.57, 0.74]（合成）。这是本轮最弱的要素，需要专门的线检测模型（R2）。
- 真实图 gm2（只在 3 条 draft 参考线附近 20 px 走廊内评估）：旧地层面边界召回 0.395，新方法 0.249；精确率均约 0.17–0.19。**这一项旧算法更好**，样本只有 3 条线、标注未审核，不能下结论，但说明真实图上边界位置仍需改进。

## 5. 真实图结果（无完整真值，只报告可复现观察）

| map | 旧：多边形数 | 旧：未出结果面积比例 | 新：区域数 | 新：使用类别数 | 新：低边际像素比例* | 旧 s | 新 s |
|---|---|---|---|---|---|---|---|
| gm2 ROI | 65 | 0.364 | 251 | 28 | 0.152 | 12.1 | 9.8 |
| u2 | 5 | 0.962 | 138 | 11 | 0.081 | 1.0 | 1.2 |
| u3 | 8 | 0.942 | 223 | 14 | 0.026 | 3.4 | 3.2 |
| u1 | 4 | 0.983 | 96 | 8 | 0.347 | 1.1 | 0.9 |

\* 分类边际 < 0.3 的像素比例，未校准，只说明“系统自己认为不确定”的面积。

旧算法公平性检查（`legacy_fairness_check.py`）：把图例颜色换成从图面实际采样的颜色后，已分类比例 u2 0.038 → 0.529，u3 0.058 → 0.416，u1 0.017 → 0.010。旧算法的问题是“要求图例色与图面色精确一致”，不是适配器问题。

gm2 draft 面参考（4 个面，类别无关评估）：

| 方法 | 平均纯度 | 平均最佳 IoU |
|---|---|---|
| 旧 地层面 | 0.227 | 0.052 |
| 新 RF + 自训练 | 0.298 | 0.233 |
| 新 RF + 自训练 + 色度不变特征 | 0.301 | 0.254 |

新方法更好，但**绝对值很低**。观察叠加图（`runs/real/gm2_roi/compare/compare_side_by_side.jpg`，本地）：真实 1:20 万图上一个地层单元内部常被分成多个近色类别（33 个图例色块中多对颜色相近），同时注记、断层符号和小面积单元造成碎片。真实图的质量远低于合成基准，合成结果不能外推。

## 6. SAM 2.1-tiny 单独测试

合成 `clean` 图，以每个真值区域最内部一点作为提示：实例 IoU 均值 0.607、中位 0.614；SAM 自报 IoU 与实际 IoU 相关系数 0.25（不能作置信度）。CPU 编码 2.1 s / 1024²，解码 0.05 s / 次。适合交互式“点一下重分割”，不适合作为主识别器。

## 7. 人工修正工作量估计

本轮**没有计时实验**，无法给出节省工时的证据。可复现的间接量：u3 的 223 个区域中，决策为 HUMAN_REVIEW 2 个、AUTO_RETRY 18 个；gm2 ROI 250 个中 HUMAN_REVIEW 98 个。这些是未校准的排序结果，不代表实际需要修改的数量。

## 8. 复现

```bash
python src/scan2arcgis/synth/generate.py runs/synth_suite
for c in runs/synth_suite/*; do PYTHONPATH=<msvcrt-shim> python experiments/R1_auto_vectorization/run_synth_case.py $c runs/r1_synth --sam <sam_dir>; done
python experiments/R1_auto_vectorization/aggregate.py runs/r1_synth experiments/R1_auto_vectorization/results/synth_summary.json
python experiments/R1_auto_vectorization/auto_retry_selection.py runs/synth_suite experiments/R1_auto_vectorization/results/auto_retry_selection.json
python experiments/R1_auto_vectorization/prepare_real.py data/raw/gm2.jpg runs/real/gm2_roi --roi 2950,300,3100,3500 --legend 6130,300,2763,4700 --scale 0.5 --min-side 25 --max-side 90
python experiments/R1_auto_vectorization/compare_real.py runs/real/gm2_roi runs/real/gm2_roi/compare --ref data/labels/legacy_baseline_v1/geological_map_2/stratigraphy_labels.geojson --ref-lines data/labels/legacy_baseline_v1/geological_map_2/boundary_labels.geojson
```

u1/u2/u3 参数见 `experiments/R1_auto_vectorization/README.md`。
