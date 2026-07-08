---
name: patent-workflow
description: 专利撰写工作流编排。用于运行或迭代专利交底书 workflow 时，按固定阶段门禁编排 pdf、deep-research、writing-style-analyzer、modular-writer，并允许在不破坏门禁的前提下并行准备背景包、风格工件和 IPR 包。workflow 强制保留运行清单、一致性审计、IPR 模拟审查和回改闭环。首步必须询问“本轮准备写哪些领域的专利”。适用于专利选题、查新、专利交底书起草、workflow 规则升级和流程排错。
---

# Patent Workflow

## 角色定位

本技能是专利交底书流程的唯一编排真源，负责：

1. 决定阶段顺序。
2. 决定每一阶段的进入条件和退出条件。
3. 决定各 skill 之间的交接格式。
4. 决定哪些中间结果必须对用户可见。
5. 决定最终是否允许宣告“已完成交付”。

本技能不直接替代：

- `pdf` 的 PDF 解读与抽取能力。
- `deep-research` 的调研能力。
- `writing-style-analyzer` 的模板与风格提取能力。
- `modular-writer` 的正文与 docx 交付能力。

正文结构与最终交付以 `modular-writer` 为真源；背景专利候选扩池与中国专利对象化检索均由 `deep-research` 提供原始候选，中国专利门禁与审查级 prior-art 包由本技能目录下 validator 脚本与阶段规则控制；模板结构约束与风格边界以 `writing-style-analyzer` 为真源；PDF 解读以 `pdf` 为工具真源；流程顺序、运行留痕、门禁、一致性审计、IPR 模拟审查和回改策略以本技能为真源。

## 本轮固化教训

在自动驾驶接管专利交付迭代中，暴露出以下高频错误，后续运行必须默认防止再次发生：

1. 附图说明中的图号定义、正文 `如图x所示` 引用、docx 中插图顺序三者容易脱节，必须作为同一联动动作处理。
2. 最终交付文件名不能再用固定占位名，默认应由最终题名驱动生成 `<专利名称>技术交底书.docx`。
3. 技术方案正确并不代表正文语气合格；交付前仍必须单独检查是否存在“解释腔、汇报腔、AI 生成腔”。
4. 用户若要求“只保留一个 docx”，workflow 结束前必须清理并行正式件，不能同时残留旧版、修订版和最终版。
5. 对复杂流程图，不得默认把 Mermaid 直接作为最终交付图；至少应同时保留 `.mmd` 与可编辑成品图源（优先 `.drawio`），并将最终嵌入 docx 的图片视为单独交付工件管理。
6. 评价、审查、对比说明等过程性文档不得再以并列正式 docx 形式留在最终交付目录中；若必须保留，应下沉到 `artifacts/` 而不是与正式终稿并列。

## 必须先问的问题

每次启动本 workflow，第一条面向用户的问题必须是：

`本轮准备写哪些领域的专利？`

处理规则：

1. 如果用户明确给出领域，后续调研和检索必须限制在这些领域内。
2. 如果用户没有给出领域，可以在以下方向中自由组合可靠交叉方向开展检索：
   - `AI`
   - `自动驾驶`
   - `智能座舱`
   - `项目管理`
   - `Agent`
3. 如果用户已经给出明确题目或标题，仍然要先完成该问题的确认，只是可以把“方向确认”阶段压缩为“固定题目下的创新轴验证”。

## 绑定文件

本技能目录下的以下文件是本技能的强绑定资源：

## 标准启动/门禁命令片段（A 模式）

1) 初始化 run manifest（建议固定为 `artifacts/run_manifest.md`）：
- `python skills/patent-workflow/scripts/init_run_manifest.py --out artifacts/run_manifest.md --domain-scope "<领域>" --output-dir "<交付目录>"`

2) 在阶段门禁处运行并写回（示例：阶段 4）：
- `python skills/patent-workflow/scripts/run_phase_gates.py --phase 4 --workspace . --manifest artifacts/run_manifest.md`

