# 绣娘文字图层：视觉验收交付（u2，Є-O / Ar₂E / 云）

状态：等待人工 UAT。本文件只描述"能否看见"的证据，不是地质正确性的结论。

## 1. 上一轮 UAT 失败的原因

上一轮启动命令加载的是原始 `u2_B2c.gpkg`（665 面、35 线、0 文字），所以切换文字层时什么都不会变。界面也没有显示加载的是哪个文件。

整改：页面顶部现在显示"已加载：文件名"和 面 / 线 / 文字 / 隔离线 / 待定碎面 五个数字，一眼能分清是否载入了编辑成果（`tools/stitchvector_editor/static/app.js`，`core.py` 的 `state()` 增加 `pending`）。

## 2. 现有 GPKG 的身份（全部只在本地 `runs/stitchvector/`）

| 文件 | 面 / 线 / 文字 | 身份 | 能否作为示范 |
|---|---|---|---|
| `editor_v01/inputs/u2_B2c.gpkg` | 665 / 35 / 0 | 原始 B2c，只读，SHA-256 `7d78a711…` | 基线 |
| `editor_text/uat/u2_text_layer.gpkg` | 534 / 28 / 3 | 自动化实验输出。Ar₂E 待定组按"颜色最近"脚本归属 | **不能**：归属未经人工确认，红色面归属已判为不通过 |
| `editor_text/ui/text_ui_e2e.gpkg` | 613 / 31 / 2 | 浏览器测试输出（只有 Є-O、云） | 否 |
| `editor_text/uat_ui/text_uat_e2e.gpkg` | 599 / 33 / 1 | 浏览器测试输出（演示一组归属、一组跳过） | 否 |
| `editor_text/demo/u2_text_demo.gpkg` | **550 / 28 / 3** | **本轮示范成果**，脚本 `experiments/STITCHVECTOR/sv_text_demo.py` 可复现，SHA-256 `11b1cd1a…` | 是，人工待验收 |

示范成果的规则：三个文字框用编辑器的默认行为处理。只并入"只挨着一个底面"的碎面；Ar₂E 在粉红面和红色面交界处的待定碎面**一组都没有归属**，保留原样等你决定。没有使用颜色最近或任何自动归属。

## 3. 截图（真实浏览器，Playwright 驱动编辑器页面）

固定条件：同一视口 1500×900、左右对照关闭、同一缩放（4.5 屏幕 px / 图像 px）和偏移；右侧原图叠加关闭，面层透明度 100%，面层和线层都开，隔离线层关闭。两个视图：`top`（偏移 20,10，含 Є-O 和 云）、`bot`（偏移 20,−700，含 Ar₂E）。

| 编号 | 内容 | 加载的文件 | 文件（`runs/stitchvector/editor_text/shots/`） |
|---|---|---|---|
| 1 | 原始 PNG | — | `top_1_original_png.png`、`bot_1_original_png.png` |
| 2 | 原始 B2c 纯矢量 | `u2_B2c.gpkg` | `top_2_b2c_vector.png`、`bot_2_b2c_vector.png` |
| 3 | 编辑后纯线面，文字关 | `u2_text_demo.gpkg` | `top_3_edited_text_off.png`、`bot_3_edited_text_off.png` |
| 4 | 编辑后线面加文字，文字开 | `u2_text_demo.gpkg` | `top_4_edited_text_on.png`、`bot_4_edited_text_on.png` |
| 放大 | 每个文字四联对照（1→4） | — | `zoom_EO.png`、`zoom_Ar2E.png`、`zoom_yun.png` |

页面整页截图 `bot_2_b2c_vector_fullpage.png` 和 `bot_4_edited_text_on_fullpage.png` 可以看到顶部加载信息分别是"u2_B2c.gpkg 面 665 线 35 文字 0"和"u2_text_demo.gpkg 面 550 线 28 文字 3 隔离线 7 待定碎面 16"。

**GitHub 附件：未交付。** `gh` 命令行不能上传 Issue/PR 评论附件（这个功能只在网页端拖拽上传时可用）。Release 附件可以上传，但那会在公开仓库发布一个版本，和"不发布正式版本"的边界冲突，所以没有做。截图没有进入 git 提交，也没有绕过 pre-push 钩子。SHA-256 见 `experiments/STITCHVECTOR/text_layer/artifacts_sha256.txt` 和 `visual_diff.json`。如果你同意，可以把这几张图拖进一个 Issue，或者允许我建一个草稿 pre-release 来存放它们。

## 4. 像素差异检查（`experiments/STITCHVECTOR/text_layer/visual_diff.json`）

