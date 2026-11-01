# 文字图层操作指南

启动：

```bash
cd ~/geomap2arcgis/.claude/worktrees/sv-editor-text && ~/geomap2arcgis/.venv-sv/bin/python -m tools.stitchvector_editor.server --image ~/geomap2arcgis/runs/stitchvector/editor_v01/inputs/u2_original.png --gpkg ~/geomap2arcgis/runs/stitchvector/editor_v01/inputs/u2_B2c.gpkg --out-dir ~/geomap2arcgis/runs/stitchvector/editor_text/my_edits --port 8796
```

浏览器打开 http://127.0.0.1:8796/ ，面层透明度拉到 100 看真实颜色。

1. 点 **框文字**，在右侧矢量图上拖一个框把文字框住（例如 Ar₂E）。
2. 等约 1 秒，面板显示 OCR 候选，文字框里已预填。绿色 = 会并入底面的残影，橙色 = 待定。
3. 改成正确内容（例如把 `ArE` 改成 `Ar₂E`），可调字号、角度、颜色。
4. 有待定组时，按提示在输入框填 `组号:面号`（例如 `0:457,15:7`），只能填该组旁边的底面；不填就保持不动。
5. 点 **应用**。框里的残影面并入底面，框内短线移到隔离层（可恢复），生成一个文字对象。
6. 勾掉 **文字层** 检查面层和线层已无残影；勾上看文字位置。
7. 要修改：选中文字后改内容或字号，点 **修改文字**；可撤销、重做。
8. 另存为新 GPKG。原文件不会被改动。

---

## 人工验收操作（本轮新增）

1. 启动（终端）：
   `cd ~/geomap2arcgis/.claude/worktrees/sv-editor-text && ~/geomap2arcgis/.venv-sv/bin/python -m tools.stitchvector_editor.server --image ~/geomap2arcgis/runs/stitchvector/editor_v01/inputs/u2_original.png --gpkg ~/geomap2arcgis/runs/stitchvector/editor_v01/inputs/u2_B2c.gpkg --out-dir ~/geomap2arcgis/runs/stitchvector/editor_text/my_uat --port 8798`
   浏览器打开 http://127.0.0.1:8798/
2. 用"框文字"分别框 Є-O、云、Ar₂E。每框一次，在"文字"栏改成正确内容（OCR 只是候选）。
3. Ar₂E 框出现橙色待定组时，选"点选归属"：
   - 点一个橙色组 → 候选底面显示黄色轮廓；
   - 点你认为正确的底面 → 白色虚线是合并前、绿色实线是合并后；
   - 对照左侧原图，按"确认此组归属"或"跳过此组（保持待定）"。跳过或不处理的组都不会被合并。
4. 按"确认文字并清理残影"。
5. 三态核验：依次按 A、B、C。B 中检查是否还有字形残影、红色突出部；C 中检查文字位置和字号。
6. 隔离线列表：逐条"高亮"，对照原图；如果是真实地质线，按"恢复为地质线"。
7. 撤销/重做随时可用（⌘Z / ⇧⌘Z）。最后"另存为新 GPKG"，原文件不会被改动。
