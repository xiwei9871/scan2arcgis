# 01 项目真实目标、架构与模块完成度

审计基准：`33e5f7b101ecf275faf72971d3237d741e8ce17f`（dev 分支，2026-10-23）。证据编号见 `evidence_index.md`。
结论标签：VERIFIED / INFERRED / HYPOTHESIS / UNKNOWN。

## 1. 项目真实业务目标

[VERIFIED, E01] 最早的设计文档 `docs/通用/计划/2025-03-02-geological-map-digitizer-design.md` 写明目标：把扫描的地质图（PNG/PDF）转换为 GIS 可读格式（Shapefile、GeoJSON），面向地矿地质单位，"尽量全自动，允许必要的人工干预"，计划周期"1个月MVP"。核心功能为地理配准、等高线矢量化、地质界线提取、地层分区。

[VERIFIED, E02] 当前代码中的实际业务范围已扩展为：上传 → 图片处理（内/外图廓裁剪）→ 地理配准（GCP、RMS、候选 CRS 推断、角点坐标 OCR）→ 图像识别五步（图例录入 → 自主识别 → 一致性检查与补识别 → 结果复核 → 校核重跑）→ 融合 → 导出。识别要素为地层、侵入岩、矿种（点符号）、地质界线、地质构造（断层）。等高线已于 2026-10-15 停用（`docs/图像识别/2026-10-15-等高线停用与五类识别范围收口.md`）。

[VERIFIED, E03] 系统处理的是中国区域地质图类扫描栅格（仓库样图 `docs/地质图1.jpg` 19011×20604 像素、300 dpi；`docs/地质图2.jpg` 8893×5330 像素、300 dpi），坐标体系涉及 CGCS2000、西安80、北京54 及高斯-克吕格 3°/6° 带（`backend/core/registration/crs/candidate_crs.py`）。

## 2. 文档一致性

| 文档 | 声称 | 实际 | 判定 |
|---|---|---|---|
| `README.md` | Celery + Redis 任务队列、Zustand、Fabric.js、导出 KML | 后端无 `import redis`、无 Celery 用法；前端无 zustand / fabric 导入；代码中无 KML | [VERIFIED, E04] README 过期 |
| `README.md` | "pytest -m smoke" 日常检查 | smoke 只覆盖 11/1149 个测试 | [VERIFIED, E05] |
| 设计文档 | 1 个月 MVP，使用 SAM 分割 | 已开发约 8 个月；代码中没有 SAM | [VERIFIED, E01/E04] |
| 设计文档 | 等高线是核心功能 | 2026-10-15 停用 | [VERIFIED, E06] |
| `docs/` 下 30 余份方案文档 | 每份方案对应一轮修改 | 多为单次改动方案，缺少统一需求规格 | [INFERRED] |

没有找到需求规格说明、验收标准或客户签字的范围文档。[UNKNOWN] 真实客户需求是否以书面形式存在。

## 3. 分支与版本

[VERIFIED, E07]
- 共 171 个提交，2 个分支，无标签、无 Release、无 Merge Request、无 Issue、无 CI 流水线（GitLab API 返回均为 0，无 `.gitlab-ci.yml`）。
- `master` 停在 `47d6b55`（2026-03-04），之后所有开发都在 `dev` 上，dev 领先 master 156 个提交。master 不代表任何可交付状态。
- 指定 commit `33e5f7b` 是 `dev` 的祖先，落后 dev HEAD `7aad0c1`（2026-10-25）2 个提交（矿种识别增强和地层图例颜色约束，35 个文件，+3012/−225 行）。
- 全部 171 个提交的作者都是 `Claude <claude@anthropic.com>`。[INFERRED] 项目基本由 AI 编码代理按用户指令生成并提交；提交 `06ff57e` 的标题是一句对话文字（"Two leftover temp scripts of mine are in the tree — let me remove them first…"），支持这一推断。

## 4. 架构与代码规模

[VERIFIED, E08] 统计口径：已跟踪的 .py/.ts/.tsx/.js/.mjs 文件行数。

