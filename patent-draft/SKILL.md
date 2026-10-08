---
name: patent-draft
description: "按可追溯证据和用户确认范围协作撰写、复审并交付软件专利技术交底书。"
---

# 软件专利交底书撰写与交付

仅处理专利交底书，不编排研发任务。先读取 run manifest、现有五段正文、facts_ledger、evidence_pack、审查状态和用户确认，再决定续写、补证、修订或导出。

## 五段正文

在 artifacts/draft 中保留实际五个非空 Markdown 文件，文件名以 part_01_ 至 part_05_ 开头：

1. 发明名称
2. 背景技术
3. 发明内容
4. 附图说明
5. 具体实施方式

题名统一最多 24 个字。正文只写 source registry、证据和用户确认支持的内容。已实现事实、来源陈述、推断和待确认事项分别标注，不把推断写成已验证事实，不编造效果或专利引用。

## 证据与特征追溯

沿用 phase_04_evidence_pack.json 和 facts_ledger.json。每个稳定 feature_id 使用 F-... 形式，并引用 source_id、evidence_id、paragraph_id 与 figure_id。材料和代码来源记录 SHA-256；外部证据记录 URL、摘录、日期、核验状态和核验日期。事实台账不要另建平行数据库。

正文引用外部证据时使用 [[EVIDENCE-ID]]，并使其与事实台账中的 evidence_id 一致。离线校验只验证结构、链接、哈希、日期和显式核验状态，不提供新颖性或授权结论。

## Mermaid 图

默认 figure_delivery_mode 是 mermaid_only：

- 每幅图在附图目录交付一个有效、非空的 .mmd 源文件。
- facts_ledger.figure_registry 记录 figure_id、caption、artifacts.mmd 和对应的 feature_id。
- part_04 引用每个图号与图名；DOCX 中包含相应 Mermaid 源码。
- 不要求 PNG、SVG、drawio 或 DOCX 中的位图。

用户明确要求图片时，manifest 设置 figure_delivery_mode 为 mermaid_and_images。每个图片文件都必须存在于实际交付目录、被终稿 Markdown 引用，并在 DOCX 中有有效图片关系。单独存在的 DOCX media 文件不能替代实际引用。

## 修改授权

审查问题用稳定 ISSUE-... ID。修订计划列出用户批准的 issue_ids 与范围，每条 edit 和 structured_diff 都引用相同 issue_id。针对已批准问题且不改变技术事实或保护范围的修复可复用授权；加入新技术事实、扩大范围或接受未解决风险时，必须记录具体用户决定。没有批准的回改时保持原稿，并将 revision_validation 设为 not_required。

材料或终稿哈希变化后，旧审查结论待复核。审查报告存在不等于通过；review_status.json 必须显式确认一致性审查、IPR 审查、issue disposition、版本哈希和高严重度豁免。

## 导出与验证

从仓库根目录执行：

~~~powershell
python patent/scripts/workflow_cli.py export --workspace . --manifest artifacts/run_manifest.md
python patent/scripts/workflow_cli.py check --workspace . --manifest artifacts/run_manifest.md --gate deliver
~~~

若 manifest 声明 `sensitive_map_path`，以上两条命令都须追加 `--sensitive-map "<manifest 中相同的绝对路径>"`。导出会重跑当前模式的有效门禁与审查，验证所选 map 的当前内容和确认绑定，并扫描最终 Markdown 与生成的 DOCX；缺少重选或路径不匹配时，在读取 map 前失败。导出使用同目录临时 DOCX，输出 `generated_pending_delivery_check` 且 `workflow_complete: false`。随后单独运行 deliver 门禁检查 manifest 绑定的输出目录、Markdown、DOCX、最新 review_status 和源文件。DOCX 文本会检查题名、证据引用、图源和 Markdown/数学残留；本机 LibreOffice 渲染不可用时记录为 `not_run`，交付门禁不能报告 complete。

## 边界

案件材料默认只留在本地。向第三方模型、MCP、搜索或消息服务发送任何材料前，先向用户确认具体材料、目的地和用途。不得仅因工作流包含检索阶段就自行发送材料。离线验证是结构检查，不是法律意见。
