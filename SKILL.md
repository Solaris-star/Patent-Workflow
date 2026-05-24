---
name: patent-workflow
description: 专利撰写工作流编排。通过 orchestrate.py 按固定阶段门禁编排 pdf、smart-search、writing-style-analyzer、modular-writer，强制保留运行清单、一致性审计、IPR 模拟审查和审后修订复审闭环。阶段 1 必须询问"本轮准备写哪些领域的专利"。适用于专利选题、查新、专利交底书起草、workflow 规则升级和流程排错。
---

# Patent Workflow

## 角色定位

本 skill 是**编排器**，负责定义阶段顺序、交接契约和门禁规则。具体执行由 `scripts/orchestrate.py` 自动完成，Agent 不介入阶段选择和工具调用。

本 skill 不直接替代：
- `pdf` 的 PDF 解读
- `smart-search` 的搜索调研能力
- `writing-style-analyzer` 的风格提取
- `modular-writer` 的正文撰写

## 新架构（v2）

```
Agent/User
    ↓ 启动
orchestrate.py (唯一入口)
    ├── validators/preflight_validator.py     ← 运行前检查
    ├── 状态机循环
    │   ├── validators/handoff_validator.py   ← 交接验证（硬阻断）
    │   ├── 用户输入节点                       ← --batch / --interactive
    │   ├── executors/phase_XX_*.py           ← 阶段执行器
    │   └── validators/gate_runner.py       ← 门禁运行
    └── 状态快照 + Trace Log
```

**关键变化**：阶段推进、交接验证、门禁检查、工具调用全部由脚本自动完成。Agent 无法凭记忆跳过任何步骤。

## 使用方式

### 冷启动 / 默认启动
```bash
python skills/patent-workflow/scripts/orchestrate.py \
    --workspace <绝对路径> \
    --manifest artifacts/run_manifest.md \
    --from-phase 0
```

首次运行会执行 Phase 0 初始化；后续再次以 `--from-phase 0` 启动时，如果 Phase 0 产物齐全且源材料指纹未变化，编排器会自动复用预处理产物并从 Phase 1 开始，不再进入 Phase 0 执行器。

### 从阶段恢复 / 再次启动
```bash
python skills/patent-workflow/scripts/orchestrate.py \
    --workspace <绝对路径> \
    --manifest artifacts/run_manifest.md \
    --from-phase 1
```

> 已完成 Phase 0 的工作区，再次启动时默认从 Phase 1 或断点阶段恢复，直接复用 Phase 0 产物；只有冷启动、源材料变化或显式刷新时才重跑预处理。

### 只验证当前状态
```bash
python skills/patent-workflow/scripts/orchestrate.py \
    --workspace <绝对路径> \
    --manifest artifacts/run_manifest.md \
    --validate-only
```

### 单步调试
```bash
python skills/patent-workflow/scripts/orchestrate.py \
    --from-phase 2 --step
```

### 非交互模式（CI/CD）
```bash
python skills/patent-workflow/scripts/orchestrate.py \
    --from-phase 0 --batch-mode
```

### Dry Run（只打印不执行）
```bash
python skills/patent-workflow/scripts/orchestrate.py \
    --from-phase 0 --dry-run
```

## 阶段列表

| 阶段 | 名称 | 执行器 | 用户输入 | 门禁 |
|------|------|--------|----------|------|
| 0 | 材料预处理与运行清单初始化 | `preprocess` | ❌ | — |
| 1 | 范围确认 | — | ✅ | — |
| 2 | 候选专利挖掘与初步查新 | **Agent 原生** 🔄 | ❌ | ✅ |
| 3 | 方向收敛 | — | ✅ | — 🔒 |

🔒 **Phase 3 安全阀（2026-05-24）**：batch 模式下若 `selected_direction` 为空且 manifest 中无 `recommended_direction`，编排器将**硬阻断退出**（exit 2），不会自动推进。必须先在交互模式中选择方向，或在 manifest 中预设 `selected_direction`。
| 4 | 内部深度专利复核步骤 | （并入 Phase 2） | ❌ | ✅ |
| 5 | 正文撰写 | `modular_writer` | ❌ | ✅ |
| 6 | 一致性审计 | `consistency_audit` | ❌ | ✅ |
| 7 | IPR模拟审查 | `ipr_review` | ❌ | ✅ |
| 8 | 审后修订与复审闭环 | `revision` | ❌ | ✅ |
| 9 | 交付 | `delivery` | ❌ | ✅ |

**阶段 1 输入收敛规则**：
- 阶段 1 不要求用户必须给出具体专利 idea；只要用户给出模糊行业领域（如“仓储物流”“工业质检”），即记录 `idea_maturity=vague_domain`、`phase_02_mode=broad_domain_discovery`，直接进入阶段 2。
- 阶段 1 在领域/题目确认后必须继续询问用户是否有本地项目或文档需要转化为专利点；用户提供路径时写入 `local_project_paths` 并启用 `phase_02_local_project_mode=enabled`，用户留空或否定时只保留 `phase_02_discovery_inputs=[online_search]`。
- 脱敏处理只在读取过本地项目/文档材料时启用；如果仅联网搜索资料生成 idea，不启用脱敏。脱敏不是写作模板，不得替代 Phase 0 的 `template_rules.json` 或 `style_profile.json`。
- 阶段 2 在 `broad_domain_discovery` 下同时执行单领域深挖和交叉领域迁移搜索，输出单领域方向与交叉领域方向，再由阶段 3 让用户确认。
- 用户给出明确题目时记录 `idea_maturity=fixed_topic`、`phase_02_mode=topic_research`，阶段 2 围绕固定题目补证据和校准创新点。
- 用户完全没有领域边界时记录 `idea_maturity=no_idea`、`phase_02_mode=domain_recommendation`，阶段 2 使用默认种子领域集合先做横向推荐；不得把 `待系统推荐` 作为真实搜索词。