3) 一键跑全部门禁（fail-fast；阶段 11 需要额外参数）：
- `python skills/patent-workflow/scripts/run_phase_gates.py --phase all --workspace . --manifest artifacts/run_manifest.md`
- （Windows 便捷封装）
  `pwsh -File skills/patent-workflow/scripts/run_phase_gates.ps1 -Phase all -Workspace . -Manifest artifacts/run_manifest.md`
- 阶段 11（交付目录与题名已确定时）：
  `python skills/patent-workflow/scripts/run_phase_gates.py --phase 11 --workspace . --deliver-dir "<deliver_dir>" --patent-title "<patent_title>" --manifest artifacts/run_manifest.md`
  （Windows 便捷封装）
  `pwsh -File skills/patent-workflow/scripts/run_phase_gates.ps1 -Phase 11 -DeliverDir "<deliver_dir>" -PatentTitle "<patent_title>" -Workspace . -Manifest artifacts/run_manifest.md`


- `HANDOFF_CONTRACT.md`
- `DELIVERY_CHECKLIST.md`
- `IPR_REVIEW_TEMPLATE.md`
- `RUN_MANIFEST_TEMPLATE.md`
- `CONSISTENCY_AUDIT_TEMPLATE.md`
- `FIGURE_DELIVERY_CHECKLIST.md`

执行本技能时：

1. 进入下一阶段前，必须满足 `HANDOFF_CONTRACT.md` 对上一阶段输出的要求。
2. 进行 IPR 模拟审查时，必须使用 `IPR_REVIEW_TEMPLATE.md` 的字段骨架输出结果。
3. 进行一致性审计时，必须使用 `CONSISTENCY_AUDIT_TEMPLATE.md` 的字段骨架输出结果。
4. 每轮运行必须初始化并持续更新 `run manifest`。
5. 宣告交付完成前，必须逐项通过 `DELIVERY_CHECKLIST.md`。
6. 凡涉及附图生成、图号联动、图稿导出、docx 嵌图与归档清理，必须逐项通过 `FIGURE_DELIVERY_CHECKLIST.md`。

## 运行留痕

每轮 workflow 必须有一个可落盘的运行清单，至少记录：

1. `current_phase`
2. `degraded_flags`
3. `key_artifacts`
4. `open_risks`
5. `revision_round`
6. `user_confirmations`
7. `source_fingerprints`
8. `cache_hits`
9. `cache_misses`
10. `research_scope_key`
11. `research_cache_hit`
12. `research_reuse_status`
13. `research_scope_match`
14. `research_reuse_basis`
15. `research_source_fingerprint`
16. `research_artifact_fingerprint`

运行清单不是可选日志，而是恢复执行、解释降级和追踪回改的必要工件。

补充规则：

1. `user_confirmations` 仅用于记录真实发生的用户覆盖、方向选择和高风险决策，不构成默认人工等待节点。
2. 除阶段 0 的领域确认、阶段 3 的方向/题目收敛，以及用户显式要求先看中间结果外，不得把“等待用户确认”设置为默认门禁。
3. `background_pack` 已就绪且风格工件可用时，应自动继续进入写作装配，不得额外插入“背景包确认”“最终导出前确认”之类默认停顿。

## 初始化层与复用层

本 workflow 明确区分：

1. `项目初始化层`
   - 模板 PDF / 参考专利 PDF 预处理
   - 模板结构分析
   - 参考专利风格分析
2. `单篇专利运行层`
   - 创新点研究
   - 方向与题目收敛
   - 背景专利检索
   - 草稿撰写
   - 一致性审计
   - IPR 模拟审查
   - 最终导出

强制规则：

1. `项目` 由 `(template_source, reference_patent_source)` 这组默认材料唯一确定；只有同一组模板与参考文档，才共享同一初始化层缓存。
2. 预处理和风格分析默认是“初始化一次、长期复用”，不是每次写专利都重跑。
3. 只要模板源文件和参考文档源文件未变化，后续运行必须优先复用：
   - `template_outline.txt`
   - `reference_patent_text.txt`
   - `template_rules.json`
   - `style_profile.md`
