# Patent Workflow Handoff Contract

本文件定义 `patent-workflow` 各阶段之间的最小交接契约。

## 0. 范围确认 -> 材料预处理

必须已有：

- `domain_scope`
- `fixed_topic_or_title`
- `template_source`
- `reference_patent_source`
- `output_dir`
- `run_id`
- `run_manifest_path`
- `source_fingerprints`
- `default_materials_reused`
- `content_artifacts_reused = false`，或给出用户明确授权的复用依据
- `forbidden_reuse_check_passed = true`

## 1. 材料预处理 -> deep-research

必须已有其一：

- `template_text_ready = true`
- `template_text_cache_hit = true`
- `template_not_provided = true`

必须已有其一：

- `reference_patent_text_ready = true`
- `reference_patent_text_cache_hit = true`
- `reference_patent_not_provided = true`

并记录：

- `preprocess_notes`
- `preprocess_skipped_reason`
- `preprocess_cache_status`
- `source_fingerprints`

## 2. deep-research -> 方向与题目收敛

必须已有：

- `research_scope_key`
- `research_cache_hit`
- `channels_used`
- `channels_skipped`
- `why_skipped`
- `degraded_run`
- `validation_channel_used`
- `strong_source_count >= 3`
- `evidence_table_count >= 3`
- `candidate_directions` 或固定题目下的 `candidate_innovation_axes`
- `recommended_direction`
- `claims_requiring_patent_verification`
- `directions_provenance`
- `direction_alignment_check`
- `brain_chain_status`
- `channel_failures`
- `fallback_actions`

## 3. 方向与题目收敛 -> 背景专利检索与审查包准备

必须已有：

- `selected_direction`
- `patent_search_queries[]`
- `patent_candidate_pool_path`
- `patent_candidate_pool_count`
- `validator_script_path`
- `candidate_pool_generated_by = deep-research`
- `candidate_pool_generation_mode = multi-chain`
- `candidate_pool_channels_used`
- `candidate_pool_reasoning_chains_used`

## 4. 背景专利检索与审查包准备 -> 模板与风格分析

必须已有：

- `patent_candidate_pool_path`
- `validator_script_path`
- `validator_ran = true`
- `validator_passed = true`
- `validator_summary_path`
- `finalRelevantPatents_count >= 5`
- `cn_only_passed = true`
- `freshness_passed = true`
- `relevance_passed = true`
- `peripheralReferences_count`
- `background_pack_ready = true`
