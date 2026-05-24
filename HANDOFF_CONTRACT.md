# Patent Workflow Handoff Contract

本文件定义 `patent-workflow` 各阶段之间的最小交接契约。

## 0. 材料预处理与运行清单初始化 -> 范围确认

必须已有：

- `run_id`
- `output_dir`
- `preprocess_notes`
- `preprocess_cache_status`
- `source_fingerprints`
- `source_fingerprints_path`
- `template_rules_ready = true`
- `style_profile_ready = true`
- `template_rules_path`
- `style_profile_path`
- `style_profile_markdown_path`
- `run_manifest_json_path`
- `template_rules_schema_version`
- `style_profile_schema_version`
- `artifacts/preprocess/phase_00_preprocess_notes.md`
- `artifacts/preprocess/source_fingerprints.json`
- `template_rules.json`
- `style_profile.json`
- `style_profile.md`
- `artifacts/run_manifest.json`

说明：模板规则和默认风格画像在阶段 0 准备，不再设置单独的模板风格分析阶段。源文件指纹必须包含 `sha256`，用于复现、缓存判断和审计追踪。Phase 0 是全局初始化阶段；再次启动 workflow 时，若源文件指纹未变化且 Phase 0 工件齐全，应复用首次预处理产物，并将 `preprocess_cache_status` 置为 `cache_hit_reused`；仅在源材料变化或显式 `force_preprocess` / `refresh_preprocess` 时刷新。

## 1. 范围确认 -> 候选专利挖掘与初步查新

必须已有：

- `domain_scope`
- `run_id`
- `output_dir`
- `preprocess_cache_status`
- `template_rules_ready = true`
- `style_profile_ready = true`

阶段 1 必须区分用户输入成熟度：

- 用户给出明确专利题目时，写入 `idea_maturity=fixed_topic`、`phase_02_mode=topic_research`、`fixed_topic_or_title=<用户题目>`。
- 用户没有具体 idea 但给出模糊行业领域时，写入 `idea_maturity=vague_domain`、`phase_02_mode=broad_domain_discovery`，并直接进入阶段 2 做单领域深挖与交叉领域创新挖掘，不得在阶段 1 反复追问。
- 用户完全未给领域边界时，`domain_scope` 可以为 `待系统推荐`，但阶段 2 必须先替换为默认种子领域集合并记录 `domain_discovery_strategy`，不得把 `待系统推荐` 作为真实搜索词。

## 2. 候选专利挖掘与初步查新 -> 方向与题目收敛

必须已有：

- `research_scope_key`
- `research_cache_enabled = true`
- `research_cache_hit`
- `research_cache_hit_count`
- `research_cache_imported_count`
- `research_cache_path`
- `channels_used`
- `channels_skipped`
- `why_skipped`
- `degraded_run`
- `strong_source_count >= 3`
- `evidence_table_count >= 3`
- `candidate_directions` 或固定题目下的 `candidate_innovation_axes`
- `recommended_direction`
- `claims_requiring_patent_verification`
- `brain_chain_status`
- `channel_failures`
- `fallback_actions`
- `artifacts/research/phase_02_research_pack.json`

`phase_02_research_pack.json` 必须是结构化 JSON，至少包含：

- `pack_type = research_pack`
- `phase = phase_02`
- `source_plan`：来源类型及示例站点
- `research_questions[]`：每项包含 `id`、`question`、`purpose`、`source_focus`、`example_sites`
- `search_results[]`：每项包含 `question_id`、`query`、`status`、`content`、`sources[]`
- `evidence[]`：每项包含 `evidence_id`、`question_id`、`source_type`、`site`、`title`、`url`、`excerpt`、`claim_supported`、`relevance_score`
- `outline_skeleton[]`：每项包含 `section_id`、`title`、`intent`、`covers_questions`、`evidence_ids`
- `ranking_policy`：评分公式与新颖性、可落地性、证据支撑、资料新鲜度、跨源一致性、迁移价值和创新潜力的打分标准
- `candidate_directions[]`：每项包含 `direction_id`、`title`、`problem_focus`、`solution_hint`、`scores`、`score_basis`、`recommendation_reason`、`evidence_summary[]`、`evidence_ids`；专利驱动候选还必须包含 `proposed_patent_title`、`title_char_count`、`reference_patent_problem`、`improvement_point`、`evidence_url`、`non_patent_hotspot`
- `recommended_direction_detail` 与 `decision_basis`

