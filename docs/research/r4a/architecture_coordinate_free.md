# Scan2ArcGIS 无坐标识别架构（R4-A，2026-10-28）

**目标：** 输入一张普通地质图像，输出可编辑的地质面、地质界线和地层属性。
**核心约束：** 识别和矢量化**不依赖**经纬度、投影坐标系、图廓、格网、官方 GIS 矢量或人工控制点。

## 1. 三个独立层次

| 层 | 输入 | 输出 | 坐标 |
|---|---|---|---|
| A. 视觉识别 | RGB 图像 | 区域分割（每个像素一个区域或类别）、边界概率、接触线和断层候选、图例和代号 OCR、不确定性 | 图像像素（行、列） |
| B. 矢量拓扑重建 | A 的输出 | Polygon / MultiPolygon、LineString、属性表（实例 ID、代号、候选代号、置信度、复核状态） | 图像像素坐标系（见第 2 节） |
| C. 可选地理配准 | B 的输出 + 可靠的坐标参考 | 投影到真实坐标系的矢量 | 真实 CRS |

- **A 和 B 必须能独立运行。** 没有可靠坐标参考时，C 不运行，输出保持在像素坐标系，**不猜测、不伪造 CRS**。
- **C 本轮不开发。** B 的输出保留原图尺寸和像素坐标约定，以后有控制点时可以直接接上 C。
- **训练和评价可以借助 GIS 数据生成标签**（例如 GSJ 官方矢量配合 GeoTIFF），但这只发生在离线的标签生成阶段，不进入 A、B 的预测流程。

## 2. 像素坐标约定（B 层输出）

| 项目 | 约定 |
|---|---|
| 原点 | 原图左上角像素的**左上角**为 (0, 0) |
| X | `X = 列坐标`，向右增大，单位为像素 |
| Y | `Y = −行坐标`，向上增大，单位为像素。图像在 GIS 中位于 Y ≤ 0 的区域，方向是正的 |
| 像素中心 | 第 r 行、第 c 列像素的中心位于 `(c + 0.5, −(r + 0.5))` |
| 像素边界 | 多边形由像素边界构成，顶点落在整数坐标上（栅格转矢量时不做半像素偏移） |
| 仿射变换 | 像素到 GIS 坐标：`X = 0 + 1·c`，`Y = 0 − 1·r`，即 GDAL GeoTransform `(0, 1, 0, 0, 0, −1)` |
| 工作尺度 | 识别在缩放后的图上进行时（例如 R1 的 0.5 倍），几何先换回**原图像素**再输出，缩放系数记入元数据 |
| CRS | **不写**。GeoPackage 的几何列使用"未定义"坐标系；Shapefile 不写 `.prj` |

- **不能用 GeoJSON 作为主格式：** RFC 7946 规定 GeoJSON 坐标必须是 WGS84，GIS 软件会把像素坐标当成经纬度。
- **叠加原图：** 同时输出原图的 world file（`.wld`，内容为 `1 0 0 -1 0.5 -0.5`，即左上角像素中心的坐标）。QGIS 读取后，原图和矢量会自然对齐。

## 3. B 层输出格式

- **主格式：** GeoPackage（`.gpkg`），图层：
  - `geologic_units`：Polygon / MultiPolygon，字段：`unit_id`、`class_id`、`code`、`code_candidates`、`area_px`、`confidence`、`review_status`、`source`
  - `contacts`：LineString，字段：`line_id`、`left_unit`、`right_unit`、`kind`（contact / fault_candidate / unknown）、`length_px`、`review_status`、`source`
  - `metadata`：键值表，记录原图文件名、原图尺寸、SHA-256、工作尺度、坐标约定、生成程序和版本
- **兼容格式：** Shapefile（`geologic_units.shp`、`contacts.shp`）。字段名截断到 10 个字符；不写 `.prj`；附带同名 `.txt` 说明坐标约定。
- **复核状态 `review_status`：** `CONFIRMED` / `LOW_CONFIDENCE` / `REVIEW`。分数一律是 `UNCALIBRATED`，不作为概率。

## 4. 数据和许可边界

- **许可状态：** 见 `licence_audit.md`：`INTERNAL_RESEARCH_APPROVED_BY_PROJECT_OWNER / THIRD_PARTY_LICENSE_UNCONFIRMED`。
- **只放本地：** GSJ 原图、官方矢量、由它们生成的标签、矢量成果和叠加图，以及用它们训练的权重。
- **公开示例：** 用合成图生成（`src/scan2arcgis/synth`），可以提交。

## 5. 与以往阶段的关系

- **R1：** 提供 A 层的颜色分类和面边界，以及 B 层的 `polygons_from_labels`。
- **R3-S1：** 提供代号 OCR 和语义赋值，对应 A 层的属性部分。
- **R2/R4 的配准工作：** 只服务于离线标签生成。产品流程不再依赖它；有关图廓的配准研发在 R4-A 停止。
