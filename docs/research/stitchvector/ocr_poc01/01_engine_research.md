# 01 引擎调研

完整版本、模型、SHA-256 见 `experiments/STITCHVECTOR/ocr_poc01/results/engine_manifest.json`。运行设备：Apple M4、16 GB、macOS，均为 CPU（Surya 识别走 llama.cpp Metal）。

## 1. 测试配置

| 引擎 | 软件版本 | 模型 / 权重 | 推理框架 | 环境 |
|---|---|---|---|---|
| RapidOCR（基线） | rapidocr 3.4.5 | ch_PP-OCRv4 det+rec mobile ONNX，ch_ppocr_mobile_v2.0_cls | onnxruntime 1.23.2 | `.venv-ocr`（已有，未改） |
| PaddleOCR | paddleocr 3.7.0，paddlex 3.7.2，paddlepaddle 3.3.1 | PP-OCRv6_medium_det、PP-OCRv6_medium_rec、PP-LCNet_x1_0_textline_ori | Paddle Inference CPU | `runs/ocr_poc01/venvs/paddle` |
| Surya | surya-ocr 0.23.0，torch 2.15.0 | 检测 `text_detection/2025_05_07`；识别 `surya-ocr-2.5` GGUF Q8_0 + mmproj | 检测 torch；识别 llama.cpp 0.8.0 | `runs/ocr_poc01/venvs/surya` |
| mapKurator | — | — | — | NOT_TESTED（按任务要求只做模块分析） |

模型选择说明：

- PaddleOCR 3.7.0 在 `lang=ch` 下默认就是 PP-OCRv6_medium。库里还列出 PP-OCRv6 tiny/small、PP-OCRv5 server/mobile，本轮 NOT_TESTED。
- Surya 0.23 已改成视觉语言模型，识别必须通过推理服务（NVIDIA 用 vllm，其他用 llama.cpp）。磁盘只剩约 13 GB，所以用 0.63 GB 的 Q8_0 量化权重，没有用 1.18 GB 的全精度 GGUF；全精度 NOT_TESTED。
- Surya 整页模式输出版面块，不是文字行，所以识别用它的 block 模式：每个检测框单独裁出送识别。

## 2. 许可证

| 引擎 | 代码 | 权重 | 商业部署 |
|---|---|---|---|
| RapidOCR | Apache-2.0 | Apache-2.0（PP-OCRv4 转 ONNX） | 可以 |
| PaddleOCR | Apache-2.0 | Apache-2.0（模型卡 `license: apache-2.0`） | 可以 |
| Surya | Apache-2.0 | **AI Pubs Open RAIL-M（修改版）** | **受限**：上一年营收或累计融资超过 500 万美元的机构，或与 Datalab 竞争的产品，只能用于个人或研究；另有 share-alike 条款覆盖模型输出。商用需向 datalab.to 购买许可 |
| mapKurator | 仓库根目录未找到 LICENSE（main/master 均 404） | README 数据卡写 CC BY-NC 2.0，可能只针对数据集 | NOT_VERIFIED，按非商用处理 |

Surya 的代码开源不等于权重可以商用。

## 3. 运行成本（U2 全图 805×780，含模型加载）

| 引擎 | 1× | 2× | 峰值内存（Python 进程 RSS） |
|---|---|---|---|
| RapidOCR | 1.7 s | 2.0 s | 318 / 805 MB |
| PaddleOCR | 14.3 s | 18.6 s | 1,341 / 3,509 MB |
| Surya | 23.5 s | 24.7 s | 402 / 456 MB，**不含 llama-server 子进程**（被强制结束，`ru_maxrss` 未计入），NOT_MEASURED |

详表 `results/runtime_metrics.csv`。磁盘：PaddleOCR 环境 979 MB + 权重 153 MB；Surya 环境 1.1 GB + 权重约 0.9 GB。

## 4. mapKurator 可复用部分（只读调研，未部署）

仓库模块（据目录名和 README 推断，未运行）：`m0_preprocessing`（大图切块）、`m2_detection_recognition`（Spotter-v2 / PALETTE 文字检测识别）、`m3_image_geojson`（切块结果拼回整图坐标，写 GeoJSON）、`m4_post_ocr`（OCR 后纠错）、`m5_geocoordinate_converter`（像素到地理坐标）、`m6_entity_linker`（对接 OpenStreetMap 实体）。

对 StitchVector 有参考价值的是：

1. 切块 + 重叠 + 拼接去重：大幅面扫描图必须这样做；本轮 U2 只有 805×780，三个引擎都能整图跑，没有用到。
2. 结果直接输出多边形 GeoJSON：与我们的 `text_labels` 图层思路一致。
3. 地名后处理靠外部地名库：中国地质图可以换成图例词典 + 行政地名库。

它的识别模型针对英文历史地图训练，对中文和地层下标没有现成能力；许可证不清楚。结论：只借鉴切块拼接和后处理的流程设计，不引入代码或模型。
