# EXACT_SCREENSHOT_MATCH_REPORT — 任务一：用户截图原位匹配

工具：`tools/stitchvector_editor/screenshot_match.py`（ORB 特征 + 多尺度边缘模板 + 去字补色版色彩布局模板三通道；可信度 = 内点率×0.6 + NCC×0.4，阈值 0.35，低于即 `SOURCE_NOT_MATCHED`）

## 截图来源（已存本地受保护目录，未推送）

| 文件 | SHA-256 | 尺寸 |
|---|---|---|
| `runs/uat_20261106_screenshots/shot1_text_betaQ.png` | `471e03d7…` | 1024×533 |
| `runs/uat_20261106_screenshots/shot2_redface_frag.png` | `1d7cdb7d…` | 657×373 |

## shot2（红色地质面内部碎裂）— **MATCHED**

| 子图 | 匹配对象 | 裁剪坐标 | 缩放 | 内点 | 内点率 | NCC | 可信度 |
|---|---|---|---|---|---|---|---|
| 左半（原始栅格） | `u2_map.png` `05cdada4…` | **[519.5, 325.0, 791.7, 632.3]** | 0.5× | 108 | 0.956 | 0.516 | **0.780** |
| 右半（矢量渲染） | `u2_full_B2c_render.png` `41c69eea…` | [488.5, 324.9, 759.5, 634.9] | 0.5× | 15 | 0.938 | 0.284 | 0.676 |

两半定位一致（中心偏差 <15px），红色 PtuD 单元（谢家坪/堂尔上/上冰沟/大端地区）。四态对照图已生成：`runs/uat_20261106_screenshots/exact_shot2_{B2c,prot}/`（A_raster/B_faces/C_lines/D_text/E_overlay）。

## shot1（βQ 希腊字母+拉丁字符区）— **SOURCE_NOT_MATCHED**

已尝试：全图 ORB（30+ 候选：u2_map、B2c render、u1/u3/gm2 work.png、docx_media×20、ocr_poc01 scratch）、两条图带切分 ORB、0.08–0.7 边缘模板、去字补色色彩布局模板（最高 NCC 0.635@(238,266) 经目视否决为 PtiL 红色区误配）。结论：该截图内容**无法可靠定位于 U2 或任何本地候选原图**（βQ 文字亦不在 U2 OCR 219 项内，疑似来自其他图件或更高放大倍率视图）。

**Gate 裁决：shot2 原位验证可用；shot1 记 `SOURCE_NOT_MATCHED / NOT_VERIFIED`，未用临时区域冒充。**
