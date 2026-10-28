# 开源项目源码调研：地质图扫描件矢量化（2026-10-28）

基线：`docs/research/r2_real_map/gsj_r1_baseline.md`（GSJ 08004/08001，rf_selftrain mIoU 0.454/0.361，接触线 R 0.59/0.55、P 0.33/0.30）。
本文只做源码阅读，没有安装或运行任何项目。代码克隆在 `/tmp`，没有进入仓库。

标注约定：**[源码]** = 在下表 SHA 的源码里读到；**[README]** = 只在 README / 文档 / metadata 里看到，没有核对实现；**[推断]** = 我们的判断。

## 0. 研究对象与版本

| # | 项目 | 研究的 commit | 许可证（LICENSE 文件） | 语言 / 形态 |
|---|---|---|---|---|
| 1 | MapReader | `13534ca04767e332b530437809b1ecdc40ad347f` | MIT（`LICENSE`） | Python 库 + Jupyter |
| 2 | Geology from points and lines (G4PL) | `3d33d8b2a6d55f3a71fe33307c77d30af6c377d6` | GPL-3.0（`LICENSE`） | QGIS Processing 插件 |
| 3 | AutoTracer | `7c13596d08ed21c21ae670d50ca0dfbb6620decb` | **仓库里没有 LICENSE 文件** | QGIS 插件 |
| 4 | Raster Vectorizer | `74321c31fe649df82de6090c6f9dc6379402c7d6` | GPL-2.0（`raster_vectorizer/LICENSE`，README 写 or-later） | QGIS 插件 |
| 5 | Allmaps | `fd64fa55216dcaa3eada0a47184ba6fdf921a761` | 按包分别声明：MIT / AGPL-3.0-only / GPL-3.0-or-later | TypeScript monorepo |
| 6 | Map Warper | `1d56d8ea681a30bbde89033b4abab7a0ebf462ad` | MIT（`LICENSE`） | Ruby on Rails 网站 |

六个 URL 都能访问，项目也和描述一致。都是 `--depth 1` 浅克隆，SHA 取自 `.git/shallow`。
来源博文（四川德格 1:20 万）只做了配准和切片，没有矢量化，这里不展开。

## 1. MapReader

**定位 [源码]**：把大幅历史地图切成 patch，再用人工标注训练 **patch 级** 分类器（例如“这个 100 px 块里有没有铁路”）。另有一个独立的 text spotting 模块。它不产出面、线拓扑或地层属性。

| 能力 | 可复用模块（path:line） | 说明 |
|---|---|---|
| 切片 | `mapreader/load/images.py:1205` `MapImages.patchify_all`；`:1325` `_patchify_by_pixel`（overlap 在 `:1380` 附近按 `patch_size*overlap` 计算）；`:2591` `save_patches_to_geojson` | 按像素或米切块，支持重叠，并保留 patch 到 parent 的坐标关系和 GeoTIFF / GeoJSON 输出。功能普通，我们用 numpy 切片 20 行就能写出来。 |
| OCR | `mapreader/spot_text/runner_base.py:24` `DetRunner`、`:894` `DetRecRunner`；`:262` / `:370` 按 IoA 去重；`:296` `convert_to_parent_pixel_bounds`；`:434` `convert_to_coords`。引擎是 `maptext_runner.py:26` MapTextPipeline（默认权重 `rumsey-finetune.pth`，`:33`）、`deepsolo_runner.py:26` DeepSolo、`dptext_detr_runner.py:28` DPText-DETR（只检测、不识别） | 有价值的是 **patch 预测合并回整图并去重** 这层（`runner_base.py:262-434`），与模型无关。识别模型依赖 detectron2（`text-requirements.txt` 从 git 安装）。 |
| 线矢量化 / 骨架化 | 无 | — |
| 拓扑重建 | 无 | — |
| 图例 / 地层属性关联 | 无。`classify/classifier.py:29` `ClassifierContainer` 是 torchvision patch 分类；`process/context_post_process.py:15` 用 3×3 邻域 patch 修正低置信预测（`:88-218`） | 邻域修正是 patch 级的，粒度对我们太粗。 |

