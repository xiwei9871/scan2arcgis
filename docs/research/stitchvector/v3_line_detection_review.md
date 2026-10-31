# 绣娘 3.0 描线：严重漏检的逐阶段归因与单因素对照

状态：`STITCHVECTOR_V3_LINE_DETECTION_REVIEW_READY`
仓库：`xiwei9871/scan2arcgis`，分支 `research/stitchvector`

| 步骤 | 提交 | 说明 |
|---|---|---|
| 起点 | `7ddf5e8` | 3.0 最小验证结果，未改动 |
| Phase A 归因 + 两个修正 + 预注册（含开发结果） | `e2ace1a` | 生成测试种子 5001–5005 前推送，`git ls-remote` 核验一致 |
| 本报告 + 测试结果 | 见提交记录 | `experiments/STITCHVECTOR/linedet/` |

没有新依赖。用到的 `skimage.filters.apply_hysteresis_threshold` 在 `.venv-sv` 已有的 scikit-image 0.26 中。

## 0. 结论

1. **上一轮 3.0 验收：** 接受 `2.0 + logical_id` 作为稳定基线；交叉处颜色检查已否决，证据保留在 `v3/`。本轮没有再碰编组和交叉。
2. **漏检发生在哪里（Phase A）：** 三类严重漏检的丢失环节不同，不能用一个办法解决。上一轮"53–61% 附近有墨迹"的说法偏高：用"只计本线、排除交叉区"的口径重算后，墨迹已出现但后面丢失的部分为淡色线 46%、渐宽线 36%、与同色填色面相接的线 15%。
3. **两个最小修正在测试种子上都有收益，但都还不能作为默认方法：**
   - **B2a（附加式双阈值）**：淡色线可见召回 0.10 → 0.56，同色填色面上的线 0.67 → 0.80，原有线一条不少；但误检长度 393 → 722 px，增加的部分主要是填色面边缘被描成线。
   - **B1（短链回收）**：红黑线 0.87 → 0.92、≥ 10 px 缺口 24 → 14；但对象数 146 → 251，误检增加 179 px，并让一条 3 px 黄色窄带从"受保护"变成"被画上线"。
4. **下一步只需一件事：** 给 B2a 新增的线段加一个"两侧颜色"检查，排除一侧是填色、另一侧是背景的边缘。如果这一步能把误检压回 B0 水平，B2a 就可以作为默认；否则保留 B0。

## 1. Phase A：线在哪一步丢失

数据：已看过的 P1 测试种子 2001–2005（描述性，不改变 P1 成绩）。逐步重跑冻结的 2.0 检测器，最终输出与冻结版逐对象完全一致。

口径：真值轴线每 1 px 采样，去掉被后画的线遮住的样本；某一阶段的像素只有在"离本线最近、且 1.5 px 内没有其他线"时才算本线的，避免把相邻线或交叉区的像素算进来。

| 线型 | 可见长度 px | 对比度候选 | 保护后 | 骨架 | 去毛刺 | 连接+长度筛选 | 最终输出 |
|---|---|---|---|---|---|---|---|
| 红线、黑线 | 5,104 | 0.99 | 0.99 | 0.95 | 0.94 | 0.87 | 0.87 |
| 淡色 1 px | 1,043 | 0.75 | 0.60 | 0.59 | 0.47 | 0.14 | 0.14 |
| 渐宽 2→5 px | 1,042 | 0.94 | 0.93 | 0.77 | 0.75 | 0.56 | 0.57 |
| 与同色填色面相接 | 452 | 0.79 | 0.77 | 0.69 | 0.69 | 0.63 | 0.62 |

各线型最大的丢失环节：

| 线型 | 主要丢失 | 原图证据 |
|---|---|---|
| 淡色线 | 连接+长度筛选 33%，对比度 25%，保护 15%，去毛刺 12% | 未达阈值的轴线像素对比度中位数 9.4–11.6 dE（阈值 12）；保护阶段丢失的像素 36–97% 确实落在保护掩膜内 |
| 渐宽线 | 骨架 16%，连接+长度筛选 18% | 对比度候选保留 94%，**15×15 背景把粗线当背景的假设不成立**；保护阶段没有损失 |
| 同色填色面上的线 | 对比度 21% | 未达阈值处对比度中位数 6.6–9.7 dE，线与填色确实接近 |

