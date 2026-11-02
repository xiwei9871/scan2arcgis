# FINAL_ARCHIVE_REPORT — STITCHVECTOR-ARCHIVE-V1 (2026-11-02)

## 交付文件（本目录 docs/archive/v1/)

| 文件 | 内容 |
| --- | --- |
| `PROJECT_INDEX.md` | 8 个研发阶段全景索引（含被否决路线与失败记录） |
| `asset_inventory.csv` | 263 条资产（类别/路径/大小/SHA-256/分支/实验/备份状态/重要性/处置） |
| `ALGORITHM_REGISTRY.md` | 21 项算法与 6 个环境登记，IMPLEMENTED/TESTED/EXPERIMENTAL/NOT_IMPLEMENTED 严格区分 |
| `BRANCH_INVENTORY.md` | 30 分支 + 11 worktree + PR 清单与状态 |
| `DATA_BACKUP_MANIFEST.json` | 222 项 B 类受保护数据 SHA-256 清单 + 打包方案 |
| `RECOVERY_GUIDE.md` | 新机器逐步恢复手册（可直接执行命令） |
| `RECOVERY_TEST_REPORT.md` | GitHub 隔离克隆 + 全管线恢复实测 |
| `OPEN_ISSUES.md` | 13 项遗留问题（含非任务书列明项） |
| `env/requirements-*.txt` | 6 个 venv 的 pip freeze |
| `FINAL_ARCHIVE_REPORT.md` | 本报告 |

## GitHub 推送（全部经 `git ls-remote` 核验）

| 分支 | 远端 SHA | 说明 |
| --- | --- | --- |
| `feature/stitchvector-studio-v01` | `575a63f60d0b71eee632d9b1d9aed0c6f5f52efb` | Studio 恢复 + E2E 30/30（前序任务） |
| `wip/stitchvector-editcost-calibration` | `bf94978923843454f57cc8aecc9f9ee1ded62a96` | 原仅本地 → 新建远端分支 |
| `research/r4a-boundary-learning` | `dee918d206bb23252cc24b1111b0ebe5499bd7b8` | 原 ahead 2 → 已推 |
| `research/r2-real-map-recognition` | `0ad6d420c8e8764e17f5918ceb907cea60d1ee0b` | 2 个未跟踪 GSJ 脚本入库 |
| `chore/stitchvector-archive-v1` | 见最终 push | 本归档文档（main 为基） |

pre-push 钩子全部通过：无二进制/密钥/`mqkj-` token/legacy 历史进入推送。
不可推项（设计使然）:`dev`、`audit/map-auto-conversion-recovery-20261027`（含 LEGACY_ROOT,gitlab 系）。

## 仅本地保留清单（不推送/不上传）

- `.playwright-cli/` 各 worktree 浏览器日志与导出副本 — TEMPORARY
- `runs/ocr_poc01/{venvs,cache}` 与 `.venv-*` — C 类可重建（freeze/模型清单已归档）
- `~/sv-studio-rescue-20261102/` 抢救快照 — 已被 git 提交取代，留作本地保险
- 用户主检出 2 个未跟踪文件已入库（gsj_*.py → r2-real-map 分支）；主检出其余未动

## 远端备份（B 类数据）

- **状态：REMOTE_BACKUP_PENDING**。候选目的地 `gitlab.manqiaotechnology.com` 凭据失效
  (`git ls-remote` → HTTP Basic denied)，无其他已授权私有远端。
- 已产出：`DATA_BACKUP_MANIFEST.json`(222 项含 SHA-256 + 5 个 bundle 打包方案）。
- **未擅自上传任何受保护数据到 GitHub 或新云服务。**

## 恢复测试

GitHub 克隆→检出→编译→插件发现→真实 U2 管线（17,047/606 一致）→版本保存回读→GPKG 导出回读：全部 PASS。
详见 `RECOVERY_TEST_REPORT.md`。限定：venv/模型缓存需按指南重建；受保护数据恢复依赖待定备份。

## 远端核验（T7)

- 分支 SHA 一致：上述 5 项 ls-remote 已核验（归档分支在最终推送后附 SHA)。
- 关键文档存在于远端：本目录全部文件在 chore/stitchvector-archive-v1。
- 源代码远端可读：克隆实测可运行完整管线。
- 敏感文件未入历史：pre-push 钩子拦截规则 + 提交内容人工复核。
- SHA-256 清单：`asset_inventory.csv` + `DATA_BACKUP_MANIFEST.json`。
- 远端数据备份校验：N/A（无远端备份，见上）。
- 未提交关键代码：全部 worktree 复核，仅剩 `.playwright-cli` 产物与治理分支未提交项（归 PR #1 审）。

## 最终状态

**`CODE_ARCHIVE_COMPLETE / DATA_BACKUP_PENDING`**

- `CODE_ARCHIVE_COMPLETE` ✓：全部源代码/文档/索引已推送 GitHub 并经远端核验。
- `DATA_REMOTE_BACKUP_COMPLETE` ✗：无已授权私有目的地，B 类数据 REMOTE_BACKUP_PENDING。
- `RECOVERY_VERIFIED` ✓ 限定成立：代码层恢复实测通过；数据层恢复待备份目的地。

## 后续行动建议

1. **决定 B 类数据备份目的地**（刷新 gitlab 凭据或指定存储），按 manifest 5 个 bundle 打包上传并校验 SHA-256。
2. 审 PR #1（治理层）与本归档分支 PR。
3. U2 真值扩充（575 项审查队列）后再谈语义指标；JP2 样本补齐。
4. B2c segfault 监控：若再发生，保存 stage.log/core 取证。
5. 人工 UAT 安排（E2E 自动化已过，真实用户验收未做）。