**阶段 0 默认行为**：
- 材料预处理、运行清单初始化、模板规则准备和默认风格画像准备统一在阶段 0 完成；它是全局初始化阶段，不是每次启动都应重跑的普通阶段。
- 冷启动时自动生成 `artifacts/preprocess/source_fingerprints.json`，对源材料记录 `path`、`relative_path`、`extension`、`size`、`modified_at`、`sha256`，用于复现、缓存判断和审计追踪。
- 后续再次以 `--from-phase 0` 启动时，若 `source_fingerprints.json`、`phase_00_preprocess_notes.md`、`template_rules.json`、`style_profile.json`、`style_profile.md`、`artifacts/run_manifest.json` 均存在且源文件指纹一致，编排器会直接从 Phase 1 开始，复用首次预处理产物，不再进入 Phase 0 执行器；只有显式 `--from-phase 0` 且源材料变化 / 强制刷新时才重新执行预处理。
- 源材料变化时返回 `preprocess_cache_status=cache_miss_refreshed` 并刷新指纹与预处理记录；用户显式设置 `force_preprocess=true` 或 `refresh_preprocess=true` 时返回 `force_refreshed` 并强制刷新。
- 自动生成/复用结构化 `template_rules.json`，包含 `schema_version`、章节顺序、禁用章节、编号规则、风格要求和后续交接要求。
- 当用户未指定其他参考专利时，自动生成/复用默认 `style_profile.json` 和 `style_profile.md`；前者供脚本消费，后者供人工阅读，语义来源为 `writing-style-analyzer` 的 `CN121526509A` 风格画像。
- 同步写入机器可读 `artifacts/run_manifest.json`，记录 `schema_version`、`manifest_type`、当前阶段状态、manifest state 和关键工件路径。
- 独立的模板风格分析阶段已取消，避免阶段空转；正文撰写阶段直接消费阶段 0 产出的模板/风格工件。

**阶段 5 写作规则（2026-04-23 更新，2026-05-24 追加安全阀）：**
- 🔒 **领域一致性安全阀（2026-05-24）**：Phase 5 执行前，编排器会检查 `manifest.domain_scope` 是否与 `phase_02_evidence_pack.json` 中记录的 `domain_scope` 一致。若不一致（说明 manifest 领域已变更但 Phase 2 产物未更新），Phase 5 **硬阻断退出**，防止基于旧领域数据生成新领域的正文草稿。必须先重新执行 Phase 2 或用一致的数据覆盖。
- 输入必须读取 Phase 2 的 `phase_02_research_pack.json`、`artifacts/prior_art/phase_02_patent_candidate_pool.json` 与 `artifacts/prior_art/phase_02_evidence_pack.json`（均由 Phase 2 直接产出），并写入 `artifacts/draft/phase_05_writing_plan.json`。
- 当 Phase 2 证据中存在 `source_type=local_project` 或 manifest 存在 `local_project_paths` 时，正文写入后必须执行本地材料脱敏过滤，并保存 `artifacts/draft/redaction_policy.json`；脱敏规则复用 `handsomestWei/patent-disclosure-skill` 的脱敏要求：公司/产品名泛化为“某系统”，客户/项目标签泛化为“对象A”，内部路径泛化为“本地路径”，真实分类标签泛化为“分类A”，具体业务规模泛化为“一定规模”。联网搜索-only 流程不得启用该过滤。
- 必须先生成短 `artifacts/draft/shared_context.json` 作为公共事实锚点，只保留标题、方向、技术问题、术语、步骤、图号、锁定事实和禁止项，不放长证据，并记录 `context_hash` 与预算。
- 每个正文分块必须生成独立 `artifacts/draft/block_contexts/{part}_context.json`，读取 `shared_context_path`，但只包含本块必要证据，作为干净上下文，降低跨块污染和幻觉风险。
- 每个正文分块必须生成 `artifacts/draft/block_reviews/{part}_review.json`，记录实际字数、建议字数范围、长度达标状态、证据引用、shared_context 一致性、上下文隔离和待补充问题。
- 若已存在分块正文但命中污染规则（修订占位注释、技术领域过度展开、背景技术引用非 CN 专利、技术问题语病、附图缺 Mermaid、具体实施缺图号/含未实验数据/公式风险），必须先备份到 `artifacts/draft/superseded_blocks/`，再用当前上下文重生安全草稿，不得复用旧污染稿。
- 正文禁止使用 `<!-- ED-xxx -->` 这类占位注释冒充扩写；无实验报告时禁止写准确率、延迟、样本量、百分比、具体设备参数等数据；公式仅在可验证 docx 渲染时使用，否则改为文字描述。
- `phase_05_writing_plan.json` 必须包含 `section_word_budget`：技术领域 50–150 字、背景技术 500–900 字、发明内容 800–1400 字、附图说明自然语言 30–120 字（不含 Mermaid/mmd 代码块，建议至少 4 张图且每图附 mmd）、具体实施方式 1800–3500 字，并说明各范围的控制理由；Phase 6 字数检查必须优先读取 `facts_ledger.block_statuses` 中的目标范围。
- 输出时必须同步生成 `artifacts/draft/step_registry.json`（方法步骤编号 S101…S10x）
- 输出时必须同步生成 `artifacts/draft/figure_registry.json`（图号及工件路径）
- 输出时必须同步生成 `artifacts/draft/terminology_registry.json`（术语及定义）
- 以上三个 registry 从 `facts_ledger.json` 拆分生成，并一并作为 phase_6 交接验证的必需工件

**阶段 6 审计增强（2026-04-23 更新）：**
- 当存在 `artifacts/draft/redaction_policy.json` 且 `enabled=true` 时，必须执行本地项目脱敏残留检查；若正文残留公司/产品名、客户/项目标签、内部路径、真实分类标签或具体业务规模，按 high severity 阻断通过。
- 复用 `handsomestWei/patent-disclosure-skill` 自检闭环思想，新增 `technical_closure` 检查：正文必须形成输入/采集→处理/判断→输出/记录/反馈闭环，并说明异常、边界样本、低置信度或冲突分支处理路径。
- 新增 `formula_parameter_consistency` 检查：全文公式、阈值范围、参数命名和实施例数值必须一致，不得同义不同名或同一阈值多版本并存。
- 新增 `cnipa_abstract_alignment` 检查：Phase 2 内部专利复核证据含 CNIPA abstract 时，背景技术对该专利的概括必须体现摘要关键词和实际技术内容，禁止只按标题或跑偏领域概括。
- 新增 `patent_description_accuracy` 检查 🔒（2026-05-24）：交叉验证 part_02 中引用的每个 CN 专利与 `phase_02_patent_verification.json` 中的 verified_title/verified_abstract 的关键词重叠率。重叠率低于 15% 判定为专利描述与实际内容不匹配（可能编造），按 HIGH severity 阻断。这是防止 agent 编造专利内容的硬性检查。
- 新增 `revision_log` 检查：进入迭代/修订模式时必须维护 `交底书修订对话记录.md` 或 `disclosure_revision_log.md`，记录时间、用户说明摘要、本轮交付文件和修订摘要。
- 新增 `step_numbering` 检查：步骤编号 S101…S10x 必须在技术方案、附图说明、具体实施方式中一致出现
- 新增 `style_compliance` 检查：具体实施方式必须匹配默认风格画像（CN121526509A）的固定起手句、总述句、核心逻辑句、对偶句
- 新增 `section_structure` 检查：章节顺序必须为 技术领域→背景技术→发明内容→专利附图→具体实施方式，不得含权利要求书

