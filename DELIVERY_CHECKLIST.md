# Patent Workflow Delivery Checklist

在宣告“专利技术交底书已完成交付”之前，逐项检查。

> 注：当前 workflow 已支持“默认直接开跑”。阶段 0 统一负责材料预处理、运行清单初始化、模板规则与默认风格画像准备；独立模板风格分析阶段已取消。

## 一、流程可见性与留痕

- [ ] 已创建并持续更新 `run manifest`（包含当前阶段、降级/失败原因、关键工件路径），并同步生成机器可读的 `artifacts/run_manifest.json`。
- [ ] 已记录初始化层源文件指纹、缓存命中/未命中情况。
- [ ] 已记录 `research_scope_key`、`research_cache_enabled`、`research_cache_hit_count`、`research_cache_imported_count` 与 `research_cache_path`。
- [ ] 已记录 `research_reuse_status`、`research_scope_match` 与 `research_reuse_basis`。
- [ ] 如本轮未复用 research，已记录 `research_refresh_reason` 或 `research_invalidation_reason`。

## 二、领域/题名（阶段 1/2/3 相关）

- [ ] 若用户未指定领域：阶段 2 已执行“交叉领域发现（cross-domain discovery）”，并给出推荐的交叉领域组合 + 证据 URL + 推荐理由。
- [ ] 阶段 3 已完成方向与题名收敛：终稿使用的“专利标题”已明确（供文件命名使用）。

## 三、材料预处理与模板风格（阶段 0）

- [ ] 若冷启动且用户提供模板/参考 PDF：已完成必要的抽取/预处理（如 `pdf`），并记录产物路径。
- [ ] 已固化或复用 `template_rules.json`、`style_profile.json` 与 `style_profile.md`。
- [ ] 已记录 `preprocess_notes`、`preprocess_cache_status`、`preprocess_reuse_status`、`preprocess_refresh_reason` 与 `source_fingerprints`。
- [ ] `source_fingerprints` 已包含 `sha256`，可用于复现、缓存判断和审计追踪。
- [ ] 非冷启动且源材料未变化时，Phase 0 产物已复用，`preprocess_cache_status = cache_hit_reused`。

## 四、候选专利挖掘、初步查新与深度复核（阶段 2/4）

- [ ] 已向用户展示候选专利挖掘与初步查新摘要（含证据链 URL）。
- [ ] 阶段 2 的 `research_pack.json` 已通过 `validate_research_pack.py`，并包含 `source_plan`、`evidence[]`、`ranking_policy`、`candidate_directions[]` 与 `decision_basis`。
- [ ] 阶段 2 已说明 `strong_source_count`、`evidence_table_count`、候选方向评分公式和 `recommended_direction` 决策依据。
- [ ] 已向用户展示深度专利复核与审查包摘要。
- [ ] 深度专利复核已保留查询词清单、链路使用记录、URL 明细与失败/降级原因。
- [ ] 阶段 2 内部专利复核已明确可信专利渠道（Google Patents、Espacenet、WIPO Patentscope、CNIPA），最终候选均来自可信专利 URL，未用骨架数据补齐。
- [ ] 阶段 2 内部专利复核已记录 `trusted_patent_source_count`、`finalRelevantPatents_count`、CN-only、freshness、relevance 门禁结果。
- [ ] 阶段 2 内部专利复核的 `smart-search` 搜索输出已明确区分“中国专利候选”与“外围网页证据”，未把普通网页直接计入最终中国专利结果集；research cache 命中只作为待重验线索。

## 五、写作与质量门禁（阶段 5/6/7/8）

- [ ] 已完成分块撰写并合并导出。
- [ ] 阶段 5 已读取 Phase 2/4 研究与专利证据，生成短 `shared_context.json`、`phase_05_writing_plan.json`、每块 `block_context.json` 与 `block_review.json`。
- [ ] `shared_context.json` 只包含公共事实锚点并在预算内；每个正文分块均有独立上下文和审核记录，关键事实能映射到 evidence_id 或可信专利号。
- [ ] `facts_ledger.json`、`step_registry.json`、`figure_registry.json`、`terminology_registry.json` 已由正文/证据总账生成，非占位示例。
- [ ] 已完成一致性审计，并向用户展示摘要。
- [ ] 已完成 IPR 模拟审查，并向用户展示摘要（结论 + Top3 风险点）。
- [ ] IPR 报告已包含“法规依据与规则映射”，并说明其为规则化风险模拟，不是法规原文检索或正式法律意见。
- [ ] 已完成阶段 8 审后修订，并直接复跑 phase_6 / phase_7 执行器重新生成报告形成闭环。
- [ ] 已输出“一致性审计评分 + IPR 审查评分”（含评分口径/满分/阈值或等级）。

## 六、附图与交付目录

- [ ] 交付前已执行脏树检查：若存在未提交修改，已记录 `delivery_from_dirty_tree=true` 及变更摘要。
- [ ] 交付结构检查已通过：
  - [ ] 终稿 docx 文件存在且非空
  - [ ] `附图/` 目录存在且包含 `.png` 和 `.mmd` 文件
  - [ ] `facts_ledger.json` 存在
  - [ ] `phase_08` 一致性审计报告存在
  - [ ] `phase_07` IPR 审查报告存在
- [ ] 最终交付目录已确认（用户本轮明确指定的绝对路径）；未明确指定时不得默认猜测路径，且 `deliver_dir_explicit=true`。
- [ ] 最终交付目录已包含：正式 docx、`artifacts/`（若保留过程件）、以及附图目录（如 `附图/`）。
- [ ] 所有附图至少保留：
  - `.mmd`（Mermaid 源码，兜底复现/手工导入调整）
  - `.drawio` 或 `.vsdx`（可编辑图源，至少其一）
  - `.png` 或 `.svg`（最终嵌图文件）
- [ ] 终稿 docx 若需要附图：已检查 docx 内部 `word/media/` 非空，确保图片已真正嵌入。
- [ ] 最终交付目录根目录中只保留最新正式 docx；旧版、修订版、`bak`、`trialbak`、`tmp` 与评价件已清理。
- [ ] 评价、审查、对比与过程说明类文档若需保留，已下沉到 `artifacts/`，未与正式终稿并列。

## 七、命名与 IM 通道交付（阶段 9）

- [ ] 终稿 docx 文件命名已符合：`<专利标题>技术交底书.docx`，且未把 Markdown 降级文件视为正式交付。
- [ ] 若用户通过 Discord / 飞书 / 等 IM 通道沟通：已直接发送终稿 docx。
- [ ] 同时已发送“一致性审计评分 + IPR 审查评分”的摘要（含 Top3 风险点与改进项）。
