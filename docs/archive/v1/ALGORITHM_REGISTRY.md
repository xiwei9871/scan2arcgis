# ALGORITHM_REGISTRY — 真实实现状态登记 (archive V1, 2026-11-02)

状态口径：**IMPLEMENTED**(代码在库中）/ **TESTED**（本次或记录在案的实测）/ **EXPERIMENTAL**（有代码、限研究用）/
**NOT_IMPLEMENTED**（只有设计/声明）。证据优先：未亲验的标注 NOT_VERIFIED。

| # | 算法/组件 | 状态 | 位置 (branch) | 证据 |
| --- | --- | --- | --- | --- |
| 1 | **B2c 矢量化器**（栅格→面/线 GPKG，冻结基线） | IMPLEMENTED + TESTED | `experiments/STITCHVECTOR/sv_{lf,d71,oracle,oracle_v2,u2_full_build}.py` + Studio 插件 `tools/stitchvector_studio/plugins/b2c` (feature/stitchvector-studio-v01) | U2 全图 17,047 面/606 线，严格覆盖 PASS；3 次复跑 17–18s；曾一次 -11 闪退未复现 |
| 2 | **PaddleOCR 插件** PP-OCRv6_medium（默认 OCR) | IMPLEMENTED + TESTED | `tools/stitchvector_studio/plugins/paddleocr`；venv `runs/ocr_poc01/venvs/paddle`；模型缓存 `cache/paddle/official_models`(3 模型，139M) | E2E 33.9s→148 候选；`packages_verified` paddleocr 3.7.0 / paddlex 3.7.2 / paddlepaddle 3.3.1 |
| 3 | **RapidOCR 插件** PP-OCRv4 ONNX（回退） | IMPLEMENTED + TESTED | `tools/stitchvector_studio/plugins/rapidocr`；venv `.venv-ocr` | 4.9s→219 候选；profile `legacy-b2c-v01-rapidocr` COMPLETED |
| 4 | **OCR 地质通用纠错** R1–R3 | IMPLEMENTED + TESTED | `tools/stitchvector_studio/geo_rules.py`（自 `experiments/STITCHVECTOR/ocr_poc01/geo_postprocess.py` GENERIC 层复制） | 建议-only（不改 raw_text)；实测 "Ar2E"→"Ar₂E"(R1)；版本 `generic-1.0 (ocr_poc01 cae5a61)` |
| 5 | **文字对象化与隔离线**（text_labels / text_residue_lines / review_status 状态机） | IMPLEMENTED + TESTED | `tools/stitchvector_editor/core.py` TextMixin；列定义见 `TEXT_COLS` | E2E：编辑/移动/加/删/undo 全部 PASS；不确定残影默认不合入；R 编号独立开关 |
| 6 | **地质线面编辑**（pick/box/grow/shrink/merge/heal/split/draw/recolour/rewidth/undo-redo/原子保存） | IMPLEMENTED + TESTED | `tools/stitchvector_editor/{core,server}.py` | 多轮浏览器验收（详见各 editor 分支提交：12/12→30/30)；保存=临时文件+回读+原子改名 |
| 7 | **Visual Diff**（确定性渲染 + 原始 RGB 残差） | IMPLEMENTED + TESTED | `experiments/STITCHVECTOR/sv_u2_visual_diff.py` + 编辑器 diffMode | 自检 0/重跑一致/植入缺陷定位；浏览器 10/10 |
| 8 | **插件式 Pipeline**（契约/注册表/代码哈希钉死/进程隔离/阶段超时/取消） | IMPLEMENTED + TESTED | `tools/stitchvector_studio/{contracts,registry,stage_runner,projects}.py` | mock-swap 与真实 profile 均跑通；code_hash 中途换码拒跑；job manifest 磁盘持久化（重启可恢复） |
| 9 | **多格式导入适配**(PNG/JPEG/BMP/WebP/TIFF/multi-TIFF/GeoTIFF/PDF 多页；JP2 声明) | IMPLEMENTED + TESTED(部分) | `tools/stitchvector_studio/inputs.py` | 11 样本：9 接收 + 2 正确拒绝；GeoTIFF→GEOREFERENCED(保 CRS+transform);PDF DPI 限 36–600;JP2 声明但**无样本未测** |
| 10 | **GIS 导出**(GPKG/SHP-ZIP/GeoJSON；像素空间诚实标注；写后回读） | IMPLEMENTED + TESTED | `tools/stitchvector_studio/exports.py` | GPKG 4 层回读一致；SHP zip 含 shp/shx/dbf/cpg+manifest；像素空间 GeoJSON→`.pixel.json`（拒绝假 EPSG);SHP 像素导出需显式确认 |
| 11 | **质量阶段** builtin.quality（拓扑/碎面统计，非地质判定） | IMPLEMENTED + TESTED | `tools/stitchvector_studio/projects.py::_quality` + `stitchvector_editor.core.coverage_report` | 每次任务产出 quality_report.v1 |
| 12 | **Mock 插件**(mock_vectorize / mock_ocr) | IMPLEMENTED + TESTED | `tools/stitchvector_studio/plugins/mock_*` | mock-swap-test profile COMPLETED(36 面/1 线/4 候选） |
| 13 | **surya OCR** | EXPERIMENTAL（未采用） | `runs/ocr_poc01/venvs/surya`（仅环境）,POC 适配器 `experiments/STITCHVECTOR/ocr_poc01/` | POC 评估过，未入选默认 |
| 14 | **StitchVector 3.0 几何优先评分**（reusable/present/convertible, 编辑成本代理） | EXPERIMENTAL(paused) | `wip/stitchvector-editcost-calibration` 链上 `sv_gc_repairability.py` 等 | 评分完成；PN2 87% 中心线可修；面碎化成主要成本 |
| 15 | **线修复/图例样式/双视图**（编辑器增强） | IMPLEMENTED + TESTED | `feature/stitchvector-editor-line-repair` @ `bcb4802` | 浏览器 30/30;legend_styles 表（实线/虚线/齿线+面填充） |
| 16 | **图例预解析** stitchvector.legend.preparse | NOT_IMPLEMENTED | vNext profile 声明 | geology-aware-vnext 显示 disabled |
| 17 | **文字保护遮罩** stitchvector.text.protect_mask | NOT_IMPLEMENTED | 同上 | — |
| 18 | **保护区矢量化** stitchvector.vectorize.lines_protected | NOT_IMPLEMENTED | 同上 | — |
| 19 | **图例约束面元归属** stitchvector.geometry.faces_legend | NOT_IMPLEMENTED | 同上 | — |
| 20 | **图例残差质检** stitchvector.quality.legend_residual | NOT_IMPLEMENTED | 同上 | — |
| 21 | 旧产品线矢量化链路（master/dev) | IMPLEMENTED(legacy) | `master`,`dev`（非 GitHub 线） | 项目前身；本归档不展开 |