**阶段 7 审查增强（2026-05-21 更新）：**
- IPR 模拟审查不是法规原文检索或正式法律意见，而是“法规依据标签 + 本地规则实现 + 风险评分”的可复现模拟审查。
- 内置 `IPR_LEGAL_RULES` 规则映射表，保留 `rule_id`、法规条款标签、审查目标、实现函数、输入文件和失败风险等级。
- 法定审查项覆盖授权客体、新颖性、创造性、实用性、充分公开、支持、单一性、修改超范围和诚实信用。
- 新颖性、诚实信用会读取 Phase 2 产出的 `artifacts/prior_art/phase_02_evidence_pack.json`，检查专利摘录、可信 URL 和专利号一致性。
- 报告必须输出“法规依据与规则映射”，明确说明本阶段不内置法规全文，只用于 IPR 风险模拟。
- 新增 `步骤编号引用一致性` 与 `结构规范检查` 形式审查项（章节顺序、附图标题、权利要求书）。

**阶段 8 回改增强（2026-05-21 更新）：**
- 阶段 8 不再被视为单独的一次性终点，而是阶段 6/7 审查后的集中修订与复审闭环。
- 新增联动回改检测：当修改涉及步骤号/图号/术语时，自动定位所有联动位置。
- `edit_plan.json` 必须区分 `fix_mode = auto | agent_required | manual_review`，只对安全的替换类问题执行脚本级自动修复。
- `structured_diff.json` 新增 `linked_changes` 字段，标注需同步检查的位置。
- 修订后直接复跑 phase_6 和 phase_7 执行器，重新生成审计/IPR 报告，并在 manifest 中记录 `review_loop_passed` 与 `review_loop_results`。
- `phase_08_post_fix_check_report.md` 为人工可读报告，`phase_08_post_fix_check.json` 为机器可读报告。
- manifest 中记录 `linked_changes_detected` 和基于复审结果统计的 `remaining_issues_count`。

**阶段 9 交付增强（2026-05-21 更新）：**
- 交付前自动执行脏树检查，若存在未提交修改，标记 `delivery_from_dirty_tree=true` 并生成变更摘要。
- 最终交付目录必须明确指定并记录 `deliver_dir_explicit=true`；未明确时不得默认猜测为正式交付。
- docx 生成失败不得把 Markdown 降级文件视为正式交付，必须记录 `docx_generated=false` 且 `delivery_passed=false`，并让 Phase 9 返回 `failed` 以中断流程、提示补齐依赖或改用可用 docx 生成后端。
- 交付健康检查前必须先复制 `附图/`，交付结构检查确认 docx、附图目录（png+mmd）、facts_ledger、审计报告均存在。
- 合并 Markdown 会根据 `facts_ledger.figure_registry` 写入图片引用，供 docx 生成时嵌入图片。
- 交付前新增正文质量硬门禁：若任一分块仍含修订占位、非 CN 背景专利、技术领域过度展开、技术问题语病、附图缺 Mermaid、具体实施缺图号、未经实验数据或公式兼容风险，Phase 9 必须返回 `failed`，不得生成或宣称正式交付成功。
- `patent_title` 不得只依赖 manifest；manifest 缺失时必须从 `facts_ledger.json`、`shared_context.json` 或 Phase 2 推荐方向回退解析，避免生成 `未命名专利技术交底书.docx`。
- 健康检查通过后必须额外生成 `patent_delivery_package.zip`；zip 内部路径使用 ASCII-only 名称（如 `final/patent_disclosure.docx`、`figures/figure_01.png`），并在 `README.md` 记录原中文标题和原中文文件名，避免 Windows/部分 unzip 工具显示乱码。

门禁未通过时，orchestrate.py 以 exit(1) 硬阻断，不推进下一阶段。

## 交接契约

阶段推进前自动验证上一阶段产出是否满足交接条件。验证规则内联于 `validators/handoff_validator.py` 的 `HANDOFF_RULES` 字典中，硬编码不可绕过。

关键交接字段（阶段2示例）：
- `research_scope_key`, `channels_used`, `brain_chain_status`
- `strong_source_count >= 3`, `evidence_table_count >= 3`
- `candidate_directions`, `recommended_direction`
- `phase_02_research_pack.json` 必须是结构化 JSON：`pack_type=research_pack`、`phase=phase_02`、`research_questions[]`、`evidence[]`、`outline_skeleton[]`、`ranking_policy`、`candidate_directions[]`、`recommended_direction_detail`

