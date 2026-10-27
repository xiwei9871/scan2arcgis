# 自动矢量化最小闭环（S2A-R1 任务 E）

脚本：`experiments/R1_auto_vectorization/run_vectorize.py`。

```
扫描图（+ 图例区） → 自动检测图例色块 → 逐图分类器 → 栅格分区
 → 多边形（rasterio.features.shapes，天然无重叠无缝隙）
 → 接触线 = 相邻不同类面的公共边（与面完全一致）
 → 断层候选（深色墨迹骨架，规则占位）
 → D0 字段（来源、版本、UNCALIBRATED 分数、硬约束、决策、审核状态）
 → GeoPackage：geologic_units / contacts / structures / review_regions
```

## 1. 坐标与“未配准”标记

- 坐标为原始图像（或明确记录的工作图）像素坐标，y 向下。
- GeoPackage **不写 CRS**；每个要素带 `coord_space=image_px_unreferenced`、`geo_referenced=false`。测试 `test_gpkg_export_is_unreferenced_and_d0_valid` 检查读回后 CRS 为空。
- 真实图的工作图为“地图 ROI + 图例条”拼接，`work.json` 记录 `roi_orig` 与 `scale`，可换算回原图：`x_orig = roi_x + x_work / scale`。未来接入配准时，只需在导出前加一步“像素 → 地理坐标”变换，不影响识别。

## 2. 结果

| 地图 | 面 | 接触线 | 断层候选 | 无效几何 | 面重叠面积 | 覆盖率 | 总耗时 s |
|---|---|---|---|---|---|---|---|
| clean_s0（合成） | 41 | 89 | 20 | 0 | 0.0 | 1.0 | 2.1 |
| gm2 ROI | 250 | 547 | 4 | 0 | 0.0 | 0.99999963 | ≈10 |
| u2 | 137 | 313 | 7 | 0 | 0.0 | 0.99999841 | ≈1 |
| u3 | 223 | 458 | 13 | 0 | 0.0 | 1.0 | 4.2 |
| u1 | 96 | 184 | 1 | 0 | 0.0 | ≈1.0 | 1.2 |

数值来源：`experiments/R1_auto_vectorization/results/real_maps_summary.json` 中的 `vectorization` 字段。

## 3. 检查项

| 检查 | 结果 | 证据 |
|---|---|---|
| 面为有效 Polygon | 是（4 张真实图 0 个无效） | `topology.invalid` |
| 线为 LineString | 是 | GeoPackage 图层几何类型 |
| 相邻面边界一致 | 是：分区天然无重叠无缝隙；接触线取自公共边 | `overlap_area_px = 0` |
| 图例属性关联 | 部分：关联到色块 ID（`S00`…），**未关联到真实地层代号**（中文代号 OCR 未实现） | `legend_code` 字段 |
| 保留来源与审核状态 | 是：`producer_*`、`run_id`、`calibration_status=UNCALIBRATED`、`review_status=UNREVIEWED`、`decision` | D0 校验通过后才写入 |
| GIS 中查看与编辑 | 可用 pyogrio 读回（测试）；本轮未在 QGIS/ArcGIS 中人工打开 | 待你本地确认 |

## 4. 已知问题

1. **碎片化**：gm2 ROI 一个 3100×3500 像素区域产生 250 个面，远多于实际地质单元数。原因：近色类别、注记、断层符号和小区域。需要“图例类别合并”和“注记移除”。
2. **简化**：shapely 2.0.2（为兼容旧代码而固定）没有 `coverage_simplify`，本轮多边形未简化，顶点较多。升级到 shapely ≥ 2.1 后可启用拓扑保持简化（代码已预留）。
3. **断层**：只有规则版候选，真实图上数量很少（1–7 条），明显漏检。
4. **ArcGIS 兼容**：未验证。像素坐标、无 CRS 的 GeoPackage 在 ArcGIS 中可能被当作未知坐标系，需要你在 ArcGIS 中打开确认。

## 5. 如何查看（本地）

```bash
# 结果在 runs/real/<map>/out/，不入库
ogrinfo runs/real/u3/out/work_r1.gpkg
# 在 QGIS 中直接拖入 .gpkg；同目录的 *_r1_overlay.jpg 为叠加预览
```
