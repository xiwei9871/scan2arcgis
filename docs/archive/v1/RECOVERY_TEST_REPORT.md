# RECOVERY_TEST_REPORT — 隔离恢复测试 (2026-11-02)

场景：模拟"新机器"——从 GitHub 全新克隆，不与开发 checkout 共用文件。
克隆：`/tmp/sv_recovery_clone` @ `feature/stitchvector-studio-v01` (`575a63f`)；工作区 `/tmp/sv_recovery_ws`；
服务端口 8840（独立实例，不碰开发环境）。

## 结果：PASS（代码恢复完整；数据依赖如实标注）

| 步骤 | 命令/动作 | 结果 |
| --- | --- | --- |
| 克隆 | `git clone git@github.com:xiwei9871/scan2arcgis.git /tmp/sv_recovery_clone` | PASS |
| 检出 | `git checkout feature/stitchvector-studio-v01` → `575a63f` | PASS |
| 编译 | `python -m compileall tools/stitchvector_studio tools/stitchvector_editor tests` | PASS(0 错误） |
| 插件发现 | `registry.discover()` | 5/5 available（依赖本机已存 venv——新机器按 RECOVERY_GUIDE §1–3 重建） |
| 管线状态 | `GET /api/studio/pipelines` | legacy-b2c-v01/-rapidocr/mock-swap-test runnable;geology-aware-vnext 正确 disabled |
| 上传 | u2_map.png(805×780 PNG) | PASS |
| 归一化 | `normalise page=0` | PASS PIXEL_SPACE 正确标注 |
| 真实管线 | `process legacy-b2c-v01` → run-20261102-114214-d7fec2 | **COMPLETED**:B2c 18.26s → 17,047 面/606 线（与开发机结果逐值一致）;PaddleOCR 34.38s → 148 候选；quality COMPLETED |
| 采纳入编辑器 | `adopt run` | PASS(opened=true) |
| 版本保存 | `save` → v001 | PASS:`readback_matches_memory=True`, `input_sha256_unchanged=True` |
| 导出 | `exports GPKG`(4 层） | PASS:7,159,808 B,`readback ok=True` |
| 取消/重启持久化 | — | 未在克隆上重测（本机在主实例已验，见 devin_reverification JSON) |

## 明确声明

- **代码可恢复性：已验证**——GitHub 克隆即得全部 Studio/编辑器/算法/文档/测试代码。
- **依赖本机既有物（新机器须按指南重建）**:`.venv-sv`/`.venv-ocr`/`runs/ocr_poc01/venvs/paddle` 三个 venv
  与 `runs/ocr_poc01/cache/paddle` 模型缓存（139M，可自动重下）。
- **依赖受保护本地数据**:`runs/stitchvector/u2_full/u2_map.png` 为 B 类 REMOTE_BACKUP_PENDING;
  无该文件则 U2 验证无法执行，mock 管线仍可全通。
- 恢复测试**未做**：全新机器 pip 安装全量依赖（网络下载未实测）、浏览器 E2E(playwright-cli 需 node)。
- 综合判定：**RECOVERY_VERIFIED（限代码层）/ DATA_RECOVERY_PENDING（受保护数据）**。
