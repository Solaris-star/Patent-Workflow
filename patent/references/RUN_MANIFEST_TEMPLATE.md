# Patent Workflow Run Manifest

One manifest records workflow state, decisions, source versions, and gate results. Keep case-specific material and private mappings in the local case workspace, not in repository documentation.

## Run

- run_id:
- started_at:
- last_updated:
- current_step: init
- last_passed_gate:
- workflow_mode: full_research
- search_depth: balanced
- output_dir:
- final_markdown_path:
- final_title:
- working_title:
- figure_delivery_mode: mermaid_only
- ipr_requested: false
- research_origin: normal
- vault_direction_origin:
- vault_case_id:
- vault_opted_out:
- sensitive_map_path:
- review_status_path: artifacts/audit/review_status.json

## Confirmations and scope

- user_confirmations:
- approved_issue_scope:
- data_transfer_confirmations:
- open_risks:
- revision_round: 0

Keep each confirmation specific to its decision. A data-transfer record names the exact material or query, destination, purpose, and confirmation time. A confirmation in one run or for one destination does not authorize a different transfer.

Record a confirmation only when the user actually made that decision. For any data transfer out of the local workspace, record the specific material, destination, purpose, and confirmation before making the transfer. A word-count or edit-count threshold is never a substitute for user approval.

## Capabilities and requested search

- capability_profile:
  - smart_search_cli:
  - search_mcp:
  - browser_mcp:
  - mmdc:
- channels_used:
- channel_failures:
- fallback_actions:
- degraded_run: false
- search_request:
  - depth: balanced
  - date_window:
  - jurisdiction:
  - requested_sources:

## Reuse and versioning

- source_fingerprints:
- initialization_reused: false
- research_scope_key:
- research_reused: false
- material_hashes:

## Canonical artifact paths

- phase_02_research_pack_path: artifacts/research/phase_02_research_pack.json
- phase_04_patent_candidate_pool_path: artifacts/prior_art/phase_04_patent_candidate_pool.json
- phase_04_evidence_pack_path: artifacts/prior_art/phase_04_evidence_pack.json
- phase_05_background_pack_path: artifacts/prior_art/phase_05_background_pack.json
- phase_05_ipr_pack_path: artifacts/prior_art/phase_05_ipr_pack.json
- facts_ledger_path: artifacts/draft/facts_ledger.json
- consistency_report_path: artifacts/audit/phase_08_consistency_audit_report.md
- ipr_report_path: artifacts/audit/phase_09_ipr_review_report.md
- review_status_path: artifacts/audit/review_status.json
- edit_plan_path: artifacts/revision/phase_10_edit_plan.json
- structured_diff_path: artifacts/revision/phase_10_structured_diff.json
- post_fix_check_report_path: artifacts/revision/phase_10_post_fix_check_report.json
- delivery_health_report_path: artifacts/delivery/phase_11_delivery_health_report.json

<!-- WORKFLOW_STATE_JSON_BEGIN -->
~~~json
{
  "workflow_mode": "full_research",
  "stage_history": [],
  "completed_stages": [],
  "completed_gates": [],
  "invalidated_gates": [],
  "required_materials": [],
  "missing_materials": [],
  "next_step": "initialize",
  "waiting_for_user": false,
  "material_hashes": {},
  "material_registry": {},
  "pending_user_decisions": [],
  "skipped": [],
  "not_run": [],
  "sensitive_map_audit": null,
  "last_export": null
}
~~~
<!-- WORKFLOW_STATE_JSON_END -->

`workflow_cli.py export` 会在状态中记录最近一次导出及 `post_export_delivery_check_required: true`，并返回待交付检查状态。导出生成 DOCX 不会令 `workflow_complete` 变为 true；需要随后单独运行 deliver 门禁。

<!-- GATE_RESULTS_JSON_BEGIN -->
~~~json
{
  "runner": "run_phase_gates.py",
  "checks_passed": false,
  "workflow_complete": false,
  "review_completed": false,
  "revision_validation": "not_run",
  "gate_status": "not_run",
  "skipped": [],
  "not_run": []
}
~~~
<!-- GATE_RESULTS_JSON_END -->