| 区域 | 文件 | 行数 |
|---|---|---|
| backend/core/recognition | 133 | 38,799 |
| backend/api（路由） | 16 | 19,807 |
| backend/core/ml | 10 | 5,274 |
| backend/core/moe | 19 | 5,263 |
| backend/core/registration | 28 | 5,235 |
| backend/core/export | 5 | 2,786 |
| backend/tests | 114 | 38,474 |
| frontend/src | 165 | 62,363 |

单文件过大：`backend/api/routes/recognition.py` 15,158 行（354 个函数，其中 323 个私有），`backend/core/recognition/pipeline.py` 8,173 行，`frontend/src/components/preprocess/PreprocessPanel.tsx` 10,840 行。路由层承载了大量业务逻辑。

技术栈：FastAPI + OpenCV（contrib）+ Shapely + scikit-learn（KMeans）+ PaddleOCR；React 18 + Ant Design + Konva；本地 JSON 文件持久化（`task_store.json`）。

## 5. 数据链路

```
扫描图(JPG/PNG) → 上传(api/routes/upload) → 预处理/裁剪(core/preprocess, 前端 PreprocessPanel)
 → 地理配准: 四角检测(detection/frame_corners) + 角点坐标OCR(coordinate_ocr) + GCP + RMS(transform/affine|polynomial|tps) + CRS候选(crs/) + GDAL GCP GeoTIFF(gdal/warp)
 → 图例录入(人工框选 + OCR + 字段表单)
 → 自主识别: 地层/侵入岩(颜色聚类+图例颜色约束) / 地质界线(候选图→追踪→清洗→分类) / 地质构造 / 矿种(模板+三门判定)
 → 一致性检查 + 人工补识别(圈选样本)
 → 结果复核编辑(result_edits) → 融合(core/fusion) → 导出 GeoJSON / Shapefile / 栅格
 旁路: ML 样本库/训练/模型发布(core/ml), MoE 专家影子运行(core/moe)
```

## 6. 外部依赖问题

| 问题 | 证据 | 判定 |
|---|---|---|
| `matplotlib` 被 `core/recognition/contour/pipeline.py` 导入，未列入 requirements | 测试收集时报 `No module named 'matplotlib'` | [VERIFIED, E09] |
| `core/ml/atomic_store.py` 无条件 `import msvcrt`（仅 Windows） | Linux 下 42 个测试文件无法导入 | [VERIFIED, E09] |
| Dockerfile 用 Python 3.12、`libgdal28`，requirements 固定 `gdal==3.7.3`、`numpy==1.24.3`（不支持 3.12） | 代码审读 | [INFERRED] Docker 构建不可用，未实际构建 |
| GDAL 依赖靠仓库根目录 46.8 MB 的 Windows wheel | `gdal-3.10.2-cp310-cp310-win_amd64.whl` | [VERIFIED] 仅能在 Windows Python 3.10 上运行 |
| 仓库跟踪了 Windows `.venv/`（147 个文件） | `git ls-files .venv` | [VERIFIED] |

[INFERRED] 实际运行环境只有一台开发者 Windows 机器（`.claude/settings.local.json` 中出现 Windows 本地绝对路径）。

## 7. 测试、CI 与发布

[VERIFIED, E05/E10] 在审计环境中（详见 `evidence/environment.md`）对 `33e5f7b` 运行全部后端测试：**245 failed，884 passed，19 skipped**，另有 1 个全分辨率端到端测试在 178 秒内未完成（被排除单独记录）。dev HEAD `7aad0c1`：245 failed，958 passed，52 skipped。

无 CI、无发布机制、无版本号。`.gitignore` 忽略了 `backend/tests/`、`frontend/tests/`、`reports/`，但这些文件仍被强制加入跟踪，说明测试入库是被动的。前端测试（41 个文件）未在本次审计中运行 [UNKNOWN]。

## 8. 技术债

