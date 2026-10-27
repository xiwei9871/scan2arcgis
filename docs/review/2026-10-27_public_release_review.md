# 公开发布前文件审核（2026-10-27）

范围：本地 `main`（`86e4cc5`，27 个文件，1 个提交）即将推送到公开仓库 `github.com/xiwei9871/scan2arcgis`。同时检查 GitHub 上已公开的旧 `master`（`47d6b55`）。
方法：逐文件列出、关键字与正则扫描、人工阅读命中行。只报告，不删改文件。

## 1. 结论

未发现令牌、密码、私钥、客户数据、图像或个人敏感信息。有 5 项**内部信息披露**风险，需要你决定是否接受（R1–R5）。在你确认之前，我没有修改任何待公开文件。

## 2. 已确认无问题

| 检查项 | 方法 | 结果 |
|---|---|---|
| GitLab 令牌（`mqkj-` 前缀） | `git log --all -S'mqkj-'`（全部分支、全部历史） | 0 处 |
| 其他凭证 | `token / password / secret / PRIVATE-TOKEN / api/v4` | 0 处 |
| 本地路径 | `/Users/`、`C:/`、`/sessions/`、`/tmp/`、`42599` | 0 处（Windows 路径已在上一提交中泛化） |
| 图像、样图、权重、wheel | `ls-tree` 扩展名检查 | 0 个；样图只在 `data/manifests/maps.csv` 中以文件名和 SHA-256 出现 |
| IP、内网主机名 | 正则 | 0 处（唯一命中 `4.10.0.84` 是 OpenCV 版本号） |
| 公司 GitLab 主机名 | `manqiaotechnology` | `main` 中 0 处 |
| 旧任务 ID、模型 ID | `task_YYYYMMDD_…`、`ml_…` | 0 处 |
| 推送体量 | `git rev-list --objects main` | 39 个对象，不会带出旧历史 |
| GitHub 旧 `master` | 同样扫描 | 无凭证；`frontend/src/services/api.ts` 中的 `token` 是浏览器 localStorage 读取逻辑，不是密钥 |

## 3. 需要决策的风险

| 编号 | 内容 | 位置 | 风险 | 可选处理 |
|---|---|---|---|---|
| R1 | 公司 GitLab 项目路径 `stock/Map-Auto-Conversion-Tool` 与项目 ID 42 | `README.md:5`；`docs/audits/.../README.md:5` | 暴露公司内部仓库命名与组织结构；主机名未出现，无法直接访问 | 保留 / 改为“公司内部旧仓库” |
| R2 | 审计报告整体：旧项目的缺陷、测试失败数、开发历史评价、“不可交付”结论 | `docs/audits/project_recovery_20261027/` 全部 | 内部管理评价公开；可能影响对外形象或客户沟通 | 保留 / 只公开摘要 / 审计目录不进入公开仓库 |
| R3 | 171 条旧提交信息全文 | `evidence/commit_timeline.txt`（49 KB） | 暴露旧系统功能细节与产品设计（五步流程、矿种三门判定、MoE 等），属产品知识 | 保留 / 只保留统计 / 不公开 |
| R4 | 旧测试名清单与失败签名 | `evidence/pytest_failed_tests_33e5f7b.txt`、`pytest_failure_signatures.txt` | 暴露旧代码内部模块名、函数名；风险低 | 保留 / 不公开 |
| R5 | 业务与客户画像：“面向地矿地质单位”、样图分辨率与尺寸、验收记录 RMS 8.74 m | `01_project_overview.md:8,12,97` | 低；不含客户名称或图幅号，但描述了业务方向 | 保留 / 删去 |

另有两点不是风险，但需要知道：

- **许可证缺失**：`main` 没有 `LICENSE` 文件。公开仓库无许可证时，默认保留全部权利，他人不能合法复用。GitHub 旧 `master` 的 README 写的是 MIT，但也没有 LICENSE 文件。是否开源、用何种许可证需要你决定。
- **提交作者**：提交者显示为 `Claude <claude@anthropic.com>`。如需显示为你本人，后续提交可在本仓库设置 `user.name` / `user.email`；已有提交不改写。

## 4. 防止误推送的措施

- `origin` 的推送规则固定为 `refs/heads/main:refs/heads/main`；直接 `git push` 不会推送 `dev`、`master`、审计分支。
- 新增本地 `pre-push` 钩子（`.git/hooks/pre-push`，不入库，源码见 `scripts/hooks/pre-push`）：推送到 GitHub 时，若要推送的提交包含旧项目历史（根提交 `b7248db`）、图像或权重文件、`mqkj-` 令牌，拒绝推送。
- `.gitignore` 默认忽略图像、GIS 数据、`legacy/`、`data/`（清单除外）。

## 5. 建议

R1、R4、R5 风险低，可保留。R2、R3 取决于这个仓库的定位：如果它是对外展示或开源项目，建议审计报告只保留摘要，把完整报告和提交时间线放在私有位置；如果它实际只是你个人的工作仓库，可以考虑把 GitHub 仓库设为 Private，问题全部消除。
