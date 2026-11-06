# FINAL_GATE_DECISION

| Gate | 状态 | 证据 |
|---|---|---|
| 任务一 截图定位 | shot2 **MATCHED**(conf 0.78)/ shot1 **SOURCE_NOT_MATCHED** | EXACT_SCREENSHOT_MATCH_REPORT.md;shot1 经 ORB/边缘模板/色彩布局 30+ 候选全部不可信,如实未冒充 |
| 任务二 掩膜安全 | **PASS** | 风险判定先于像素修改;66 auto_clean/65 preserve_review;重叠像素无归属;56 条存疑线进复核队列 |
| 任务三 Studio 契约 | **STUDIO_INTEGRATION_VERIFIED** | Point 几何+全字段;打开→审核→编辑→撤销→v001→重开→导出(confirmed1/unconfirmed130)全链实测 |
| 任务四 原位验证 | shot2 **PARTIAL**;shot1 **NOT_VERIFIED** | shot2 原位:small_frag 2265→1956(-14%)、interior_ring 41→38、glyph_line 26→25、anomalies 2626→2374——缺陷减轻但未消除;enclosed+35;shot1 位置未定位无法裁决 |

## 综合裁决

`PARTIAL` —— 不声称 `EXACT_REAL_CASE_VALIDATED`。

原因:
1. shot2(红面碎裂)在原位确认缺陷机制成立,OCR 保护版使碎片减少 ~14%,但**红面碎裂主要成因不是文字**(本区文字框少),残余碎面属 B2c 面切分固有伪影——需走 T02 `internal_fragment_scan` 诊断+人工确认的半自动路径,不是 OCR 保护管线能单独解决的。已定位的 2,265→1,956 碎面全部保留地质信息可审计。
2. shot1(βQ 区)无法可靠定位——U2 全图 OCR 不含该文字,疑似非本图件或特殊放大视图。**请确认 shot1 是否来自 U2 之外的原图;若是其他图件,提供源文件即可复跑同一匹配与四态流程。**
3. 掩膜与 Studio 契约两项硬伤已修复并实测;但按规则"任何新流程若造成更严重地质信息损失不能替换 B2c"——保护版保守至 +35 enclosed,需人工复核 56 条存疑线后才能谈替换。

## 未满足前不安排集中人工验收的事项

- 56 条 `possible_real_geology_REVIEW` 线的人工裁决(决定保护版可否作为默认)。
- 65 个 preserve_review OCR 框对应的残区(文字下碎面仍在)。
- shot1 原图来源确认。

## 复跑入口

```bash
# 匹配(截图放入后):
.venv-sv/bin/python -m tools.stitchvector_editor.screenshot_match <shot>.png runs/stitchvector/u2_full/u2_map.png
# 重建保护版:
.venv-sv/bin/python experiments/STITCHVECTOR/sv_u2_ocr_protected_build.py
# 四态对照:
#   runs/uat_20261106_screenshots/exact_shot2_{B2c,prot}/ 已生成(本地)
```
