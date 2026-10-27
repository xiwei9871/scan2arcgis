# 证据索引（S2A-R1）

运行环境：Ubuntu 22.04 VM，aarch64，4 核，约 3.9 GB 内存，无 GPU；Python 3.10.12。旧代码 `7aad0c1`（只读 worktree `legacy/`，Linux 下需 `msvcrt` 空实现 shim）。真实图像与运行产物在本地 `data/raw/`、`runs/`，不入库。

| 编号 | 结论 | 证据（入库） | 产物（本地，不入库） | 复现 |
|---|---|---|---|---|
| E-A1 | 旧系统无深度学习识别 | `legacy_algorithm_review.md` §1 | — | `git grep -lE "import torch|onnxruntime|ultralytics" dev -- backend` 为空 |
| E-A2 | 旧地层流程要求 BGR，传 RGB 时几乎不出结果 | `src/scan2arcgis/adapters/legacy.py` 文档字符串 | `runs/_probe` | 同一合成图 RGB 输入 0 个多边形，BGR 输入 10 个 |
| E-A3 | 旧 `confidence` 为启发式离散值 | `results/synth_summary.json` rows | `runs/r1_synth/*/metrics.json` | 旧地层 0.85/0.99；旧界线 0.56–0.83 |
| E-A4 | 旧算法失败主因是颜色精确匹配 | `results/real_maps_summary.json` `legacy_fairness` | `runs/real/*/legacy_fairness.json` | `legacy_fairness_check.py runs/real/<map>` |
| E-A5 | 旧算法稳定性问题 | `results/synth_summary.json`（scan_jpeg_s2 error；hillshade_s2 缺失） | `runs/r1_synth_hillshade_s2.err` | `run_synth_case.py` |
| E-C1 | 合成基准总体结果 | `experiments/R1_auto_vectorization/results/synth_summary.json`、`tables.md` | `runs/r1_synth/` 叠加图 | `aggregate.py` |
| E-C2 | 真实图观察结果 | `results/real_maps_summary.json` | `runs/real/*/compare/compare_side_by_side.jpg` | `prepare_real.py` + `compare_real.py` |
| E-C3 | gm2 draft 参考上的比较 | `real_maps_summary.json` → `gm2_roi.reference_eval` / `reference_lines_eval` | — | `compare_real.py --ref --ref-lines` |
| E-B1 | SAM 2.1-tiny 可在 CPU 运行 | `src/scan2arcgis/recog/sam2_onnx.py`；`synth_summary.json` 中 `legend_rf_selftrain+sam2` | 模型缓存 `/tmp/models/sam21t`（不入库） | 下载 `onnx-community/sam2.1-hiera-tiny-ONNX` |
| E-B2 | SAM 许可证 Apache-2.0 | HuggingFace `facebook/sam2.1-hiera-tiny` 卡片（2026-10-27 查询） | — | HF API `cardData.license` |
| E-B3 | uncharted-ta1 MIT，依赖 ultralytics / detectron2 / torch 2.0.1 | `modern_algorithm_candidates.md` | — | GitHub raw `LICENSE`、`pyproject.toml` |
| E-B4 | LOAM MIT | 同上 | — | GitHub raw `LICENSE` |
| E-D1 | 区域边际 AUROC 与错误定位能力 | `synth_summary.json` `conf_auroc`、`cap10`、`cap20` | — | `run_synth_case.py` |
| E-D2 | AUTO_RETRY 自动选择 | `results/auto_retry_selection.json` | — | `auto_retry_selection.py` |
| E-D3 | 从不 AUTO_ACCEPT | `src/scan2arcgis/confidence/decide.py`；测试 `test_decision_policy_never_auto_accepts` | — | `pytest tests` |
| E-E1 | 矢量化结果有效、无重叠、未配准 | `real_maps_summary.json` `vectorization`；测试 `test_polygons_form_a_partition_and_contacts_agree`、`test_gpkg_export_is_unreferenced_and_d0_valid` | `runs/real/*/out/*.gpkg` | `run_vectorize.py` |
| E-E2 | 伪造概率被拒绝写出 | 测试 `test_export_rejects_fake_probability` | — | `pytest tests` |
| E-T | 测试结果 | `experiments/R1_auto_vectorization/results/pytest_report.txt` | — | `pytest -q tests` |

## 样本访问约束

| map_id | SHA-256 | 约束 |
|---|---|---|
| gm1、gm2 | 见 `data/manifests/maps.csv` | 来自公司旧仓库；授权未确认，不公开 |
| u1、u2、u3 | 见 `data/manifests/maps.csv` | 项目负责人 2026-10-27 提供；授权未确认，不公开 |

公开仓库只包含合成数据生成器（`src/scan2arcgis/synth/generate.py`），任何人可用固定随机种子重现全部合成基准。
