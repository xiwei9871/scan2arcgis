# Map Auto Conversion Tool 独立技术审计（2026-10-27）

## 范围

- 仓库：`stock/Map-Auto-Conversion-Tool`（GitLab 项目 ID 42）
- 基准 commit：`33e5f7b101ecf275faf72971d3237d741e8ce17f`（dev，2026-10-23）；同时对照 dev HEAD `7aad0c1`
- 性质：只读审计。未修改任何业务代码、分支、数据或部署。本目录是审计分支上唯一的新增内容。

## 结论摘要

总体建议：**`RESEARCH_FIRST`，M1 验证通过后转 `PARTIAL_REBUILD`（路线 B）**。

- 项目目标是把扫描的中国区域地质图转换为带坐标和图例属性的 GIS 矢量。流程界面基本可走通，但核心输出质量未达可交付：面要素 mIoU 0.38（2 张图），地质界线 F1 0.12，等高线已停用，导出文件的地理位置正确性没有任何证据。
- 三个根因：没有定义正确结果和评估数据；把研究型识别问题当作功能开发、用手工规则逐图修补；没有 MVP 边界，持续扩展范围并反复改字段契约。
- 245/1,148 个后端测试失败（主要是字段改名后测试未同步）；无 CI；只能在 Windows 开发机运行。
- 优先解决：建立真实评估集与门槛；打通并验证 GDAL 配准 → 坐标转换 → 导出链路；把线和点要素改为由面拓扑导出或人工确认。
- 冻结：界线规则调参、ML/MoE 平台、等高线、UI 细节。

## 文件导航

| 文件 | 内容 |
|---|---|
| `01_project_overview.md` | 真实目标、文档一致性、分支、架构、依赖、模块清单 |
| `02_development_history.md` | 时间线、被推翻的功能、重复失败分析 |
| `03_root_cause_analysis.md` | 根因分析树 |
| `04_technical_architecture_review.md` | 端到端步骤、逐模块审计、P0–P3 问题 |
| `05_alternative_solutions.md` | 外部方案、三条路线对比、自研边界（附来源） |
| `06_recovery_roadmap.md` | MVP 定义、M0–M4、三个优先问题、停止投入清单 |
| `07_acceptance_framework.md` | 数据盘点、数据缺口、指标与验收方法 |
| `08_executive_decision_memo.md` | Q1–Q8 回答与总体建议 |
| `evidence_index.md` | 结论与证据对应表、证据缺口 |
| `evidence/` | 提交时间线、测试结果、失败签名、复现脚本、执行环境 |

## 方法

1. `git clone --mirror` 获取完整历史；通过 GitLab API 检查分支、MR、Issue、Pipeline、Tag。
2. 阅读 README、设计文档、方案文档、评估数据与配置。
3. 统计代码规模、提交频率、模块修改次数、硬编码阈值。
4. 在隔离的 Linux 虚拟机中安装依赖并运行全部后端测试（`evidence/run_audit_tests.sh`）。
5. 检索 DARPA/USGS AI4CMA、CriticalMAAS、GDAL/QGIS 等外部资料。
6. 所有结论标注 VERIFIED / INFERRED / HYPOTHESIS / UNKNOWN。

## 限制

- 未安装 GDAL Python 绑定和 PaddleOCR，相关路径未实际执行。
- 未运行前端测试和构建，未构建 Docker 镜像。
- 全分辨率端到端测试超出审计环境时限，未得到结果。
- 外部文献数值来自检索摘要，未逐篇核对原文。
- 没有业务方访谈，需求相关结论基于仓库文档。
- 审计证据中不包含任何凭证或客户资料；样图仅以已在仓库中的路径和哈希引用。