- **对地质图的适配度 [推断]**：差。patch 级分类无法给出 1–3 px 精度的接触线，而我们 34–42% 的错误就在边界带。MapTextPipeline 在 David Rumsey 英文历史地图上微调 [README/文档 `6-spot-text.rst:10`]。GSJ 单元代号是拉丁字母加下标、字号小、压在彩色底上，能识别多少**未验证**。
- **人工 vs 自动 [源码]**：patch 分类必须人工标注（`annotate/annotator.py`，基于 ipyannotate 的 Jupyter 小部件），然后训练。text spotting 不需要训练，但要手动下载 config 和权重（`6-spot-text.rst:44-55`）。
- **集成可行性 [源码 `setup.py:29-67`]**：`python_requires>=3.9`。`numpy>=1.21.5,<3` 与 1.24.3 兼容；`geopandas>=1.0`、`shapely>=2` 也兼容。
  - **冲突一**：依赖 `opencv-python>=4.8.1.78`。它和我们的 `opencv-contrib-python` 都安装 `cv2` 模块，同装会互相覆盖 [推断，pip 的常见问题]。
  - **冲突二**：强制安装 torch / torchvision / jupyter / tensorboard / cartopy / azure-storage-blob 等，依赖面很重。
  - OCR 还要编译 detectron2（macOS 上没有官方 wheel）。
  - 可以作为库调用，不是 GUI。
- **商用**：代码 MIT，无 copyleft。**模型权重的许可证没有在本仓库声明**，需要到 MapTextPipeline / DeepSolo / DPText-DETR 各自的仓库核对（未核对，**未验证**）。detectron2 本身是 Apache-2.0 [推断，未在本次源码中读到]。
- **值得验证的方法**：只有一个。拿 MapTextPipeline 在 GSJ 图面上做代号检测加识别，用官方 `geo_A` 单元代号做真值，量出检出率和识别率。这能回答“图面代号 OCR 能否作为一路证据”。但它代价高（torch + detectron2），不作为下一步实验。切片和 patch 分类相对我们**没有新东西**。

## 2. Geology from points and lines（G4PL）

**定位 [源码]**：输入是**人工已经数字化好的**接触线图层，加上**人工放置的**带岩性 / 时代属性的点。插件把线多边形化，再按空间关系把点属性连接到面上。它不处理栅格。

| 能力 | 模块（`G4PL_algorithm.py`） |
|---|---|
| 主流程 | `:555` `processAlgorithm`，一共 9 步 |
| 线→面 | `:958` `_polygonize_lines`，调用 `native:polygonize`（`:981`） |
| 属性关联 | `:1021` `_join_attributes_to_polygons`，调用 `native:joinattributesbylocation`（`:1057`），参数 `DISCARD_NONMATCHING=True`、one-to-many；`:1261` `_validate_attribute_join` 只检查“有没有面拿到属性” |
| 面→接触线 | `:1065` polygons→lines、`:1095` 去重复节点（用户给 tolerance）、`:1129` 打散、`:1159` 去重复线段、`:1191` 按属性 dissolve、`:1225` 多部件转单部件 |
| 切片 / OCR / 骨架化 | 无 |

- **对地质图的适配度**：它解决的是“线已经闭合、点已经给出”之后的拓扑和属性问题。断线、虚线、文字切断线这些问题它都不处理。`native:polygonize` 遇到不闭合的线，相邻单元会直接连成一个面 [推断，这是 polygonize 的标准行为]。不落在任何面里的点会被丢弃。一个面里有多个点时，one-to-many 连接会把这个面**复制成多个要素** [源码参数 + 推断]。
- **人工 vs 自动**：线、点、属性字段、容差、空间谓词都由用户在 QGIS 对话框里给出（`:365` `initAlgorithm`）。真正自动化的只有 GIS 拼装这几步。
- **集成**：要求 QGIS ≥3.16 / PyQGIS（metadata），不能脱离 QGIS 当库用。不过整个逻辑等价于 `shapely.polygonize_full` + `geopandas.sjoin` + `unary_union`，十几行就能重写，不需要依赖它。
- **商用**：GPL-3.0。直接复制代码会让衍生作品受 GPL 约束。只借用思路（polygonize + 点属性连接是标准 GIS 操作）不受影响。
- **相对我们是否新**：**不新**。`vector/polygonize.py` 已经从标签栅格得到面，并把接触线取为共享边，拓扑本来就由构造保证。G4PL 的意义在于给出了架构 A 的末端形态，即“线网 → 面 → 用点（例如图面代号 OCR 的位置）赋属性”。它说明架构 A 的末端可以很简单，难点全在前端能不能得到闭合线网。

