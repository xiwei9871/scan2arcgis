# D0 数据规范 v0.1

状态：DESIGN，分支 `design/d0-e1-e4`。D0 是 E1–E4 以及以后所有识别器共用的数据与评估基础，不属于某一个实验。

## 1. 设计原则

1. **预测与真值分开存放**，格式相同，来源字段不同。评估工具只读这两类文件，不依赖任何识别代码。
2. **每个要素一条完整记录**：几何、类别、置信度、来源、模型版本、审核状态、质量评价。从第一天起就有这些字段，旧算法的缺失值必须显式标记，不能留空或猜测。
3. **不伪造概率**：没有经过校准的分数一律标为 `UNCALIBRATED`，只放在 `raw_score` 中，`calibrated_p_correct` 必须为空。校验器强制执行。
4. **按图幅管理数据切分**，`holdout` 图幅在开发期间封存。
5. **门槛有来源**：任何通过/失败判断都要引用 `thresholds` 注册表中的一项，并写明来源；没有来源就是 `UNSET`，报告只给数值，不给结论。

## 2. 坐标约定

- 识别与评估的标准坐标是**原始全分辨率扫描图的像素坐标**：原点在左上角像素的左上角，x 向右，y 向下，单位为像素。
- GeoPackage 中像素层不设地理 CRS（`srs_id = 0`，未定义笛卡尔坐标）。
- 预测结果若在缩放图上产生，必须由适配器换算回原图像素，并在 `run_manifest` 中记录 `analysis_scale`。旧系统有 `input_image_px`、`source_image_px`、`inner_frame_original_pixels` 等多种空间（已在旧代码中确认），E1 适配器必须逐一核对。
- 地理坐标只在 E4 和导出阶段出现，由配准结果统一变换，识别器不直接输出地理坐标。

## 3. 文件结构

```
data/
  manifests/maps.csv                       # 入库：图幅清单（见 §4）
  manifests/dataset_<version>.json         # 入库：数据集版本（图幅列表 + 切分 + 标注文件哈希）
  raw/<map_id>/<file>                      # 不入库：原始扫描图
  labels/<map_id>/labels.gpkg              # 不入库：真值
  labels/<map_id>/legend.json              # 不入库：真值图例字典
  labels/<map_id>/checkpoints.csv          # 不入库：配准检查点（E4）
runs/<run_id>/
  run_manifest.json                        # 一次运行的完整来源记录
  <map_id>/predictions.gpkg                # 预测结果
  <map_id>/legend.json                     # 本次运行使用的图例
reports/<eval_id>/report.json, report.md   # 评估报告
```

GeoPackage 图层（真值与预测相同）：

| 图层 | 几何 | 内容 |
|---|---|---|
| `geologic_units` | Polygon/MultiPolygon | 地层、侵入岩（`feature_class` 区分） |
| `contacts` | LineString | 接触界线 |
| `structures` | LineString | 断层及其他构造线 |
| `mineral_points` | Point | 矿种点 |
| `eval_regions` | Polygon | 标注范围（L1 局部 ROI 或 L2 全幅图廓），评估只在范围内进行 |

## 4. 图幅清单字段（`maps.csv`）

`map_id, file_name, sha256, source, sheet_no, scale_denominator, crs_hint, scan_dpi, width_px, height_px, style_group, split, license_status, publishable, notes`

- `split`：`dev`（可调参）/ `calib`（只用于置信度校准）/ `holdout`（封存）。
- `style_group`：图式分组（出版单位、年代、比例尺组合），用于分层统计和分布外检测。
- `license_status`：`unconfirmed` / `internal_only` / `public_ok`。`publishable=false` 的图幅不得出现在任何入库文件中，只能出现 `map_id` 和哈希。

## 5. 要素记录字段

所有图层共用以下属性列。JSON 结构的列在 GeoPackage 中以 TEXT 存储 JSON 字符串。机器可读定义见 `schemas/d0/feature_record.schema.json`。

### 5.1 身份与类别

| 字段 | 类型 | 说明 |
|---|---|---|
| `feature_id` | text | 运行内唯一 |
| `map_id` | text | 图幅 |
| `record_kind` | enum | `prediction` / `ground_truth` |
| `feature_class` | enum | `stratigraphic_unit` / `intrusive_unit` / `contact` / `fault` / `structure_other` / `mineral_point` |
| `legend_code` | text | 图例代号；未绑定为空 |
| `legend_entry_id` | text | 对应图例字典条目 |
| `class_candidates` | json | top-k 候选 `[{legend_code, raw_score}]`，没有则 `[]` |

### 5.2 置信度

| 字段 | 类型 | 说明 |
|---|---|---|
| `calibration_status` | enum | `UNCALIBRATED` / `CALIBRATED` / `NOT_APPLICABLE`（真值） |
| `raw_score` | real/null | 识别器原始分数，原样保存 |
| `raw_score_semantics` | text | 分数含义，例如 `legacy_heuristic:boundary.confidence`、`softmax_max` |
| `calibrated_p_correct` | real/null | 只有 `CALIBRATED` 时可以有值，取值 [0, 1] |
| `p_error` | real/null | 误差预测模型输出，同样要求 `CALIBRATED` |
| `calibration_ref` | json/null | `{calibrator_id, method, calib_dataset_version, fitted_at}`；`CALIBRATED` 时必填 |

