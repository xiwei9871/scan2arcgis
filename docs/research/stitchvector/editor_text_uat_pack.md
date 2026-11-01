# Text Layer V0.1：人工验收包

状态：`READY_FOR_VISUAL_UAT`
基线：`feature/stitchvector-editor-text-layer @ 0f4178d`
验收对象：`runs/stitchvector/editor_text/demo/u2_text_demo.gpkg`（SHA-256 `11b1cd1ad6269d421f723ad0643c5f3a053766ae2eb2a227ae8e88ca2039e533`），由 `experiments/STITCHVECTOR/sv_text_demo.py` 从原始 B2c 复现生成。Ar₂E 的待定碎面没有合并。

标注规则：`PASS` 只用于已由数据或浏览器自动化证明的项；凡是需要人眼判断"看起来对不对、地质上对不对"的项一律 `PENDING`；没有交付的项为 `FAIL`。

## 总表

| # | 验收项 | 状态 | 依据 |
|---|---|---|---|
| 1 | PNG 证据上传 GitHub 并可浏览 | **FAIL（未交付）** | 见第 1 节 |
| 2a | 文字清除完整度：Є-O、云（数据） | PASS | 框内小碎面 0、压字形的线 0 |
| 2b | 文字清除完整度：Ar₂E（数据） | PENDING | 16 个待定碎面（27 px²）按要求保留 |
| 2c | 文字清除完整度：三处视觉 | PENDING | 需人工看四联图 |
| 2d | 原始地质边界保真度（数据） | PASS | 框外各扩 1 px 后颜色面积变化 0 px²；不碰框的线 0 条改动；面层严格拓扑有效 |
| 2e | 7 条隔离线是否误隔离地质线 | PENDING | 都不与 Oracle 已描线重合，但 Oracle 未描文字和小符号 |
| 2f | 文字重建位置与大小（视觉） | PENDING | 数据偏移 0.5–2 px；云的字号可能偏大 |
| 3 | Ar₂E 16 个待定碎面 | PENDING_HUMAN | 清单见第 3 节；未合并 |
| 4 | 编辑器交互 | PASS | 浏览器 10/10 |
| 5 | 回归保护 | PASS | B2c SHA-256 不变；只改编辑器、测试、文档、实验目录 |

## 1. PNG 证据：未上传 GitHub

仓库 `xiwei9871/scan2arcgis` 是**公开**仓库。`pre-push` 钩子拒绝推送 `*.png`、`*.gpkg` 等数据和二进制文件，用途是防止把地图数据发布到公开远端。我没有绕过它，也没有改用 Release 资产、base64 内嵌或其他方式上传，因为这些都等于把扫描图截图公开发布，和钩子的目的冲突。

截图只在本地：`runs/stitchvector/editor_text/shots/`。

| 文件 | 内容 |
|---|---|
| `top_1_original_png.png` … `top_4_edited_text_on.png` | 上视窗（Є-O、云）：原图 / B2c 矢量 / 编辑后文字关 / 编辑后文字开 |
| `bot_1_original_png.png` … `bot_4_edited_text_on.png` | 下视窗（Ar₂E），同上 |
| `zoom_EO.png`、`zoom_yun.png`、`zoom_Ar2E.png` | 三个文字区域的四联放大图 |
| `bot_*_fullpage.png` | 带侧栏的整页截图（顶部显示已加载文件和计数） |

全部 SHA-256 在 `experiments/STITCHVECTOR/text_layer/artifacts_sha256.txt`。复现：先运行 `sv_text_demo.py` 生成示范 GPKG，再按第 6 节启动两个编辑器，用 `tests/stitchvector_editor/shots_text_demo.js` 截图，`experiments/STITCHVECTOR/sv_text_shots_diff.py` 做像素差异。

如果你决定可以公开这些截图，最简单的做法是在 GitHub 网页上新建 Issue，把 `shots/` 里的图片拖进去，我再把链接写进本报告。

## 2. 验收指标（`experiments/STITCHVECTOR/text_layer/uat_metrics.json`）

### 2.1 文字清除完整度

