# OPEN_ISSUES — 遗留问题汇总 (archive V1, 2026-11-02)

本轮只归档、不研发。严重度：P0 阻断交付 / P1 影响验收 / P2 改进项。

| # | 问题 | 严重度 | 当前证据 | 影响 V0.1? | 推荐下一步 | 立即修? |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | **U2 地质面语义准确率缺完整真值** | P1 | u2_full_validation：真值仅覆盖图面 4.5%,575 项审查队列；多数语义 NOT_EVALUATED | 否（几何/拓扑已验，语义结论悬置） | 扩充 oracle 真值（在 575 队列上继续人工审查）；指标按真值覆盖率分层报告 | 否 |
| 2 | **地质线准确率验证范围不足** | P1 | line_error_triage / v3_line_geometry_attribution：误识别多为跨线/重叠歧义（409/632)+2–4px 偏移（103) | 否 | 扩大真实图幅验证集；把"已知线邻域内"与"真油墨"区分统计 | 否 |
| 3 | **OCR 小数字/上下标漏检** | P1 | POC-01 + Studio E2E:148 候选仍含误识别（Ar2E→Ar₂E 靠规则修）；小字号下标识别不稳 | 部分（文字层需人工复核兜底，已有 review_status 机制） | 提高 scale/局部放大重检；引入地层码专用字典（注意 POC 弃用的未确认词表） | 否 |
| 4 | **文字残影安全清除未完成** | P1 | 文字清理流程只做"隔离",16 个 Ar₂E 接触碎片留 pending 不自动归并；BACKGROUND_CLEAR_PENDING 状态存在但无自动清除实现 | 否（保守策略本身是安全特性） | 设计"残影归属确认"批量 UX；评估几何证据自动归入的门槛 | 否 |
| 5 | **Geology-Aware Pipeline 未实现** | P1 | profile `geology-aware-vnext` 正确显示 disabled;5 个阶段插件全部 NOT_IMPLEMENTED | 否（V0.1 范围外） | 按 `geology_aware_vnext_plan.md` 立项；先做 legend.preparse | 否 |
| 6 | **B2c 间歇性 segfault(-11)** | P1 | 2026-11-01 会话一次；此后 3 次完整复跑 17–18s 无异常 | 否（当前稳定，但未证明修复） | 保留 stage.log 取证；复现时保存 core/输入快照；排查 sv_lf/sv_d71 原生路径 | 否 |
| 7 | **GSJ 大图性能与稳定性未系统测试** | P2 | GSJ 只有 08001/08004 两幅裁剪做过 R2 审计；无整幅时延/内存曲线 | 否 | 选 1–2 幅整图跑全流程并记录资源曲线；确认 MAX_PIXELS 上限行为 | 否 |
| 8 | **Studio 人工 UAT/界面体验** | P2 | E2E 30/30 为自动验收；真实用户 UAT 未做；studio.js 132 行是最小 UI | 否 | 安排人工 UAT 清单（复用 editor UAT 方法）；收集交互反馈 | 否 |
| 9 | **JP2 导入声明未测** | P3 | inputs.sniff 支持 JP2，但样本套件无 JP2 文件 | 否 | 补一个 JP2 样本进 make_samples.py | 否 |
| 10 | **受保护数据无远端备份** | P0（数据安全） | DATA_BACKUP_MANIFEST.json:222 项 B 类 REMOTE_BACKUP_PENDING;gitlab 凭据失效 | 否（代码已全量推送） | 指定授权存储目的地后按 manifest 打包上传并校验 SHA-256 | **是——等目的地** |
| 11 | **gitlab 凭据失效** | P2 | `git ls-remote gitlab` → HTTP Basic access denied | 否（不影响 GitHub 线） | 刷新凭据；决定 audit/dev 是否仍需镜像 | 否 |
| 12 | **OCR truth 仍是草稿** | P2 | `runs/ocr_poc01/truth_draft/`(WIP,neg_draft/notes_*.tsv/sheet_*.png) | 否 | 完成 truth 定稿再谈语义指标 | 否 |
| 13 | **文档/依赖缺口** | P3 | 新机器需手工建 6 个 venv + 模型缓存（RECOVERY_GUIDE 已给步骤） | 否 | 需要时写 bootstrap 脚本 | 否 |
