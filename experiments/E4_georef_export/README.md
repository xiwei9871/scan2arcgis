# E4 配准与 GIS 导出独立精度验证

- 假设：当前配准与导出的位置误差在业务容差内（未验证）。
- 输入：2–3 张图，每张 ≥8 个不参与配准的独立检查点。
- 候选：旧系统配准；GDAL 原生 GCP 变换（gdal_translate -gcp + gdalwarp -order/-tps）；uncharted-ta1 georeferencing。
- 指标：检查点 RMSE 与最大误差（米、图上 mm）、CRS 正确性、QGIS/ArcGIS 打开与属性完整率。
- 成功标准：误差在业务容差内（容差待业务确认）。
- 失败后决策：先修配准，识别成果暂缓对外交付。
