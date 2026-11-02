# PROJECT_INDEX — StitchVector 研发全景索引 (archive V1, 2026-11-02)

Repo: github.com:xiwei9871/scan2arcgis (public). Path references are repo-relative; the branch column tells
where each artifact lives. Full branch table: `BRANCH_INVENTORY.md`. File-level data: `asset_inventory.csv`.

> 原则：保留失败与被否决路线的记录——它们是避免重复试错的资产。

## 阶段 0 — 技术路线研究与"绣娘模式"路线确立

- **目标**：为地质图自动矢量化选型：深度分割 vs 几何优先的栅格路线。
- **关键发现 / 证据**
  - M2_hybrid 小实例召回 0.596 / 0.554 / 0.694（图幅 15023/15041/13015）；失败中多实例合并占 0.73–0.80（E1–E2）。
  - M0（图例颜色随机森林）小实例召回 0.215/0.163；图例颜色不可避免混入印刷边界（E3）。
  - OSS 深度路线核查：uiuc-pipeline(U-Net, 需 GPU, 无公开权重/许可证）、soduco(19 世纪巴黎图, 域不匹配）；
    Mutex Watershed / clDice / SPLIT 等损失级方案仅部分有原文核查——结论：**几何优先、可审计的
    栅格→矢量路线（"绣娘模式" StitchVector）优先于端到端学习**。
  - 早期 R1→R4/ARCH 系列在 runs/ 留下大量实验输出（r4a2 5.9G、r4c0 4.3G…），多为可再生中间产物。
- **被否决路线**：M2_hybrid/M0 学习式面元分割（证据 E1–E3）；外部深度管线（许可/权重/算力约束）。
- **报告**：`docs/research/route_review_2026-10-30.md`, `docs/plan/technical_route_v1.md`,
  `docs/research/{r4a,r4b0,r4b1,arch2}/`, `docs/audits/project_recovery_20261027/`(main 分支)。
- **分支/SHA**：`research/r4a-boundary-learning` @ `dee918d206bb23252cc24b1111b0ebe5499bd7b8`,
  `research/auto-vectorization-r1` @ `926be33ca95993e46d0f2c38f28fb1dcc9ce4177`,
  `design/d0-e1-e4` @ `c2c0788f5eeb9042e2d65c0ef4be4ec8512c99fb`。
- **测试**：研究性证据（门控评审），非工程测试。 **已知缺陷**：路线判断依赖未补读原文的 3 篇文献（Saxton/SPLIT/Xia）。

## 阶段 1 — 地质线面提取与 B2c

- **目标**：冻结的 B2c 算法产出 `colour_faces`(Polygon) + `visual_lines`(LineString)，像素坐标。
- **关键发现**：严格覆盖率检查通过；多部件 B2c 线在分组前拆段（multipart_split 15）;
  早期 line-detection/linedet/linerec/lf/d71/protabl 系列实验沉淀在 `experiments/STITCHVECTOR/sv_*.py`(~90 个脚本）。
- **当前结论**：B2c 是 CURRENT_BASELINE 矢量化器，U2 全图 17,047 面 / 606 线（~18s,M4)。
- **代码**：`experiments/STITCHVECTOR/sv_{lf,d71,oracle,oracle_v2,u2_full_build,b2c*}.py`
  （经 `tools/stitchvector_studio/plugins/b2c` 封装为 Studio 插件）。
- **报告**：`docs/research/stitchvector/{v3_line_face_integration,v3_b2b_edge_filter_review,d71_line_face_diagnostic,v3_b2c_luminance_review,v3_minimal_line_recovery,v3_line_detection_review,v3_line_error_triage}.md`。
- **分支/SHA**：`research/stitchvector` @ `de621967204f9a5e64be1d213c0f27f058ce78e5`。
- **测试**：B2c 三次稳定复跑 17.36–17.95s；严格覆盖 PASS。 **已知缺陷**：曾发生一次间歇性子进程
  segfault(-11)，未复现亦未证明修复；B2c 本身不做语义判定（面=颜色域，不区分地质体/符号/文字油墨）。

## 阶段 2 — 编辑器 V0.1（线修复 + 文字分离/安全清理）

- **目标**：人对 B2c 结果的可审计编辑：面/线编辑、undo/redo、原子保存；文字对象化（独立 text_labels)，
  字形残影线移入可恢复的 text_residue_lines；不确定残影默认不合入背景。
- **关键发现**："加文字/移文字/改文字 + review_status 状态机"已实现（OCR_DRAFT→HUMAN_EDITED…，默认永不自动确认）;
  三态核验视图（A 原图 / B 线面 / C 线面+文字）；隔离线 R 编号单独调试开关。
- **当前结论**：编辑器 V0.1–V0.2 功能齐全并通过多轮浏览器验收（20/20→30/30→21/21→17/17)。
- **代码**：`tools/stitchvector_editor/{core.py,server.py,static/}`（本地 stdlib HTTP,127.0.0.1)。
- **报告**：`docs/research/stitchvector/editor_{v01_guide,v01_uat,poc0_poc1,line_repair_legend,line_repair_guide,text_layer,text_layer_guide,text_uat_pack,text_visual_uat}.md`。
- **分支/SHA**：`feature/stitchvector-editor-v01` @ `5019ce41a590c70aa8a6d7050eb3818e2ffd2a7e`;
  `-poc1` @ `79619c564c7b90912bb2e4ead2de92122135e189`; `-line-repair` @ `bcb4802d47a3f3f35cc4673de2051eeae9c3c36c`;
  `-text-layer` @ `24d2d14db53a3e534256e0440f1f89d340166602`。