4. 只有以下情况允许重跑初始化层：
   - 源文件路径变化；
   - 源文件指纹变化；
   - 用户明确要求刷新；
   - 现有工件缺失或损坏。
5. 若命中复用，必须在 `run manifest` 中记录：
   - `cache_hits`
   - `source_fingerprints`
   - `initialization_reused = true`
6. 若未命中复用，必须记录：
   - `cache_misses`
   - `initialization_reused = false`
7. 以下仅属于通用默认材料或项目初始化层工件，可默认复用：模板路径、参考路径、默认输出目录、`template_outline.txt`、`reference_patent_text.txt`、`template_rules.json`、`style_profile.md` 及其对应指纹。
8. 以下属于单篇专利运行层内容工件，默认不得跨 run 复用：历史 `run_manifest`、创新点研究结论、`candidate_directions`、`recommended_direction`、历史题名、`background_pack`、`ipr_pack`、权利要求草案、正文草稿、一致性审计结果、IPR 审查结果，以及任何带具体专利主题限定的信息。
9. 若用户明确要求沿用某历史单案工件，必须在 `user_confirmations` 与 `run manifest` 中同时记录复用依据；否则不得默认读取历史单案内容工件作为本轮先验。

## 研究工件复用

`deep-research` 产物不属于初始化层长期模板缓存，但必须支持“同题目/同范围/同约束”的研究工件复用。

强制规则：

1. 进入研究阶段前，必须生成 `research_scope_key`，至少包含：
   - `domain_scope`
   - `topic_scope`（由 `fixed_topic_or_title` 或当前候选方向的核心关键词集合组成）
   - `constraints`
   - `freshness_window`
2. `freshness_window` 默认为 30 天；超过该窗口的 research artifact 不得默认复用，除非用户明确要求沿用并记录覆盖依据。
3. 研究复用匹配结果必须区分为：`full` / `domain_only` / `partial` / `none`，不得再用单一布尔值表达。
4. 仅当 `domain_scope` 与 `topic_scope` 都匹配、研究工件完整、强来源链接仍可用且用户未要求刷新时，才允许默认复用已有 research artifact；并记录：
   - `research_cache_hit = true`
   - `research_reuse_status = reused`
   - `research_scope_match = full`
   - `research_reuse_basis`
   - `research_source_fingerprint`
5. 若只有 `domain_scope` 匹配而 `topic_scope` 不匹配，或只是部分主题重叠，不得直接跳过 research 阶段；最多只能把重叠部分作为参考上下文注入新 research，并记录：
   - `research_cache_hit = false`
   - `research_scope_match = domain_only` 或 `partial`
   - `research_reuse_basis`
   - `research_refresh_reason`
6. 若以下任一条件成立，必须刷新 research artifact：
   - `research_scope_key` 变化；
   - 用户明确要求刷新；
   - 关键来源失效；
   - 现有 research artifact 缺失或损坏；
   - 当前轮次没有固定题目且需要重新发散候选方向。
7. 刷新时必须记录：
   - `research_cache_hit = false`
   - `research_reuse_status = refreshed`
   - `research_scope_match = partial` / `domain_only` / `none`，或记录导致刷新的条件
   - `research_reuse_basis`
   - `research_refresh_reason`
8. 若已有 research artifact 被判定为失效而不得继续沿用，必须额外记录：
   - `research_reuse_status = invalidated`
   - `research_invalidation_reason`

## deep-research 在专利 workflow 中的专用约束

`deep-research` 在本 workflow 中被视为通用搜索执行器；凡涉及创新点研究、背景专利候选扩池、中国专利对象化检索与背景技术证据链留痕，均由 `patent-workflow` 负责定义检索细节、输出契约与通过标准，`deep-research` 负责按约执行。

强制规则：

1. 同样调用 `deep-research`，阶段 2 与阶段 4 的任务目标必须严格区分：
   - 阶段 2 面向创新点研究、候选方向、创新轴、技术差异与背景证据；
   - 阶段 4 面向中国专利对象本身，不得用普通网页资料冒充专利候选。