## 3. AutoTracer

**定位 [源码]**：对整幅栅格依次做灰度化、Otsu / 自适应 / 手动阈值、中值或高斯平滑、`skimage.skeletonize`、像素图追踪成折线，最后做 Douglas-Peucker 简化，输出 QGIS 内存线图层。

| 能力 | 模块（`processing.py`） |
|---|---|
| 二值化 | `:21` `binarize`（Otsu / adaptive blockSize=15, C=5 / 手动），**只看灰度** |
| 平滑 | `:70` `smooth` |
| 骨架化 | `:100` `skeletonize_image`（skimage） |
| 线矢量化（图结构） | `:125` `vectorize`：度数不等于 2 的像素作为节点，度数等于 2 的像素作为链。用 `visited_edges` 保证每条分支只走一次，节点像素可以被多条分支共享（`:162-210`），然后 `cv2.approxPolyDP`（`:219`） |
| 管线 | `:235` `run_pipeline` |
| 切片 / OCR / 拓扑成面 / 属性 | 无。`dialog.py:427-476` 用 GDAL 读波段，按地理变换转坐标后写入内存图层 |

- **对地质图的适配度 [推断]**：只用全局灰度阈值。在彩色地质图上，深色单元、花纹、文字、图廓、等高线和接触线会一起进入前景，它没有颜色或线型区分，也没有断线连接和闭合处理，所以不能直接用于地质图。我们 `recog/lines.py:22` `fault_candidates` 已经用 blackhat 加色度门限（chroma<25）挑近黑墨线，比它更有针对性。
- **人工 vs 自动**：阈值方法、阈值、核大小、DP epsilon、最短长度都靠用户在对话框里调。处理本身全自动。
- **集成**：`processing.py` 只 import numpy / cv2 / skimage，不依赖 QGIS，技术上可以直接调用。纯 Python 的像素集合遍历在 6000×4300 的图上会很慢 [推断]。与 numpy 1.24.3 / opencv 4.10 无冲突。
- **商用**：**仓库和 `AutoTracer.zip` 里都没有 LICENSE 文件。按默认版权规则，等于未授权（all rights reserved），不能复制代码。** metadata 和 README 里也没有许可证声明 [源码]。
- **值得借鉴的点（只借思路，自己实现）**：`vectorize` 的“节点共享、分支只走一次”图追踪，比我们的 `vector/polygonize.py:63` `trace_skeleton` 正确。后者是贪心单路径遍历，遇到分叉就会丢分支，源码注释里自己也写了“production should use a graph-based tracer (e.g. sknw)”。如果做架构 A/B 的墨线网，应该用这种图追踪，或者用许可证明确的 `sknw` / `skan`（许可证待核对）。除此之外**没有新方法**。

## 4–6. 简述

**4. Raster Vectorizer（GPL-2.0）[源码]**：一个 QGIS 插件，面向扫描地形图。用户交互取色，形成 HSV 颜色范围（`classifier.py:26` `ColorClass`、`:186` `RasterClassifier`），按范围分类并做形态学后处理，最后调用 `gdal.Polygonize`（`vectorizer.py:117`）。它和我们 R1 的 nearest_color 加 `rasterio.features.shapes` 是同一类方法，而且更弱：要人工取色、没有学习、没有自训练。**没有新东西**，GPL 也不宜复制。

