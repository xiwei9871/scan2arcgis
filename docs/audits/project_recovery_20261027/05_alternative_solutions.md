# 05 外部成熟技术与替代路线

说明：本节外部资料通过网络检索获得（2026-10-27），引用的数值来自检索结果摘要和论文摘要，未逐篇下载原文复核，标为 INFERRED。采用前应阅读原文确认适用条件。

## 1. 同类问题的行业现状

本项目要解决的问题（扫描地质图 → 按图例提取面、线、点要素 → 带坐标的矢量）与 DARPA 和 USGS 于 2022 年举办的 AI for Critical Mineral Assessment Competition（AI4CMA），以及后续 CriticalMAAS 项目的 TA1 任务基本相同。

| 来源 | 关键信息 | 对本项目的意义 |
|---|---|---|
| USGS《Extracting data from maps: Lessons learned from the AI4CMA competition》 | 有用户提示（图例）的面、线、点提取，中位 F1 分别约 0.77、0.56、0.35 | 线和点要素即使在国际竞赛水平上也远未达到全自动可交付；本项目界线 F1 0.12 的差距需要放在这个背景下看 [INFERRED] |
| MDPI Geosciences 14(11):305《Accurate Feature Extraction from Historical Geologic Maps Using Open-Set Segmentation and Detection》 | 在 AI4CMA 数据上，面要素中位 F1 0.91，点要素 0.73 | 面要素用图例驱动的分割方法可达到较高水平，是 MVP 最可行的部分 [INFERRED] |
| USGS 数据集《Training and validation data from the AI4CMA Competition (ver. 2.0, July 2025)》 | 公开的地质图训练和验证数据，带图例标注 | 可用作方法对比和预训练，弥补本项目数据不足；但为美国地质图，与中国图式不同，需要验证可迁移性 |
| USGS《Automated georeferencing and feature extraction of geologic maps and mineral sites》 | 总结 DARPA 系列挑战中自动配准和要素提取的进展 | 自动配准有可参考的成熟做法 |
| DARPA AI4CMA 竞赛页与挑战说明 PDF | 任务定义：根据图例符号在扫描图中提取要素 | 可以直接借用其任务定义和评分方法 |

## 2. 开源项目

| 项目 | 内容 | 成熟度 | 可用方式 |
|---|---|---|---|
| GDAL / OGR（gdal_translate -gcp、gdalwarp -order n / -tps） | GCP 配准、重投影、栅格与矢量格式读写 | 行业标准，活跃维护 | **直接替换**自研变换与输出 |
| QGIS Georeferencer / PyQGIS | 交互式 GCP、多种变换、残差表、输出 GeoTIFF | 成熟 | 作为配准的参照实现，或直接作为人工配准工具 |
| PROJ / pyproj | CGCS2000、西安80、北京54、高斯-克吕格 | 成熟 | 直接使用（项目已部分使用） |
| Shapely / GEOS、GeoPandas、Fiona/pyogrio | 几何、拓扑、Shapefile/GeoPackage 写出 | 成熟 | 直接使用（项目已使用） |
| Rasterio | 栅格读写、窗口读取（适合 2 亿像素以上大图分块） | 成熟 | 解决大图性能问题 |
| OpenCV | 颜色空间、形态学、模板匹配 | 成熟 | 已使用 |
| DARPA-CRITICALMAAS/uncharted-ta1 | 地质图要素提取与自动配准流水线 | 竞赛和项目代码，需评估维护状态 | 参考架构，局部复用 |
| Fandel-Lin/LOAM | 利用图例面元数据理解栅格地图（面要素） | 研究代码 | 面要素方法对比基线 |
| DARPA-CRITICALMAAS/ta1-geopackage | 地质图矢量输出的 GeoPackage 模式 | 有明确模式定义 | 参考输出数据模型 |
| priyammaz/DARPAMapExtraction | 竞赛提交代码 | 研究代码 | 方法参考 |
| Segment Anything（SAM）类交互分割 | 点击提示分割 | 成熟模型 | 原设计提到但未实现；可用于"人工点一下 → 得到面"的半自动模式 |

[UNKNOWN] 上述研究项目在中国 1:5 万 / 1:20 万地质图上的效果，需要用本项目数据实测。

## 3. 三条路线比较

成本以"人月"为相对量级，假设：1–2 名熟悉 Python/GIS 的开发人员，加 1 名能做标注和验收的地质人员；不含客户沟通时间。数值只用于比较三条路线，不是工期承诺。