- **测试**：浏览器端到端 12/12、20/20、30/30、21/21（分支各自提交信息）。 **已知缺陷**：text-clear 后的
  字形残影仍需人工确认指派；Ar₂E 类 16 个接触碎片留 pending（不自动归并）。

## 阶段 3 — U2 全图验证

- **目标**：对真实 U2 图幅（805×780）跑全链路并量化。
- **关键发现**：B2c 全图 17,047 面/606 线（16.8s)，严格覆盖 PASS；面/线/OCR/文字清理拓扑审计 +
  **575 项人工审查队列**；Oracle 真值只覆盖图面 **4.5%** → 多数语义指标 NOT_EVALUATED。
- **当前结论**：U2_FULL_UAT_READY；几何/拓扑层面可靠，语义层待真值扩充。
- **数据**：`runs/stitchvector/u2_full/`（原图、B2c/text-cleared GPKG、u2_ocr_full.json、visual_diff）。
- **报告**：`docs/research/stitchvector/u2_full_validation_report.md`。
- **分支/SHA**：`research/stitchvector-u2-full-validation` @ `988699ef482657655ccf0660ae8f679423f072c2`。
- **测试**：全量审计脚本（sv_u2_full_audit）+ 审查队列产出。 **已知缺陷**：真值覆盖率低；B2c 一次 -11 闪退史。

## 阶段 4 — Visual Diff 图像残差分析