**阶段 2 候选专利挖掘与初步查新规则（2026-05-22 更新）：**
- 搜索统一由 `smart-search` 执行。Phase 2 先检索最近 18 个月有效参考专利，再结合非专利信源做候选专利名称生成；research pack 内按来源类型标注：`patent`（Google Patents / CNIPA / WIPO Patentscope / Espacenet）、`hotspot`（X/Twitter / Hacker News / Reddit / Product Hunt / GitHub Trending）、`academic`（Google Scholar / Semantic Scholar / arXiv / IEEE Xplore）、`technical`（GitHub / Stack Overflow / Hacker News / 官方 Docs）、`industry`（Gartner / McKinsey / IDC / 公司白皮书）、`web`（官网 / 技术博客 / 新闻报道 / 产品文档）。Phase 2 不输出法律性新颖性结论或侵权风险结论，并在同一 Phase 2 内完成内部深度专利复核。
- Phase 2 支持两种专利点挖掘方式：其一是“联网搜索专利点挖掘”，适用于用户只给出行业/领域/交叉方向时，直接通过专利库、热点平台、学术和工程信源探索候选；其二是“本地项目/文档专利点挖掘”，仅在用户或 manifest 明确提供 `local_project_path`、`local_project_paths`、`local_material_paths` 或 `project_material_paths` 时启用。不得写死或默认扫描任意本地目录。
- 本地项目/文档专利点挖掘必须先基于用户指定材料提取候选专利点，并为每个候选给出 `技术背景`、`创新点`、`与现有技术区别`、`可实施性`；随后仍必须执行 CNIPA 查新、同申请号授权状态追查、联网非专利证据/热点/学术/工程信源检索与改良点校准，不得把本地挖掘当作终点。
- 融合建议只适用于本地项目/文档中存在共享技术链路、共享模块或共享证据的多个候选专利点；外部联网搜索产生的候选方向可能互不相关，禁止一刀切融合，禁止把用户输入的多个领域强行做“大融合”。
- Phase 2 的核心参考专利只允许使用授权、实质审查中、实质审查生效或等价有效状态；明确排除撤回、驳回、视为撤回、放弃、失效、终止等状态。法律状态不明的专利只能作为辅助线索，不得作为候选专利名称生成的核心依据。
- `evidence[]` 是标准证据表，每条包含 `evidence_id`、`question_id`、`source_type`、`site`、`title`、`url`、`excerpt`、`claim_supported`、`relevance_score`。
- Phase 2/4 必须把 smart-search 返回内容沉淀为 `source_reading_notes[]`，每条包含 URL、来源类型、页面摘要、关键技术事实、可写作使用标记和禁止过度主张说明；Phase 5 写作上下文优先读取这些阅读笔记，再结合短 `evidence[]` 摘要。
- Phase 2/4 必须启用 external research cache。默认目录：`$PATENT_RESEARCH_CACHE_ROOT` 环境变量 → `$XDG_CACHE_HOME/patent-workflow/research-cache/` → `~/.cache/patent-workflow/research-cache/`。第一版采用 `cache.db`（SQLite + FTS5 + hash index）和 `records/YYYY/MM/*.jsonl` append log，不引入向量数据库。该 cache 仅保存外部公开资料的结构化摘要、来源、TTL、复用策略和重验标记；不得写入本地项目/客户文档/代码路径/内部代号/私有仓库 URL。
- Phase 2 在联网前先用 sanitized query 查询 research cache，命中结果只能作为历史线索或背景证据；联网 smart-search 后仍需把新的 `source_reading_notes[]` 导入 cache，并在 manifest 写入 `research_cache_enabled`、`research_cache_hit_count`、`research_cache_imported_count` 和 `research_cache_path`。
- `strong_source_count` 表示去重后的可信来源 URL 数；`evidence_table_count` 表示真实结构化证据条数，不再用来源数量近似。
- 候选按 `total_score = 0.25 * novelty + 0.20 * feasibility + 0.20 * evidence_support + 0.15 * freshness + 0.10 * cross_source_consistency + 0.05 * transferability + 0.05 * innovation_potential` 排序。
- `candidate_directions[]` 默认输出 7 个候选专利名称；标题必须参考检索到的有效同类专利命名风格生成，不能写死格式，且总字数不超过 25。每个候选只需向用户展示：候选专利名称、参考专利解决的问题、本候选的改良点、证据 URL、非专利热点信源。不得把所有领域强行拼成“四领域大融合”，也不得用通用模板覆盖真实领域。需要后续深度查新的组合特征写入 `claims_requiring_patent_verification`，并在 Phase 2 内部的深度复核步骤中继续处理。

**阶段 2 内部深度专利复核规则（2026-05-21 更新）：**
- 专利检索仍由 `smart-search` 执行，但 query 必须显式指向可信专利渠道：Google Patents、Espacenet、WIPO Patentscope、CNIPA。
- `phase_02_patent_candidate_pool.json` 只允许可信专利 URL 进入最终 `patents[]`；普通网页只能作为 `peripheral_sources` 或辅助证据。
- 禁止用骨架专利补齐 `finalRelevantPatents_count`；若可信专利不足，阶段应降级并让门禁阻断。
- Freshness 按 `filingDate` 或 `publicationDate` 距当前时间是否不超过 1.5 年判断；Relevance 按候选标题、摘要、关键词、场景与专利检索 profile 的关键词命中得分判断。
- Manifest 必须记录 `trusted_patent_channels`、`trusted_patent_source_count`、`cn_only_passed`、`freshness_passed`、`relevance_passed`。
- Phase 2 内部专利复核在联网专利检索前可先查询 research cache 中的 `patent` 类型历史命中，但这些命中只能作为 `prior_art_candidate_requires_revalidation` 线索；进入 top-N 或影响碰撞判断的专利，必须重新查 CNIPA/官方来源的法律状态、同申请号授权公告号和摘要/权利要求相关性，不能把 cache 中法律状态当最终结论。

完整规则参见 `HANDOFF_CONTRACT.md`。

## 绑定文件

执行本 skill 时以下文件为强绑定资源：

- `HANDOFF_CONTRACT.md` — 交接契约
- `DELIVERY_CHECKLIST.md` — 交付检查单
- `IPR_REVIEW_TEMPLATE.md` — IPR审查模板
- `RUN_MANIFEST_TEMPLATE.md` — Manifest模板
- `CONSISTENCY_AUDIT_TEMPLATE.md` — 一致性审计模板
- `FIGURE_DELIVERY_CHECKLIST.md` — 附图交付检查单

## 运行留痕

每轮 workflow 通过 orchestrate.py 自动记录：
- `current_phase`, `last_passed_gate`
- `degraded_flags`, `degraded_run`
- `stage_skill_audit`（每阶段实际调用的 skill）
- `channel_failures`, `fallback_actions`
- `trace_log`（完整操作序列）

写入位置：`artifacts/orchestrator_trace.json`

## 状态快照

每阶段开始前自动备份：`artifacts/snapshots/snapshot_<phase>_<timestamp>/`
包含 manifest + 相关工件。失败后支持从快照恢复重试。

## 降级规则

允许降级，但必须明示：
1. orchestrate.py 自动记录 `degraded_run = true`
2. 自动记录 `channel_failures` 与 `fallback_actions`
3. 自动记录 `degraded_reason`
4. 门禁脚本判断是否允许降级后继续（某些门禁是 critical 不可绕过）

## Phase 2 Agent-Native 执行指南（v4 — 2026-05-24 更新）

⚠️ **Phase 2 已改为 Agent 原生模式。** 不再通过脚本转发。Agent 使用 `smart-search` CLI（主力）+ `web_fetch`（补详情）完成搜索，并将结果写入标准化 JSON 工件。`web_search`（SearXNG）仅作为 smart-search 故障时的降级通道。

### 前置条件

Agent 在执行 Phase 2 前必须确认：
1. Phase 0 预处理已完成（`artifacts/run_manifest.json` 存在，phase 0 status=success）
2. Phase 1 范围已确认（manifest 中有 `domain_scope` 和 `phase_02_mode`）
3. 确认本次模式：`broad_domain_discovery` / `topic_research` / `domain_recommendation`
4. 运行 `smart-search doctor --format json` 确认至少 2 个后端可用（main_search + web_search）

