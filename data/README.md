# data（本地，不入库）

建议结构：

```
data/
  raw/          原始扫描图（不入库）
  labels/       标注真值 GeoPackage（不入库）
  manifests/    入库：每张图一条元数据记录
```

`data/manifests/maps.csv` 字段：`map_id, file_name, sha256, source, sheet_no, scale, crs, scan_dpi, split(dev|calib|holdout), license_status, notes`

`split=holdout` 的图幅在开发期间封存，只在里程碑评测时使用。
