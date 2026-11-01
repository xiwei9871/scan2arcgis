# 07 最终推荐

状态：`OCR_POC01_READY_FOR_REVIEW`。不合并、不部署、不替换 RapidOCR、不修改 U2 地质线面。

**全部数字基于 agent 起草的真值（`AGENT_DRAFT`，142 文字 / 57 负样本），人工复核前只能作参考。** 只测了 U2 一张图。

## 1. 六个问题

**问题一：哪个 OCR 对普通中文地名识别最好？**
PaddleOCR（PP-OCRv6_medium）。端到端 37/39 = 0.949 [0.83, 0.99]，固定框 1× 38/39、2× 39/39。RapidOCR 端到端 0.821，Surya 0.487（会输出繁体字，如 軒岡鎮、長梁沟鎮）。

**问题二：哪个 OCR 对地层代号、特殊字母和上下标最好？**
单引擎原始输出：Surya 最好（端到端地层代号 0.600，特殊符号 0.344；PaddleOCR 0.491 / 0.000；RapidOCR 0.345 / 0.000）。PaddleOCR 和 RapidOCR 从不输出下标字符，也读不出 `Є`。
但 PaddleOCR 字母基本读对（NFKC 口径 0.709），加上不依赖 U2 的通用规则后，地层代号升到 **0.800** [0.68, 0.88]，高于任何单引擎，也高于三引擎投票（0.782）。规则是看过本轮错误后写的，属于探索性结果。

**问题三：哪个 OCR 的文字检测最不容易误伤地质界线？**
RapidOCR 最保守：无真值的框 13 个（PaddleOCR 24、Surya 20），会隔离线的无真值框 8 个（19、16），负样本命中 0（Surya 2）。在 Oracle 窗口（4.5% 地图、13 条真实线）内，三个引擎按"穿框线不切"策略都没有自动删除真实地质线；窗口外 NOT_EVALUATED。三个引擎都不允许自动清除。

**问题四：单一模型是否足够，还是双模型 + 地质词典更好？**
本轮数据下，**PaddleOCR + 通用地质规则**就够了，Surya 复读和 U2 图例词典都没有带来额外提升。推荐架构：PaddleOCR 主引擎 + GENERIC 规则生成候选 + 人工复核。双模型（Surya 复读）只在下标场景有帮助，但许可受限、慢 2 倍，不建议进入产品。图例词典值得保留为候选来源，但 U2 图例 OCR 本身只解出 7/14 条代号，需要人工校对图例才能用。

**问题五：是否具备商业产品部署条件？**
- PaddleOCR、RapidOCR：许可证允许商用（代码和权重均 Apache-2.0）。CPU 上 U2 全图 15–33 s、峰值内存 1.3–3.5 GB，可以接受。
- Surya：权重为修改版 OpenRAIL-M，营收或融资超过 500 万美元的机构不能商用，**不进入生产推荐**。
- mapKurator：许可证未确认，只参考设计。
- 准确率：检测 F1 最高 0.848（目标 0.90）、普通文字 0.949（目标 0.90，样本 39 个）、地层代号 0.800（目标 0.85）。**未达到生产级目标**，而且真值未复核、只有一张图。可以做"OCR 候选 + 人工确认"的辅助功能，不能做全自动文字图层。

**问题六：下一阶段是否需要地质专用 OCR 微调？**
需要，但优先级低于两件更便宜的事：(1) 人工复核真值、补第二张图做跨图验证；(2) 小字检测——15 个三引擎都漏掉的真值多为 6–10 px 高的产状数字，可先试切块放大检测。
如果做识别微调（PP-OCRv6 rec），目标是下标和 `Є`：估计需要 **约 3,000–5,000 个真实文字行裁片**（覆盖 10–20 张不同风格的地质图，每张 200–300 个），加上用图例字体合成的 2–5 万条带下标代号的样本。这是估计，没有实验支撑。

## 2. Gate 状态

| Gate | 内容 | 状态 |
|---|---|---|
| G1 | RapidOCR 基线复现 | PASS（219/219 条一致） |
| G2 | ≥2 个候选引擎可比测试 | PASS（PaddleOCR、Surya；mapKurator NOT_TESTED） |
| G3 | 独立人工真值集 | **PENDING_HUMAN**：142 + 57 已起草，未复核 |
| G4 | 检测、识别分别报告 | PASS（实验 A / B） |
| G5 | 地质代号、特殊符号专项 | PASS（暂定，依赖 G3） |
| G6 | 线面安全独立审计 | PASS（窗口外 NOT_EVALUATED） |
| G7 | 许可证与运行成本 | PASS（Surya 子进程内存 NOT_MEASURED） |
| G8 | 交互式对比工具 | PASS（浏览器已检查） |
| G9 | 选型结论 | PASS（暂定，依赖 G3） |
| G10 | GitHub 提交与远端核验 | 见提交说明 |

## 3. 未做的项目

- 对比度增强、u3/GSJ 跨图测试、旋转文字：NOT_TESTED / NOT_EVALUATED。
- PP-OCRv6 tiny/small、PP-OCRv5 server、Surya 全精度权重：NOT_TESTED。
- 符号类负样本只有 2 个。

## 4. 复现

```bash
cd ~/geomap2arcgis/.claude/worktrees/sv-ocr-poc01/experiments/STITCHVECTOR/ocr_poc01
# 引擎运行命令见 README.md；打分：
~/geomap2arcgis/runs/ocr_poc01/venvs/eval/bin/python benchmark_runner.py
~/geomap2arcgis/runs/ocr_poc01/venvs/eval/bin/python fusion_eval.py
~/geomap2arcgis/.venv-sv/bin/python safety_audit.py
~/geomap2arcgis/runs/ocr_poc01/venvs/eval/bin/python -m pytest -q tests
```