## 运行环境登记（C 类：可重建，勿上传）

| 环境 | Python | 包数 | 用途 | 重建依据 |
| --- | --- | --- | --- | --- |
| `.venv-sv` | 3.11.15 | 34 | Studio 服务 + B2c + 编辑器 | `env/requirements-.venv-sv.txt` |
| `.venv-ocr` | 3.11.15 | 26 | RapidOCR 子进程 | `env/requirements-.venv-ocr.txt` |
| `runs/ocr_poc01/venvs/paddle` | 3.11.15 | 72 | PaddleOCR 子进程 | `env/requirements-runs_ocr_poc01_venvs_paddle.txt` |
| `runs/ocr_poc01/venvs/surya` | 3.11.15 | 57 | surya POC（未采用） | `env/requirements-runs_ocr_poc01_venvs_surya.txt` |
| `runs/ocr_poc01/venvs/eval` | 3.11.15 | 11 | POC 评估 | `env/requirements-runs_ocr_poc01_venvs_eval.txt` |
| `.venv-ml` | 3.11.15 | 20 | ML 杂项 | `env/requirements-.venv-ml.txt` |

模型缓存：`runs/ocr_poc01/cache/paddle/official_models/{PP-OCRv6_medium_det,PP-OCRv6_medium_rec,PP-LCNet_x1_0_textline_ori}`(139M);
`cache/{datalab 81M, hf 797M}`(surya/eval 系，可重下）。系统依赖：GDAL/rasterio(pip wheel 自带）、pypdfium2、onnxruntime。
