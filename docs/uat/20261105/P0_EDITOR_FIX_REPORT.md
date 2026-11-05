# P0 编辑器修复报告 — STITCHVECTOR-V02-UAT-REMEDIATION Phase 1

日期：2026-11-05 · 分支：`fix/stitchvector-v02-uat-remediation` · 基线：`feature/stitchvector-studio-v01` @ `575a63f`

状态词：`PASS / PARTIAL / FAILED / NOT_EVALUATED / DEFERRED_TO_MANUAL`

## 修复项与证据

| 任务 | 问题 | 修复 | 测试状态 |
|---|---|---|---|
| T01 | E22 文字移动后命中区不同步 | 单一显示框函数 `_display_box()`（画布坐标 w=em·font_px、h=font_px/0.8）驱动 box_*、服务器 `pick_text()` 旋转命中、客户端 `pickText()`；`edit_text`/`add_text`/`text_apply` 后同步 | PASS（单测 4 + 浏览器 9 项） |
| T02 | E04 框选确认重复建字 | `text_preview` 检出框内已有独立文字（锚点在框内或显示框相交）；`text_apply` 默认编辑已有对象，`existing_mode="create"` 才新建；无距离启发式去重 | PASS（单测 3 + 浏览器 4 项，真实框选路径） |
| T03 | E31 合并丢来源属性 | `merged_from` JSON 列：每个来源面记 `eid/rgb/label/area/source/kept/op/t`；`merge_faces`/`merge_components`/`heal_apply`/`text_apply` 残影合并全接入；`merge_history` op；异 label 默认拒绝、`allow_mixed_labels` 显式选择 + 前端 confirm | PASS（单测 4 + 浏览器 4 项） |
| T04 | E09 OCR 字号/角度异常 | `_quad_metrics()`：font_px=检测框短边×0.9、angle=长边方向（归一 ±90°）；`add_text_drafts` 改为逐条调用 | PASS（单测 4：水平/45°/竖排/端到端） |
| T05 | E12 局部 OCR 空候选 | `_ocr_python()` 解析顺序：仓库根 `.venv-ocr` → `$HOME` → `STITCHVECTOR_OCR_PY` → PATH；`ocr_box`/`text_preview` 返回 `status`(`reused/no_detection/low_confidence/engine_unavailable/failed`)+`reason`+`engine`；预览 UI 显示状态与原因 | PASS（单测 3 + 浏览器 2 项） |

## 自动化测试

- `tests/stitchvector_editor/test_p0_fixes.py`：18 项，合成 GPKG（不依赖受保护数据），全部 PASS。
- 既有套件 `tests/stitchvector_editor/` + `tests/stitchvector_studio/`：51 项全部 PASS（含本分支新增 18 项）。
- 既有测试适配：新混合标签守卫与 T03 要求一致，2 处旧测试改为覆盖「拒绝 + 显式选择」两条路径；无断言删除/放宽。

## 浏览器验证（playwright-cli，真实 U2 数据 `u2_B2c.gpkg` + `u2_original.png`）

- `tests/stitchvector_editor/e2e_p0_fixes.js`：**28/28 PASS，fail=0**。覆盖：移动后新位置可点/旧位置失效（客户端 `pickText` + 服务端 `text_pick` + 真实画布点击）、旋转后范围跟随、保存后命中保持、撤销×2 还原；框选已有文字 → `reused` → 两次确认零重复；lasso → `merge_groups` → `merge_history`/`merged_from`/undo 清除；空白框 → `status:"no_detection"`、`engine:"rapidocr"`（真实 `.venv-ocr` 子进程）。
- `tests/stitchvector_editor/e2e_text_layer.js`（既有回归）：17/17 PASS，fail=0——框文字→OCR 候选（真实 rapidocr 分数）→确认→残影清理→图层开关→编辑→撤销/重做→保存回读。
- 注意：编辑器 `save_as` 拒绝覆盖同名文件为既有防误写设计，测试中已用唯一文件名。

## 治理门

`python3 tools/gov/s2a_gates.py all`（主检出）：`state-head` PASS、`state-workspace` PASS（2 个 R2 未提交文件为已知用户工作）、`assets-decisions` FAIL——命中均为 `runs/ocr_poc01/venvs/` 内第三方库文件（cv2 dylib、pycrypto RSA.py/ECC.py），系历史遗留 vendored 依赖，与本分支改动无关，非真实密钥泄露。

## 尚未解决 / 说明

- E22 浏览器端「保存→重新加载页面后命中」未做整页 reload 验证（beforeunload 干扰自动化）；等价覆盖：GPKG 保存回读单测 `test_box_sync_survives_save_reopen` + 保存后客户端/服务端命中断言。
- E31 仅阻止「静默」异类合并；显式确认后仍可合并——属设计意图（半自动原则）。
- E12 在迁移工作区以仓库根 `.venv-ocr` 解析成功（实测 rapidocr 子进程返回真实分数与 `no_detection` 状态）；`.venv-ocr` 为本地资产不入库。
- A 类问题（A01–A33）属 P2 半自动修复范围，本阶段未改 B2c。

## 下一阶段建议

进入 P1：OCR 置信度分级 + 审核队列 UI + `review_status` 持久化扩展（`AUTO_ACCEPTED_UNVERIFIED`/`REVIEW_REQUIRED`），并统计 0.80–0.95 阈值送审率。