- **目标**：确定性像素级对比（扫描 vs 矢量、B2c vs 当前），供人工定位缺陷。
- **关键发现**：自检 0 差分、重跑逐位一致、植入线/面缺陷可被定位；diff 模式
  (scan/vector, scan/heat, B2c/current, 阈值, 透明度, 同步视图, 点击定位）。
- **当前结论**：工具并入编辑器（diffMode），E2E 中验证可用。
- **代码**：`experiments/STITCHVECTOR/sv_u2_visual_diff.py` + 编辑器 diff 模式。
- **报告**：`docs/research/stitchvector/u2_visual_diff_report.md`；数据 `runs/stitchvector/u2_full/visual_diff/`(.npy 残差 + 渲染）。
- **分支/SHA**：`research/stitchvector-u2-visual-diff` @ `56146bd440d0e466fb664d5aa9cf8dd5b68c95e0`。
- **测试**：浏览器检查 10/10。 **已知缺陷**：无。

## 阶段 5 — OCR POC-01（引擎选型）

- **目标**：多引擎比较（PaddleOCR / RapidOCR / surya），确定默认 OCR 与回退。
- **关键发现**：选 **PaddleOCR PP-OCRv6_medium**（det+rec+textline_ori, CPU）为默认；RapidOCR(PP-OCRv4 ONNX)
  为回退；地质通用规则 R1–R3 只做**建议**(suggested_text/candidate_texts/rule_reasons)，不改写 raw_text;
  U2 图例词典因含未确认条目(Jxd→J₂d）被显式弃用。
- **当前结论**：决策已落地为 Studio 默认/回退配置。
- **代码**：`experiments/STITCHVECTOR/ocr_poc01/`（适配器）, `tools/stitchvector_studio/plugins/{paddleocr,rapidocr}`,
  `tools/stitchvector_studio/geo_rules.py`。
- **报告**：`docs/research/stitchvector/poc01_preregistration.md` + POC 运行记录 `runs/ocr_poc01/`。
- **分支/SHA**：`research/stitchvector-ocr-poc01` @ `cae5a61cc3e921d06dd84875ac3ba2e190b1f55c`。
- **测试**：U2 实测——PaddleOCR 33.9s→148 候选；RapidOCR 4.9s→219 候选；含已知误识别(Ar2E→Ar₂E 由规则修正）。
- **已知缺陷**：小数字/上下标漏检；surya 路线未采用（重、慢）；真值仍为草稿(truth_draft WIP)。

## 阶段 6 — StitchVector Studio V0.1

- **目标**：项目化产品壳——导入（PNG/JPG/TIFF/GeoTIFF/PDF…) → 插件流水线 → 异步任务 →
  编辑 → 版本 → GIS 导出，含可恢复性与诚实坐标标注。
- **当前结论**：**STUDIO_V01_READY_FOR_UAT**；U2 浏览器 E2E **30/30**。
- **代码**：`tools/stitchvector_studio/`（契约/注册表/stage_runner/项目/任务/导入/导出/服务+UI)。
- **报告**：`docs/stitchvector_studio/v01/`(12 份规范 + `handoff_report_2026-11-02.md`);
  证据 `experiments/STITCHVECTOR/studio_v01/{e2e_u2_browser_result,devin_reverification_2026-11-02,input_format_results}.json`。
- **分支/SHA**：`feature/stitchvector-studio-v01` @ `575a63f60d0b71eee632d9b1d9aed0c6f5f52efb`。
- **测试**：E2E 30/30（两次中断会话遗留的"canvas settled"抖动已定位为字体懒加载单帧瞬态并修复）；
  Mock 管线、格式套件、RapidOCR 回退、取消、重启持久化均 PASS。
- **已知缺陷**：见 `OPEN_ISSUES.md`（语义真值、残影清理、B2c 闪退史、JP2 未测、vNext 未实现）。

## 阶段 7 — Geology-Aware Pipeline（未来，尚未实现）

- **目标**：图例预解析 → 文字保护遮罩 → 保护区域矢量化 → 图例约束面元归属 → 图例残差质检。
- **当前状态**：**设计上已声明、实现上 NOT_IMPLEMENTED**——profile `geology-aware-vnext` 在注册表中
  正确显示为 disabled；相关阶段插件（legend.preparse / text.protect_mask / vectorize.lines_protected /
  geometry.faces_legend / quality.legend_residual）均未实现。不得以"已设计"当作"已有算法"。
- **报告**：`docs/stitchvector_studio/v01/{geology_aware_vnext_plan,pipeline_current_vs_target}.md`,
  `docs/research/stitchvector/route_review.md`。
- **分支/SHA**：接口锚定在 `feature/stitchvector-studio-v01` @ `575a63f`。

## 并行/暂停线（归档保留）

| 线 | 状态 | 分支 @ SHA | 说明 |
| --- | --- | --- | --- |
| StitchVector 3.0 几何优先评分 | paused | `wip/stitchvector-editcost-calibration` @ `bf94978` | 编辑成本标定 WIP；G1–G3 评分完成：面碎化(merge/recolour ~1,000 ops)成主要成本 |
| R2 GSJ 真图 | active-ish | `research/r2-real-map-recognition` @ `0ad6d42` | GSJ 08001/08004 图幅 + 图例完整性审计/指标拆分脚本（本归档期入库） |
| R3 修复 / 线面融合 / 语义 OCR | done | `research/r3-*` | 见各分支提交 |
| OSS 调查 | done | `research/oss-survey-20261028` @ `d41ef93` | 外部管线/许可核查 |
| 编辑器路线图 | done | `research/stitchvector-editor-roadmap` @ `bec2956` | 设计文档 |
| 项目治理层 | PR 待审 | `chore/project-continuity-v101` @ `c42f549` | PR #1 OPEN |
| 旧产品线 | legacy | `master`/`dev`/`audit/...` | 含 LEGACY_ROOT，不可推 GitHub(钩子设计） |
