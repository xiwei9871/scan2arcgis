# StitchVector Editor V0.1 操作指南（Mac）

## 启动

在仓库目录（含 `tools/stitchvector_editor/` 的分支 `feature/stitchvector-editor-v01`）运行：

```bash
cd ~/geomap2arcgis/.claude/worktrees/sv-editor-v01 && ~/geomap2arcgis/.venv-sv/bin/python -m tools.stitchvector_editor.server --image ~/geomap2arcgis/runs/stitchvector/editor_v01/inputs/u2_original.png --gpkg ~/geomap2arcgis/runs/stitchvector/editor_v01/inputs/u2_B2c.gpkg --out-dir ~/geomap2arcgis/runs/stitchvector/editor_v01/my_edits
```

然后在浏览器打开 <http://127.0.0.1:8765/>。按 Ctrl-C 停止。

换合成图试用：把 `--image` 换成 `inputs/synth_7001.png`，`--gpkg` 换成 `inputs/synth_7001_B2c.gpkg`。

- 只监听本机 127.0.0.1，不对外开放。
- 打开的 GPKG 只读，不会被修改；保存一律写到 `--out-dir` 里的新文件。

## 界面

左侧是工具栏，右侧是画布。

| 操作 | 方法 |
|---|---|
| 缩放 | 鼠标滚轮 |
| 平移 | 右键拖动，或按住空格拖动 |
| 适应窗口 | "适应窗口"按钮 |
| 显示开关 | 原图 / 面层 / 线层复选框；面层透明度滑块 |

## 常用流程

**改一块面的颜色**
1. 选"选面"，点击面（Shift 点击加选）。
2. 选"吸管"，在原图上点正确的颜色。
3. 点"应用颜色"。

**改一整条线（逻辑组）**
1. 选"选线"，点击线。
2. 点"选整组线"。
3. 吸管取色 → "应用颜色"；在"线宽"填数字 → "应用线宽"。

**窄色带被存成了线（如 PN2）**
1. 按上一步选整组、改色、把线宽改成色带宽度。
2. 需要真正的面时，点"线转面（实验）"。结果若通不过拓扑检查会自动撤回并提示。

**线缺一段（如 PN1）**
1. "选线"选中线 → "拆分线"工具 → 在要断开的位置点一下。
2. "补画线"工具：逐点单击，双击结束；起点和终点会吸附到 3 px 内的已有线端点。补画前先选中一条线，新线会加入它的组。
3. 不需要的线："删除所选线"。

**合并碎面**
1. "选面"点一个面，Shift 点击相邻的面；或用"框选面"拖一个框；或点"扩展相邻同色面"。
2. 点"合并所选面"。不相邻的面不会被合并，会提示原因。

**撤销 / 重做**：按钮，或 ⌘Z / ⇧⌘Z。Esc 清除选择。

## 保存

在"保存"框填文件名（字母、数字、`._-`），点"另存为新 GPKG"。

提示会显示三项检查：回读与编辑一致、面层拓扑有效、原文件未变。同目录下还会生成 `*.edits.json`，记录每一步修改和前后差异。

标题旁的"● 未保存"表示有未保存的修改；有未保存修改时关闭页面会提示。

## 已知限制

- 不能移动单个节点。
- 线转面会在线端产生少量越过色带的面积，需要目测判断。
- "扩展相邻同色面"对颜色差别大的碎面效果差，碎面多时仍需逐个 Shift 点选。
- GPKG 是像素坐标、没有 CRS；在 QGIS 中打开会提示坐标系未定义。
