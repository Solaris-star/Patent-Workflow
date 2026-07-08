# Patent Workflow Run Manifest Template

本模板用于记录每轮专利 workflow 的运行状态。

## 基本信息

- `run_id`:
- `started_at`:
- `last_updated`:
- `current_phase`:
- `last_passed_gate`:
- `resume_from_phase`:

## 任务范围

- `domain_scope`:
- `fixed_topic_or_title`:
- `output_dir`:  # 冷启动必填：用户本轮明确指定的绝对路径；不得默认猜测
- `source_fingerprints`:
- `default_material_sources`:

## 降级标记

- `degraded_flags`:
- `cache_hits`:
- `cache_misses`:

## 阶段工件路径（固定下沉到 artifacts/）

- `phase_02_research_pack_path`: `artifacts/research/phase_02_research_pack.json`
- `phase_04_patent_candidate_pool_path`: `artifacts/prior_art/phase_04_patent_candidate_pool.json`
- `phase_04_evidence_pack_path`: `artifacts/prior_art/phase_04_evidence_pack.json`
- `phase_07_facts_ledger_path`: `artifacts/draft/facts_ledger.json`
- `phase_10_edit_plan_path`: `artifacts/revision/phase_10_edit_plan.json`
- `phase_10_structured_diff_path`: `artifacts/revision/phase_10_structured_diff.json`
- `phase_10_post_fix_check_report_path`: `artifacts/revision/phase_10_post_fix_check_report.md`
- `phase_11_delivery_health_report_path`: `artifacts/delivery/phase_11_delivery_health_report.json`

## 专利检索阶段留痕（阶段 4）

- `patent_search_queries`:
- `candidate_pool_generated_by`:
- `candidate_pool_generation_mode`:
- `candidate_pool_channels_used`:
- `candidate_pool_reasoning_chains_used`:
- `patent_candidate_pool_path`:
- `patent_candidate_pool_count`:

## 阶段门禁脚本运行结果（可审计）

- `validators_ran`: # 例如 ["validate_research_pack", "validate_patent_candidates", ...]
- `validator_summaries`: # key -> summary json path（若落盘）

- `phase_02_validate_research_pack_ran`:
- `phase_02_validate_research_pack_passed`:
- `phase_02_validate_research_pack_summary_path`:

- `phase_04_validate_patent_candidates_ran`:
- `phase_04_validate_patent_candidates_passed`:
- `phase_04_validate_patent_candidates_summary_path`:

- `phase_04_validate_evidence_pack_ran`:
- `phase_04_validate_evidence_pack_passed`:
- `phase_04_validate_evidence_pack_summary_path`:

- `phase_07_validate_facts_ledger_ran`:
- `phase_07_validate_facts_ledger_passed`:
- `phase_07_validate_facts_ledger_summary_path`:

- `phase_10_validate_edit_plan_ran`:
- `phase_10_validate_edit_plan_passed`:
- `phase_10_validate_edit_plan_summary_path`:

- `phase_10_validate_structured_diff_ran`:
- `phase_10_validate_structured_diff_passed`:
- `phase_10_validate_structured_diff_summary_path`:

- `phase_11_health_check_delivery_package_ran`:
- `phase_11_health_check_delivery_package_passed`:
- `phase_11_health_check_delivery_package_summary_path`:

## 专利候选门禁细项（由 validate_patent_candidates.py 产出摘要回填）

- `finalRelevantPatents_count`:
- `peripheralReferences_count`:
- `cn_only_passed`:
- `freshness_passed`:
- `relevance_passed`:
- `min_count_passed`:

<!-- GATE_RESULTS_JSON_BEGIN -->
```json
{
  "note": "Machine-readable gate results written by scripts/run_phase_gates.py (--manifest).",
  "example": {
    "cmd": "python skills/patent-workflow/scripts/run_phase_gates.py --phase 4 --workspace . --manifest artifacts/run_manifest.md",
    "exitCodes": {"0": "all gates passed", "2": "any gate failed"}
  }
}
```
<!-- GATE_RESULTS_JSON_END -->