### 执行模式：Sub-Agent 并行搜索

⚠️ **Phase 2 搜索必须使用 sub-agent 并行模式，不得在主 agent 中串行调用 smart-search。**

```
Main Agent
  ├── spawn sub-agent → 领域1 smart-search → 读全部返回数据 → 返回结构化报告
  ├── spawn sub-agent → 领域2 smart-search → 读全部返回数据 → 返回结构化报告
  └── spawn sub-agent → 领域N smart-search → 读全部返回数据 → 返回结构化报告
        ↓ 并行执行（总耗时 ≈ 单次 smart-search 时间）
  汇总 N 份报告 → 生成 3 个 JSON 产物
```

**Sub-agent 数量:** 由 `domain_scope` 中的领域数动态决定。`broad_domain_discovery` 模式下每个独立领域一个 sub-agent，`topic_research` 模式下一个 sub-agent 按多角度拆分。Agent 自行判断拆分粒度。

**Sub-agent 任务规范:**
- 调用 `smart-search search "..." --providers openai-compatible,tavily --parallel --format json --extra-sources 5 --timeout 120`
- **`--providers openai-compatible,tavily --parallel` 是强制参数**：确保三路并行 —— Grok（X/Twitter生态+综合搜索）、GLM5（深度专利分析+补充发现）、Tavily（实时新闻+网页抓取）
- 保存原始 JSON 到 `artifacts/research/raw/ss_<domain>.json`
- **读取 smart-search 返回的全部数据**（不预设后端名称）：
  - `content` — 主回答文本，提取专利号、技术事实、行业热点
  - `parallel_results[]` — **全部条目的 `content` 都要读**，可能有多条不同模型的独立分析
  - `extra_sources[]` — 读取标题+URL，`web_fetch` 最相关的 2-3 个页面
  - `primary_sources[]` — 去重后记录
- 返回结构化报告给 Main Agent（不需要写产物，Main Agent 统一汇总）

**Main Agent 职责:**
- 解析 `domain_scope`，决定 sub-agent 数量和拆分策略
- 并行 spawn 所有 sub-agent
- 等待全部完成后汇总报告
- 去重、时效过滤、评分排序
- 写入 3 个 JSON 产物 + 更新 manifest

---

### smart-search CLI 返回数据结构

⚠️ **smart-search 是可配置的终端工具，后端供应商可随时变更。Agent 必须读取返回的全部数据，不得写死特定后端名称或数量。**

运行 `smart-search doctor --format json` 可查看当前配置的供应商。

**标准返回结构：**
```json
{
  "content": "<主模型生成的结构化回答，含 [[N]](url) 来源引用>",
  "primary_sources": [{"title": "...", "url": "..."}],
  "extra_sources": [{"title": "...", "url": "..."}],
  "sources_count": "<primary + extra 总数>",
  "parallel_results": [
    {"provider": "...", "model": "...", "ok": true, "content": "<该模型的独立回答>"},
    ...
  ],
  "providers_used": ["...", "..."],
  "provider_attempts": [
    {"capability": "main_search|web_search", "provider": "...", "result_count": N, "status": "ok|error"},
    ...
  ]
}
```

**数据读取要求（通用，不绑定特定后端）：**
1. `content` — 主回答，提取技术事实和专利号
2. `parallel_results[]` — **遍历全部条目**，每个条目的 `content` 都是独立分析，都必须读
3. `extra_sources[]` — 全部标题+URL，挑最相关的 `web_fetch` 获取详情
4. `primary_sources[]` — 去重写入 source_reading_notes
5. `providers_used` + `provider_attempts` — 记录到 search_log（动态记录实际使用的后端）

#### 调用规范

**标准调用：**
```bash
smart-search search "<英文查询>" --format json --extra-sources 5 --timeout 120
```

**参数说明：**
- `--format json` — **必须**，输出结构化 JSON
- `--extra-sources N` — web_search 后端并行拉 N 条额外网页源（推荐 5）
- `--timeout 120` — 超时 120 秒，多后端同时跑需要足够时间

**查询语言：** 始终用英文写 query（smart-search 的 LLM 后端对英文查询效果更好）。中文领域术语不翻译（如"智能座舱""端到端自动驾驶""多智能体"）。

**查询数量：** 每个领域至少 1 次 smart-search，由 sub-agent 独立完成。领域数由 `domain_scope` 动态决定。

**原始数据留存（必须！）：** 每次 smart-search 调用后，完整 JSON 必须保存到 `artifacts/research/raw/ss_<domain>.json`，用于后续审计和 Phase 5 回溯引用。不得只把结果放 `/tmp/` 下。

**结果提取流程（每次 smart-search 调用的必须操作，通用不绑定后端）：**
1. 读取 `content` → 提取关键技术事实和专利号
2. 遍历 `parallel_results[]` → **全部条目的 `content` 都要读**，提取各模型互补信息
3. 遍历 `extra_sources[]` → 读取标题+URL，挑选最相关的 2-3 个 `web_fetch` 获取详情
4. 遍历 `primary_sources[]` → 去重后写入 source_reading_notes
5. 记录 `sources_count` 和各 provider 实际返回量到搜索日志

#### 时效过滤

**硬性要求：** 候选专利池中的专利，`filing_date` 或 `publication_date` 必须在距今 18 个月内。
- ✅ 2024-06 之后 → 可用
- ❌ 2024-05 之前 → 仅作背景参考，不入候选池
- ❌ 法律状态为撤回/驳回/视为撤回/放弃/失效/终止 → 排除

Agent 在搜索时就应该在 query 中限定时间范围（`2024 2025`），避免返回过期结果。

---

### 执行步骤

#### Step 1: 读取上下文
```
artifacts/run_manifest.json → domain_scope, phase_02_mode, local_project_paths
artifacts/preprocess/phase_00_preprocess_notes.md → 源材料关键信息
```

#### Step 2: 确认后端状态
```bash
smart-search doctor --format json
```
确认 `providers_used` 至少 2 个后端可用（至少 1 个 main_search + web_search）。不可用项记录到 `channel_failures`。

#### Step 3: 启动 Sub-Agent 并行搜索

根据 `domain_scope` 动态拆分，**每个独立领域 spawn 一个 sub-agent**。

Sub-agent 任务模板（每个 sub-agent 执行一次 smart-search）：

