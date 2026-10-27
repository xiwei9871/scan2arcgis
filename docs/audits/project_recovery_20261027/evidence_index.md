# 证据索引

所有路径相对仓库根目录，commit 默认为 `33e5f7b101ecf275faf72971d3237d741e8ce17f`。复现命令在 Linux 下执行；测试需要 `evidence/run_audit_tests.sh` 中的 shim。

| 编号 | 结论 | 类型 | 证据位置 | 复现方法 |
|---|---|---|---|---|
| E01 | 原始目标：扫描地质图转 Shapefile/GeoJSON，1 个月 MVP，计划用 SAM | VERIFIED | `docs/通用/计划/2025-03-02-geological-map-digitizer-design.md` 第 1–80 行 | 阅读文件 |
| E02 | 当前流程为五步识别 + 五类要素 | VERIFIED | 提交 `b1a14f1`、`c133723`、`1d8828a` | `git show --stat <hash>` |
| E03 | 样图尺寸与分辨率；中国坐标系候选 | VERIFIED | `docs/地质图1.jpg`（19011×20604，300 dpi）、`docs/地质图2.jpg`（8893×5330）；`backend/core/registration/crs/candidate_crs.py` | Pillow 读取 `size`/`info['dpi']`（需 `MAX_IMAGE_PIXELS=None`） |
| E04 | README 声称的 Celery/Redis/Zustand/Fabric/KML 在代码中不存在；SAM 未实现 | VERIFIED | `README.md` | `git grep -l "import redis" backend`；`git grep -l zustand frontend/src`；`git grep -il kml backend frontend/src`（均为 0） |
| E05 | smoke 标记仅 11/1149 个测试 | VERIFIED | `pytest.ini` | `pytest --co -q -m smoke backend/tests` |
| E06 | 等高线 2026-10-15 停用，接口返回 410 | VERIFIED | `docs/图像识别/2026-10-15-等高线停用与五类识别范围收口.md`；提交 `1d8828a` | 阅读文件 |
| E07 | 171 提交、2 分支、无 tag/MR/issue/pipeline/CI；master 停在 `47d6b55`；`33e5f7b` 落后 dev HEAD `7aad0c1` 2 个提交；作者全部为 Claude | VERIFIED | Git 历史；GitLab API `/projects/42/{merge_requests,issues,pipelines,repository/tags,releases}` 返回空列表 | `git rev-list --count 33e5f7b..origin/dev`；`git shortlog -sne --all` |
| E08 | 代码规模与超大文件 | VERIFIED | `backend/api/routes/recognition.py` 15,158 行；`backend/core/recognition/pipeline.py` 8,173 行；`frontend/src/components/preprocess/PreprocessPanel.tsx` 10,840 行 | `git ls-files … | xargs wc -l` |
| E09 | Linux 下无法导入：`msvcrt`（`backend/core/ml/atomic_store.py:10`）；`matplotlib` 未声明（`backend/core/recognition/contour/pipeline.py:11`） | VERIFIED | 测试收集错误：42 个文件 | 新环境 `pytest --co backend/tests` |
| E10 | 测试结果：33e5f7b 245 失败 / 884 通过 / 19 跳过；dev HEAD 245 失败 / 958 通过 / 52 跳过；失败主要来自字段改名 | VERIFIED | `evidence/pytest_total_33e5f7b.txt`、`evidence/pytest_by_dir_33e5f7b.txt`、`evidence/pytest_failure_signatures.txt`、`evidence/pytest_failed_tests_33e5f7b.txt` | `bash evidence/run_audit_tests.sh . <venv>/bin/python` |
| E10b | 全分辨率端到端测试在 4 核/3.9 GB 环境中 178 秒未完成 | VERIFIED（环境相关） | `backend/tests/api/test_id_contract_e2e.py::test_real_upload_to_recognition_with_original_resolution_geologic_map`；超时位置 `api/routes/recognition.py:14501` → `core/recognition/pipeline.py:7970` | 单独运行该测试 |
| E11 | 硬编码浮点字面量：boundary 1,410（12,061 行）、commodity 763（7,864 行） | VERIFIED | `backend/core/recognition/{boundary,commodity}` | `grep -oE '\b[0-9]+\.[0-9]+\b' | wc -l` |
| E12 | Git 历史中约 1.5 GB（未压缩）MoE 影子运行 JSON；克隆包 151 MB；Windows GDAL wheel 与 `.venv` 入库 | VERIFIED | `backend/ml_sidecar/moe/shadow_runs/…`；`gdal-3.10.2-cp310-cp310-win_amd64.whl`；`.venv/` | `git rev-list --objects --all | git cat-file --batch-check` |
| E13 | baseline 结果：界线 buffer_f1 0.1222（门槛 0.12）、地层 mIoU 0.3813、等高线 elevation_accuracy 0.0（可选项）、总体 PASS；门槛 05-11 设定；最后一次评估入库 06-01 | VERIFIED | `evaluations/recognition_baseline_v1/full_baseline_reference_fix5_evaluation.json`；`minimum_metrics.json`；提交 `1dd78f3`、`313a00b` | `git log -p -- evaluations/recognition_baseline_v1/minimum_metrics.json` |
| E14 | 界线模块 33 个提交，同类误检/漏检反复出现 | VERIFIED | `evidence/commit_timeline.txt`；提交 `4551a4c`、`d769b02`、`24976d4`、`953b405`、`33e5f7b` 等 | `git log --oneline -- backend/core/recognition/boundary` |
| E15 | 字段改名时间：`symbol_shape_id`→`symbol_shape_key` 于 `caa44b5`（10-13） | VERIFIED | `backend/core/recognition/commodity/runtime.py:111` | `git log -S symbol_shape_key -- backend/core` |
| E16 | 唯一端到端验收记录只验证流程，不验证输出正确性 | VERIFIED | `reports/validation/frontend_full_acceptance_20260913.json` | 阅读文件 |
| E17 | MoE 只有影子运行；YOLO adapter 仅做格式转换，无模型 | VERIFIED | `backend/core/moe/adapters/yolo.py`；`docs/图像识别/2026-09-07-MoE外挂专家通道说明.md` | 阅读文件 |
| E18 | Dockerfile 与依赖版本冲突 | INFERRED（未构建） | `backend/Dockerfile`（python:3.12-slim、libgdal28）对比 `backend/requirements.txt`（numpy==1.24.3、gdal==3.7.3） | `docker compose build` |
| X01–X12 | 外部方案与公开指标 | INFERRED（来自检索摘要） | 见 `05_alternative_solutions.md` 来源列表 | 阅读原文 |

## 未能获取或未执行的部分（证据缺口）

| 缺口 | 原因 | 影响 |
|---|---|---|
| Issue / MR / 评审记录 | GitLab 上不存在 | 无法还原决策原因 |
| 业务需求与精度要求书面文件 | 仓库中不存在 | 无法设定验收门槛 |
| 更多真实图幅 | 仓库中只有 2 张 | 所有质量结论样本量极小 |
| GDAL 配准输出与 GIS 叠加验证 | 审计环境未安装 GDAL Python 绑定 | 地理位置正确性 UNKNOWN |
| PaddleOCR 路径（图例 OCR、角点坐标 OCR） | 未安装 PaddleOCR/PaddlePaddle | 实际 OCR 准确率 UNKNOWN |
| 前端测试与构建 | 未执行 `npm ci && npm run build` | 前端可构建性 UNKNOWN |
| 全分辨率端到端运行结果 | 超出审计环境时限 | 处理耗时与结果 UNKNOWN |
| Docker 构建 | 未执行 | E18 仅为推断 |
| 开发者本地 `reports/`、`backend/ml_sidecar/` 当前内容 | 被 gitignore | ML 模型效果 UNKNOWN |
