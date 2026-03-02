# 地质图自动转换工具 - 系统设计文档

**日期**: 2025-03-02
**项目周期**: 1个月MVP
**目标用户**: 地矿地质单位（国企、政府机构、私企等）

---

## 项目概述

将扫描的地质图（PNG/PDF格式）自动转换为GIS软件可读取的格式（Shapefile、GeoJSON等），实现地质图的数字化。

**核心功能**：
- 地理配准（允许人工干预）
- 等高线矢量化
- 地质界线提取
- 地层分区识别

**设计目标**：尽量全自动，允许必要的人工干预（如配准环节）

---

## 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                        Web Frontend                         │
│                    (React + TypeScript)                     │
│  - 图片上传  - 配准交互  - 进度展示  - 结果下载              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      Backend API                            │
│                      (FastAPI)                              │
│  - 任务管理  - 文件处理  - 状态监控  - 结果输出              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   Processing Pipeline                       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │
│  │地理配准  │ │等高线提取│ │地质界线  │ │地层分区  │      │
│  │Geo-Reg   │ │Contour   │ │Boundary  │ │Polygon   │      │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Core Libraries                           │
│  GDAL │ OpenCV │ SAM │ PaddleOCR │ GeoPandas │ Shapely   │
└─────────────────────────────────────────────────────────────┘
```

---

## 技术栈

### 后端
| 技术 | 用途 |
|------|------|
| FastAPI | Web框架，高性能API服务 |
| Python 3.12+ | 主要开发语言 |
| OpenCV | 图像预处理、线条检测 |
| GDAL/Rasterio | 地理配准、坐标转换 |
| SAM (Segment Anything) | 智能图像分割 |
| PaddleOCR | 图例文字识别 |
| GeoPandas | 矢量数据处理 |
| Shapely | 几何操作 |

### 前端
| 技术 | 用途 |
|------|------|
| React 18 | 用户界面框架 |
| TypeScript | 类型安全 |
| Ant Design | UI组件库 |
| Konva.js / Fabric.js | 画布交互（配准标注） |
| Axios | HTTP客户端 |

---

## 核心模块设计

### 1. 地理配准模块 (GeoRegistration)

**功能**：将扫描图的像素坐标转换为地理坐标

**流程**：
1. 用户在Web界面点击图像控制点
2. 输入对应的经纬度或投影坐标
3. 至少需要3-4个控制点
4. 使用GDAL进行多项式变换或TPS变换

**人工交互点**：控制点标注

```python
class GeoRegistration:
    def __init__(self):
        self.gcp_pairs = []  # 地面控制点 (像素坐标 → 地理坐标)

    def add_control_point(self, pixel_xy, geo_xy):
        """用户添加控制点"""
        self.gcp_pairs.append((pixel_xy, geo_xy))

    def transform(self, image, target_crs="EPSG:4326"):
        """执行坐标变换，返回变换后的图像和变换矩阵"""
        pass
```

### 2. 等高线提取模块 (ContourExtractor)

**功能**：提取等高线并矢量化

**方法**：
1. 颜色分割（棕色/橙色等高线）
2. Canny边缘检测
3. 霍夫直线检测 + 曲线拟合
4. 矢量化为LineString

```python
class ContourExtractor:
    def extract(self, image):
        """提取等高线，返回LineString列表"""
        # 1. 颜色分割
        # 2. 边缘检测
        # 3. 线条检测
        return contour_lines
```

### 3. 地层分区识别模块 (StratigraphyExtractor)

**功能**：识别地层区域并生成多边形

**方法**：
1. 颜色聚类 (K-means)
2. SAM辅助分割边界
3. 连通区域分析
4. 多边形矢量化

```python
class StratigraphyExtractor:
    def extract(self, image, legend_info):
        """提取地层分区，返回{color: Polygon}字典"""
        pass
```

### 4. 地质界线提取模块 (BoundaryExtractor)

**功能**：提取地层界线、断层等地质界线

**方法**：
1. 颜色边缘检测
2. SAM分割mask边界
3. 线条连接和简化

```python
class BoundaryExtractor:
    def extract(self, image):
        """提取地质界线，返回LineString列表"""
        pass
