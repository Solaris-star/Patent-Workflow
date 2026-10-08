# 案件目录布局

仅用案件本地目录保存运行材料。按实际工作需要创建目录，不复制真实案件样例到仓库或公共示例。

建议结构：

- inputs/：用户明确选择并导入的源文件副本。
- artifacts/research/：研究包和范围记录。
- artifacts/prior_art/：证据、背景比较和按请求创建的 IPR 包。
- artifacts/draft/：五段正文、事实台账和附图源文件。
- artifacts/audit/：审查报告与 review_status。
- artifacts/revision/：获准的 edit_plan、structured_diff 和复审结果。
- artifacts/delivery/：最终 Markdown、DOCX 与交付健康报告。

run manifest 记录当前阶段、实际材料路径、缺失项、下一步、用户等待状态和哈希。初始化不得覆盖已有文件；恢复时保留现有材料。
