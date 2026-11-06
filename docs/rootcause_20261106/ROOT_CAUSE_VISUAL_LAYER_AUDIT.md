# ROOT_CAUSE_VISUAL_LAYER_AUDIT — T01 四态图层诊断

任务: `STITCHVECTOR-TEXT-FACE-LINE-ROOTCAUSE-FIX` · 分支 `feat/stitchvector-tfl-rootcause` · 基线 `c7b74d9`

## 证据缺口（如实声明）

用户 2026-11-06 两张截图（红面内碎裂 / 含希腊字母+拉丁字符区）**未在本地留存**。本报告用程序扫描在真实 U2 全图上定位的**临时对应区域**验证机制，不得视为截图原位的等价证据：
- `case1_red_frag` = [500,640,720,780]（红色 Pt₁D 类面内碎斑密集区，由 enclosed_face 密度扫描选出）
- `case1b_red2` = [600,380,760,540]
- `case2_ocr_dense` = [330,280,500,470]（OCR/线密度最高区）

四态图输出在本地 `runs/stitchvector/u2_full/rootcause/{case}_{B2c|prot}/`（A_raster / B_faces / C_lines / D_text / E_overlay，4× 放大），未提交远端。

## 方法（tools/stitchvector_editor/layer_audit.py）

- B_faces：关栅格/线/字，面 100% 不透明；C_lines：纯线；D_text：纯文字框+串；E_overlay：叠加。
- 像素↔矢量双向定位：`face_id`/`line_id`/OCR `quad` 均落在扫描像素网格；审计逐对象给出 id、bounds、OCR 相交 share。
- 异常分型：uncovered_px / enclosed_face / interior_ring / island_face / small_frag / glyph_line(inside_ocr_share≥0.6) / line_crosses_text / raster_only(底图透显)。
- **不以 coverage=PASS 作为内部无碎裂证据**——基线 coverage 通过的同时存在 17,344 处对象级异常。

## 全图诊断（冻结 B2c 基线，OCR 219 框叠加）

| 指标 | 值 |
|---|---|
| faces / lines / text 层 | 17,047 / 606 / 0 |
| small_frag（≤60px² 有邻接） | 14,568 |
| enclosed_face（唯一邻接=更大面） | 2,313（≥10px² 的 106 个全部与宿主异色） |
| interior_ring | 172 |
| glyph_line（线长≥60%在文字框内） | **214（占全部线 35%）** |
| line_crosses_text | 77 |

## 异常归因结论（Gate A）

- **A02 确证**：214 条线的绝大部分长度位于 OCR 框内 → 字形笔画确实作为 `visual_lines` 地质线对象存在（如 line_id=292/301 等 inside_share=1.0）。
- **A01/E10 确证**：字形墨迹在面分类中切割出大量 small_frag/enclosed_face；OCR 保护重建后面数 17,047→9,638（见 T03），说明约 43% 的"面"由文字碎片机制产生。
- **A08/A09 部分确证**：红面区内 enclosed_face+small_frag 密集且与宿主**异色**（非同色误并）；另有 172 interior_ring 为伪孔洞候选。但 0 个同色自动可并对——真实边界不能跨，自动合并无安全证据。
- **透显排除**：`residual_px_gt40_faces_only` 大残差像素集中在真实线/字位置，属线字对象位置而非面层漏盖。

## Gate A 状态： **PASS**（异常已定位到具体图层与对象 id）