- TODO/FIXME 仅 2 处（且都是 UI 文案），不能作为技术债少的证据；技术债体现在硬编码阈值：`core/recognition/boundary` 12,061 行代码中有 1,410 个浮点字面量，`commodity` 7,864 行中有 763 个。[VERIFIED, E11]
- Git 历史中包含约 1.5 GB（未压缩）的 MoE 影子运行 JSON（`backend/ml_sidecar/moe/shadow_runs/...`，单个约 48 MB），已于 `4f7893e` 停止跟踪，但仍留在历史中，克隆包 151 MB。[VERIFIED, E12]
- 与项目无关的文件：`decrypt_to_mp4.py`（TS 视频解密拼接脚本）、`task_update_save_toast_test_5s.py`、`backend/_codex_probe.tmp`、`frontend/pw-home-final.png`。[VERIFIED]

## 9. 模块清单

实现状态说明：WORKING 指在真实样图上有可复核的正确输出证据；"能运行"不等于 WORKING。

| 模块 | 设计目标 | 实现状态 | 可运行证据 | 测试覆盖 | 当前问题 |
|---|---|---|---|---|---|
| 上传 / 任务存储 | 上传扫描图、建任务 | WORKING | api 测试通过；`test_real_upload_to_recognition_with_repository_sample_image` 通过（512px 缩略图） | api 67 项，4 项失败 | 本地 JSON 存储，单机 |
| 图片预处理 / 裁剪 | 去噪、内外图廓裁剪 | PARTIAL | preprocess 19 项全部通过 | 中 | 前端单文件 10,840 行 |
| 地理配准 GCP + RMS | 像素→地理坐标 | PARTIAL | 自研 affine/poly2/TPS 求解；2026-09-13 验收记录 RMS 8.74 m | registration 54 项，10 项失败 | 角点 OCR 测试因字段改名失败；GDAL 输出仅 Windows 可跑 |
| 候选 CRS 推断 | 从投影坐标反推中国坐标系 | PARTIAL | 有实现与测试 | 部分 | 无真实多样本验证 [UNKNOWN] |
| 图例录入（人工 + OCR） | 建立图例字典 | PARTIAL | 前端流程存在；PaddleOCR 路径未在审计中执行 | recognition 内 | 依赖大量人工字段输入 |
| 地层 / 侵入岩面识别 | 按图例颜色切分面 | PARTIAL | baseline mIoU 0.38（2 张图、7 个面标注，2026-06-01 数据） | stratigraphy 54 项通过 | 评估集极小；6 月后无新评估 |
| 地质界线 | 提取并分类界线 | PARTIAL（质量未达可用） | baseline buffer_f1 0.1222，门槛 0.12 | boundary 249 项，5 项失败 | 33 个提交反复修误检/漏检 |
| 地质构造（断层） | 从界线中拆分 | PARTIAL | 2026-10-16 才引入 | 少 | 无独立评估 |
| 矿种点符号 | 匹配图例符号 | PARTIAL / BROKEN（测试） | 有真实裁片回归用例 | commodity 161 项，91 项失败 | 数据结构字段改名后测试未同步 |
| 等高线 | 矢量化 + 高程 | NOT_IMPLEMENTED（已停用） | baseline elevation_accuracy = 0.0 | 11 项 | 2026-10-15 停用 |
| 融合 | 合并各模块结果 | PARTIAL | fusion 24 项，1 项失败 | 中 | 依赖上游质量 |
| 导出 GeoJSON / Shapefile | GIS 可读输出 | PARTIAL | 代码存在；未在审计中生成真实 GIS 文件并在 QGIS 中校验 [UNKNOWN] | 少 | KML 未实现 |
| ML 样本库 / 训练 / 发布 | 积累样本、训练模型 | MOCK 级别（流程完整，模型价值未证明） | machine_learning 26 项通过 | 中 | 只用于矿种视觉特征；无效果评估 |
| MoE 专家影子运行 | 专家模型旁路 | MOCK | 文档声明"不影响生产结果"；YOLO adapter 只做数据转换 | moe 4 项 | 无真实专家模型；历史中留下 1.5 GB 运行记录 |
| Canonical ID / 契约 | 统一字段命名 | PARTIAL | 多次全系统迁移 | 测试大量因改名失败 | 迁移导致 245 项测试失败的主要来源 |
| Docker 部署 | 容器化 | BROKEN（推断） | 未构建 | 无 | 版本冲突，见第 6 节 |
| CI/CD | 自动测试与发布 | NOT_IMPLEMENTED | 无流水线 | — | — |
