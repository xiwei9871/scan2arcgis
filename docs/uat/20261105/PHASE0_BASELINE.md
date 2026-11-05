# PHASE0_BASELINE — STITCHVECTOR-V02-UAT-REMEDIATION (2026-11-05)

## 基线选择

- **开发基线**：`feature/stitchvector-studio-v01` @ `575a63f60d0b71eee632d9b1d9aed0c6f5f52efb`
  - 经 `git merge-base --is-ancestor` 核验：`feature/stitchvector-editor-text-layer`(`24d2d14`）与
    `feature/stitchvector-editor-line-repair`(`bcb4802`）均为其祖先——该分支已含全部编辑器既有工作。
- **工作分支**:`fix/stitchvector-v02-uat-remediation`（自 575a63f 切出）
- **工作区**:`/Volumes/LexarDev/Dev/geomap2arcgis/.claude/worktrees/sv-v02`
- 不混入：`chore/stitchvector-archive-v1`（归档）、`chore/stitchvector-requirements-install-v1`(PR #3,
  仍 OPEN，安装配置线，待人工审）——与本轮缺陷修复保持独立。

## 环境状态（新工作区 /Volumes/LexarDev)

- 仓库已迁移到外置盘 `/Volumes/LexarDev/Dev/geomap2arcgis`;runs/(20G)与各 venv 已随盘复制。
- `.venv-sv`（新路径直接可用，site-packages 解析到新位置；冷启动 import 较慢属正常）。
- **插件运行时仍解析 `Path.home()` 相对路径** → `/Users/xiwei/geomap2arcgis/...`:
  - PaddleOCR:`runs/ocr_poc01/venvs/paddle/bin/python` + `runs/ocr_poc01/cache/paddle`(139M)均在旧路径，已确认存在。
  - RapidOCR:`~/geomap2arcgis/.venv-ocr/bin/python` 已确认存在。
  - **在 PR #3(repo-relative 解析）落地前，旧目录不可删除**，否则 OCR 失效——记入 OPEN_ISSUES。
- 编辑器 `ocr_box` 另有独立硬编码 `OCR_PY = ~/geomap2arcgis/.venv-ocr/bin/python`(core.py:718),E12 修复范围内一并核对。

## 用户 UAT 数据来源核实

- 报告原文：`问题20261105.docx`(12 页/19 项/20 图），位于微信收件目录（未入仓库）。
- 提取文本与 20 张截图 → `runs/uat_20261105/docx_media/image1..20.png`(**仅本地**，含受保护地图）。
- 图号映射：A01→img1, A02→img2, A09→img3, A10→img4+5, A05→img6, A06→img7, A08→img8, A33→img9,
  A15→img10, A20→img11, A24→img12;E09→img13, E10→img14, E01→img15, E02→img16, E04→img17, E12→img18,
  E22→img19, E31→img20（已解析 document.xml 关系表核验）。
- 用户测试对象 = Studio U2 项目（148 条 OCR 草稿；T039=芽、T059=怀道）。
  报告记 "T040 芽" 与实际 label_id T039 有出入——按文字内容定位，非 ID。
- 报告记 "152→153" 为用户会话中手工新增文字后的数量；基线草稿数为 148。
- 早前实验产物 `runs/stitchvector/u2_full/u2_full_text_cleared.gpkg`(126 texts，无 review_status)
  是另一实验线输出，**不是**本次 UAT 工作文件。

## 台账

- `ISSUE_REGISTER.csv`:19 项全部登记（A 类 11 + E 类 8)，含现象/测试图/可复现性/初步根因/风险/建议方案/预计人工步骤/状态。
- 5 项 P0(E04、E09、E12、E22、E31）根因已通过代码核验确认（见 ROOT_CAUSE_REPORT.md);
  A 类与 E01/E02/E10 机制已理解，待 P2/P3 按项验证。
- 无 `EVIDENCE_MISSING`：全部 19 项有 docx 现象描述 + 截图 + U2 复现数据。

## 冻结说明

本阶段不改任何算法/产品代码。P0 修复在后续提交中进入，均带最小复现测试。
