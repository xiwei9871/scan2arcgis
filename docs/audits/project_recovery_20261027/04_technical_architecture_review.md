# 04 架构、算法与工程质量审计

严重程度：P0 阻止核心业务目标；P1 严重影响正确性/可靠性/交付；P2 影响效率/质量/可维护性；P3 一般优化。
复现命令默认在仓库根目录、commit `33e5f7b` 上执行，环境见 `evidence/environment.md`。

## 1. 端到端处理步骤（可独立验证的单元）

| # | 步骤 | 输入 | 输出 | 正确性如何检验 | 当前能否独立验证 |
|---|---|---|---|---|---|
| S1 | 上传与任务创建 | JPG/PNG | task_id、原图副本 | 文件哈希一致 | 能 |
| S2 | 图廓裁剪 | 原图 | 内/外图廓图 + 四角像素坐标 | 四角与人工标注的像素误差 | 部分（无四角真值集） |
| S3 | 角点坐标获取 | 图廓条带 | 四角经纬度/投影坐标 | 与图面注记人工读数一致 | 部分（OCR 测试 7 项失败） |
| S4 | 配准求解 | GCP | 变换参数 + RMS | 留一法检查点误差（不是拟合 RMS） | 能（数学部分） |
| S5 | 栅格地理参考输出 | 图 + GCP | GeoTIFF | 在 QGIS 中与已知底图叠加 | 不能（GDAL 仅 Windows） |
| S6 | 图例录入 | 图例区 | 图例字典（代号、颜色、符号裁片） | 与人工录入对比 | 能（主要靠人工） |
| S7 | 面要素（地层/侵入岩） | 内图廓图 + 图例 | 带代号的多边形 | 全幅 mIoU、图例绑定准确率 | 能，但数据只有 2 张图 |
| S8 | 线要素（界线/断层） | 同上 | 带类型的折线 | 缓冲区 F1、拓扑闭合率 | 能，但标注只有 5 条线 |
| S9 | 点要素（矿种） | 同上 + 符号裁片 | 带矿种的点 | 点 F1（距离容差） | 部分（只有裁片级用例） |
| S10 | 人工复核 | 识别结果 | 编辑记录 | 人工修正耗时 | 不能（无计时记录） |
| S11 | 像素→地理坐标变换 | 矢量 + 配准参数 | 地理坐标矢量 | 已知点位误差 | 未见专门测试 |
| S12 | 导出 | 地理矢量 | GeoJSON / Shapefile | 能被 QGIS/ArcGIS 打开，CRS 正确，属性完整 | 未验证 [UNKNOWN] |

**关键发现**：S5、S11、S12 是"转成 GIS 可读格式"这一核心业务目标的最后一公里，但仓库中没有任何一个测试或报告证明导出的文件放入 GIS 后位置正确。

## 2. 模块审计

### 2.1 地理配准（`backend/core/registration`）

- 设计：自研 affine、二阶多项式、TPS 求解与 RMS（`transform/affine.py`、`polynomial.py`、`tps.py`），GDAL 只用于写带 GCP 的 GeoTIFF（`gdal/warp.py`）。
- 评价：数学实现本身简单正确的概率较高 [INFERRED]，但 GDAL（`gdal_translate -gcp` + `gdalwarp -order/-tps`）和 QGIS Georeferencer 已经提供同样的变换和残差报告。自研求解器与 GDAL 实际重采样使用的变换可能不一致，RMS 显示值与最终栅格可能不对应 [HYPOTHESIS]。
- 问题：
  - **P1** 用拟合 RMS 作为质量指标。TPS 在控制点上残差恒为 0，拟合 RMS 不能反映真实误差，应使用独立检查点。复现：读 `transform/tps.py:compute_tps_rms`。
  - **P1** 角点坐标 OCR 测试 7 项失败（`OCRRegion.region_id` → `region_key`），配准提交测试 1 项失败（`AppliedCandidateContext` 校验）。复现：`pytest backend/tests/registration`。
  - **P2** 四角检测（`detection/frame_corners.py` 1,257 行）为大量启发式规则，嵌套双图廓、角格法等只针对已见样图调过 [INFERRED]。
- 结论：**可保留**交互标注 UI 和 CRS 候选逻辑；变换与输出应直接交给 GDAL。

### 2.2 面要素识别（`stratigraphy/`、`intrusive_rock/`）

- 设计：KMeans 颜色聚类 → 像素分类 → 实例分区 → 多边形 → 按图例颜色绑定。
- 评价：方法合理，是同类问题中最容易做的部分。公开研究中按图例提示的面要素中位 F1 约 0.77–0.91（见 05 文档）。
- 问题：
  - **P1** 评估集只有 2 张图、7 个多边形，mIoU 0.38 的统计意义很弱。
  - **P2** 6 月后的大量改动（`7aad0c1` 图例颜色约束等）没有指标验证。
- 结论：**值得保留并作为 MVP 的核心**。

