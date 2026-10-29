# R4-B1 Gate 0：封存 R4-B0.1 结果（2026-10-29）

起点：`research/r4a-boundary-learning` @ `393729d87d1f97db1582136ee6cb3e0d2be703e0`。
清单：`experiments/R4B1/gate0/seal_manifest.json`。

| 项 | 状态 |
|---|---|
| A1（M2 距离种子 + 边界概率地形） | 按预注册判 **FAIL**。召回提升 +0.0115（15023）和 +0.0117（15041），只作为研究证据保留，不采用为正式后处理 |
| C1（亚像素线宽估计器） | `SCALE_ESTIMATOR_FAILED`。R4-B1 不再尝试第三种估计器 |
| 正式基线 | `M2_hybrid`：R4-A2.2 的 M2 `best.pt` 加 `hybrid_markers`；小实例召回 0.5960 / 0.5543 |
| M1/M2 权重 sha256 | 与 R4-B0 Gate 0 清单一致 |
| 预测文件 | 56/56 与清单一致 |
| 训练、标签、评价代码和冻结配置 | sha256 已记录（11 个文件），本轮不修改 |

没有修改任何历史结果。