| 文字 | 框内小碎面 前 → 后 | 小碎面面积 | 深色字形碎面面积 | 框内线 | 字形面积清除比例 | 状态 |
|---|---|---|---|---|---|---|
| Є-O | 40 → 0 | 93 → 0 px² | 30 → 0 px² | 2 → 0 | 100% | 数据 PASS，视觉 PENDING |
| 云 | 10 → 0 | 45 → 0 px² | 9 → 0 px² | 2 → 0 | 100% | 数据 PASS，视觉 PENDING |
| Ar₂E | 81 → 16 | 147 → 27 px² | 42 → 0 px² | 3 → 0 | 100% | PENDING（16 个待定） |

"深色字形碎面"按原图亮度判定。这里的阈值比上一份报告严格，所以 Ar₂E 的字形碎面在上一份报告里是 28 → 2，这里是 16 → 0。两种口径都说明剩下的 16 个碎面主要不是黑色字形，而是粉红底面和红色楔形面交界处的浅色、红色小块。

屏幕像素变化（同一缩放 4.5×，`visual_diff.json`）：Є-O 框内 24.8%，云 26.8%，Ar₂E 11.9%。

### 2.2 原始地质边界保真度

- 框外颜色面积变化：按框本身算 2 px²；框各向外扩 1 px 后为 0 px²。这 2 px² 是框边缘的像素。
- 不碰任何文字框的线：0 条改动。
- 移入隔离图层的 7 条线：L1、L6、L22、L24、L25、L31、L33，可在编辑器里逐条高亮、恢复。是否有真实地质线：PENDING。
- 下视窗框外有 64 个屏幕像素变化，最大差值 34 级，都在粉红底面靠近 L23、L26、L27 的边缘，属于边界渲染变化，几何上框外 1 px 以外没有改动。
- 面层严格拓扑检查：通过。

### 2.3 文字重建位置和大小

| 文字 | 文字点位置 | 原图字形中心 | 中心偏移 | 字号 / 字形高度 | 状态 |
|---|---|---|---|---|---|
| Є-O | (19.0, 33.5) | (19.0, 33.0) | 0.5 px | 13.6 / 10 = 1.36 | PENDING |
| Ar₂E | (26.0, 210.5) | (24.0, 210.5) | 2.0 px | 23.2 / 29 = 0.80 | PENDING |
| 云 | (32.5, 67.5) | (32.5, 69.5) | 2.0 px | 13.6 / 7 = 1.94 | PENDING，可能偏大 |

- 字号默认取框高的 0.8 倍，不是从字形测出来的，所以云的字号明显偏大，Є-O 略大。可以在编辑器里改。
- Ar₂E 的"字形高度"测到 29 px，等于整个框高，因为框里混有红色楔形面的深色像素。这个比值不可靠。
- OCR 候选都不是最终内容：Є-O 读成 C-0，Ar₂E 读成 ArE，只有云读对。三个文字内容都是人工给定的。
- Є 和下标 ₂ 在浏览器里显示正常与否，要看 `bot_4_edited_text_on.png` 和 `zoom_*.png`：PENDING。

## 3. Ar₂E 的 16 个待定碎面

完整清单：`experiments/STITCHVECTOR/text_layer/ar2e_pending_fragments.csv`（同内容 `.json`）。字段：编号、面 ID、中心坐标、面积、颜色、原图亮度、是否深色字形、相邻面、每个候选底面的共享边长度和色差、建议归属、状态。

候选底面只有两个：粉红底面 #7（`#ffdfec`）和红色楔形面 #415（`#d85241`）。面 ID 是示范 GPKG 中的编号。

| 编号 | 面 ID | 中心 | 面积 px² | 颜色 | 建议 | 备注 |
|---|---|---|---|---|---|---|
| P01 | 419 | (19.5, 200.5) | 2 | #d8736b | #415 红 | |
| P02 | 420 | (18.5, 202.5) | 1 | #d8736b | #415 红 | |
| P03 | 421 | (17.5, 203.5) | 1 | #d8736b | #415 红 | 只挨红色面 |
| P04 | 422 | (18.5, 203.5) | 1 | #c8baa3 | #7 粉 | 只挨粉红面 |
| P05 | 423 | (16.5, 204.5) | 1 | #d8736b | #415 红 | |
| P06 | 424 | (17.5, 204.5) | 1 | #c8baa3 | #7 粉 | 只挨粉红面 |
| P07 | 425 | (15.5, 205.5) | 1 | #d8736b | #415 红 | |
| P08 | 426 | (14.5, 206.5) | 1 | #9a7267 | #415 红 | 两边色差接近（44 / 36） |
| P09 | 427 | (12.5, 209.5) | 5 | #d8736b | #415 红 | 面积最大 |
| P10 | 428 | (11.5, 212.5) | 2 | #d8736b | #415 红 | |
| P11 | 429 | (10.5, 215.5) | 2 | #d8736b | #415 红 | |
| P12 | 430 | (9.5, 217.5) | 2 | #9a7267 | #415 红 | |
| P13 | 431 | (10.5, 216.5) | 1 | #c8baa3 | #7 粉 | |
| P14 | 432 | (9.5, 218.5) | 1 | #d8736b | #7 粉 | **两边色差几乎相同（36.8 / 39.3），最不确定** |
| P15 | 433 | (9.5, 219.5) | 1 | #c8baa3 | #7 粉 | |
| P16 | 434 | (7.0, 224.5) | 4 | #c8baa3 | #415 红 | |

