---
name: patent-review
description: |
  对软件专利技术交底书、证据和交付稿进行多视角审查，并把结论绑定到材料版本与稳定 issue ID。
  包含一致性、IPR、技术可实现性、文体和交付检查；不自动修改案件材料。
  触发方式：/patent-review、「审查交底书」「一致性审计」「IPR 审查」「复审」。
---

# 软件专利交底书审查

读取 run manifest、五段正文、facts_ledger、evidence_pack 和当前交付文件。按用户要求覆盖一致性、IPR、技术可实现性、文体和交付结构。专利判断必须有来源支持；没有检索到的结论标记为待验证。离线校验只验证结构和版本，不能证明新颖性、授权或法律充分性。

## 审查能力

审查材料路径按当前 run manifest 的 canonical artifact path 字段解析到本次 workspace。当前仓库 runner 使用 manifest 模板声明的工作区相对 artifacts/audit/ 路径，不把 output_dir 当报告根目录，也不复用其他案件目录。自定义路径必须先确认 runner 支持，否则不能据此宣称门禁通过。


仓库当前包含两份 reviewer 提示文件：`agents/patent-consistency-auditor.md` 与 `agents/patent-tech-reviewer.md`。它们不是自动部署或自动启动的代理。只有宿主明确提供独立 reviewer 能力时才派发；没有时按各视角顺序审查，并如实注明使用了单一审查会话。IPR、可行性和文体是审查视角，不代表仓库中存在对应的专属 agent。

如需独立复核，只有在宿主实际支持独立调用且材料授权范围允许时才派发；宿主同时支持两路独立调用且两者审查职责可分时可以并行，否则按视角顺序审查并注明单会话。宿主须提供真实可读路径、SHA-256、审查范围及所需材料。只向每个 reviewer 提供完成任务所必需且已获准的材料或摘录；共享案件材料给外部服务前仍须对具体内容、目的地和用途取得用户明确确认。每条发现带稳定 ISSUE-... ID、严重度、位置、证据、修复建议和处置状态。不得把代码结构校验描述为语义审查或法律意见。

## 公式检查

- 技术审查视角核对公式是否可交付、变量/单位/取值域、量纲、代数关系、定义域、边界条件，并在可能时做最小数值核算；不能核验的结论标记 `blocked` 或待验证。
- 一致性视角核对公式编号与引用、符号跨段一致、约束说明一致，以及 Markdown 源文与 DOCX/其他导出件渲染一致。
- 先清点公式。没有公式时记录 `not_applicable`；有公式但缺少源文、变量定义或导出件时列明缺项。
- 格式、文档内一致性和数学正确性分别记录，不互相替代。

## 报告与版本

报告写入当前 manifest 指定的 consistency_report_path、ipr_report_path 与 review_status_path。本仓库 runner 的默认 canonical 路径由 manifest 模板给出，位于当前 workspace 的 artifacts/audit/；若字段缺失、路径不符 runner 支持范围或无法确定本次 workspace，先标为 blocked，不复用其他案件的绝对路径：

- consistency_report_path（Markdown 报告；取当前 manifest 的值）
- ipr_report_path（Markdown 报告；取当前 manifest 的值）
- 结构化 JSON 报告保存在同一 audit 目录，实际路径和哈希记录在 review_status 中。

同时保存供校验器使用的结构化 JSON 报告。每份报告包含对应 `doc_type`（`consistency_review_report` 或 `ipr_review_report`）、`report_type`、`review_id`、`completed_at`、具体 `scope`、`reviewed_materials.files`、`reviewed_materials.version_sha256` 和 `issues` 列表。每个 issue 有稳定 ID、严重度、处置状态和摘要。报告的原始 SHA-256 记录在 `review_status.json`。

review_status_path 至少记录：两份结构化报告的实际路径、类型、SHA-256 和完成状态；对应 Markdown 路径；被复核文件的 SHA-256 清单与版本指纹；问题 ID、严重度和处置状态；revision_validation。文件路径与哈希须匹配当前材料。哈希只绑定字节，不验证报告作者、用户身份或语义质量。

最终题名少于 25 个字，即最多 24 字。

## 高严重度问题与回改

未解决的高严重度问题必须解决，或由用户对具体 issue 明确豁免。豁免列出确切 issue ID、接受的具体风险、明确限制、确认时间、批准记录和当前材料版本哈希。`yes`、`all`、整份报告或字数阈值都不是有效范围。

审查只记录发现，不自动修改案件文件。修改前把用户批准的 issue ID 和具体范围写入 edit_plan；同一 ID 贯穿 edit、structured_diff、复审和豁免。已授权范围内不改变事实或保护范围的修复可以复用授权；新增事实、保护范围或风险决定仍需用户判断。

未授权修改时 `revision_validation` 可为 `not_required`，并将修订子检查标记为 skipped。已授权修改时，edit_plan 与 structured_diff 都要存在，复审报告针对修改后的哈希，post-fix 报告需记录 `checks_passed: true`、最新材料哈希和每个 issue 的处置。报告文件存在本身不代表检查通过。

## 数据边界

案件材料、未公开技术内容和脱敏映射默认留在本地。发送材料或由材料派生的查询给第三方模型、MCP、浏览器或检索服务前，先就具体材料、目的地和用途取得用户明确确认。未确认时保持离线，并记录该通道不可用。
