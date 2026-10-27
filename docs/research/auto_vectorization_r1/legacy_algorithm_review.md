# 旧算法能力与可复用性（S2A-R1 任务 A）

旧代码：GitLab `dev` `7aad0c1`，通过本地 `git worktree add legacy dev` 只读使用，未修改。
运行方式：`src/scan2arcgis/adapters/legacy.py` 直接调用 `StratigraphyPipeline.run` 与 `BoundaryPipeline.run`，绕过 Web API。
实测数据见 `comparison_experiment.md`；本文件只对能力做判断。

## 1. 结论

旧系统**没有任何深度学习识别**（后端无 torch / onnx / ultralytics / SAM 依赖；`core/moe/adapters/yolo.py` 只做格式转换）。全部识别是颜色、形态学和局部规则。

| 模块 | 代码位置（`legacy/backend/core/recognition/`） | 规模 | 实测能力 | 主要失败模式 | 作为候选生成器 | 继续优化？ | 替换核心算法？ |
|---|---|---|---|---|---|---|---|
| 地层面 | `stratigraphy/`（`detection/palette_resolution.py`、`pixel_classification.py`、`color_clustering.py` KMeans、`postprocess/feature_assembly.py`） | 5,907 行 | 合成干净图 mIoU 0.922（与新方法 0.972 接近）；4 张真实图上大面积不出结果：未标注比例 0.364 / 0.962 / 0.942 / 0.983 | 依赖图例颜色与图面颜色**精确一致**；印刷/扫描色偏后大面积拒绝分类；对象级过分割（合成图 object F1 0.122） | 否（作为基线保留） | 否 | 是：改为“图例样本训练 + 图面自适应”的分类器（见 `modern_algorithm_candidates.md`） |
| 地质界线 | `boundary/`（候选图、骨架追踪、`classification/`、`ink_evidence.py` 等） | 12,061 行，1,410 个浮点字面量 | 合成图全部线 F1 0.092（P 0.535，R 0.053）；1024² 单图 3–40 s，1 例超过 165 s | 召回极低；规则多、相互绕过；耗时不稳定 | 部分：墨迹证据（`ink_evidence.py`）可作特征 | 否 | 是：接触界线由面拓扑导出；独立线改为专门的线检测 |
| 断层 | `geologic_structure/`（从界线中拆分） | 797 行 | 合成图中断层只被少量检出（`boundary_kind=fault` 每图 2–12 条） | 依赖界线模块输出，误差传递 | 否 | 否 | 是 |
| 图例 | 前端人工录入 + `utils/ocr`（PaddleOCR） | — | 本轮未运行（审计环境无 PaddleOCR） | 依赖人工框选与字段填写 | 数据模型可复用 | — | 补充自动色块检测（本轮 PoC） |
| 侵入岩 | `intrusive_rock/` | 220 行 | 复用地层面流程 | 同地层面；花纹填充未专门处理 | 否 | 否 | 随地层面替换 |
| 矿种点 | `commodity/`（模板 + 外形/图案/颜色三门） | 8,146 行 | 本轮未复测（R1 优先面和线） | 前次审计：91 个测试因字段改名失败 | 是：模板裁片与正负样本有价值 | 待 R2 评估 | 待定 |
| 矢量化 | `stratigraphy/postprocess`、`core/fusion`、`core/export` | — | 能输出 Polygon/LineString GeoJSON | 面与线分别产生，接触线与面边界不保证一致 | 否 | 否 | 是：栅格分区 → 多边形 → 公共边（本轮 PoC） |

## 2. 本轮新确认的事实

1. **输入通道顺序**：旧地层流程要求 OpenCV BGR。传入 RGB 时同一合成图只有约 0.7% 像素被分类、输出 0 个多边形，不报错。旧 Web 流程用 `cv2.imread` 所以不会触发，但这是一个无防护的隐含假设。（`runs/_probe` 复现，见 evidence E-A2）
2. **置信度不是概率**：旧地层多边形的 `confidence` 只出现 0.85、0.99 两个值；旧界线 `confidence` 分布在 0.56–0.83。两者都是启发式打分，没有校准依据，D0 中一律标 `UNCALIBRATED`。
3. **对颜色一致性的依赖是失败主因**：公平性检查（`experiments/R1_auto_vectorization/legacy_fairness_check.py`）把图例颜色换成“从图面实际采样的颜色”（对旧算法有利的条件），u2 的已分类比例从 0.038 升到 0.529，u3 从 0.058 升到 0.416；u1（低分辨率截图）仍只有 0.010。说明旧方法的瓶颈在“图例色 ≠ 图面色”，不是适配器问题。
4. **稳定性**：合成 `scan_jpeg_s2` 上旧地层流程抛出 `IndexError`；`hillshade_s2` 上旧界线流程超过 165 s 未完成。

## 3. 值得保留的部分

| 资产 | 理由 | 用法 |
|---|---|---|
| 图例数据模型（代号、名称、颜色、符号裁片、矿种属性） | 新路线完全由图例驱动 | 作为 S2 图例字典的字段来源 |
| 墨迹证据与线型特征（`boundary/ink_evidence.py`、`classification/`） | 可作为线检测器的输入特征或后处理 | R2 线要素实验 |
| 矿种模板裁片与已标注误检 | 点要素的真实正负样本 | R2 点要素评估集 |
| 残差图机制 | 可作为几何质量信号 | 置信度特征 |
| 复核编辑与修订记录 | 反馈闭环数据来源 | 后续接入 |

## 4. 不建议继续投入

旧地层颜色匹配阈值调参、旧界线规则调参、旧断层拆分逻辑。依据：同一输入下新方法已明显优于它们（`comparison_experiment.md` §3、§4），且失败原因是方法本身（颜色精确匹配、规则召回），不是参数。
