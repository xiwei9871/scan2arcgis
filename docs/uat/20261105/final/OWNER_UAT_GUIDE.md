# OWNER_UAT_GUIDE — 集中人工验收指南

## 环境准备（2 分钟）

```bash
cd /Volumes/LexarDev/Dev/geomap2arcgis/.claude/worktrees/sv-v02
# 1. Studio（推荐验收入口，含项目管理+编辑器）
/Volumes/LexarDev/Dev/geomap2arcgis/.venv-sv/bin/python -m tools.stitchvector_studio.server \
    --workspace /tmp/uat_studio_ws --port 8820
# 浏览器打开 http://127.0.0.1:8820/
# 2. 或独立编辑器（加载已清理 U2 工程）
/Volumes/LexarDev/Dev/geomap2arcgis/.venv-sv/bin/python -m tools.stitchvector_editor.server \
    --image /tmp/closeout_u2/map.png --gpkg /tmp/closeout_u2/in.gpkg \
    --out-dir /tmp/uat_out --port 8791
```

- Studio：新建项目→上传 `runs/stitchvector/u2_full/u2_map.png`→选 legacy-b2c-v01→开始矢量化（约 2 分钟）。
- 已备好的工程：`/tmp/closeout_studio/ws/projects/p-20261105-170725-064dc2`（17,047 面+148 文字，含版本 v001/v002 与草稿导出）。

## 推荐验收顺序（对照 checklist）

1. **路径 A OCR 审核**：勾选「审核模式」→红框=待审→点击文字→面板改/确认→自动下一项；只看待审过滤；保存版本不被阻断。
2. **路径 B 碎面**：选面点大面→「碎面筛选」调阈值→加入选区→预览合并（绿=将并，红=冲突警示）→按预览合并或归为同组→⌘Z 撤销。
3. **路径 C 残影**：选文字→「残影建议」→逐条勾选→确认；三态核验 A/B/C 对照原图与矢量。
4. **路径 D 窄面/线**：「端点接线」点断口两端→确认补线；「补画线」手绘+吸附；「拆分线」沿切点；线转面。
5. **路径 E 导出**：框 ROI→ROI 审计→裁剪预览→保存版本选 keep/clip→正式导出（应被门禁拒）→勾草稿导出→GPKG/SHP 下载→回读验证。

## 需要您指认的真实缺陷位置

- A05/A33：请指认 1-2 处实际漏检/被吞的窄面，用「补画线→线转面」当场修复验证。
- A09：若找到确定属于同一地质体的破碎邻面，验证几何合并（否则逻辑归组已足够）。
- E02：请指认明显漏检文字，用「框文字」局部重识别或「加文字」手动补。

## 判定标准

- 每项勾选：功能可达、步骤直观、结果正确、可撤销、可保存重开、不破坏原数据。
- 发现问题请记录：位置坐标、操作序列、期望 vs 实际。
