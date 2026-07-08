---
name: deep-research
description: 多源深度调研技能。用于需要当前证据、引用链接和跨来源综合的研究任务，尤其适用于专利创新点发现、候选技术方向筛选、竞品研究和工作流首轮创新研究。在专利模式下，必须显式输出 channels_used、channels_skipped、why_skipped、candidate_directions、recommended_direction、claims_requiring_patent_verification 和带来源链接的 Evidence Table，且不能仅用 Grok 或 DeepSeek 作为唯一证据链。
---

# Deep Research

## 角色定位

本技能负责“当前信息调研”和“创新方向发现”，不是专利引用验证工具。

在专利 workflow 中，本技能的职责是：

1. 找出可行的创新方向或创新切入轴。
2. 用多来源证据支持这些方向不是拍脑袋得出的。
3. 标出哪些主张仍需交给 `cn-patent-search` 做专利验证。

`cn-patent-search` 仍然是背景专利验证唯一真源。

## 统一能力集合

把以下能力视为默认应启用的提供者集合，而不是互斥模式；执行时优先全量尝试，只有在实际不可用、超时、缺失权限或返回异常时，才在最终结论中记录为 skipped / failed：

- `brave`：发现网页与新闻线索。
- `ddg`：第二发现通道，用于补召回与交叉验证。
- `exa`：语义发现与高质量扩展。
- `grok`：外置大脑，用于假设生成、方向发散、查询扩展、证据 URL 建议。
- `deepseek`：外置大脑，用于假设生成、方向发散、查询扩展、证据 URL 建议；默认本地 OpenAI 兼容链路为 `model=deepseek-v3.5-search`、`url=http://localhost:8317/v1`。
- `firecrawl`：深页抓取或批量页面提取。
- `playwright`：动态页面、登录态页面、复杂交互页面读取。

如果某些提供者不可用，不要在起跑阶段预先关闭；默认先尝试全部链路，仅在实际调用失败或宿主能力缺失后再降级，并把降级说清楚。

## 外置大脑链路

`grok` 与 `deepseek` 在本技能中属于“外置大脑”而不是“证据真源”。

使用规则：

1. 可以把它们并行接入调研链路，用于生成检索式、候选创新方向、claim 草案、query expansion 和证据 URL 建议。
2. 它们可以出现在 `channels_used` 中，但不能单独充当 `validation_channel_used`。
3. 它们的输出不能直接计入 `strong_source_count`，除非其中引用的 URL 又被页面直读、`firecrawl` 或 `playwright` 独立验证。
4. 它们不能单独支撑 `recommended_direction` 的最终证据基础。
5. 本技能默认脚本入口为：
   - `scripts/external_brain_dispatch.ps1`
   - `scripts/grok_chat.ps1`
   - `scripts/deepseek_chat.ps1`
6. 若需要统一探测可用性、执行并行或顺序回退，并输出标准化状态，优先调用 `scripts/external_brain_dispatch.ps1`，其余两个脚本视为 provider adapter。
7. dispatcher 默认支持 `QueryFile` 输入、provider 级 `TimeoutSec` 和调度级超时，用于避免长中文提示在命令行边界被污染，以及避免单 provider 卡死拖住整轮调研。
8. 对专利创新点挖掘、长提示词发散或高推理负载场景，默认应使用更宽松的超时预算；除非用户明确要求快失败，否则不应沿用短超时配置。
8. 外置大脑链路默认采用“UTF-8 文件输入 + UTF-8 文件输出 + ASCII-safe stdout JSON”传输约定，避免中文长提示和中文响应在 PowerShell 子进程与控制台码页之间被污染。
9. 若主代理只需要结构化结果，优先消费 dispatcher 的 JSON 结果，不要再从控制台文本二次猜测编码。

## 链路健康与回退

默认把 `grok` 与 `deepseek` 视为并行优先、可相互兜底的外置大脑链路。

回退顺序：

