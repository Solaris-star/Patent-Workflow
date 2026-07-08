---
name: patent-review
description: |
  专利交底书多视角对抗式审查 + 结构性回改闭环。四个独立视角（一致性审计/IPR 模拟审查/
  技术审查/语言审查）并行审查，汇总对抗后输出可打分可定位的审计与 IPR 报告，
  并驱动 edit_plan → 修改 → structured_diff → 复审的回改闭环。
  触发方式：/patent-review、「审查交底书」「一致性审计」「IPR 审查」「模拟审查」「回改」。
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

**梯度 1 —— 宿主支持并行子代理**（Claude Code 的 Task/Agent 机制、Codex/Hermes 的等价原生机制）：

- 4 个视角各派 1 个子代理并行，互不通信（保证发现独立性）。
- 子代理指令模板：
  ```
  角色：{视角名}。只戴这一顶帽子，只报本视角问题。
  输入：{文件清单或正文}；证据：{facts_ledger / ipr_pack 路径（如有）}
  输出纯 JSON：{ "findings": [ { "issue": "…", "severity": "high|medium|low",
    "location": "part_XX/章节/图号", "symptom": "…", "evidence_or_reason": "…",
    "fix_suggestion": "…" } ], "dimension_scores": { 本视角相关分项: 0-10 } }
  要求：每个发现必须可定位（能指到具体部分/段落/图号）、可操作（fix_suggestion 具体）。
  ```

**梯度 2 —— 宿主无并行能力（自动降级）**：

- 主模型顺序执行 4 轮独立审查，每轮开头明确「抛弃上一轮结论，以 {视角名} 角色重新通读原文」，输出同一 JSON 结构。

**汇总对抗（两条梯度相同）**：

1. 合并 4 路 findings，按 `location + issue` 去重。
2. 冲突发现（两视角对同一处结论相反）→ 主模型复核原文裁决，裁决理由记入报告。
3. 按严重度排序，产出 top_issues（一致性）与 top_risks（IPR）。

## 落盘两份报告

- `artifacts/audit/phase_08_consistency_audit_report.md`：按 CONSISTENCY_AUDIT_TEMPLATE 填全——12 项审计结果、10 个分项评分（0-10）、`overall_score`（0-100）、`top_issues`（带 severity/location/symptom/fix_suggestion）、`pass_fail`（建议阈值 80）。
- `artifacts/audit/phase_09_ipr_review_report.md`：按 IPR_REVIEW_TEMPLATE 填全——证据基础（`evidence_granularity` 如实标注）、4 个分项评分（0-25）、`overall_score`、9 法定项逐项结论（通过/警告/驳回）、`top_risks`、`pass_fail_suggested`（建议阈值 70）。

独立审查外部文件且无 ipr_pack 时：IPR 报告如实标注 `evidence_basis: 无对比文献，仅形式与逻辑审查`，新颖性/创造性结论降级为「待检索验证」，不得假装做过对比。

## 回改闭环（审出问题时）

1. **edit_plan**：把 high/medium 的发现转为 `artifacts/revision/phase_10_edit_plan.json`：
   ```json
   {
     "doc_type": "edit_plan",
     "phase": "phase_10",
     "edits": [{
       "edit_id": "E1",
       "type": "consistency|ipr_risk|technical|language",
       "problem": "…",
       "change_instruction": "具体改法…",
       "risk_if_not_fixed": "high",
       "target": {"section": "part_03_发明内容", "anchor": "技术方案第2段"}
     }],
     "acceptance_checks": ["rerun_phase_08_consistency_audit", "rerun_phase_09_ipr_review"]
   }
   ```
2. **应用修改**：按 edit_plan 逐条修改对应 part（沿用 patent-draft 的版本备份与联动检测规则）；语言类问题调 `patent-deslop` 执行改写。
3. **structured_diff**：每条 edit 落实后记录 `artifacts/revision/phase_10_structured_diff.json`（`doc_type: structured_diff`，每条含 `linked_edit_id` 对应 edit_id、修改前后摘要）。
4. **复审**：复跑一致性审计与 IPR 审查的关键项（至少覆盖被修改部分与全部 high 项），结果写 `artifacts/revision/phase_10_post_fix_check_report.md`。
5. **门禁**：
   ```
   python <patent-skill-dir>/scripts/run_phase_gates.py --gate review --workspace . --manifest artifacts/run_manifest.md
   ```
   通过且复审无新增 high 项 → 放行终稿导出；否则回到第 1 步（`revision_round` +1，超过 3 轮仍有 high 项时向用户说明分歧点请求决策）。

## 纪律

1. 评分必须给口径（满分/阈值），发现必须可定位——「整体感觉不错」不是审查结论。
2. 未做对比文献核验时禁止给出新颖性「通过」结论。
3. 审查不顺手改稿——发现与修改分离，修改必须走 edit_plan 留痕。
4. 全流程模式下回改完成后必须复审，不得「改完即过」。