说明：渐宽线在"骨架"阶段的 16% 可能部分来自统计口径。渐宽线画得较晚，压在它下面的线不算遮挡，而交叉区的骨架像素按规则不算任何一条线的。这一点没有逐处核实。

逐阶段图（原图 / 对比度 / 保护掩膜 / 墨迹掩膜 / 骨架 / 去毛刺 / 2.0 画出的链 / 2.0 输出）在 `runs/stitchvector/v3_linedet/stages/`，15 张。

## 2. 成熟方案的取舍

| 方案 | 与现有代码的关系 | 本轮决定 |
|---|---|---|
| scikit-image hysteresis | 已安装；只替换"对比度 > 12"这一行 | **测试（B2a）** |
| 短链回收 | 复用冻结的 `sv_linker`，不新增算法 | **测试（B1）** |
| sknw / Skan | `sv_d71.skeleton_chains` 已经做了骨架转节点-边；真串线每 5 张图只有 1 个 | 不引入 |
| Frangi / Meijering | 多尺度脊线增强；本轮的淡色线问题用双阈值已能大部分解决，没有必要 | 暂不 |
| Steger / ImageJ Ridge Detection | 需要 Java/ImageJ 或另找实现；增加依赖 | 暂不 |
| SLD-Vectorization | 神经网络连接，针对复杂笔画 | 不采用 |
| AutoTracer / Raster Scribe | QGIS 插件，适合以后做人工修正对照 | 以后 |

开发种子 1001–1003 上还试过直接用双阈值替换 2.0 的候选掩膜（B2）：淡色线 0.12 → 0.51，但原来画好的线少了 199 px，红黑线 ≥ 10 px 缺口 8 → 15。所以改为"只附加、不替换"的 B2a，这一点在预注册中写明。`c_low = 8` 是唯一试过的值。

## 3. Phase C：测试种子 5001–5005（冻结后运行一次，7.2 s）

### 3.1 视觉层

| 方案 | 红线黑线 | 淡色线 | 渐宽线 | 同色填色面上的线 | ≥10 px 缺口（红黑/淡/渐宽/填色面） |
|---|---|---|---|---|---|
| B0 冻结 2.0 | 0.871 | 0.104 | 0.820 | 0.668 | 24 / 10 / 8 / 5 |
| B1 短链回收 | **0.915** | 0.173 | **0.863** | 0.710 | **14** / 10 / **5** / 5 |
| B2a 附加双阈值 | 0.893 | **0.555** | 0.843 | **0.802** | 15 / 15 / 6 / **2** |

淡色线在 B2a 下缺口数从 10 增到 15，是因为原来整段没找到，现在找到了大部分，剩下的被切成更多段。

### 3.2 代价

| 方案 | 误检长度 px（填色面边缘 / 色带附近） | 误检占比 | 对象数 | 真串线对象 | 窄色带受保护 | 原有线丢失 |
|---|---|---|---|---|---|---|
| B0 | 393（202 / 183） | 0.072 | 146 | 1 | 6/10 | — |
| B1 | 572（311 / 254） | 0.096 | 251 | 1 | 5/10 | 0 |
| B2a | 722（417 / 255） | 0.115 | 201 | 1 | 6/10 | 0 |

窄色带逐条（带轴线上有线的比例，≤ 0.1 为受保护）：B0 本来就有 4 条未受保护（0.11–0.21），说明窄色带保护是 2.0 已有的问题，不是本轮引入的。B1 让 5003 的 3 px 黄带 0.088 → 0.181，由受保护变成被画线；B2a 让 5003 的绿带 0.207 → 0.279，其余不变。

### 3.3 判断

| 方案 | 收益 | 代价 | 结论 |
|---|---|---|---|
| B1 | 红黑线和渐宽线的缺口明显减少 | 对象数增加 72%，一条窄带被破坏 | **不采用为默认**；对象增加违背"对象合理"的目标 |
| B2a | 淡色线召回提高约 5 倍，同色填色面上的线提高 0.13；原有线不受影响 | 误检几乎翻倍，主要是填色面轮廓被描成线 | **值得再走一步**，但现在不能作为默认 |