**5. Allmaps（按包混合许可）[源码 package.json]**：基于 IIIF 的地图配准、浏览和叠加平台（TypeScript）。25 个库包是 MIT，例如 `transform`、`render`、`iiif-parser`、`annotation`、`openlayers` / `leaflet` / `maplibre` 插件。应用和 API 是 AGPL-3.0-only 或 GPL-3.0-or-later：`apps/editor|viewer|tiles|here|latest|explore`、`apis/*`、`packages/api-shared|db`。与识别无关。将来做“原图与矢量结果叠加浏览”时，MIT 的 `render` / `maplibre` 插件和 Georeference Annotation 格式可以复用，但要避开 AGPL 的 apps / apis。

**6. Map Warper（MIT）[源码]**：Rails 网站。用户手工打 GCP，后台调用 GDAL `gdal_translate` / `gdalwarp` 纠正（`app/models/map.rb:691`、`:709`），并提供 WMS / XYZ 切片服务（`config/routes.rb:86-91`）。只做配准、切片和浏览，没有矢量化。将来可作为瓦片服务的参考，但 Ruby 技术栈和我们不符。

## 7. 汇总

| 能力 | MapReader | G4PL | AutoTracer | 我们已有 |
|---|---|---|---|---|
| 切片 | 有（MIT，普通） | — | — | 整图处理，暂时不需要 |
| OCR | MapTextPipeline / DeepSolo（torch + detectron2，权重许可未核） | — | — | tesseract 读图例代号（可选） |
| 骨架 + 线追踪 | — | — | 图追踪（无许可证，只借思路） | `trace_skeleton` 贪心（有缺陷） |
| 线→面拓扑 | — | `native:polygonize`（GPL，标准操作） | — | 标签→面，共享边当接触线 |
| 属性关联 | — | 点→面空间连接（需人工点） | — | 图例 RF + 评价用匈牙利上限 |
| 无需 QGIS / GUI | 是 | 否 | `processing.py` 是 | — |
| 商用可直接复制代码 | 是（MIT） | 否（GPL-3.0） | 否（无许可证） | — |

这三个项目都没有针对“近色单元、花纹、细黑接触线、断层”的地质图识别方法，可直接复用的识别能力为零。实际可借鉴的只有三点：MapTextPipeline 可作为图面代号 OCR 的候选引擎；G4PL 说明了线网→面→点属性这条末端流程；AutoTracer 示范了正确的骨架图追踪。

## 8. 架构对比

- **A**：先独立检测地质线，再重建拓扑成面，最后给面分类。
- **B**：保留现有面分类，另外独立检测墨线，再做线面融合和冲突修复。

下表的“已测”指 R2 基线里实测过的数字，其余为推断。

| 问题（R2 已测量级） | A 的表现 | B 的表现 |
|---|---|---|
| 近色（24/42 单元 ΔE<10，占错误约 21–23%） | 线网只要闭合，面就由线决定，不再依赖颜色分界。但如果接触线是颜色变化本身、没有印刷墨线，线检测也会漏掉 | 墨线可以把两个近色单元强行分开。没有墨线的地方，结果维持 R1 现状 |
| 花纹（IoU 约 0.30） | 花纹线条和接触线同为细线，会大量误检成线网碎片，形成**过分割** | 花纹区内部的墨线如果当作边界，也会碎片化。但 B 可以要求“墨线两侧标签不同”才采纳，不至于一碎到底 |
| 小单元（IoU≥0.5 只有 2–4/16、1–3/18） | 小单元往往被线完整包围，A 在这里有潜在优势，前提是线网闭合 | 只能把墨线围出的小区域从周围大类中切出来，类别仍然靠颜色判定 |
| 断线、虚线 | **致命**。一处缺口就会让 polygonize 把相邻单元合并（G4PL 的流程就默认线已闭合） | 不致命。断线处由面分类兜底 |
| 文字压线（墨线 / 文字下方错误占 6–11%） | 文字笔画会生成伪线和伪闭合面，必须先做文字检测和掩膜 | 文字区域可以按“不像长线”过滤掉（`lines.py` 已有长度和伸长度过滤） |
| 不构成单元边界的断层 | 断层会把同一单元切成两个面，需要再按标签合并 | 天然适配：墨线两侧同标签就保留为断层，不改面。现有 `fault_candidates` 就是这个逻辑 |
| 需要的证据 | 高召回、可闭合的接触线（目前接触线 P 只有 0.30）、文字掩膜、面属性（颜色 + OCR 代号点） | 现有 R1 标签 + 近黑墨线骨架图 + 融合规则 |
| 拓扑来源 | polygonize，线网闭合时拓扑天然正确 | 标签栅格→面，与现在一样，构造上保证正确 |
| 风险 | 高。整条流程的上限受线检测闭合率限制，需要从头重做 | 低。增量改动、可以消融，最差退回 R1 |