2. 阶段 4 的 `deep-research` 输出必须是结构化中国专利候选数组；每条候选至少包含：
   - `title`
   - `applicationNumber` 或 `publicationNumber`
   - `filingDate` 或 `publicationDate`
   - `abstract`
   - `url`
   - `keywords`
   - `scenario`
3. 阶段 4 的查询策略必须显式约束为“专利检索模式”，至少记录：
   - `patent_search_queries`
   - `candidate_pool_channels_used`
   - `candidate_pool_reasoning_chains_used`
   - `candidate_pool_generation_mode`
   - `channel_failures`
   - `fallback_actions`
4. 阶段 4 必须优先使用中文关键词生成检索式，可在必要时做中英混合扩展，但最终入池对象必须是可核验的中国专利。
5. 阶段 4 不得把普通新闻、博客、产品页、论坛页直接写入 `finalRelevantPatents`；非专利页面最多只能作为外围证据来源，用于辅助关键词扩展、主题判断或背景说明。
6. 若 `deep-research` 声称使用 Grok、DeepSeek 或等价外部推理链路，必须保留真实 URL 与可审计留痕；无 URL 的推理结论不得直接充当专利候选证据。
7. 阶段 4 检索不足时，必须自动执行多轮换词重检；允许扩展同义词、申请人、场景词、近义应用域与分类号辅助词，但不得放宽中国专利门禁、时效门禁与高相关门禁。
8. `deep-research` 只负责候选扩池与证据留痕；是否通过中国专利门禁、时效门禁、相关性门禁与最小数量门禁，始终由本 workflow 与 validator 共同裁决。

## 统一流程

### 阶段 0：范围确认与运行清单初始化（可选）

默认策略：**用户未提供领域/题名/模板/参考专利时，不阻塞提问，直接进入阶段 2 进行交叉领域发现 + 创新点研究**；仅当用户明确要求严格逐项确认，或后续阶段需要缺失信息时，再回补本阶段。

当需要执行本阶段时，必须完成：

1. 确认专利领域（若用户未指定，则由阶段 2 的交叉领域发现给出推荐领域对与理由）。
2. 确认是否有固定题目或固定标题（若无，则由阶段 3 收敛生成）。
3. 确认是否有模板文件（若无且属于冷启动，则阶段 5 将生成并固化可复用工件）。
4. 确认是否有参考专利全文或参考 PDF（若无且属于冷启动，则阶段 5 将用默认参考集或用户后续补充的参考件生成风格工件）。
5. 确认最终交付目录或项目目录；**若用户未另行指定，不得默认猜测路径**，必须询问用户给出交付目录（冷启动必问）。
   - 冷启动判定建议：不存在 `artifacts/run_manifest.md`，或该 manifest 中 `output_dir` 为空/无效。
6. 初始化 `run manifest` 并写入起始状态（建议固定为 `artifacts/run_manifest.md`，用 `init_run_manifest.py` 生成/更新）。
7. 检查项目是否已存在可复用的初始化工件和对应源文件指纹。
8. 初始化最终交付目录结构，默认至少包括：正式 docx 所在根目录、`artifacts/`、附图目录（命名可为 `附图/` 或等价目录）。

### 阶段 1：材料预处理（可选，冷启动优先）

触发条件：
- 冷启动且用户提供了模板/参考 PDF 需要预处理；或
- 用户明确要求先抽取模板/参考专利再进入研究。

按情况调用：`pdf`

### 阶段 2：创新点研究（含交叉领域发现）

必须调用：`deep-research`

若用户未指定领域：阶段 2 必须先执行“交叉领域发现（cross-domain discovery）”，通过多链路检索证据，给出 2 个最有交叉专利应用前景的领域组合（含证据 URL 与推荐理由），再在该组合语境下继续完成创新点研究。

本阶段强制落盘工件（固定路径，统一下沉到 `artifacts/`）：
- `artifacts/research/phase_02_research_pack.json`

