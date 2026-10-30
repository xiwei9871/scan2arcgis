# R4-C0.1b Work 1：不依赖官方标签的 GIS 导出（2026-10-30）

代码：`experiments/R4C0/r4c0_1b_export.py`。回归结果：`experiments/R4C0/r4c0_1b/export_regression.json`，9 项验证 `r4c0_1b/*_export_validation.json`。导出文件只保存在本地：`runs/r4c0_1b/export/`。
这是工程修正：不改变任何预测、区域图或评价结果。旧的导出脚本 `experiments/R4A/r4a2_2_export.py` 保持不变，历史结果都不改。

## 1. 问题

旧导出用 `ignore.npy` 裁剪范围，而 `ignore.npy` 来自官方 geo_A 的覆盖范围，所以导出这一步读取了官方标签。

## 2. 为什么不能简单换成图像白/黑掩膜

- GSJ GeoTIFF 没有 NoData 也没有 alpha 通道，rasterio 的 dataset_mask 显示全部像素有效。
- **真实地质单元可以是纯白的：** 13014 上，官方单元内部有 27,411 块纯白像素，最大的一块 4,309 px。用"去掉纯白"做掩膜会删掉真实单元。
- R4-A2.2 的 M0 内容掩膜还会腐蚀 9 px，会破坏细长结构。

## 3. 新规则（只用图像和预测，不删除任何区域）

- **导出范围 = 整幅图像。** 每个预测区域都导出。
- **图边空白候选：** 接触图像边界、且 90% 以上像素接近纯白（三个通道都 > 245）的区域，标为 `REVIEW_MARGIN`，可能是图廓外的空白。**只标记，不删除。**
- 区域编号、多边形、共享边界和属性的生成方式与原导出完全相同。

## 4. 回归结果

| 图 / 方案 | 区域图不变 | 导出像素比例 | 旧方法裁掉的像素（比例） | REVIEW_MARGIN 区域（像素） | 9 项检查 |
|---|---|---|---|---|---|
| 13014 M2_hybrid | ✓ | 100% | 176,018（1.68%） | 0 | 通过 |
| 13014 RAG_BOUNDARY_ONLY | ✓ | 100% | 176,018（1.68%） | 1（160,450） | 通过 |
| 15076 M2_hybrid | ✓ | 100% | 25,824（0.25%） | 0 | 通过 |
| 15076 RAG_BOUNDARY_ONLY | ✓ | 100% | 25,824（0.25%） | 0 | 通过 |

13014 上被标记的那个区域，与官方未覆盖的图边白区高度吻合：官方未覆盖区共 160,193 px，其中 94.9% 是纯白。所以新规则不读标签，也能把它找出来交给人复核。M2_hybrid 在 13014 上没有标出这个区域，因为它把这块白区并进了相邻单元。这是 M2_hybrid 自身的分割问题，与导出规则无关。

## 5. 复现

```bash
cd experiments/R4C0 && ../../.venv/bin/python r4c0_1b_export.py 13014 RAG_BOUNDARY_ONLY ../../runs/r4c0/gate4/13014_RAG_BOUNDARY_ONLY.npy ../../runs/r4c0_1b/export/13014/RAG_BOUNDARY_ONLY ../../runs/r4c0/pred_test/13014/B2/prob_right.npy prob
```
