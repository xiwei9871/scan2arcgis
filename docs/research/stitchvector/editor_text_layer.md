# StitchVector Editor: text layer and text-residue clean-up (u2, three boxes)

Branch `feature/stitchvector-editor-text-layer` (from `feature/stitchvector-editor-line-repair @ bcb4802`).
Input: copy of `u2_B2c.gpkg` (SHA-256 unchanged). B2c, M2 and history untouched. No new OCR model.

## What was built
- **Text box tool** (`框文字`): the user drags a box; the server proposes a plan (preview id bound to the document version):
  - residue faces = faces with area <= 60 px² and >= 50 % of their area inside the box;
  - residue groups that touch exactly one ground face are proposed to merge into it;
  - groups touching two or more ground faces (the box may sit on a contact) or none are **uncertain** and left alone,
    unless the user assigns a target; the target must be one of that group's ground faces (otherwise refused);
  - lines with >= 90 % of their length inside the box move to `text_residue_lines` (restorable, not deleted);
    lines crossing the box edge are kept as geology.
- **OCR candidate**: RapidOCR (R3 tooling) run in `.venv-ocr` as a separate process (`tools/stitchvector_editor/ocr_cli.py`).
  The candidate only pre-fills the text field; the user confirms or edits it.
- **`text_labels` point layer** in the GPKG: `text, ocr_text, ocr_score, font_px, angle_deg, anchor, rgb, box_x0..y1, source`.
  Edit (text, size, angle, colour, position), delete, undo/redo.
- **QGIS label style** written to `layer_styles` (one row for `text_labels`) so QGIS can show the labels on open.
  Not checked in QGIS (not installed).
- Text layer toggle in the UI; the left original pane is unchanged.

## Results (DATA_LEVEL_VERIFIED, `sv_text_layer_uat.py`, `text_layer/text_result.json`)

| Box | OCR candidate (score) | Residue before (faces / lines) | After | Note |
|---|---|---|---|---|
| Є-O `(3,25)-(35,42)` | `C-0` (0.73) | 40 / 2 | 0 / 0 | Є read as C, as expected; text confirmed by user |
| Ar₂E `(0,196)-(52,225)` | `ArE` (0.84) | 81 / 3 | 0 / 0 | subscript 2 dropped; 16 faces in 8 groups were uncertain (touch pink face 7 and red face 457); cleared only after the user assigned each group |
| 云 `(24,59)-(41,76)` | `云` (1.00) | 10 / 2 | 0 / 0 | OCR correct |

- Faces 665 -> 534, lines 35 -> 28 (7 moved to `text_residue_lines`), 3 text objects.
- Objects changed whose original geometry does not touch any box: **0 faces, 0 lines**.
- Face layer passes the strict coverage check; save: readback equal, text equal, input SHA-256 unchanged.
- Reopened file: texts `Є-O, Ar₂E, 云`, font 13.6 / 23.2 / 13.6 px, 7 residue lines, 1 `layer_styles` row.
- Negative checks: wrong target for an uncertain group refused; stale text preview refused after edit / undo / redo.

Without the user's assignment, Ar₂E keeps 16 small faces: the box touches two ground faces, so the rule does not merge
on its own. This is the intended behaviour for a box that may sit on a contact.

## Browser (UI_INTERACTION_VERIFIED, script-driven, `tests/stitchvector_editor/e2e_text_layer.js`)
17/17 checks: box drag -> preview with OCR candidate pre-filled -> user text -> apply (Є-O, 云), no residue left,
stale preview refused after undo/redo, text layer on shows 2 labels / off shows 0, edit font 13.6 -> 16 with undo/redo,
save with readback. Ar₂E with group assignment was checked at data level only.

Unit tests: 56 passed (editor + stitchvector).

## Not done / limits
- Text position is the box centre and size is 0.8 × box height; no rotation detection.
- Uncertain-group assignment in the UI is a text field (`组号:面号`), not a click.
- The underlying pink face is continuous after the merge, but the face colour itself was not re-checked.
- QGIS display of labels not verified.
- Only three boxes in one 300×300 window; no automatic text detection.
- Operation time not measured; only operation counts.

---

## 更正与补充（只读复核后，提交 ee43dae 之后）

### 更正
1. **Ar₂E 待定组的旧归属不是人工确认。** 上一版验收脚本 `sv_text_layer_uat.py` 按"残影面颜色与候选底面存储颜色最接近"自动为 8 组选了目标（7 组并入红色楔形面，1 组并入粉红底面），并记录为"模拟用户决定"。这是测试者的脚本规则，不是人对照原图做出的判断。
2. **复核结论：** 并入红色楔形面的 7 组（面积增加 29 px²，全部在框内）不予验收：这些像素在原图中与红色面的色差中位数 29.7 dE，只有 3 px 是深色笔画。并入粉红底面的部分（增加 163 px²，其中 46 px² 在框外）需要人工看图确认。
3. **"框外改动 0"的口径：** 对象级（原始几何完全不碰任何文字框的对象）改动为 0；按像素比较，框外有 2 px 颜色改变，位于 (10, 24) 和 (7, 225)，分别在 Є-O 和 Ar₂E 文字框边缘。
4. **7 条隔离线：** 都离 Oracle 线稿超过 2.5 px，和已描的地质线不重合；L1 是 Є-O 位置的闭合小环。Oracle 不描文字和小符号，所以只能说"没有发现误隔离已知地质线"，不能证明它们都不是地质线。

### 本轮改动（只改编辑器交互，不改 B2c，不加 OCR）
- 三态按钮：A 只看原图；B 线面 100% 不透明、文字关、原图叠加关；C 为 B 加文字。
- 待定碎面默认不合并。"点选归属"工具：先点橙色待定组，再点它旁边的候选底面，画面显示合并前（白色虚线）和合并后（绿色实线）的局部边界；按"确认此组归属"或"跳过此组"。点非候选面不会设置目标。
- 隔离线列表：每条有编号（R+id）、长度、颜色，可高亮、可一键恢复到线层；恢复可撤销。
- 旧的"组号:面号"输入框已删除。

### 浏览器验收（脚本驱动，21/21 通过，结果见 `experiments/STITCHVECTOR/text_layer/text_uat_e2e_result.json`）
三态切换；Ar₂E 预览中所有待定组默认无目标；点组、点候选面、预览、确认；跳过一组；点非候选面被忽略；建立文字后只有被指定的一组被合并，其余待定组不动；3 条隔离线列出并高亮；恢复一条、撤销、重做；会话中原 GPKG 哈希不变；保存后回读一致、面层有效、原文件未变。

注：浏览器里拖出的 Ar₂E 框是 [0,195,52,225]，比脚本里的 [0,196,52,225] 高 1 px，因此待定组是 9 组（17 面），不是 8 组（16 面）。框的范围会影响分组，这是预期行为。

### 仍未完成
- 每一组的真实归属需要你对照原图逐组决定；本轮没有替你做任何归属。
- QGIS 显示文字未实测；"生成前先隔离文字"未实现。