说明：`strong_source_count` 是去重可信 URL 数；`evidence_table_count` 是 `evidence[]` 的真实条数。推荐候选必须由评分排序得出，不得固定写死。阶段 2 先检索最近 18 个月有效参考专利，再结合 X/学术/工程/产业等非专利信源生成 7 个候选专利名称；核心参考专利只允许授权、实质审查中、实质审查生效或等价有效状态，明确排除撤回、驳回、视为撤回、放弃、失效、终止等状态。候选标题必须参考检索到的有效同类专利命名风格生成，不写死格式，且总字数不超过 25；每个候选向用户展示候选专利名称、参考专利解决的问题、本候选的改良点、证据 URL、非专利热点信源。Phase 2 不输出法律性新颖性结论或侵权风险结论；需要深度查新的组合特征写入 `claims_requiring_patent_verification`，并在 Phase 2 内部的深度专利复核步骤中继续处理。

## 3. 方向与题目收敛 -> Phase 2 内部深度专利复核

必须已有：

- `selected_direction`
- `patent_title`
- `claims_requiring_patent_verification[]` 或明确记录无需深度复核的理由
- `patent_search_queries`
- `candidate_pool_channels_used`
- `candidate_pool_generation_mode`
- `trusted_patent_channels`
- `trusted_patent_source_count`
- `patent_candidate_pool_count`
- `finalRelevantPatents_count`
- `cn_only_passed`
- `freshness_passed`
- `relevance_passed`
- `artifacts/prior_art/phase_02_patent_candidate_pool.json`
- `artifacts/prior_art/phase_02_evidence_pack.json`

说明：Phase 2 现在同时承担候选专利挖掘、初步查新和内部深度专利复核，不再拆成独立 Phase 4。它必须先完成候选方向生成，再在同一阶段内复核可信专利渠道、生成候选池和 evidence_pack。最终候选必须来自可信专利 URL，并通过 CN、freshness、relevance 三类门禁。research cache 中的历史专利命中只能作为 `prior_art_candidate_requires_revalidation` 线索；进入碰撞判断或影响正文背景的专利必须重新验证官方法律状态、授权公告号和摘要/权利要求相关性。外围网页只能进入 `peripheral_sources` 或 `is_auxiliary=true` 的证据条目。

## 4. Phase 2 -> 正文草稿撰写

必须已有：

- `template_rules.json`
- `style_profile.md`
- `selected_direction`
- `patent_title`

## 5. 正文草稿撰写 -> 一致性审计

必须已有：

- `template_rules_ready = true`
- `style_profile_ready = true`
- `draft_status`
- `facts_ledger_ready = true`
- `step_registry_ready = true`
- `figure_registry_ready = true`
- `terminology_registry_ready = true`
- `research_inputs_ready`
- `shared_context_ready = true`
- `shared_context_within_budget = true`
- `block_contexts_ready = true`
- `block_reviews_ready = true`
- `artifacts/draft/shared_context.json`
- `artifacts/draft/phase_05_writing_plan.json`
- `artifacts/draft/facts_ledger.json`
- `artifacts/draft/step_registry.json`
- `artifacts/draft/figure_registry.json`
- `artifacts/draft/terminology_registry.json`
- `artifacts/draft/block_contexts/part_01_context.json`（其余分块同结构）
- `artifacts/draft/block_reviews/part_01_review.json`（其余分块同结构）