| 维度 | 路线 A：继续维护现有架构 | 路线 B：保留可用模块，替换薄弱环节 | 路线 C：基于成熟生态重新设计 |
|---|---|---|---|
| 内容 | 修 245 个测试、修部署，继续在规则上调界线和矿种 | 保留上传、预处理、图例录入、面要素、复核 UI；配准输出换成 GDAL；界线改为由面拓扑导出 + 人工描线；冻结 ML/MoE；先建评估集 | QGIS 插件或轻量 Web + GDAL/QGIS 后端；面要素用图例颜色分割或 SAM 交互；线和点人工辅助 |
| 技术可行性 | 低：没有证据表明继续加规则能把界线从 0.12 提到可用 | 中高：面要素已有 0.38 mIoU 起点，方法正确；其余为工程集成 | 中高：工具成熟，但识别算法仍需自研或集成 |
| 可复用代码比例 | 约 90%+ | 约 40–60%（INFERRED：上传/预处理/图例/面识别/复核 UI/CRS） | 约 10–20%（算法片段、CRS 规则、图例数据结构） |
| 实现复杂度 | 低（短期），长期递增 | 中 | 中（新技术栈学习成本） |
| 精度或质量上限 | 受手工规则限制，不确定 | 面要素可向文献水平靠近；线和点靠人工保证 | 与 B 相近；用 QGIS 时人工编辑效率更高 |
| 开发维护成本 | 持续高：每张新图都可能出新误检 | 中：核心代码变少 | 前期中，后期低 |
| 主要技术风险 | 继续停滞 | 面要素在更多图幅上达不到要求；现有代码耦合使拆分困难 | 团队对 QGIS/PyQGIS 不熟；丢失已打磨的 Web 交互 |
| 可验证性 | 低（无数据） | 高（先建评估集，每个阶段有门槛） | 高 |
| 推荐程度 | 不推荐 | **推荐** | 备选（当 B 在 M1 不通过时，或客户本来就用 QGIS/ArcGIS） |

**是否已陷入路线锁定或补丁式开发？** 是。[INFERRED，证据见 02 文档 4.1 与 03 文档树 1] 地质界线模块 6 个月内约 20 轮修补没有任何客观指标改进的记录；修补引入了相互绕过的规则路径；测试失效后仍继续开发。这是典型的补丁式开发困境。路线锁定主要发生在"线要素必须全自动提取"这一隐含假设上，而不是技术栈上，所以路线 B 不需要更换技术栈。

## 4. 哪些需要自主研发

| 类别 | 内容 |
|---|---|
| 1. 直接使用成熟软件 | GCP 变换与重采样（GDAL）、坐标系转换（PROJ）、几何与拓扑（GEOS）、格式输出（OGR：GeoJSON、Shapefile、GeoPackage）、大图分块读取（Rasterio）、OCR 引擎（PaddleOCR） |
| 2. 工程集成与少量适配 | 中国坐标系候选推断（已有）、图例录入表单与数据模型、面要素多边形化与拓扑清理、面公共边转界线、像素坐标到地理坐标的统一转换层、复核编辑 UI |
| 3. 必须自行开发算法 | 按图例颜色切分面要素在中国图式上的参数与后处理；矿种符号模板匹配；独立线要素（断层）的半自动追踪（吸附、跟随） |
| 4. 目前无法稳定全自动 | 全图独立线要素自动提取与分类、点符号全自动识别、等高线高程关联、无图例情况下的识别。这些应设计为"系统给候选，人工确认"，并按人工修正工作量衡量 |

## 来源

- [AI for Critical Mineral Assessment Competition（DARPA）](https://criticalminerals.darpa.mil/The-Competition)
- [The Map Feature Extraction Challenge 说明（DARPA PDF）](https://criticalminerals.darpa.mil/Files/Map_Feature_Extraction_Challenge_Details.pdf)
- [Extracting data from maps: Lessons learned from the AI4CMA competition（USGS）](https://www.usgs.gov/publications/extracting-data-maps-lessons-learned-artificial-intelligence-critical-mineral)
- [Accurate Feature Extraction from Historical Geologic Maps Using Open-Set Segmentation and Detection（MDPI Geosciences）](https://www.mdpi.com/2076-3263/14/11/305)
- [Training and validation data from the AI4CMA Competition ver. 2.0（USGS）](https://www.usgs.gov/data/training-and-validation-data-ai-critical-mineral-assessment-competition)
- [Automated georeferencing and feature extraction of geologic maps and mineral sites（USGS）](https://www.usgs.gov/publications/automated-georeferencing-and-feature-extraction-geologic-maps-and-mineral-sites)
- [DARPA-CRITICALMAAS/uncharted-ta1（GitHub）](https://github.com/DARPA-CRITICALMAAS/uncharted-ta1)
- [Fandel-Lin/LOAM（GitHub）](https://github.com/Fandel-Lin/LOAM)
- [DARPA-CRITICALMAAS/ta1-geopackage（GitHub）](https://github.com/DARPA-CRITICALMAAS/ta1-geopackage)
- [priyammaz/DARPAMapExtraction（GitHub）](https://github.com/priyammaz/DARPAMapExtraction)
- [gdalwarp 文档（GDAL）](https://gdal.org/en/stable/programs/gdalwarp.html)
- [QGIS Georeferencer 文档](https://docs.qgis.org/testing/en/docs/user_manual/working_with_raster/georeferencer.html)