## 4. 对六个问题的回答

| 问题 | 回答 |
|---|---|
| 1 漏检主要在哪一步？能否只改现有代码？ | 三类不同：淡色线分散在对比度、保护、去毛刺、连接各环节；渐宽线在骨架和连接，**不在背景估计**；同色填色面上的线主要是对比度不足。用现有代码加一个已安装的函数，就能救回大部分淡色线 |
| 2 最值得复用的成熟方法 | scikit-image 的双阈值：已安装、只改一行、对淡色线效果最大 |
| 3 sknw / Skan 值得吗 | 不值得。骨架转节点-边已有；真串线很少（每次测试 1 个） |
| 4 哪种增强最有帮助 | 双阈值已足够帮助淡色线；渐宽线的损失不在对比度阶段，Frangi 等增强方法解决不了它 |
| 5 如何不把窄色带画成线 | 本轮两种方案都没有改善窄色带；B0 本身已有 4/10 未受保护。新增线段必须先过"两侧颜色"检查，判断不了就不加 |
| 6 能否就此结束 | 不能。B2a 的收益是真实的，但误检翻倍；再做一步边缘排除后再决定 |

## 5. 已解决、暂时保留与下一步

**已解决：**
- 三类严重漏检的丢失环节已经量化（第 1 节）。
- 渐宽线不是背景窗口问题，不需要做多尺度背景。

**暂时保留：**
- B1 短链回收：收益在红黑线，但对象太多，暂不使用。
- 窄色带保护：2.0 本身就有约 4/10 未受保护，是独立的老问题。
- 交叉串线、编组：维持上一轮结论，不动。

**下一步（建议，需要你批准）：** B2a + "两侧颜色"检查。只对 B2a 新增的线段，沿法线两侧采样：一侧接近某种填色、另一侧接近背景或另一种填色，且中心没有更深的墨迹，就不加入。目标是在保住淡色线收益的同时，把误检压回 B0 水平。仍在合成图上，换新测试种子。

## 6. 产物

文本（已推送）：`experiments/STITCHVECTOR/linedet/`

| 文件 | 内容 |
|---|---|
| `phaseA_stages_p1test.json` | 逐阶段归因（每条线、每张图） |
| `ld_dev.json` | 开发种子结果（冻结前） |
| `ld_test.json`、`run_test.log` | 测试种子结果 |
| `ld_test_posthoc.json` | 误检位置分解（填色面边缘 / 色带）、逐条窄色带比例 |

代码：`sv_ld_stages.py`、`sv_ld_fix.py`、`sv_ld_compare.py`、`sv_ld_run.py`、`sv_ld_prereg.json`。stitchvector 测试共 31 个，全部通过。

图片（pre-push 钩子禁止 PNG，没有绕过，也没有公开发布）在本地 `runs/stitchvector/v3_linedet/`，入口 `index.html`：
- `test/ld_test_<种子>_x3.png`：原图 / B0 / B1 / B1 误差 / B2a / B2a 误差（绿 = 与 B0 相同，蓝 = 新增且在真值线上，品红 = 新增误检，红点 = 仍漏检）
- `stages/stages_<种子>_<线>.png`：Phase A 逐阶段图

复现：

```bash
cd experiments/STITCHVECTOR && ../../.venv-sv/bin/python -W ignore sv_ld_run.py <json_dir> <img_dir> test
```

```bash
cd experiments/STITCHVECTOR && ../../.venv-sv/bin/python -W ignore sv_ld_stages.py <json_out> <img_dir> 2001 2002 2003 2004 2005
```

SHA-256：