| 领域示例 | Sub-agent 查询 |
|----------|---------------|
| 智能座舱AI | `2024-2025 smart cockpit multi-agent AI interaction driver monitoring emotion recognition CNIPA patent` |
| 自动驾驶AI | `2024-2025 end-to-end autonomous driving BEV Transformer VLM perception decision planning CNIPA patent` |
| AI项目管理 | `2024-2025 AI multi-agent orchestration workflow automation task decomposition project management CNIPA patent` |

**Sub-agent 必须完成的操作（通用，不绑定后端名称）：**
1. 调用 `smart-search search "..." --format json --extra-sources 5 --timeout 120`
2. 保存原始 JSON 到 `artifacts/research/raw/ss_<domain>.json`
3. 读取 `content` → 提取专利号、技术事实、行业热点
4. 遍历 `parallel_results[]` → 读**全部条目**的 `content`（每条都是独立分析）
5. 遍历 `extra_sources[]` → 提取标题+URL+摘要，`web_fetch` 最相关的 2-3 个页面
6. 记录各 provider 实际返回量和状态
7. 返回结构化报告给 Main Agent（含主回答摘要 + 各并行模型补充 + 网页发现）

**Main Agent 等待全部 sub-agent 完成后汇总，再继续 Step 4。**

#### Step 4: 汇总 → 生成初版创新点

╔══════════════════════════════════════════════════════════════╗
║  ⚠️ 此时只生成「初版创新点」，不是候选专利                    ║
║     国知局查新后再基于查新结果生成候选专利推荐                  ║
╚══════════════════════════════════════════════════════════════╝

Main Agent 汇总所有 sub-agent 报告后，提取：
1. **技术热点**：各领域的前沿方向、行业关注点
2. **参考专利**：smart-search 发现的相近专利（专利号 + 摘要线索）
3. **非专利证据**：学术论文、行业报告、新闻报道中的创新方向
4. **初版创新点**（每个领域 2-3 个）：用一句话描述可能的创新方向

初版创新点格式：
```
领域: 智能座舱多Agent交互
初版创新点:
  1. 基于驾驶员疲劳/情绪的多Agent主动干预机制
  2. 多模态感知融合的座舱Agent协同决策
  3. LLM驱动的上下文感知座舱交互
```

---

#### Step 5: 国知局查新 —— 创新点新颖性检索 (⚠️ 硬性前置步骤)

⚠️ **强制步骤，不可跳过。缺少 verification records 的 run 不得进入 Phase 3。**

拿着初版创新点去 CNIPA / Google Patents 查新，确认不存在冲突的已授权/在审专利。

**查新必须产出结构化验证记录（`artifacts/prior_art/phase_02_patent_verification.json`）：**

🔴 **强制双路查证（2026-05-24 更新）**：每个候选专利必须同时经过两条路径验证，缺一不可：
1. **LLM 综合搜索**：`smart-search search --providers openai-compatible,tavily --parallel` → 获取 AI 合成的专利描述
2. **实际页面抓取**：`smart-search fetch "https://patents.google.com/patent/CNXXXXXXXXXA/zh"` → 从 Google Patents 实际页面提取标题和摘要
3. **交叉验证**：对比 LLM 描述与实际页面内容，不一致的标记为 `hallucinated` 并剔除

**禁止**仅使用 LLM 生成的专利摘要作为验证依据。GLM5 曾将土壤健康专利（CN119539254A）包装为座舱安全专利。

```json
{
  "record_type": "patent_verification",
  "phase": "phase_02",
  "generated_at": "<ISO 8601>",
  "verification_records": [
    {
      "patent_id": "CNXXXXXXXXXA",
      "verified_title": "从 Google Patents / CNIPA 查到的实际标题",
      "verified_abstract": "实际摘要，不少于 50 字符",
      "verification_source": "Google Patents",
      "verification_url": "https://patents.google.com/patent/CNXXXXXXXXXA/zh",
      "verification_date": "YYYY-MM-DD",
      "legal_status": "授权|实质审查|公开|...",
      "publication_date": "YYYY-MM-DD",
      "matched_in_direction": "被哪个候选方向引用",
      "description_match_note": "记录该专利实际内容与初版创新点的关系（匹配/不匹配/部分相关）"
    }
  ]
}
```

**对每个初版创新点，提取关键词后检索：**

```
web_fetch "https://patents.google.com/?q=<关键词>&language=ZH&status=GRANT"
```
或直接用专利号精准查询：
```
web_fetch "https://patents.google.com/patent/CN<专利号>/zh"
```

**查新必须核实：**
| 字段 | 来源 | 用途 |
|------|------|------|
| `legal_status` | Google Patents / CNIPA | 排除撤回/驳回/失效（这些不构成障碍） |
| `abstract` | 官方摘要 | 判断与初版创新点的重叠程度 |
| `publication_date` | 官方公布日 | 时效检查（18 个月） |
| `claims` | 权利要求 | 判断保护范围覆盖 |
| `applicant` | 申请人 | 了解竞争格局 |

**查新结果分类：**
- 🟢 **无冲突**：初版创新点附近没有高度重叠的授权/在审专利 → 可推进
- 🟡 **有重叠**：存在相近专利但侧重点不同 → 调整创新方向，差异化
- 🔴 **严重撞车**：已有授权专利覆盖核心创新点 → 放弃该方向

---

#### Step 6: 基于查新结果 → 生成候选专利推荐

**只有查新后无冲突/可差异化的方向才能生成候选。**

每个候选专利方向包含：
- 专利名称（≤25字）
- 要解决的问题（基于查新确认的技术空白）
- 本候选改良点（与相近专利的差异化）
- 相近专利列表（查新时的参考专利）
- 证据 URL（非专利来源支撑）
- 非专利热点
- 查新记录（verification_source + verification_date）

**评分调整：** 查新结果为 🟢 的方向在"新颖性"指标加权

评分公式：`total_score = 0.25*新颖性 + 0.20*可行性 + 0.20*证据支撑 + 0.15*时效性 + 0.10*跨源一致性 + 0.05*可迁移性 + 0.05*创新潜力`

---

#### Step 7: 搜索日志

**搜索日志**（每次 smart-search 调用后记录）：
```json
{
  "search_log": [
    {
      "query": "2024-2025 smart cockpit multi-agent AI...",
      "timestamp": "<ISO 8601>",
      "providers_used": ["provider-a", "provider-b", "tavily"],
      "provider_stats": [
        {"provider": "...", "capability": "main_search", "model": "...", "status": "ok", "content_chars": 5824},
        {"provider": "...", "capability": "main_search", "model": "...", "status": "ok", "content_chars": 5063},
        {"provider": "tavily", "capability": "web_search", "status": "ok", "sources_count": 5}
      ],
      "total_sources": 24,
      "key_patent_ids_found": ["CN121297879A", "..."]
    }
  ]
}
```

