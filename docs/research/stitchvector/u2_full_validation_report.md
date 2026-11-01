# StitchVector U2 全图端到端验证报告

状态：`U2_FULL_UAT_READY`（等待人工复核；不合并、不部署、未修改生产基线）

分支 `research/stitchvector-u2-full-validation`，基线 `feature/stitchvector-editor-text-layer @ 24d2d14`。

## 0. 结论

| 问题 | 回答 | 状态 |
|---|---|---|
| 全图能否跑通 | 能。B2c 自动处理 U2 地图区 805×780，用时 16.8 s，无人工步骤、无 Oracle | PASS |
| 地质面几何是否合法 | 17,047 个面通过严格覆盖检查（无重叠、无缝隙、面积和等于窗口） | PASS |
| 地质面语义是否正确 | **无法回答**：U2 没有逐单元人工真值，只能按颜色找最近的图例色块（候选，不是分类） | NOT_EVALUATED |
| 地质面是否破碎 | 14,662 / 17,047 个面（86%）≤ 5 px²，合计 25,205 px²（地图的 4.0%） | FAIL |
| 地质线是否完整 | 只能在 Oracle 窗口内测：召回 0.704、精确率 0.667（2.5 px 容差）；窗口只占地图 4.5% | PENDING_REVIEW |
| 窗口外的线 | 没有真值 | NOT_EVALUATED |
| OCR 是否正确 | 全图 127 个文字框；仅 3 个有人工真值，其中 1 个正确（云）；Є-O→E-O、Ar₂E→ArE 错 | 3 个样本 1/3；全图 NOT_EVALUATED |
| 文字清除是否破坏面 | 16 个残影面越过文字框 +1px，越界 28.7 px²；11 个大面因此被改动 | FAIL（小量，已定位） |
| 文字清除是否破坏线 | 不碰任何文字框的线 0 条被改；但 188 条被隔离的线中 16 条所属逻辑组有部分在框外，10 条长于 25 px，可能是真实地质线 | PENDING_REVIEW |
| 清除后的联合拓扑 | 严格覆盖检查通过，保存回读一致，原 GPKG 哈希不变 | PASS |

**一句话判断**：全图矢量化的可执行性已证实；全图识别准确性没有被证实，因为真值只覆盖地图的 4.5%。

## 1. 真值覆盖（先清点，不假设）

| 真值 | 范围 | 占地图 |
|---|---|---|
| Oracle 线稿 `oracle/u2_300_oracle.json` | 中心 300×300 窗口（偏移 x711 y240），与地图区重叠 94×300 px；18 条线，不含文字和小符号 | 4.5%（28,200 / 627,900 px） |
| 文字真值 | 人工确认的 3 个：Є-O、Ar₂E、云，都在 Oracle 窗口内 | — |
| 地质单元真值 | 无 | 0 |

此前说"约 14%"有误：300×300 窗口大部分落在图例和图外，与地图区的重叠只有 4.5%。

## 2. T1 全图自动处理

- 输入：`runs/real/u2/work.png` 的地图框 [0,0,805,780]，裁出为 `runs/stitchvector/u2_full/u2_map.png`（SHA-256 `05cdada4…`）。
- 流程：现有 `sv_lf.build(method="B2c")`，代码版本 `24d2d14`，未改算法。唯一适配：15 个 MultiLineString 线对象拆成单段后再送 linker（否则 linker 报错），拆分数记录在 `u2_build_run.json`。
- 输出：`u2_full_B2c.gpkg`（SHA-256 `988df621…`）：11 个颜色类，590 个 B2c 线对象 → 606 条线记录，17,047 个面，渲染空洞 0。
- OCR：RapidOCR（`.venv-ocr`）1× 和 2× 两次，219 个原始结果，去重后 127 个文字框，32 个置信度 < 0.8。文字内容一律是自动 OCR 结果，没有人工改写。

## 3. T2 地质面

`u2_face_audit.csv` 每个颜色类一行：面数、面积、小碎面数、最大面、最近图例色块及色差。

- 小碎面来源：6,704 个在 OCR 文字框内，1,301 个在线条足迹下，6,657 个在其他位置（符号、抗锯齿、纹理，未进一步区分）。
- 几个颜色类与图例色块差距大（#63413b 42 dE、#92959e 19 dE、#c78a99 18.5 dE），而且没有任何大面（最大面 ≤ 445 px²），它们更像线、文字或符号的墨色，而不是地层面。这是推断，PENDING_REVIEW。
- 错误合并 / 错误分裂：没有单元真值，NOT_EVALUATED。

## 4. T3 地质线

`u2_line_audit.csv` 每条线一行：长度、宽度、颜色、逻辑组、是否在文字框内、是否在 Oracle 窗口、状态。

- 606 条线，501 个逻辑组，总长 14,904 px；32 条短于 10 px；191 条完全落在文字框内，82 条穿过文字框边界。
- Oracle 窗口内：召回 0.704，精确率 0.667。Oracle 不描文字和符号，所以精确率是下限。
- 线与面边界的一致性：未单独计算，NOT_EVALUATED。

## 5. T4 文字识别

`u2_text_recognition_audit.csv`：127 个框的 OCR 字符串、置信度、尺度、坐标、是否在真值窗口、真值及状态。

- 1 个 PASS（云），2 个 FAIL（Є-O、Ar₂E），124 个 PENDING_REVIEW。
- 从 OCR 原始结果能看出常见错误类型：地层代号的 Є 读成 C/E、下标丢失（Ar2E→ArE）、地名正确率较高（宁武县、五寨县、三井镇等）、也有 "。""/TH" 这类可能是符号的误检。这是观察，不是统计。

## 6. T5 文字清除的联合破坏性检查

