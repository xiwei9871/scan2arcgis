# R1 自动矢量化研究实验

文档：`docs/research/auto_vectorization_r1/`。本目录只放脚本和结果摘要；运行产物写到 `runs/`（不入库）。

| 脚本 | 作用 |
|---|---|
| `run_synth_case.py` | 单个合成图：旧算法、新候选（含 SAM）对比，输出 metrics.json 与叠加图 |
| `aggregate.py` | 汇总合成结果，按图 bootstrap 置信区间 |
| `auto_retry_selection.py` | AUTO_RETRY 变体自动选择实验 |
| `prepare_real.py` | 真实图：ROI + 图例条拼接、自动检测图例色块 |
| `compare_real.py` | 真实图：新旧方法同图对比；可选 draft 参考 |
| `legacy_fairness_check.py` | 旧算法公平性检查（三种输入条件） |
| `run_vectorize.py` | 自动矢量化闭环，导出 GeoPackage（像素空间，未配准） |
| `render_tables.py` | 从结果 JSON 生成 `results/tables.md` |

真实图参数（原图像素）：

| map | --roi | --legend | --scale | --min-side / --max-side |
|---|---|---|---|---|
| gm2 | 2950,300,3100,3500 | 6130,300,2763,4700 | 0.5 | 25 / 90 |
| u1 | 24,54,774,722 | 818,62,452,740 | 1.0 | 6 / 30 |
| u2 | 80,18,805,780 | 80,805,909,175 | 1.0 | 14 / 60 |
| u3 | 33,33,3357,2177 | 33,2250,3357,560 | 0.5 | 20 / 90 |

依赖：见 `pyproject.toml` 的 `r1` 可选组；旧算法需 `legacy/` worktree 与 Linux 下的 `msvcrt` shim（`docs/audits/project_recovery_20261027/evidence/run_audit_tests.sh`）。
