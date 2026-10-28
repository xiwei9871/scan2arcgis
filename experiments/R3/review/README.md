# 同色组图例色块人工审核包（PROVISIONAL）

**状态：** `PROVISIONAL`。人工确认之前，这里的转录不能当作正式 OCR 真值。用它算出的分数一律标注为 PROVISIONAL。

**范围：** 全部同色组色块，没有抽样。08004 有 6 个（S07、S10、S11、S12、S17、S33），08001 有 2 个（S05、S08）。

## 内容

- **索引文件：** `same_colour_review_index.json`，已提交到仓库。每个色块一条记录，包含：
  - 系统 OCR 的原文和规范化结果（4 个引擎）
  - Claude 的转录和把握程度
  - 本地图片路径和 SHA-256
  - 三个空的人工确认字段：`human_confirmed`、`human_code_if_different`、`human_comment`
- **图片（只在本地，不提交）：** 原图局部和 4 倍放大图来自有许可限制的印刷图，存放在：
  - `/Users/xiwei/geomap2arcgis/runs/r3fix/review_pkg/08004/`
  - `/Users/xiwei/geomap2arcgis/runs/r3fix/review_pkg/08001/`

  每个色块有两张：`<色块>_context.png`（色块和右侧的说明文字）和 `<色块>_zoom4x.png`（色块放大 4 倍）。

## 转录方法和需要说明的情况

- **方法：** 转录只依据印刷图例的局部和放大图，没有打开官方 xlsx。
- **不完全盲转录：** 在 R2/R3 的评价输出里，转录人已经看到过每个同色组包含哪些官方代号，例如 {Mz, Sm, Jg, Hf}。但没有看到哪个色块对应哪个代号。
- **下标写法：** 08001 的 S08 印刷为 M 加下标 3，转录为 `M3`，和项目里其他带下标代号的写法一致。

## 人工确认的方法

1. 打开上面目录中的图片，逐个核对 `transcription`。
2. 正确的，把 `human_confirmed` 填为 `true`。不正确的，填 `false`，并在 `human_code_if_different` 里写正确代号。
3. 全部确认后，把文件头的 `status` 改为 `CONFIRMED`，提交即可。之后的评价会自动改用确认后的参考。