Research Pack 最小字段要求（仅结构化，不承载专利门禁；专利相关约束仍由本 workflow 装配）：
- `research_questions[]`（多视角追问清单）
- `outline_skeleton[]`（章节骨架）
- `evidence[]`（证据对象：url + excerpt + locator 等）

门禁（必须通过）：
- 运行 `python skills/patent-workflow/scripts/run_phase_gates.py --phase 2 --workspace . --manifest <run_manifest_path>` 并返回通过；否则不得进入阶段 3。
  - 该命令会调用 `validate_research_pack.py` 并将汇总 JSON 写回 run manifest（可审计）。

### 阶段 3：方向与题目收敛

### 阶段 4：背景专利检索与审查包准备

必须执行：
1. 调用 `deep-research` 以“专利检索模式”产出中国专利候选数组，不得只返回普通网页列表；
2. 要求 `deep-research` 在本阶段输出中显式记录：
   - `patent_search_queries`
   - `candidate_pool_channels_used`
   - `candidate_pool_reasoning_chains_used`
   - `candidate_pool_generation_mode = multi-chain`
   - `channel_failures`
   - `fallback_actions`
   - `patent_candidate_pool_path`
   - `patent_candidate_pool_count`
3. 要求候选数组中的每条对象至少包含：
   - `title`
   - `applicationNumber` 或 `publicationNumber`
   - `filingDate` 或 `publicationDate`
   - `abstract`
   - `url`
   - `keywords`
   - `scenario`

本阶段强制落盘工件（固定路径，统一下沉到 `artifacts/`）：
- `artifacts/prior_art/phase_04_patent_candidate_pool.json`
- `artifacts/prior_art/phase_04_evidence_pack.json`

门禁（必须全部通过）：
4. 运行 `python skills/patent-workflow/scripts/run_phase_gates.py --phase 4 --workspace . --manifest <run_manifest_path>` 并返回通过；
   - 该命令会依次调用：
     - `validate_patent_candidates.py artifacts/prior_art/phase_04_patent_candidate_pool.json`
     - `validate_evidence_pack.py artifacts/prior_art/phase_04_evidence_pack.json`
   - 并将汇总 JSON 写回 run manifest（可审计）。
5. 仅当门禁返回通过时，才允许阶段退出。

强制门禁：
- `CN-only`
- 距当前时间 `≤ 1.5 年`
- `high relevance` 分数达阈值
- `finalRelevantPatents >= 5`
- 不满足则自动换词重检，不得推进下一阶段。

补充约束：
1. 本阶段允许使用普通网页、行业文章、企业页面作为外围证据，用于扩词、判定主题与补充背景；但它们不得直接进入中国专利最终候选集合。
2. 若 `deep-research` 在本阶段启用了 Grok、DeepSeek 或其他外部推理链路，则所有影响候选入池的关键判断都必须能回落到真实 URL，不得以无 URL 结论代替专利对象。
3. 若首轮检索未达到数量或相关性门禁，必须自动重检，优先重写：同义词、场景词、申请人词、近义应用域词、分类号辅助词；不得拿低相关专利凑数。

### 阶段 5：模板与风格分析（可选，冷启动优先）

触发条件：
- 冷启动（首次在本机/本项目运行，尚无可复用的模板/风格工件）；或
- 用户明确更换模板/参考专利，要求重新固化写作规范。

当触发时，必须调用：`writing-style-analyzer`

### 阶段 6：写作任务单装配（并入阶段 7）

本阶段不再作为独立对外阶段暴露；其职责并入阶段 7，作为调用 `modular-writer` 前的内部装配动作（将创新点/背景包/模板规则/风格工件/附图交付规则组装为写作输入）。

### 阶段 7：正文草稿撰写（含写作任务单装配）

必须调用：`modular-writer`

本阶段强制落盘工件（固定路径，统一下沉到 `artifacts/`）：
- `artifacts/draft/facts_ledger.json`