⚠️ `provider_stats[]` 从 smart-search 返回的 `provider_attempts[]` 中动态提取实际的后端名称和状态，不写死特定供应商。

#### Step 8: 写入 3 个 JSON 工件

##### ① `artifacts/research/phase_02_research_pack.json`
```json
{
  "pack_type": "research_pack",
  "phase": "phase_02",
  "generated_at": "<ISO 8601>",
  "domain_scope": "...",
  "mode": "broad_domain_discovery",
  "research_questions": ["不少于 8 个"],
  "search_log": [{...}],
  "evidence": [
    {
      "evidence_id": "EV-001",
      "question_id": "Q-001",
      "source_type": "patent|hotspot|academic|technical|industry|web",
      "site": "Google Patents|CNIPA|arXiv|...",
      "title": "...",
      "url": "https://...",
      "source_date": "YYYY-MM",
      "excerpt": "不少于 50 字符的关键摘录",
      "claim_supported": "该证据支持的具体主张",
      "relevance_score": 0.85
    }
  ],
  "source_reading_notes": [
    {
      "url": "https://...",
      "source_type": "patent|web|academic|...",
      "source_date": "YYYY-MM",
      "page_summary": "页面内容摘要",
      "key_technical_facts": "可写入专利正文的关键技术事实",
      "usable_in_writing": true,
      "overclaim_warning": "避免过度主张的注意事项"
    }
  ],
  "outline_skeleton": ["不少于 5 个方向"],
  "ranking_policy": "total_score = 0.25*novelty + 0.20*feasibility + 0.20*evidence_support + 0.15*freshness + 0.10*cross_source_consistency + 0.05*transferability + 0.05*innovation_potential",
  "candidate_directions": [
    {
      "title": "候选专利名称（≤25字）",
      "problem": "参考专利解决的问题",
      "improvement": "本候选的改良点",
      "evidence_urls": ["https://..."],
      "non_patent_hotspots": ["..."],
      "total_score": 0.82
    }
  ],
  "recommended_direction_detail": {
    "title": "推荐方向名",
    "reason": "推荐理由（证据充分性/新鲜度/空白区）"
  }
}
```

##### ② `artifacts/prior_art/phase_02_patent_candidate_pool.json`
```json
{
  "pool_type": "patent_candidate_pool",
  "phase": "phase_02",
  "generated_at": "<ISO 8601>",
  "trusted_patent_channels": ["Google Patents", "CNIPA"],
  "age_cutoff_date": "2024-11-24",
  "patents": [
    {
      "patent_id": "CNXXXXXXXXXA",
      "title": "...",
      "url": "https://patents.google.com/patent/CNXXXXXXXXXA/...",
      "filing_date": "YYYY-MM-DD",
      "publication_date": "YYYY-MM-DD",
      "legal_status": "授权|实质审查|...",
      "abstract": "...",
      "relevance_score": 0.85,
      "freshness": true,
      "candidate_direction": "对应候选名称"
    }
  ],
  "peripheral_sources": ["非专利参考来源列表"],
  "cn_only_passed": true,
  "freshness_passed": true,
  "relevance_passed": true
}
```

##### ③ `artifacts/prior_art/phase_02_evidence_pack.json`
```json
{
  "pack_type": "evidence_pack",
  "phase": "phase_02",
  "generated_at": "<ISO 8601>",
  "strong_source_count": 8,
  "evidence_table_count": 15,
  "evidence_summary": [
    {
      "evidence_id": "EV-001",
      "source_type": "patent",
      "url": "https://...",
      "key_finding": "关键技术发现（1-2 句）",
      "supports_direction": "支持的候选方向名"
    }
  ],
  "claims_requiring_patent_verification": [
    "需要 CNIPA 进一步核实的权利要求或法律状态"
  ]
}
```

---

### Step 9: 更新 Manifest

Agent 在 `artifacts/run_manifest.json` 中补充以下字段：
```json
{
  "research_scope_key": "<domain_scope 值>",
  "research_cache_enabled": true,
  "research_cache_hit": false,
  "research_cache_hit_count": 0,
  "research_cache_imported_count": 0,
  "research_cache_path": "~/.cache/patent-workflow/research-cache/cache.db",
  "channels_used": ["smart-search", "web_fetch"],
  "channels_skipped": [],
  "why_skipped": "",
  "degraded_run": false,
  "brain_chain_status": "completed",
  "channel_failures": [],
  "fallback_actions": [],
  "strong_source_count": "<去重URL数，≥3>",
  "evidence_table_count": "<evidence[]条数，≥3>",
  "candidate_directions": "<逗号分隔的7个候选名称>",
  "recommended_direction": "<推荐方向名称>",
  "claims_requiring_patent_verification": ["..."],
  "patent_search_queries": ["<所有 smart-search 查询词列表>"],
  "patent_candidate_pool_count": "<patents[]条数>",
  "finalRelevantPatents_count": "<过滤后可信专利数>",
  "cn_only_passed": true,
  "freshness_passed": true,
  "relevance_passed": true,
  "candidate_pool_generation_mode": "agent_native",
  "candidate_pool_channels_used": ["Google Patents", "CNIPA"],
  "trusted_patent_channels": ["Google Patents", "CNIPA"],
  "research_pack_path": "artifacts/research/phase_02_research_pack.json",
  "evidence_pack_path": "artifacts/prior_art/phase_02_evidence_pack.json",
  "phase_status": {"phase_2": "success"}
}
```

---

### Step 10: 推进到 Phase 3

产物齐全后运行：
```bash
python skills/patent-workflow/scripts/orchestrate.py \
    --workspace . --manifest artifacts/run_manifest.md \
    --from-phase 2
```
编排器检测到产物齐全 → 跳过 Phase 2 执行 → 运行 Gate → 进入 Phase 3 方向收敛。

### Phase 2 Gate 校验清单

⚠️ **Phase 2 门禁为警告模式。** 全部检查执行但不会硬阻断——问题清单传递给 Phase 3，由用户决定是否继续或补搜。

编排器自动运行以下 8 项检查：

