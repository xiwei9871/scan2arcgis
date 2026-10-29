# R4-B0 Gate 0：R4-A2.2 基线封版（2026-10-29）

起点：`research/r4a-boundary-learning` @ `a4108a2f02f4bdc8581b533387748b4c080cb44c`。

**状态：`DEVELOPMENT_VALIDATION`。** 15023、15041 在训练中也被用来按早停选检查点，所以 R4-A2.2 的成绩是开发验证结果，不是独立的最终验收。

## 内容

- 清单：`experiments/R4B0/gate0/baseline_manifest_r4a2_2.json`，包括：
  - M0、M1、M2_oldseed、M2_hybrid 的方法定义；
  - 验证图（15023、15041）与封存图（08011、08021，未读取）；
  - 两个权重文件的 sha256，与 `experiments/R4A/r4a2_2/checkpoint_sha256.txt` 一致；
  - 56 个本地预测文件的 sha256（根目录 `runs/r4a2/r4a22`）；
  - 32 个已提交文件的 sha256：冻结配置、日志、评价 JSON、报告和代码。
- 历史门槛：v1 Gate FAIL，v2 Gate FAIL；正式训练的依据是 `OWNER_AUTHORIZED_DIAGNOSTIC_EXCEPTION`。这些记录保留原样。

## 零差异复算

我用未修改的 `experiments/R4A/r4a2_2_eval.py`，在本地已保存的预测上重新计算了 2 幅图 × 4 种方法共 8 份评价。与已提交的 `experiments/R4A/r4a2_2/eval/*.json` 逐键比对（只排除文件路径字段），**8 份全部一致，差异为 0**。比对结果：`experiments/R4B0/gate0/recompute_check.json`。

## 未做

没有重新训练，没有修改任何历史结果或冻结文件，没有读取 08011、08021。

## 复现

```bash
cd experiments/R4A && ../../.venv-ml/bin/python r4a2_2_eval.py 15023 ../../runs/r4a2/r4a22/15023/M1/regions_M1.npy /tmp/15023_M1.json ../../runs/r4a2/r4a22/15023/M1/prob.npy
```
