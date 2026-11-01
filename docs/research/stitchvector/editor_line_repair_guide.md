# 绣娘编辑器：线修复 + 线角色 + Legend + 左右对照 操作指南

## 启动（Mac 终端）

```bash
cd ~/geomap2arcgis/.claude/worktrees/sv-editor-lr && ~/geomap2arcgis/.venv-sv/bin/python -m tools.stitchvector_editor.server --image ~/geomap2arcgis/runs/stitchvector/editor_v01/inputs/u2_original.png --gpkg ~/geomap2arcgis/runs/stitchvector/editor_v01/inputs/u2_B2c.gpkg --out-dir ~/geomap2arcgis/runs/stitchvector/editor_lr/my_edits --port 8791
```

浏览器打开 http://127.0.0.1:8791/ 。原 GPKG 只读，保存一律写成 `--out-dir` 里的新文件。

## 左右对照

勾选"左右对照"：左边是原图（只读），右边是矢量结果（可编辑）。在任一侧滚轮缩放、拖动平移，两侧同步；鼠标位置在两侧都有十字标记。

## 一次完整的局部修复

1. **补画线**：工具"补画线"，在右侧逐点单击，双击结束。新线角色默认 `UNKNOWN`。
2. **设定线角色**：工具"选线"点中这条线，在"线角色"下拉框选 `COVER`（覆盖线）或 `SPLIT`（分割线），点"设定角色"。
3. **COVER：清理线下碎面**
   - 工具"碎面修复刷"，沿线刷一下。
   - 预览颜色：绿 = 建议并入，蓝 = 保留，橙 = 待定。
   - 点"执行修复"，只合并绿色项。修复后文档一旦再改动，旧预览自动作废，需重新刷。
4. **SPLIT：切开跨界面**
   - 线要从面的一侧边界画到另一侧。
   - 选中这条线，点"预览切面"，黄色轮廓是切开后的各块；点"执行切面"。
   - 线是 `UNKNOWN` 或 `COVER` 时会拒绝切面。
5. **套用 Legend**：选中线（或面），在图例下拉框选一项，点"应用图例"。齿形的间距、大小、朝向（左/右）可在下方改，点"保存样式"立即重绘。套用图例只改样式，不动中心线和面顶点。
6. **保存**：填文件名，点"另存为新 GPKG"。保存会先写临时文件并回读校验，校验失败不会留下文件，界面保持"未保存"。

撤销 ⌘Z，重做 ⇧⌘Z。

## 注意

- 角色由你判断，编辑器不推断地质含义。
- 齿形和虚线只用于显示，不写成几何；QGIS 打开时看不到这些样式。
- GPKG 用像素坐标、没有 CRS，QGIS 会提示坐标系未定义。