```
c5ee53dbd0169e79c0bc893ae273cd489cba7b4395540c783cc23346cac8e5b6  runs/stitchvector/v3_linedet/test/ld_test_5001_x3.png
6ce74b3f566ad89c9bd5ff3925a49bd12fe80730730138ef6025aebb4dfa9fd9  runs/stitchvector/v3_linedet/test/ld_test_5002_x3.png
94e58aa3dca14e0a44ce863269e5d23d56f0c558a47ecdaf8b891a73f49e5fbf  runs/stitchvector/v3_linedet/test/ld_test_5003_x3.png
119451f28906d1e4c1589fb1f64065b934edcf4bac13128e17a11df5c63edc2d  runs/stitchvector/v3_linedet/test/ld_test_5004_x3.png
24bc23936f46d9bcbb032f54e1d8abfab94ca258f2806b346682f9568a7bca2a  runs/stitchvector/v3_linedet/test/ld_test_5005_x3.png
4d0dd1c76a5567f31c89fbaeecf0a4838c2995dec24330ec91408c99b3d5c9b0  runs/stitchvector/v3_linedet/stages/stages_2001_pale_1.png
7ad4036a815435e1c3601943bace0c0561ea3b5f30c213939ae166ff1a8028b5  runs/stitchvector/v3_linedet/stages/stages_2001_red_touch_fill.png
040835b9f25fbd3082b40380aa47602091e4b00fb8aa411d507a9b1292632dc6  runs/stitchvector/v3_linedet/stages/stages_2001_red_var_2to5.png
3cd940f590572651a1fa144efe035cf27558dd768d4de3617a132683e091e30d  runs/stitchvector/v3_linedet/stages/stages_2002_pale_1.png
3043f7a8c05d3550e679ad2320a184b96157cb6f01068b034f286137c95d8fe8  runs/stitchvector/v3_linedet/stages/stages_2002_red_touch_fill.png
861bf1ffb2242dce2f61e0a1aacb216cc86d1eb47f44a9887f23e6288e5a7ccc  runs/stitchvector/v3_linedet/stages/stages_2002_red_var_2to5.png
29f6ef7176b68f5242713624e645f599c137fa83d23eaf186f0b7cd345b2dbf3  runs/stitchvector/v3_linedet/stages/stages_2003_pale_1.png
62d04d1ea68d4269d7b616b0d8357bf8ccf64b292fc761d651bc1a6904320d17  runs/stitchvector/v3_linedet/stages/stages_2003_red_touch_fill.png
c2104dd7749af9f1c2a6552967b57ed772027dd85a7bf0a01c88e18513c085db  runs/stitchvector/v3_linedet/stages/stages_2003_red_var_2to5.png
8ef596237f964796f102645a1d21ec4747d55499b94df21d4a2c636d24ade9f2  runs/stitchvector/v3_linedet/stages/stages_2004_pale_1.png
3703b297485c5d79f898e09053f945a857152d02421f19b199c3f274213747d4  runs/stitchvector/v3_linedet/stages/stages_2004_red_touch_fill.png
d019809287e1dafb84b990f6400d6ce1ee8ccb61bcf0d2541dc87735657dd226  runs/stitchvector/v3_linedet/stages/stages_2004_red_var_2to5.png
d666005d22126b3fd8053ea3297ec9baef7cf9463581379ed250cdb0431d2748  runs/stitchvector/v3_linedet/stages/stages_2005_pale_1.png
1dc26ddc37f5a0bc584463ad6d1b4d03a804773f8523cba79ea5dd430de964c4  runs/stitchvector/v3_linedet/stages/stages_2005_red_touch_fill.png
f13cc77e8672a67a2a56df4c75f23f01ffb269ffb8dfeffb557869a0eee283b2  runs/stitchvector/v3_linedet/stages/stages_2005_red_var_2to5.png
```

## 7. 遵守的约束与偏离

- 只用合成图；没有真实地图，没有访问封存测试池，没有改 M1/M2/B2/RAG，没有改面层，没有改动 POC-01、D71、Oracle、P1、Line Recovery、3.0 的记录；没有新依赖；在独立 worktree 中工作。
- Phase A 用的是已看过的 P1 测试种子，属于描述性分析；修正方案在开发种子上试过（全部写在预注册 `dev_disclosure` 中），测试种子冻结后只运行一次，运行后没有改代码或参数。
- 3.2 节的误检位置分解和逐条窄色带比例是运行后的描述性统计（`ld_test_posthoc.json`），不是预注册指标。