门禁（必须通过）：
- 运行 `python skills/patent-workflow/scripts/run_phase_gates.py --phase 7 --workspace . --manifest <run_manifest_path>` 并返回通过；否则不得进入一致性审计。
  - 该命令会调用 `validate_facts_ledger.py artifacts/draft/facts_ledger.json --base-dir . --require-docx-visible-mermaid`。

### 阶段 8：一致性审计

门禁（强制）：一致性审计输出必须可打分且可定位（参见 `CONSISTENCY_AUDIT_TEMPLATE.md` 的评分字段与 `top_issues` 定位字段）。

### 阶段 9：IPR 模拟审查

门禁（强制）：IPR 审查输出必须可打分且可定位（参见 `IPR_REVIEW_TEMPLATE.md` 的评分字段与 `top_risks` 证据/原因字段）。

### 阶段 10：回改闭环

本阶段强制落盘工件（固定路径，统一下沉到 `artifacts/`）：
- `artifacts/revision/phase_10_edit_plan.json`
- `artifacts/revision/phase_10_structured_diff.json`
- `artifacts/revision/phase_10_post_fix_check_report.md`

门禁（必须通过）：
- 运行 `python skills/patent-workflow/scripts/run_phase_gates.py --phase 10 --workspace . --manifest <run_manifest_path>` 并返回通过；
  - 该命令会调用：
    - `validate_edit_plan.py artifacts/revision/phase_10_edit_plan.json`
    - `validate_structured_diff.py artifacts/revision/phase_10_structured_diff.json --edit-plan artifacts/revision/phase_10_edit_plan.json`
- 完成回改后必须复跑阶段 8/9 的关键门禁并写入 `phase_10_post_fix_check_report.md`。

### 阶段 11：最终导出与交付

必须调用：`modular-writer`

本阶段强制落盘工件（固定路径，统一下沉到 `artifacts/`）：
- `artifacts/delivery/phase_11_delivery_health_report.json`

门禁（必须通过）：
- 运行 `python skills/patent-workflow/scripts/run_phase_gates.py --phase 11 --workspace . --deliver-dir <deliver_dir> --patent-title <patent_title> --manifest <run_manifest_path>` 并返回通过；否则不得宣告交付完成或执行 IM 发送。
  - 该命令会调用 `health_check_delivery_package.py` 生成健康报告并写入 `artifacts/delivery/phase_11_delivery_health_report.json`。

强制交付规则：
1. 终稿 docx 文件命名必须为：`<专利标题>技术交底书.docx`（其中 `<专利标题>` 来自阶段 3 的收敛题名）。
2. 最终交付目录必须由用户在本轮明确指定（绝对路径）；不得在未询问用户的情况下默认使用某个本地路径。
3. 附图交付至少保留三类工件：
   - `.mmd`：逻辑源（兜底复现/手工导入与调整）；
   - `.drawio`（或等价可编辑图源，如 `.vsdx`）：成品可编辑源；
   - `.png`/`.svg`：最终嵌入 docx 的图像工件。
4. 终稿 docx 中若需要附图，宣告交付完成前必须检查 docx 内部 `word/media/` 非空，确保图片已真正嵌入，而非仅在目录中存在。
5. 最终交付目录中的正式 docx 默认只保留最新正式件；旧版、修订版、`bak`、`trialbak`、`tmp`、评价件等 docx 必须清理，不得与正式终稿并列保留。
6. 评价、审查、对比、过程说明等文档若需保留，统一下沉到 `artifacts/`，不得作为根目录正式 docx 保留。

IM 通道交付（可选，按会话渠道能力执行）：
- 若用户通过 Discord / 飞书 / 等 IM 通道沟通，导出后应直接发送终稿 docx。
- 同时发送“一致性审计评分 + IPR 审查评分”的摘要（含 Top3 风险点与改进项）。

## 使用摘要

当用户说以下任一类请求时，使用本技能：

- “跑一遍专利工作流”
- “按 workflow 写专利交底书”
- “帮我选题、查新、写交底书”
- “升级 patent-workflow skill”
- “检查这条专利流程有什么缺陷”
