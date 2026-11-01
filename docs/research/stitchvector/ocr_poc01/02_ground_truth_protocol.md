# 02 真值协议（T1）

## 当前状态：`AGENT_DRAFT`，未经人工复核

按用户指示（"你先识别，我之后来复核"），真值由 agent 起草，**全部标为 `AGENT_DRAFT`**。在人工复核前，G3 不算通过，本轮所有准确率都是暂定值。

| 文件 | 内容 |
|---|---|
| `experiments/STITCHVECTOR/ocr_poc01/truth/u2_text_draft.tsv` | 起草原始记录（文字、框、类别、备注） |
| `experiments/STITCHVECTOR/ocr_poc01/truth/build_truth.py` | 把 TSV 转成标注规范 JSON |
| `experiments/STITCHVECTOR/ocr_poc01/truth/u2_text_truth.json` | 142 个文字对象 |
| `experiments/STITCHVECTOR/ocr_poc01/truth/u2_negatives.json` | 57 个非文字负样本 |

## 1. 起草方法

1. U2 地图（805×780）切成 25 块 180×180（步长 160，重叠 20 px），放大 4 倍，叠 10 px 网格。
2. **起草用的图块不叠加任何模型框**。逐块读出文字内容和像素框，写进 TSV。
3. 地层代号的写法对照图例（`work.png` 右侧）确认，例如 Pt₁L、J₁y、J₂d、Ar₂E、Є-O。
4. 合并重叠图块里的重复记录（同文字且 IoU > 0.3），共 144 条 → 142 条。
5. 生成 24 张缩略图联系表（`runs/ocr_poc01/truth_draft/sheet_*.png`，本地），抽查了第 0、1 页框与文字是否对齐。

起草前我看过一次三个引擎的合并候选列表（`scratch/candidates.json`）和叠框图块，用来确认引擎能跑通。这可能让起草偏向模型已检出的文字。为减少这种影响，正式起草用的是不叠框的新图块，并且逐块扫完整幅地图，包括没有模型框的区域。仍有 15 个真值三个引擎都没检出（多为小号产状数字），说明起草不只覆盖模型检出的部分。这一点需要复核人知情。

## 2. 覆盖

| 类别 | 数量 | 含特殊符号/下标 | 与地质线交叉 |
|---|---|---|---|
| GEOLOGICAL_CODE 地层代号 | 55 | 32（Є、₁₂₃） | 见下 |
| CHINESE_PLACE_NAME 中文地名 | 39 | 0 | |
| NUMERIC_ATTITUDE 产状数字 | 28 | 0 | |
| LATIN_LABEL 剖面/采样点（A、B′、S1…） | 16 | 部分含 ′ | |
| NUMERIC_SCALE 比例尺 | 3 | 0 | |
| MIXED_ANNOTATION（图7a） | 1 | 0 | |
| 合计 | **142** | 32 | **22**（B2c 线长 ≥ 25 px 且穿出框，自动预填） |

方向：全部 HORIZONTAL。U2 上没有发现明显倾斜或旋转的文字，所以本轮**没有测旋转文字**，NOT_EVALUATED。

负样本 57 个，都与任何真值框（外扩 3 px）不重叠：

| 类型 | 数量 | 选取方式 |
|---|---|---|
| LINE_RANDOM | 30 | 随机选 B2c 线，沿线随机取点，18×18 框，种子 20261101 |
| LONG_LINE | 15 | 只从长度 ≥ 60 px 的线（多为断层、界线）取点，种子 7 |
| AREA_RANDOM | 10 | 地图内随机位置 |
| SYMBOL_PICKED | 2 | 人工挑的居民点圆圈；原计划 24 个，22 个因与文字框过近被剔除 |

负样本偏线条，符号类只有 2 个，"符号误检为文字"这一项样本不足。

## 3. 字段

每个对象符合任务给出的规范：`sample_id, image_id, polygon（原图像素）, raw_text, normalized_text（NFC，不做纠正）, category, orientation, overlaps_geological_line, review_status`，另加 `has_special_symbol`、`note`、`revision`（修订记录：rev、by、date、action）。

## 4. 人工复核流程（待执行）

1. 打开可视化页面（见 `03_benchmark_results.md` 第 6 节），勾选"人工真值"，表格选"全部真值"，逐行点击检查文字和框。
2. 在 `u2_text_truth.json` 中对每个对象：内容正确则把 `review_status` 改为 `HUMAN_VERIFIED`；需要改的直接改 `raw_text`/`polygon`，并在 `revision` 追加 `{"rev": 2, "by": "<复核人>", "date": "...", "action": "..."}`；无法判断的标 `PENDING_HUMAN`。
3. 补标漏掉的文字（尤其小号数字）和更多符号类负样本。
4. 重跑 `benchmark_runner.py`、`fusion_eval.py`、`safety_audit.py`，结果才算 G3 下的正式数字。

起草时已标出的不确定项（`note` 字段）：`4`（左侧有模糊数字，可能是 84 或 54）、`马坊镇` 左边界、`S4` 右边界、图边被裁的 `T` 和 `A′`、`云` 是否为地名。