截图 2（原始 B2c）对比截图 3（编辑后，文字关）：

| 文字 | 框内屏幕像素 | 发生变化 | 比例 | 截图 3→4 文字层带来的变化 |
|---|---|---|---|---|
| Є-O | 11,088 | 2,750 | 24.8% | 1,863 |
| 云 | 5,776 | 1,546 | 26.8% | 1,127 |
| Ar₂E | 30,420 | 3,625 | 11.9% | 5,274 |

几何层面的残影（`demo_geometry_check.json`，以及框内统计）：

| 文字 | 框内小面 前 → 后 | 其中深色（字形） | 框内覆盖字形的线 前 → 后 |
|---|---|---|---|
| Є-O | 40 → 0 | 10 → 0 | 2 → 0 |
| Ar₂E | 81 → **16** | 28 → **2**（27 px²） | 2 → 0 |
| 云 | 10 → 0 | 4 → 0 | 2 → 0 |

- Є-O 和 云：文字关闭时框内不再有字形残影，文字打开时显示一个独立文字对象。
- **Ar₂E：在截图 3 里仍能看到部分残影。** 这是待定的 16 个碎面（其中 2 个深色），按你的要求没有合并。它们要你在编辑器里逐组决定归属后才会消失。

框外检查：
- 几何：框外扩 1 px 以外，面的颜色面积变化 0 px²；不碰任何文字框的线，改动 0 条。
- 屏幕：top 视图框外 0 个像素变化。bot 视图框外有 13 个屏幕像素变化超过 10 级（最大 34 级），都落在 Ar₂E 框右下方 L23、L26、L27 三条线经过的位置。这些像素下面的面仍然是同一个粉红面，三条线的坐标和颜色也没变，所以是重画时多边形边缘抗锯齿的差别，不是对象被改。请在放大图里亲眼确认。

## 5. 隔离线

7 条线移入 `text_residue_lines`（Є-O：L1、L31；Ar₂E：L22、L24、L25；云：L6、L33）。它们都离 Oracle 已描地质线 2.5 px 以上，但 Oracle 没有描文字和小符号，所以不能证明全都不是地质线。编辑器侧栏有编号、高亮和"恢复为地质线"按钮。

## 6. 两条启动命令

**A. 打开已完成文字编辑的示范成果**（看效果用；8799 端口我已经启动了一份，也可以自己起）：

```bash
cd ~/geomap2arcgis/.claude/worktrees/sv-editor-text && ~/geomap2arcgis/.venv-sv/bin/python -m tools.stitchvector_editor.server --image ~/geomap2arcgis/runs/stitchvector/editor_v01/inputs/u2_original.png --gpkg ~/geomap2arcgis/runs/stitchvector/editor_text/demo/u2_text_demo.gpkg --out-dir ~/geomap2arcgis/runs/stitchvector/editor_text/demo_edits --port 8799
```

页面顶部应显示：`已加载：u2_text_demo.gpkg … 面 550 线 28 文字 3 隔离线 7 待定碎面 16`。在这里可以继续处理 Ar₂E 的 16 个待定碎面。

**B. 从原始 B2c 开始人工编辑**（8800 端口已启动一份）：

```bash
cd ~/geomap2arcgis/.claude/worktrees/sv-editor-text && ~/geomap2arcgis/.venv-sv/bin/python -m tools.stitchvector_editor.server --image ~/geomap2arcgis/runs/stitchvector/editor_v01/inputs/u2_original.png --gpkg ~/geomap2arcgis/runs/stitchvector/editor_v01/inputs/u2_B2c.gpkg --out-dir ~/geomap2arcgis/runs/stitchvector/editor_text/my_uat --port 8800
```

页面顶部应显示：`已加载：u2_B2c.gpkg … 面 665 线 35 文字 0`。

两份都只读打开输入文件，保存一律另存为新文件。

## 7. 复现

1. `python experiments/STITCHVECTOR/sv_text_demo.py` 生成示范 GPKG（结果 `text_layer/text_demo.json`）。
2. 用上面两条命令分别在 8799、8800 启动编辑器。
3. 用 `playwright-cli run-code --filename` 运行 `tests/stitchvector_editor/shots_text_demo.js`，把 `__PORT__`、`__OUT__`、`__SHOTS__` 换成端口、输出目录和截图列表（视图参数见 `visual_diff.json` 的 `views`）。
4. `python experiments/STITCHVECTOR/sv_text_shots_diff.py` 计算像素差异。

## 8. 没有做的

没有改 B2c、M2 或历史结果，没有改 OCR，没有合并或部署。QGIS 中的文字显示仍未实测。"生成前先隔离文字"仍未实现。