1. 默认优先并行尝试 `grok + deepseek`。
2. 若其中一条链路失败，记录失败原因，并继续使用剩余可用链路，不因此阻断整轮调研。
3. 若并行模式未达到 `MinSuccessCount`，dispatcher 应自动对失败链路再做一轮顺序回退重试，并把重试结果写入 `fallback_actions`。
4. `external_brain_dispatch.ps1` 的退出码只表示外置大脑链路是否达到 `MinSuccessCount`，不等于整轮 research 必须中止；若发现通道与验证链路仍满足门禁，主代理仍可继续执行并标记 `degraded_run: true`。
5. 若两条外置大脑链路都失败，但 `brave/ddg/exa + 验证链路` 仍完整，可继续执行，但必须标记 `degraded_run: true`。
6. 若两条外置大脑链路都失败，且发现通道不足 2 条或没有独立验证链路，则：
   - 固定题目场景：允许在明确降级后继续做保守研究；
   - 非固定题目场景：停止推荐方向收敛，先向用户说明本轮创新发散能力下降。
7. 若某条链路返回内容异常、空结果、结构化字段缺失或明显幻觉，应视为该链路本轮不可用，而不是视为成功调用。

每次发生链路回退时，至少记录：

- `channel_failures`
- `fallback_actions`
- `brain_chain_status`

## 来源分层

优先把来源分成以下层级：

1. `L1`：官方文档、标准、监管或权威机构页面。
2. `L2`：论文、专利数据库、权威技术文档、正式产品文档。
3. `L3`：行业媒体、技术博客、公司博客。
4. `L4`：论坛、社区帖子、转述页面。

专利模式下，优先使用 `L1-L2` 作为主证据；`L3-L4` 只能作为补充线索，不能独自支撑核心创新结论。

## 专利模式硬规则

当本技能为 `patent-workflow` 服务时，必须满足以下规则：

1. 默认至少尝试：
   - 3 个发现通道，优先 `brave`、`ddg`、`exa` 全开。
   - 1 个验证通道，优先从页面直读、`firecrawl`、`playwright` 中选择。
   - 2 条外置大脑链路：`grok` 与 `deepseek` 全开。
2. 至少深入阅读 3 个强来源，优先来自 `L1-L2`。
3. `Evidence Table` 至少包含 3 条证据行，且每条必须带 `Source URL`。
4. `grok` 或 `deepseek` 都不能作为唯一证据来源。
5. 如果实际只使用了单一发现通道，必须输出 `degraded_run: true` 并说明原因。
6. 不能把“Grok 认为”或“DeepSeek 认为”直接当成证据结论。
7. 如果同时启用了 `grok` 与 `deepseek`，应把二者视为并行脑力链路，而不是额外的验证链路。
8. 若外置大脑链路失效，优先保持“发现通道数量 + 验证链路”完整，其次才是保持脑力链路数量完整。

## 研究工作流

### Step 1：明确目标

至少确认以下字段：

- `objective`
- `domain_scope`
- `fixed_topic_or_title`
- `constraints`
- `freshness_window`

在专利场景下，额外明确：

- `application_scenario`
- `candidate_innovation_axes`
- `what_is_not_novel_enough`

### Step 1.5：主题簇发散（仅无固定题目时）

当 `fixed_topic_or_title` 为空、为 `exploratory`，或仅给出宽领域而未固定具体题目时，必须先执行一轮主题簇发散，再进入研究问题拆分：

1. 默认优先通过 `grok + deepseek` 并行生成 3-7 个候选主题簇。
2. 每个主题簇至少要说明：核心问题、预期创新空间、与用户约束的匹配点。
3. 进入正式研究输出时，只能收敛为 2-3 个技术主轴明确不同的候选方向，不得把同一技术轴的轻微改写伪装成多个方向。
4. 若外置大脑链路不可用，可降级为主代理基于发现通道自行发散，但必须记录 `topic_divergence_degraded = true`，并在 `why_skipped` 或 `fallback_actions` 中说明原因。

### Step 2：拆成研究问题

把任务拆成 3-5 个子问题，例如：

1. 当前行业正在发生什么。
2. 已有主流方法是什么。
3. 哪些痛点仍然没有被很好解决。
4. 哪些方向更像“可专利化差异”，而不是常规工程拼装。

### Step 3：选择渠道

默认策略不是“最小组合优先”，而是“可见能力全链路优先”。只要链路已配置、能力已 surfaced、权限允许，就默认全部启用；只有链路实际失败时，才在最终结论里说明 skipped / failed。

专利模式推荐默认组合：

- `brave`
- `ddg`
- `exa`
- 页面验证通道 1 个，优先 `playwright` 或页面直读，必要时 `firecrawl`
- `grok`
- `deepseek`

若其中任一链路实际失败，再按失败结果降级，而不是在研究开始前预裁剪。

推荐回退顺序：

