---
name: patent-review
description: |
  专利交底书多视角对抗式审查。四个独立视角（一致性审计/IPR 模拟审查/技术审查/语言审查）
  并行审查，汇总对抗后输出可打分可定位的审计与 IPR 报告，向用户汇报问题清单与修改建议。
  只审不改——修改由用户决策（自己改或委托代改），改完可触发复审。
  触发方式：/patent-review、「审查交底书」「一致性审计」「IPR 审查」「模拟审查」「复审」。
  可独立审查外部现成交底书（docx/md），也被 patent 全流程编排调用。
---

# patent-review：多视角对抗审查与回改闭环

审查对象：本项目的 5 个 part + facts_ledger + ipr_pack，或用户提供的外部交底书文件（docx/md，读入后按同一流程审）。

报告骨架为强绑定模板：[references/CONSISTENCY_AUDIT_TEMPLATE.md](references/CONSISTENCY_AUDIT_TEMPLATE.md)、[references/IPR_REVIEW_TEMPLATE.md](references/IPR_REVIEW_TEMPLATE.md)。

## 四个审查视角

| 视角 | 审什么 | 证据基础 |
|---|---|---|
| **一致性审计员** | 术语统一、图号/图名/正文引用/插图顺序四方一致、交叉引用、章节结构、模块命名、公式符号、交付结构 | facts_ledger + 全文 |
| **IPR 审查员** | 9 项法定审查（授权客体/新颖性/创造性/实用性/充分公开/权利要求支持/单一性/修改超范围/诚实信用，依《专利审查指南》）+ 形式审查 | ipr_pack（feature_to_prior_art_matrix、novelty_evidence_table）+ 全文 |
| **技术审查员** | 技术方案完整性与可实现性、模块/步骤连接关系与数据流是否闭合、数据真实性（揪编造的百分比/准确率）、实施例与本发明领域相关性 | 全文 + research_pack 证据 |
| **语言审查员** | AI 浓度（排比、过度工整、列表腔）、语气（解释腔/汇报腔/对外文档用语）、专利文体规范（「所述」体） | 全文（只查不改，修复路由到 patent-deslop） |

## 执行（能力梯度，宿主中立）

**梯度 1 —— 预定义审查子代理（首选）**：宿主的用户级 agent 目录已部署 4 个专属审查员（随家族 `deploy.ps1` 一并安装），并行派发、互不通信（保证发现独立性）。每个 agent 自带审查清单、证据纪律与输出契约：

| agent | 视角 |
|---|---|
| `patent-consistency-auditor` | 一致性审计（术语/图号四方/交叉引用/结构） |
| `patent-ipr-examiner` | IPR 模拟审查（9 法定项 + 形式审查） |
| `patent-tech-reviewer` | 技术审查（数据流闭合/可实现性/数据真实性/实施例相关性） |
| `patent-language-auditor` | 语言审查（AI 浓度/语气/专利文体，只查不改） |

派发时给每个 agent：待审文件清单 + 对应证据路径（facts_ledger / ipr_pack / research_pack，按视角；ipr_pack 固定在 `artifacts/prior_art/phase_05_ipr_pack.json`，background_pack 在 `…/phase_05_background_pack.json`）。

**梯度 2 —— 预定义 agent 缺失**：用宿主通用子代理机制并行派发，指令按视角现场组装：

```
角色：{视角名}。只戴这一顶帽子，只报本视角问题。
输入：{文件清单}；证据：{facts_ledger / ipr_pack 路径（如有）}
输出纯 JSON：{ "findings": [ { "issue", "severity": "high|medium|low",
  "location", "symptom", "evidence_or_reason", "fix_suggestion" } ],
  "dimension_scores": {…} }
要求：每个发现必须可定位、可操作。
```

**梯度 3 —— 宿主无并行能力**：主模型顺序执行 4 轮独立审查，每轮开头明确「抛弃上一轮结论，以 {视角名} 角色重新通读原文」，输出同一 JSON 结构。

**汇总对抗（两条梯度相同）**：

1. 合并 4 路 findings，按 `location + issue` 去重。
2. 冲突发现（两视角对同一处结论相反）→ 主模型复核原文裁决，裁决理由记入报告。
3. 按严重度排序，产出 top_issues（一致性）与 top_risks（IPR）。

## 落盘两份报告

- `artifacts/audit/phase_08_consistency_audit_report.md`：按 CONSISTENCY_AUDIT_TEMPLATE 填全——12 项审计结果、10 个分项评分（0-10）、`overall_score`（0-100）、`top_issues`（带 severity/location/symptom/fix_suggestion）、`pass_fail`（建议阈值 80）。
- `artifacts/audit/phase_09_ipr_review_report.md`：按 IPR_REVIEW_TEMPLATE 填全——证据基础（`evidence_granularity` 如实标注）、4 个分项评分（0-25）、`overall_score`、9 法定项逐项结论（通过/警告/驳回）、`top_risks`、`pass_fail_suggested`（建议阈值 70）。

独立审查外部文件且无 ipr_pack 时：IPR 报告如实标注 `evidence_basis: 无对比文献，仅形式与逻辑审查`，新颖性/创造性结论降级为「待检索验证」，不得假装做过对比。

## 审查后动作：汇报并停下，修改权在用户

落盘报告后**向用户汇报并结束本次审查**，不自动修改任何文件：

1. 汇报内容：两个总分（含口径）、top_issues / top_risks 逐条（severity / location / symptom / fix_suggestion），按严重度排序——每条建议都要具体到「改哪里、怎么改」，让用户可以直接照着自己动手。
2. 用户决策分支（如实列出，不催促）：
   - **用户自己修改** → 改完说「复审」即进入复审模式；
   - **委托代改** → 用户点名要改哪些条目后，修改动作走 `patent-draft` 的修改能力（版本备份 + 联动检测 + facts_ledger 同步），代改留痕规则见 patent-draft；
   - **豁免放行** → 用户明确接受某些风险不改，记入 run manifest 的 `user_confirmations`。
3. 全部视角零问题（无 high/medium）时如实说明可直接进入交付，无需停顿。

## 复审模式（用户改完后触发）

1. 复审范围：被修改的部分 + 上一轮全部 high 项 + 修改联动可能波及的关联段（以 patent-draft 联动修改建议清单为准；最小充分集，不必全文重审——用户要求全审除外）。
2. 结果写 `artifacts/revision/phase_10_post_fix_check_report.md`，与上一轮报告对照给出「已解决 / 未解决 / 新引入」三类清单。
3. 仍有 high 项 → 回到汇报等用户决策（`revision_round` +1）；无 high 项或用户豁免 → 全流程可进入终稿导出。

## 纪律

1. 评分必须给口径（满分/阈值），发现必须可定位——「整体感觉不错」不是审查结论。
2. 未做对比文献核验时禁止给出新颖性「通过」结论。
3. **只审不改**：本 skill 不修改任何交底书文件；发现问题的出口只有向用户汇报。
4. 复审不得走过场——「已解决」结论必须基于重新读取修改后的文本，不得沿用记忆。