说明：阶段 5 必须读取 Phase 2/4 的研究资料与背景专利证据，先生成短 `shared_context.json` 作为公共事实锚点，再生成每个正文分块独立的 `block_context.json` 与 `block_review.json`。`shared_context.json` 只保留标题、方向、技术问题、术语、步骤、图号、锁定事实和禁止项，不放长证据，且必须控制在预算内；每个分块上下文只包含本块必要证据，避免长上下文污染；分块审核至少检查实际字数、建议字数范围、长度达标状态、证据引用、shared_context 一致性、上下文隔离和占位内容。`phase_05_writing_plan.json` 必须包含 `section_word_budget`，默认范围为技术领域 50–150 字、背景技术 500–900 字、发明内容 800–1400 字、附图说明自然语言 30–120 字（不含 Mermaid/mmd 代码块，建议至少 4 张图且每图附 mmd）、具体实施方式 1800–3500 字；`facts_ledger.block_statuses` 必须保留各分块的字数检查结果，供 Phase 6 复核。若已有分块命中正文污染规则（修订占位、非 CN 背景专利、技术领域过度、技术问题语病、附图缺 Mermaid、具体实施缺图号或含未实验数据/公式风险），必须备份到 `artifacts/draft/superseded_blocks/` 后重生安全草稿。`facts_ledger.json` 是步骤、附图、术语、约束效果和分块状态总账，三个 registry 文件从该总账拆分给后续阶段直接读取。

## 6. 一致性审计 -> IPR 模拟审查

必须已有：

- `consistency_audit_score`
- `consistency_audit_passed = true`
- `top_issues`
- `artifacts/audit/phase_06_consistency_audit_report.md`

## 7. IPR 模拟审查 -> 审后修订与复审闭环

必须已有：

- `ipr_review_score`
- `ipr_review_passed = true`
- `top_risks`
- `artifacts/audit/phase_07_ipr_review_report.md`

说明：阶段 7 必须输出“法规依据与规则映射”，每个法定审查项至少包含 `rule_id`、法规条款标签、审查目标、实现函数和输入文件；该阶段不内置法规全文，也不等同正式法律意见。新颖性与诚实信用相关核查必须读取 Phase 2 内部专利复核的 `phase_02_evidence_pack.json`，用于复核背景专利摘录、可信 URL 与专利号一致性。

## 8. 审后修订与复审闭环 -> 最终导出与交付

必须已有：

- `edit_plan_validated = true`
- `structured_diff_validated = true`
- `post_fix_check_passed = true`
- `review_loop_passed = true`
- `artifacts/revision/phase_08_edit_plan.json`
- `artifacts/revision/phase_08_structured_diff.json`
- `artifacts/revision/phase_08_post_fix_check_report.md`
- `artifacts/revision/phase_08_post_fix_check.json`

阶段 8 必须在修订后直接复跑 phase_6 和 phase_7 执行器，重新生成审计/IPR 报告，并记录 `review_loop_results`。`edit_plan.json` 必须区分 `fix_mode = auto | agent_required | manual_review`，避免把需要内容重写的问题误判为脚本可修。`.md` 报告用于人工阅读，`.json` 报告用于机器校验。

## 9. 最终导出与交付 -> 完成交付

必须已有：

- `delivery_health_report_path`
- `delivery_passed = true`
- `final_docx_path`
- `deliver_dir`
- `deliver_dir_explicit = true`
- `docx_generated = true`
- `delivery_structure_passed = true`
- `delivery_from_dirty_tree`
- `artifacts/delivery/phase_09_delivery_health_report.json`

说明：阶段 9 不得把 Markdown 降级文件视为正式交付；docx 生成失败时必须 `delivery_passed = false`。交付健康检查前必须先执行正文质量硬门禁，仍含修订占位、非 CN 背景专利、技术领域过度、技术问题语病、附图缺 Mermaid、具体实施缺图号、未实验数据或公式兼容风险时必须 `failed`。交付健康检查前必须先复制 `附图/`，并确保终稿命名为 `<专利标题>技术交底书.docx`；manifest 缺标题时从 `facts_ledger.json`、`shared_context.json` 或 Phase 2 推荐方向回退解析。健康检查通过后必须生成 `patent_delivery_package.zip`，zip 内部文件名使用 ASCII-only 路径，并用 `README.md` 保留原中文标题和原中文文件名，避免解压工具乱码。若最终交付目录未明确指定，必须记录 `deliver_dir_explicit = false` 并阻断正式交付。