1. 默认先尝试全部已 surfaced 且已配置的链路：`brave + ddg + exa + grok + deepseek + validation`
2. 若部分链路失败，保留成功链路并记录失败原因，再继续完成研究输出
3. 若并行模式未达到外置大脑最小成功数，dispatcher 应自动对失败链路再做一轮顺序回退重试，并把重试结果写入 `fallback_actions`
4. 若两条外置大脑链路都失败，但 `brave/ddg/exa + 验证链路` 仍完整，可继续执行，但必须标记 `degraded_run: true`
5. 若两条外置大脑链路都失败，且发现通道不足 2 条或没有独立验证链路，则：
   - 固定题目场景：允许在明确降级后继续做保守研究；
   - 非固定题目场景：停止推荐方向收敛，先向用户说明本轮创新发散能力下降。

不得降到仅剩外置大脑而没有独立验证链路。

## 效率优先规则

为避免专利模式调研阶段过慢，默认采用以下快路径：

1. 外置大脑链路优先通过 `external_brain_dispatch.ps1` 一次性并行调度，而不是分别串行调用 `grok_chat.ps1` 和 `deepseek_chat.ps1`。
2. 固定题目或固定标题场景下，默认只产出 2-3 个创新切入轴，不额外扩展大范围候选方向。
3. 页面深读默认聚焦最强的 3-5 个来源；只有证据冲突时才扩展到更多来源。
4. 外置大脑提示词默认使用短结构化控制格式，避免无必要的长篇对话式提示。
5. 若同一轮 workflow 已经产出合格 research artifact，后续回改阶段默认复用该 artifact，不重复跑完整 research，除非用户明确要求刷新。

### Step 4：抓取与阅读

不要只停留在搜索摘要。至少要深入阅读 3-8 个强来源，提取：

- `claim`
- `source_url`
- `source_type`
- `date`
- `supporting_evidence`
- `caveat`

### Step 5：综合输出

将内容分成：

- 已证据支持的事实。
- 跨来源共识。
- 推断。
- 仍不确定的问题。

## 专利模式输出契约

为 `patent-workflow` 服务时，至少输出以下字段：

```markdown
## Research Scope
- objective:
- domain_scope:
- fixed_topic_or_title:
- application_scenario:

## Channels
- channels_used:
- channels_skipped:
- why_skipped:
- degraded_run:
- brain_chain_status:
- channel_failures:
- fallback_actions:
- validation_channel_used:

## Source Summary
- strong_source_count:
- source_tiering_summary:
- evidence_table_count:

## Evidence Table
| Claim | Evidence | Source URL | Source Tier | Confidence | Notes |

## Candidate Directions
- candidate_directions:
- candidate_innovation_axes:
| Direction | Novelty | Practicality | Why It May Be Patentable |

## Recommendation
- recommended_direction:
- recommended_title_seed:

## Needs Patent Verification
- claims_requiring_patent_verification:
```

## 降级规则

允许降级，但必须明示：

1. 哪些通道没跑。
2. 为什么没跑。
3. 降级后哪些结论可信度下降。
4. 哪些结论不能直接进入专利正文。
5. 如果外置大脑链路不可用，哪些 query expansion 或候选 claim 由主代理自行补齐。
6. 如果只剩单条外置大脑链路，是否已经改成“单脑 + 多证据验证”模式。

## 禁止事项

1. 禁止把 Grok 或 DeepSeek 输出当成唯一证据。
2. 禁止编造专利号、论文、产品、日期或指标。
3. 禁止在本技能里直接断言某专利可作为背景引用。
4. 禁止只给“方向结论”，不交代渠道和依据。
5. 禁止把外置大脑返回的未验证链接直接写入 `Evidence Table`。

## 与 patent-workflow 的交接

只有满足以下条件，才算研究阶段可交接：

1. 已记录 `channels_used`、`channels_skipped`、`why_skipped`。
2. 已给出 2-3 个候选方向，或固定题目下的 2-3 个创新切入轴。
3. 已给出推荐方向。
4. 已给出需由 `cn-patent-search` 继续验证的主张列表。
5. 已给出至少 3 行带链接的 `Evidence Table`。
6. 已明确 `validation_channel_used` 与 `strong_source_count`。
7. 若发生链路失效，已记录 `channel_failures` 与 `fallback_actions`。

若不满足，`patent-workflow` 不应进入专利检索阶段。