### 5.3 来源与版本

| 字段 | 类型 | 说明 |
|---|---|---|
| `producer_kind` | enum | `legacy_rule` / `model` / `hybrid` / `human` / `import` |
| `producer_name` | text | 例如 `legacy.boundary`、`unet_fault_v0` |
| `producer_version` | text | 代码 commit 或模型版本 ID |
| `model_version_id` | text/null | 有模型权重时必填 |
| `run_id` | text | 关联 `run_manifest.json`（输入哈希、参数哈希、环境） |
| `derived_from` | json | 上游要素 ID 列表，例如由面公共边生成的接触线 |

### 5.4 审核状态

| 字段 | 类型 | 说明 |
|---|---|---|
| `review_status` | enum | `UNREVIEWED` / `AUTO_ACCEPTED` / `HUMAN_CONFIRMED` / `HUMAN_CORRECTED` / `HUMAN_REJECTED` |
| `reviewer_role` | text/null | `geologist` / `annotator` / `qa`（不记录个人姓名） |
| `reviewed_at` | text/null | UTC ISO 8601 |
| `supersedes` | text/null | 人工修正后指向被替换的要素 ID |
| `review_sampling` | enum/null | `risk_queue` / `random_audit`；只有 `random_audit` 的结果可用于估计自动接受错误率 |

### 5.5 质量评价与决策

| 字段 | 类型 | 说明 |
|---|---|---|
| `hard_checks` | json | `[{check_id, status: PASS/FAIL/NOT_RUN, detail}]` |
| `geometry_score` | real/null | 几何质量软分数，同样受 `calibration_status` 约束语义 |
| `quality_signals` | json | 原始信号，例如与图例色差、残差、边缘一致性；误差预测模型的特征来源 |
| `decision` | enum | `AUTO_ACCEPT` / `AUTO_RETRY` / `HUMAN_REVIEW` / `BLOCKED` / `NONE` |
| `decision_policy_id` | text/null | 产生决策的策略版本 |

### 5.6 真值专用字段

`annotator_role`、`label_status`（`draft` / `reviewed` / `adjudicated`）、`label_method`（`from_scratch` / `corrected_from_prediction` / `imported_vector`）、`double_annotated`（bool）。

`label_method = corrected_from_prediction` 的真值会偏向产生它的算法，报告中必须分组列出，`holdout` 中至少一部分图幅应为 `from_scratch` 或 `imported_vector`。

## 6. 校验规则（校验器强制执行）

| 编号 | 规则 |
|---|---|
| V1 | `calibration_status = UNCALIBRATED` ⇒ `calibrated_p_correct`、`p_error` 为空，`calibration_ref` 为空 |
| V2 | `calibration_status = CALIBRATED` ⇒ `calibration_ref` 完整，且 `calib_dataset_version` 不能包含任何 `holdout` 图幅（评估时检查） |
| V3 | `decision = AUTO_ACCEPT` ⇒ `calibration_status = CALIBRATED`，且所有 `hard_checks` 为 `PASS` |
| V4 | `producer_kind = legacy_rule` ⇒ `calibration_status = UNCALIBRATED`（旧算法没有校准器） |
| V5 | `record_kind = ground_truth` ⇒ `calibration_status = NOT_APPLICABLE`，`producer_kind ∈ {human, import}` |
| V6 | `review_status = AUTO_ACCEPTED` ⇒ `decision = AUTO_ACCEPT` |
| V7 | `model_version_id` 非空 ⇔ `producer_kind ∈ {model, hybrid}` |
| V8 | 分数类字段取值在 [0, 1] 或为空 |

## 7. 数据集版本与防泄漏

- `dataset_<version>.json` 记录图幅列表、切分、每个真值文件的 SHA-256。任何标注改动都产生新版本。
- 评估报告必须写明数据集版本与 `run_id`。
- 切分以图幅为单位，同一图幅的局部块不能跨切分。
- `holdout` 只能由评估命令在里程碑节点读取一次，读取记录写入报告。
- 人工复核得到的修正只进入 `dev` 训练数据或失败案例库，不进入 `calib` / `holdout`。

## 8. 分层数据（L0–L3）

| 层 | 内容 | 用途 | 首批来源 |
|---|---|---|---|
| L0 | 旧仓库 2 张样图与旧标注（迁移为 D0 格式，标记 `label_status=draft`） | 回归、管线冒烟 | 旧 `datasets/recognition_baseline_v1` |
| L1 | 局部 ROI 精确标注，覆盖近色地层、经纬网、图框、断层、矿种密集区等难例 | 失败模式分析、开发集 | 先从 2 张样图开始，再扩到新图幅 |
| L2 | 少量全幅标注 | 完整性、拓扑、导出 | 优先使用已有数字化矢量（如可获取） |
| L3 | 从未参与调参的新图幅 | 泛化与校准评估 | 需项目负责人提供 |

数量不预先固定，由指标置信区间决定（见 `evaluation_framework.md` §5）。
