# DEPLOYMENT_GUIDE — 部署说明（本地/单用户）

## 状态
`PRODUCTION_UNCHANGED` — 本轮不合并 main、不部署生产。以下为将来部署/验收时参考。

## 依赖
- Python 3.11 + 项目 venv：`/Volumes/LexarDev/Dev/geomap2arcgis/.venv-sv`（shapely/geopandas/pyogrio/Pillow/numpy）。
- OCR：RapidOCR 子解释器（`tools/stitchvector_editor/ocr_cli.py`，自动探测 `_ocr_python`）；无引擎时局部识别自动降级为手工输入。
- 浏览器：Chromium 系。

## 启动
```bash
# Studio（全功能入口）
python -m tools.stitchvector_studio.server --workspace <工作区目录> [--port 8820]
# 独立编辑器
python -m tools.stitchvector_editor.server --image <扫描图> --gpkg <矢量GPKG> --out-dir <保存目录> [--port 8765]
```
- 均只绑 127.0.0.1；单用户单机。
- Studio 工作区结构：projects/<pid>/{source, working, versions, exports}。

## 数据保护
- 原始 U2 扫描与 GPKG 属受保护资产：不放公开仓库、不进 git。
- 截图含地图内容同样只留本地。

## 上线前待办
- 地理配准（当前 PIXEL_SPACE）。
- 多用户/并发与持久化会话（如需要）。
- 治理门脚本入 worktree 后补跑 s2a_gates.py。