```

---

## 数据流程

```
1. 用户上传扫描图 (PNG/PDF)
         │
         ▼
2. 图像预处理 (去噪、增强、旋转校正)
         │
         ▼
3. 地理配准 (用户标注3-4个控制点)
         │
         ▼
4. 并行处理:
   ├─ 等高线提取 (OpenCV边缘检测)
   ├─ 地质界线提取 (SAM分割 + 线条检测)
   └─ 地层分区识别 (颜色聚类 + SAM)
         │
         ▼
5. 结果整合与验证
         │
         ▼
6. 输出Shapefile/GeoJSON
```

---

## 错误处理策略

| 场景 | 处理方式 |
|------|----------|
| 控制点不足 | 提示用户至少添加3个点 |
| 配准误差大 | 显示残差，警告用户 |
| 图像质量差 | 允许用户调整参数阈值 |
| 识别失败 | 降级到传统CV方法 |
| 文件格式不支持 | 返回清晰的错误提示 |

---

## 项目目录结构

```
geological-map-digitizer/
├── backend/
│   ├── api/
│   │   ├── __init__.py
│   │   ├── main.py           # FastAPI入口
│   │   ├── routes/
│   │   │   ├── upload.py
│   │   │   ├── registration.py
│   │   │   └── download.py
│   │   └── websocket.py      # 进度推送
│   ├── core/
│   │   ├── __init__.py
│   │   ├── registration.py   # 地理配准
│   │   ├── contour.py        # 等高线提取
│   │   ├── boundary.py       # 地质界线提取
│   │   ├── stratigraphy.py   # 地层分区识别
│   │   └── preprocessing.py  # 图像预处理
│   ├── models/
│   │   ├── __init__.py
│   │   ├── task.py           # 任务模型
│   │   └── result.py         # 结果模型
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── image.py          # 图像工具
│   │   ├── geo.py            # 地理工具
│   │   └── config.py         # 配置
│   ├── requirements.txt
│   └── README.md
├── frontend/
│   ├── package.json
│   ├── tsconfig.json
│   ├── src/
│   │   ├── components/
│   │   │   ├── Upload.tsx
│   │   │   ├── RegistrationCanvas.tsx
│   │   │   ├── ProgressBar.tsx
│   │   │   └── ResultViewer.tsx
│   │   ├── pages/
│   │   │   ├── Home.tsx
│   │   │   └── Result.tsx
│   │   ├── services/
│   │   │   └── api.ts
│   │   ├── types/
│   │   │   └── index.ts
│   │   ├── App.tsx
│   │   └── main.tsx
│   └── index.html
├── docs/
│   └── plans/
│       └── 2025-03-02-geological-map-digitizer-design.md
└── README.md
```

---

## 输出格式

### Shapefile文件结构
```
output/
├── contours.shp          # 等高线
├── contours.shx
├── contours.prj
├── contours.dbf
├── boundaries.shp        # 地质界线
├── boundaries.shx
├── boundaries.prj
├── boundaries.dbf
├── stratigraphy.shp      # 地层分区
├── stratigraphy.shx
├── stratigraphy.prj
└── stratigraphy.dbf
```

### 属性字段示例
- **等高线**: `elevation` (高程值)
- **地质界线**: `type` (界线类型: 断层/地层界线)
- **地层分区**: `layer_name` (地层名称), `age` (年代), `lithology` (岩性)

---

## 开发里程碑

| 阶段 | 时间 | 内容 |
|------|------|------|
| Week 1 | Day 1-7 | 项目初始化、后端API框架、前端基础界面 |
| Week 2 | Day 8-14 | 地理配准模块、图像预处理 |
| Week 3 | Day 15-21 | 等高线提取、地质界线提取、地层分区识别 |
| Week 4 | Day 22-28 | 整合测试、优化、文档 |

---

## 参考资料

- [PEACE Framework - CVPR 2025](https://github.com/microsoft/PEACE-Geologic-Map)
- [SAM (Segment Anything Model)](https://github.com/facebookresearch/segment-anything)
- [GDAL地理处理库](https://gdal.org/)
- [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR)
- [中国地质调查局 - 数字填图技术](http://www.cgs.gov.cn/)