### 2.3 地质界线 / 地质构造（`boundary/`、`geologic_structure/`）

- 设计：候选图（颜色/墨迹）→ 骨架追踪 → 清洗（端点吸附、悬挂枝裁剪）→ 分类（线型、齿状装饰、图例匹配），另有"面公共边导出线"路径。
- 问题：
  - **P0** 质量没有达到可用的证据：缓冲区 F1 0.12。即使只算地层面之间的公共边，也可以从面要素的结果直接导出，独立线提取的增量价值未经证明。
  - **P1** 1,410 个浮点字面量，规则路径相互绕过（`33e5f7b` 提交信息第 1 项），任何修改都可能在其他图上退化，无数据可测。
  - **P1** 原图/分析图坐标换算曾多次出错（`4f7893e`、`d5d771a`），说明多分辨率坐标管理没有统一抽象。
  - **P2** 5 个界线测试失败（`KeyError: 'boundary_name'` 等）。
- 结论：**停止在当前方式上继续投入**。接触界线应由面要素拓扑导出；断层等独立线要素应改为"人工描线 + 吸附辅助"或在有数据后再研究。

### 2.4 矿种点符号（`commodity/`）

- 设计：以图例裁片为模板，整图颜色搜索 + 外形/内部图案/颜色三门判定；ML 视觉特征参与打分。
- 评价：图例驱动的模板匹配方向正确；公开结果点要素 F1 约 0.35–0.73，属于难任务。
- 问题：
  - **P1** 161 个测试中 91 个失败，主要是 `CommodityVariantProfile` 不接受 `symbol_shape_id`（字段已改名）。复现：`pytest backend/tests/commodity`。
  - **P2** `runtime.py` 4,903 行，有总时长预算（120 秒）与超时部分结果机制，说明全图扫描很慢。
- 结论：保留模板思路，但应限制为"候选 + 人工确认"，不追求自动全检。

### 2.5 等高线（`contour/`）

- 已停用。**P3**（若业务确认不需要）。建议从活跃代码中移出，避免 `RecognitionPipeline.contour_pipeline` 类残留引起 15 个测试失败。

### 2.6 ML 样本库 / MoE（`core/ml`、`core/moe`）

- 设计：样本库 → 数据集快照 → 训练任务 → 模型版本 → 发布/回滚；MoE 专家注册、路由、影子运行、晋级。
- 问题：
  - **P1** 约 1 万行后端代码 + 前端整页，但没有任何一个模型被证明比基线更好；MoE 只有影子运行，"不改变生产结果"。
  - **P1** `core/ml/atomic_store.py` 无条件 `import msvcrt`，Linux/Docker 下整个识别 API 无法导入。复现：在 Linux 执行 `python -c "import sys; sys.path.insert(0,'backend'); import core.ml.atomic_store"`。
  - **P2** 影子运行 JSON 曾入库（约 1.5 GB 历史），仓库克隆变慢。
- 结论：**冻结**。保留样本数据格式（人工确认的正/负样本有价值），停止平台功能开发。

### 2.7 API 与持久化

- **P2** `api/routes/recognition.py` 15,158 行 / 354 个函数，路由层包含业务逻辑，无法单独测试核心算法。
- **P2** 任务状态存于本地 JSON 文件（`task_store.json`），无并发控制（Windows 文件锁是唯一保护），只适合单用户。
- **P3** FastAPI `on_event` 已弃用。

### 2.8 工程与交付

| 问题 | 级别 | 复现 |
|---|---|---|
| 无 CI，245 个测试失败无人发现 | P1 | `bash evidence/run_audit_tests.sh . <python>` |
| 全分辨率端到端测试（19011×20604 原图）在 4 核/4GB 环境中 178 秒未完成 | P1 | `pytest backend/tests/api/test_id_contract_e2e.py::test_real_upload_to_recognition_with_original_resolution_geologic_map` |
| `matplotlib` 未声明 | P2 | 新环境 `pip install -r backend/requirements.txt` 后收集测试 |
| Dockerfile Python 3.12 与 numpy 1.24.3 冲突、`libgdal28` 包名与 slim 基础镜像不匹配（推断） | P1 | `docker compose build`（审计中未执行） |
| GDAL Windows wheel、`.venv/` 入库 | P2 | `git ls-files` |
| README 过期 | P3 | 对照 01 文档第 2 节 |
| 无关文件（`decrypt_to_mp4.py` 等） | P3 | 根目录 |

## 3. 系统性问题（无法通过局部修补解决）

1. **没有评估数据**，任何算法改动都无法判断好坏。这不是代码问题，是数据问题。
2. **线要素靠手工规则**，在未见过的图幅上必然出现新的误检类型；规则越多越难维护。
3. **地理坐标输出链路未验证**，即使识别完美，交付价值也无法确认。
4. **单机 Windows 开发环境**，无法交付给客户或在服务器上运行。