| # | 检查项 | 类型 | 检查内容 |
|---|--------|------|----------|
| 1 | `validate_research_pack.py` | 脚本 | questions≥8, evidence≥8, outline≥5, excerpt≥50字符 |
| 2 | `validate_patent_candidates.py` | 脚本 | 至少 1 个 CN 专利，freshness+relevance 通过，≥5 final（CN 仅对专利类强制，学术/热点/行业源不要求） |
| 3 | `validate_evidence_pack.py` | 脚本 | evidence≥3, alignment≥3 |
| 4 | **search_log_check** | 内联 | 所有后端状态 ok；`total_sources ≥ 10`；`content_chars ≥ 500`（main_search）；`key_patent_ids_found ≥ 2` |
| 5 | **raw_archive_check** | 内联 | `artifacts/research/raw/` 目录存在且非空 |
| 6 | **freshness_check** | 内联 | 入池专利 publication_date 在 18 个月内 |
| 7 | **evidence_date_check** | 内联 | source_reading_note/evidence 有 `source_date` 且在 18 个月内 |
| 8 | **patent_verification_check** 🔒 | 内联 | `phase_02_patent_verification.json` 存在且非空，每条 record 含 verified_title/verified_abstract（≥50字符）/verification_source/verification_date；候选池专利均被覆盖 |

未通过项标记 `warning: true`，打印到 Phase 3 用户确认界面。

---

### 常见错误与禁止事项

| # | ❌ 错误做法 | ✅ 正确做法 |
|---|-----------|-----------|
| 1 | 只用 `web_search`（SearXNG）跑 Phase 2 | smart-search 做主力，web_search 只做降级 |
| 2 | 只看 `content`，忽略 `parallel_results[]` 和 `extra_sources[]` | 必须读全部返回数据：`content` + 全部 `parallel_results[].content` + `extra_sources[]`，关键页面 web_fetch |
| 3 | 搜完立刻写产物，未做时效过滤 | 所有入池专利必须 public_date ≥ 18 个月 |
| 4 | 候选池混入 2018/2020 年的旧专利 | 过期专利只做背景参考，写入 peripheral_sources |
| 5 | 用骨架专利补齐 finalRelevantPatents_count | 可信专利不足时降级标记，不造假 |
| 6 | 法律状态不明的专利做核心依据 | 必须 web_fetch CNIPA/Google Patents 确认法律状态 |
| 7 | 把不相关的候选方向强行融合 | 外部搜索产生的独立方向保持独立 |
| 8 | 编造专利号、论文、日期或指标 | 所有数据必须来自搜索结果 |
| 9 | 把 `待系统推荐` 作为真实搜索词 | 必须用实际领域词搜索 |
| 10 | 通用模板覆盖真实领域 | 保留领域特化术语 |
| 11 | smart-search 扔后台不管，结果没读就写产物 | 每个 smart-search 调用必须等待完成并全量阅读 |
| 12 | Main Agent 串行跑所有 smart-search，耗时数分钟 | 使用 sub-agent 并行：每个领域 spawn 一个 sub-agent |

## 初始化层与复用层

1. `项目初始化层`（模板/参考专利/风格工件）— 初始化一次、长期复用
   - **默认风格**：`writing-style-analyzer` 内置的 `CN121526509A` 风格画像，自动加载，无需每次重新提取
2. `单篇专利运行层`（创新点/背景包/正文/审计）— 每次新 run 不跨 run 复用

复用判定由 orchestrate.py 自动检查源文件指纹，Agent 不介入。

## 风格来源与默认加载

- **默认风格画像**：`writing-style-analyzer/profiles/CN121526509A.json`
  - 用途：具体实施方式撰写规范
  - 内容：固定起手句、步骤总述链（S101…）、解释型说明书笔法、长句链、对偶归纳句
  - 加载时机：阶段 0 自动准备，后续正文撰写直接消费，无需单独模板风格阶段
  - 覆盖条件：仅当用户明确给出"重新提取风格"或"使用其他风格"时才覆盖
- **用户指定风格**：若用户上传其他参考专利 PDF，则按正常流程提取并保存到 `workspace/analysis/`，本次运行使用新风格，但不影响默认配置

## 禁止事项

1. Phase 2 搜索不得以 `web_search`（SearXNG）为主力 — 必须用 `smart-search` CLI
2. smart-search 返回的全部数据必须阅读 — 不得只读 `content` 而忽略 `parallel_results[]` 或 `extra_sources[]`
3. 候选池中的所有专利必须满足 18 个月时效要求
4. Agent 不得跳过门禁脚本
5. Phase 5 暂走 modular_writer 脚本（未改为 agent-native）
6. 禁止编造专利号、论文、日期或指标
7. 禁止用骨架专利补齐 finalRelevantPatents_count
8. 禁止在 SKILL.md 中写死后端名称/数量 — smart-search CLI 配置可随时变更

## 使用摘要

用户说以下任一类请求时，使用本 skill：
- "跑一遍专利工作流"
- "按 workflow 写专利交底书"
- "帮我选题、查新、写交底书"
- "升级 patent-workflow skill"
- "检查这条专利流程有什么缺陷"

**执行方式**：不手动逐阶段推进，而是调用 `orchestrate.py` 让脚本自动完成。

## CN 专利交底书撰写规范

以下规则已通过 preflight 校验和 executor 实现部分自动化，但撰写者仍需遵守：

### 标题规范
- 长度 ≤ 25 个汉字
- 纯中文，不含英文字母和特殊符号（`-`、`/` 等）
- 以"一种"开头，以"方法及系统"或"方法、装置及系统"结尾
- 参考 Phase 2 中检索到的 CN 专利标题格式
- Preflight 校验会自动警告标题违规

### 术语规范
- CN 专利正文中高频出现的英文术语必须翻译为中文（如 Agent→智能体、API→接口、DMS→驾驶员监测系统）
- 英文缩写首次出现时需给出中文全称
- 附图标记不使用随意编造的编号（如 100/200/300），仅在 mmd 源码中保留节点 ID

### 格式规范
- 正文每句一行，方便审查阅读
- 排比列表（第一/第二/第三、其一/其二/其三）每项独占一行
- 附图说明采用"每图一组"结构：图号标题 → 组成说明 → mmd 代码
- 具体实施方式使用 doc 格式行文，不使用 Markdown 加粗/分割线

### 领域隔离
- 所有 executor 的硬编码领域术语已替换为从 `manifest.domain_scope` 动态读取
- 撰写时确保正文术语与 facts_ledger.json 的 terminology 一致
- 不要照搬其他领域的模板句式（如"仓储质检"→应替换为当前 domain_scope）