**"建议归属"只是按原图色差最小给出的参考，不是判定。** 上一轮已经确认，这种规则把 7 组并入红色面的结果不可接受，所以这里所有碎面的状态都是 `PENDING_HUMAN`，示范 GPKG 中一个都没有合并。

这些碎面排成一条斜线，从 (19.5, 200.5) 到 (7.0, 224.5)，正好沿着粉红面和红色楔形面的交界。它们更可能是交界线的抗锯齿边，而不是文字残影。可选的处理：逐个并到你认为正确的一侧，或者整体保留、等以后把这条交界作为 SPLIT 线处理。

在编辑器里：用"框文字"重新框 Ar₂E，再用"点选归属"工具，先点橙色碎面，再点目标底面，看预览后确认或跳过。

## 4. 编辑器交互检查（`demo_ui_check_result.json`，浏览器实际操作）

在示范 GPKG 上运行 `tests/stitchvector_editor/e2e_text_demo_check.js`，10 项全部通过：

1. 页面顶部显示 `已加载：u2_text_demo.gpkg  面 550 线 28 文字 3 隔离线 7 待定碎面 16`
2. 文字层开关会改变矢量画布
3. B 视图：原图叠加关闭，面层 100%
4. A 视图：原图叠加打开
5. 切换视图不产生编辑
6. 修改文字字号后显示"未保存"
7. 撤销恢复字号
8. 重做重新应用
9. 撤销回到示范状态后，计数仍是 550 / 28 / 3 / 7 / 16
10. 另存为 `demo_reopen_check.gpkg`：回读一致、面层有效、原文件未变

## 5. 回归保护

- 原始 B2c `u2_B2c.gpkg` 的 SHA-256 `7d78a7111320…` 全程不变。
- 本轮和前几轮的改动只在 `tools/stitchvector_editor/`、`tests/stitchvector_editor/`、`docs/research/stitchvector/`、`experiments/STITCHVECTOR/`。没有改 M2、B2c 生成代码、OCR 研究代码或其他生产基线。
- 单元测试 59 项通过。

## 6. 启动命令

打开示范成果做人工验收：
```bash
cd ~/geomap2arcgis/.claude/worktrees/sv-editor-text && ~/geomap2arcgis/.venv-sv/bin/python -m tools.stitchvector_editor.server --image ~/geomap2arcgis/runs/stitchvector/editor_v01/inputs/u2_original.png --gpkg ~/geomap2arcgis/runs/stitchvector/editor_text/demo/u2_text_demo.gpkg --out-dir ~/geomap2arcgis/runs/stitchvector/editor_text/my_review --port 8801
```

从原始 B2c 开始自己编辑：
```bash
cd ~/geomap2arcgis/.claude/worktrees/sv-editor-text && ~/geomap2arcgis/.venv-sv/bin/python -m tools.stitchvector_editor.server --image ~/geomap2arcgis/runs/stitchvector/editor_v01/inputs/u2_original.png --gpkg ~/geomap2arcgis/runs/stitchvector/editor_v01/inputs/u2_B2c.gpkg --out-dir ~/geomap2arcgis/runs/stitchvector/editor_text/my_edits --port 8802
```

打开 http://127.0.0.1:8801/ 或 http://127.0.0.1:8802/ 后，先确认页面顶部的文件名。

## 7. 需要你决定的事

1. 截图是否允许公开到 GitHub（Issue 附件）。
2. Ar₂E 16 个碎面逐个归属，或整体保留。
3. 7 条隔离线中是否有真实地质线需要恢复。
4. 三个文字的位置、字号是否可接受（云的字号可能要调小）。