在副本上对 127 个框全部执行"框文字 → 清理"，只合并只挨着一个底面的残影组，待定组一律不动。结果 `u2_full_text_cleared.gpkg`（SHA-256 `9e9b87f6…`），用时 88 s。

| 项目 | 数值 |
|---|---|
| 面 | 17,047 → 12,995（并入底面 4,052 个） |
| 线 | 606 → 418（188 条移入可恢复的 `text_residue_lines`） |
| 保留的待定组 | 273 组、3,593 个面 |
| 面像素变化 | 9,467 px，其中文字框 +1px 以外 27 px |
| 不碰任何文字框却被改的线 | 0 |

`u2_topology_changes.csv` 列出 4,308 项变化（对象 ID、坐标、原因、状态）：

- **FAIL 11 项**：底面吸收的残影面有一部分在文字框外。原因已确认：残影规则是"面积 ≥ 50% 在框内"，16 个被合并的残影面另一部分伸出框外 +1px，共 28.7 px²。要修正需要把规则改成"完全在框内"或"只合并框内部分"，本轮未改。
- **PENDING_REVIEW 26 项**：16 条被隔离线所属逻辑组在框外还有部分，10 条长于 25 px，都可能是穿过文字的真实地质线。
- 其余 4,214 项 PENDING_REVIEW 是按规则的合并或隔离，没有真值能判断对错；57 项 PASS。

## 7. T6 人工复核

- `u2_manual_review_queue.csv`：575 项，按类型：待定残影组 273、小碎面聚集区 240、低置信度文字 32、可能是真实线的隔离线 16、短线 12、OCR 错误 2。
- 可视化（本地，未推送）：`view_faces_x2.png`、`view_lines_x2.png`、`view_ocr_boxes_x2.png`（三个独立视图）和 `u2_problem_map_x2.png`（问题分布）。
- 编辑器可直接打开全图清除结果：加载 0.0 s，生成界面状态 1.0 s，状态 JSON 6 MB（12,995 面）。大图下的交互流畅度没有测。
- Oracle 外 95.5% 的区域建议做分层抽样复核（例如按颜色类和问题类型各抽若干处），而不是全图重描。

## 8. 回归保护

- 300×300 编辑器输入 `u2_B2c.gpkg` 的 SHA-256 不变；全图 B2c GPKG 审计前后哈希一致。
- 只新增 `experiments/STITCHVECTOR/sv_u2_full_*.py`、`experiments/STITCHVECTOR/u2_full/`、本报告；没有改 B2c、M2、OCR 或编辑器代码。

## 9. 性能说明

第一次审计跑了 11 分钟无输出被中止。原因：编辑器的 `text_apply()` 每处理一个文字框都对全层 17k 面做一次严格覆盖检查（约 8–9 s/次）。审计脚本在循环内改用局部检查，最后对结果做一次完整严格检查，总耗时降到 113 s。编辑器本身没改；如果以后在全图上交互使用框文字，这一步需要优化。

## 10. 本地产物（不能公开，未推送）

都在 `/Users/xiwei/geomap2arcgis/runs/stitchvector/u2_full/`：

| 文件 | SHA-256 |
|---|---|
| `u2_map.png` | `05cdada47beed21363e7d1bf11bfa308ec3d02d6b270d06b4074906c6dcd64c7` |
| `u2_full_B2c.gpkg` | `988df621966d1b3ea25843c51a27ee0b3d691c6b3bb83f979ebff654fa9a6fd7` |
| `u2_full_text_cleared.gpkg` | `9e9b87f683d20a4b06638427af078f97c655ba6b48ca5b1ac85c9a521401523d` |
| `view_faces_x2.png` | `80efacedb7be483cf983c5ddfe21ac8867c43932a94802175795266ccbaf88ac` |
| `view_lines_x2.png` | `f46b821eea4abb3308d2e433b0125b5b83fb6d3ac0bc76a1c63fefeb84a9d1c9` |
| `view_ocr_boxes_x2.png` | `c2812726360f0ed221342e8ad4d83a09d6af366caa6ead2e3592ece958901718` |
| `u2_problem_map_x2.png` | `7841fb4c75abdf5a925294d80ba86aa67fd155f46eec1fe18d17773e86506620` |

## 11. 复现与打开

```bash
cd ~/geomap2arcgis/.claude/worktrees/sv-u2-full
~/geomap2arcgis/.venv-sv/bin/python experiments/STITCHVECTOR/sv_u2_full_build.py   # 全图 B2c，约 17 s
~/geomap2arcgis/.venv-sv/bin/python experiments/STITCHVECTOR/sv_u2_full_audit.py   # 审计 + 文字清除，约 2 min（需先有 u2_ocr_full.json）
```

在编辑器中打开（任选其一）：

```bash
# 全图 B2c 原始结果
cd ~/geomap2arcgis/.claude/worktrees/sv-editor-text && ~/geomap2arcgis/.venv-sv/bin/python -m tools.stitchvector_editor.server --image ~/geomap2arcgis/runs/stitchvector/u2_full/u2_map.png --gpkg ~/geomap2arcgis/runs/stitchvector/u2_full/u2_full_B2c.gpkg --out-dir ~/geomap2arcgis/runs/stitchvector/u2_full/review --port 8810
# 全图自动文字清除结果
cd ~/geomap2arcgis/.claude/worktrees/sv-editor-text && ~/geomap2arcgis/.venv-sv/bin/python -m tools.stitchvector_editor.server --image ~/geomap2arcgis/runs/stitchvector/u2_full/u2_map.png --gpkg ~/geomap2arcgis/runs/stitchvector/u2_full/u2_full_text_cleared.gpkg --out-dir ~/geomap2arcgis/runs/stitchvector/u2_full/review --port 8811
```
