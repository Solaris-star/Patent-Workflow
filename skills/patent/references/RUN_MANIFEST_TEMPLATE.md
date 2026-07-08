# Patent Run Manifest

每轮专利 workflow 的运行状态记录。由 `init_run_manifest.py` 生成，各步骤持续更新。

## 基本信息

- `run_id`:
- `started_at`:
- `last_updated`:
- `current_step`:          # 初始化层 / 调研 / 方向收敛 / 查新 / 写作 / 审查 / 交付
- `last_passed_gate`:      # research / prior-art / draft / review / deliver

## 任务范围

- `domain_scope`:
- `fixed_topic_or_title`:
- `selected_direction`:
- `working_title`:
- `final_title`:
- `output_dir`:            # 冷启动必填：用户明确指定的绝对路径，不得默认猜测

## 能力画像（开局探测一次）

- `capability_profile`:
  - `smart_search_cli`:    # true/false
  - `search_mcp`:          # 可用的搜索类 MCP 工具名列表或 none
  - `browser_mcp`:         # 可用的浏览器类 MCP 工具名列表或 none
  - `mmdc`:                # true/false（附图渲染）
- `channels_used`:
- `channel_failures`:
- `fallback_actions`:
- `degraded_run`:          # 仅当兜底通道失败或用户豁免门禁时为 true

## 缓存复用

- `source_fingerprints`:           # 模板/参考件指纹
- `initialization_reused`:         # true/false
- `research_scope_key`:            # domain + topic + constraints 摘要
- `research_reused`:               # true/false

## 工件路径（固定下沉 artifacts/）

- `phase_02_research_pack_path`: `artifacts/research/phase_02_research_pack.json`
- `phase_04_patent_candidate_pool_path`: `artifacts/prior_art/phase_04_patent_candidate_pool.json`
- `phase_04_evidence_pack_path`: `artifacts/prior_art/phase_04_evidence_pack.json`
- `relevance_terms_path`: `artifacts/prior_art/relevance_terms.json`
- `facts_ledger_path`: `artifacts/draft/facts_ledger.json`
- `consistency_report_path`: `artifacts/audit/phase_08_consistency_audit_report.md`
- `ipr_report_path`: `artifacts/audit/phase_09_ipr_review_report.md`
- `edit_plan_path`: `artifacts/revision/phase_10_edit_plan.json`
- `structured_diff_path`: `artifacts/revision/phase_10_structured_diff.json`
- `post_fix_check_report_path`: `artifacts/revision/phase_10_post_fix_check_report.md`
- `delivery_health_report_path`: `artifacts/delivery/phase_11_delivery_health_report.json`

## 用户决策留痕

- `user_confirmations`:    # 只记真实发生的：领域选择、方向确认、豁免放行、历史工件沿用授权
- `open_risks`:
- `revision_round`:

<!-- GATE_RESULTS_JSON_BEGIN -->
```json
{
  "note": "Machine-readable gate results written by run_phase_gates.py (--manifest)."
}
```
<!-- GATE_RESULTS_JSON_END -->
