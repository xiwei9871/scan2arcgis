# scan2arcgis

扫描版地质图 → 标准 GIS 矢量成果（ArcGIS / GeoPackage / Shapefile）的自动化转换研究与重建。

本仓库是 Map Auto Conversion Tool（公司 GitLab `stock/Map-Auto-Conversion-Tool`）的重建工作区。
路线：自动识别优先 + 经过校准的置信度 + 自动质量检查 + 少量异常人工复核 + 反馈学习。
每一项改进必须在独立评估集上有客观证据。

## 目录

| 路径 | 内容 |
|---|---|
| `docs/audits/project_recovery_20261027/` | 第一轮独立技术审计（基于旧仓库 `33e5f7b`） |
| `docs/plan/` | 技术路线与实验计划 |
| `experiments/` | E1–E4 实验，每个实验自带说明、脚本和结果摘要 |
| `src/` | 新系统代码（识别器接口、平面拓扑、置信度、导出） |
| `tests/` | 测试 |
| `data/` | 本地数据，不入库；只提交 `data/manifests/` 中的元数据 |

## 旧代码

旧项目完整历史保留在本地 Git 中（分支 `dev`、`master`、`audit/map-auto-conversion-recovery-20261027`，远端名 `gitlab`），**不推送到 GitHub**。需要参考时：

```bash
git worktree add legacy dev      # 检出到 ./legacy（已被 .gitignore 忽略）
git worktree remove legacy       # 用完移除
```

## 远端

- `origin`：GitHub `xiwei9871/scan2arcgis`（公开），只推送 `main`
- `gitlab`：公司 GitLab 旧仓库，只读参考

## 数据规则

地质图图件、客户资料、标注真值默认不入库。`data/manifests/` 只记录文件名、SHA-256、来源、比例尺、坐标系、授权状态。