**建议做 B 作为下一步实验。** 理由有三点：

1. 边界带和近色两类合计约占错误的 55–65%。墨线正好是两者共同缺失的那路证据。
2. A 对断线零容忍，而 GSJ 图上接触线有大量虚线和推定线（R1 的线 P≈0.3 说明线证据本身很嘈杂），这一点**未量化，需要先统计**。
3. B 的结果可以直接用现有 `evaluate()` 与 R1 做逐项对比。

A 并没有被否定。等 B 证明墨线证据有效，并且量出墨线闭合率之后，再评估 A。

## 9. 一个最小对照实验（未运行）

**E1：墨线屏障下的区域多数投票。** 这是 B 的最小形态，只改后处理。

- **输入**：
  - `runs/r2_gsj/{08004,08001}/r1/pred_legend_rf_selftrain.npy`（R1 输出，不改动）；
  - 同一张 100 dpi 工作尺度图像；
  - GT 与 `map_mask` 沿用 `experiments/R2_real_map/` 的产物。
- **改动**：
  1. 用 `lines.py:22` 里的同一套近黑墨线掩膜（blackhat + chroma<25）得到墨线像素，不做按长度的断层过滤。
  2. 骨架化后，用 AutoTracer 式的图追踪（自己实现，或用许可证核实后的 sknw / skan）去掉长度小于 L 的分支，用来去掉文字和点状符号。
  3. 把骨架膨胀 1 px 作为屏障，对非屏障像素求连通域。每个连通域内取 rf_selftrain 标签的多数票作为整块标签。面积小于 A_min 的连通域保持原标签。
  4. 屏障像素本身取最近非屏障像素的标签。
- **对照组**：
  - E0：R1 rf_selftrain 原样。
  - E1：墨线屏障投票。
  - E1-ctrl：用 SLIC 超像素代替墨线连通域，块数与 E1 相近。这一组用来区分“墨线证据”和“单纯区域平滑”各自的贡献。
- **指标**：
  - 主指标：`gsj_run_r1.py:49` `evaluate()` 的全部输出（mIoU、小单元 IoU≥0.5、接触线 R/P、连通块数）。
  - 附加指标：用 `gsj_error_analysis.py` 的分类，看“近色”和“边界带”两类错误像素的变化。
- **判据**：
  - E1 相对 E0 和 E1-ctrl，近色错误下降，接触线 P 提高，且 mIoU 不下降，才说明墨线证据有效。
  - 如果 E1 ≈ E1-ctrl，说明增益只是平滑带来的，B 方向要重新考虑。
  - 同时记录墨线骨架覆盖官方接触线的召回率（容差 1.5 px）。这个数直接给出 A 的可行性上限。
- **参数**：L、A_min 只能在 08004 上调，08001 只用来报告结果。

## 10. 产品待办（未排期）

以下能力只做登记，**当前不分配开发资源**：

| 能力 | 说明 | 将来可参考 |
|---|---|---|
| 地图瓦片浏览 | 原始扫描图配准后按 XYZ / WMS 切片浏览 | Map Warper（MIT，GDAL + 瓦片路由）、Allmaps `apps/tiles`（AGPL，只看思路） |
| 原图与矢量结果叠加 | 在原扫描图上叠加识别出的面和线，支持透明度切换 | Allmaps MIT 包（`render`、`maplibre` / `openlayers` / `leaflet` 插件、Georeference Annotation） |
| 错误区域定位与复核登记 | 自动标出低置信或冲突区域，供人工复核和登记 | MapReader 的 patch 网格、`save_patches_to_geojson`、`context_post_process` 可借鉴为复核单元格的组织方式；`annotate/annotator.py` 可借鉴为 Jupyter 内的复核交互（MIT） |
