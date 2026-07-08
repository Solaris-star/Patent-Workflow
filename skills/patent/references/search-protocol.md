# 数采能力协议（search-protocol）

patent 家族所有联网调研类 skill（patent-research、patent-research-cli、patent-prior-art）共用本协议。

核心原则：**门禁只约束产出质量，不约束用了哪些通道**。通道能用尽用、缺了自动降档、兜底永远存在，因此任何外部 CLI / MCP 都是可选增强，不是前置依赖。

## 两层能力模型

| 层 | 职责 | 缺失后果 |
|---|---|---|
| 发现层 discovery | 找到候选来源、线索、专利号 | 无 —— 兜底通道内置于宿主 |
| 验证层 fetch | 抓取页面正文，把线索变成证据 | 无 —— 兜底通道内置于宿主 |

发散、扩词、假设生成、候选方向收敛由**当前会话模型自行完成**，不设外部依赖，不参与探测与降级。

## Provider 分级表

每层按优先级从上到下选用。「探测」失败即静默跳过该 provider，**不报错、不重试、不追问用户**。

### 发现层

| 优先级 | provider | 探测方式 | 说明 |
|---|---|---|---|
| 1 | `smart-search` CLI | `Get-Command smart-search`（或 `which smart-search`）成功 | 多源聚合，**用通用入口让 CLI 自行路由 provider**（`search` 广域 / `research` 一键深度）；不要硬编码具体 provider 子命令，实际可用 provider 以本机 `smart-search doctor` 为准 |
| 2 | 搜索类 MCP 工具（exa / brave 等） | 会话工具列表中存在 | 语义发现增强 |
| 3 | **宿主内置网页搜索** | 恒可用 | 兜底，零依赖（Claude Code：WebSearch；Codex / Hermes：各自内置浏览搜索能力） |

### 验证层

| 优先级 | provider | 探测方式 | 说明 |
|---|---|---|---|
| 1 | `smart-search fetch` | 同上（CLI 存在） | Tavily→Jina→Firecrawl 抓取链 |
| 2 | 浏览器类 MCP（playwright / browser-cdp） | 会话工具列表中存在 | 动态页、登录态页面专用 |
| 3 | **宿主内置网页抓取** | 恒可用 | 兜底，零依赖（Claude Code：WebFetch；其他宿主用其等价抓取能力） |

**对象特化例外**：当检索对象存在权威官方源时，具体 skill 可重排本层优先级——如 `patent-prior-art` 的专利对象检索以「浏览器自动化直上国知局官方检索系统」为主路径（检索+验证一体），上表通用优先级仅作其兜底。

## 能力探测规则

1. 每轮 workflow 开始时**一次性**探测，结果写入 run manifest 的 `capability_profile`，整轮直接查表，不得反复探测。
2. 探测必须轻量：命令存在性检查即可；禁止为探测发起真实搜索。
3. MCP 工具直接看会话工具列表，无需命令探测。
4. 单个 provider 中途连续失败 2 次 → 本轮内标记为不可用，落到下一优先级，在 `channel_failures` 记录一次。

## 质量门禁（与通道解耦）

门禁只校验产出，全部可离线核验：

| 门禁项 | 标准 | 裁决者 |
|---|---|---|
| 研究证据 | `evidence ≥ 8` 条，每条带可访问 URL + ≥50 字符摘录 | `validate_research_pack.py` |
| 强来源 | ≥ 3 个 L1/L2 级来源支撑核心结论 | skill 自查 + manifest 留痕 |
| fetch_before_claim | 关键结论必须有已抓取正文支撑；仅有搜索摘要的来源标记「未验证候选」 | skill 自查 |
| 专利候选 | CN-only、时效 ≤ 1.5 年、相关分 ≥ 阈值、`finalRelevantPatents ≥ 5` | `validate_patent_candidates.py` |
| 检索证据包 | 对齐条目 ≥ 3 且每条含非辅助专利证据 | `validate_evidence_pack.py` |

产出不达标时的正确动作是**换词重检、加大迭代轮数**（同义词、场景词、申请人、分类号辅助词、近义应用域），而不是要求用户安装更多工具。数采深度靠迭代轮数与抓取深度保证，与已安装通道数量无关。

## 来源分层

- `L1`：官方文档、标准、监管或权威机构页面
- `L2`：论文、专利数据库、权威技术文档、正式产品文档
- `L3`：行业媒体、技术博客、公司博客
- `L4`：论坛、社区帖子、转述页面

专利场景主证据用 `L1-L2`；`L3-L4` 只能作补充线索，不得独自支撑核心结论。

## degraded 语义

- 少装某个 CLI / MCP → **不是 degraded**，只是 `capability_profile` 不同。
- `degraded_run = true` 仅在以下情况成立：
  1. 兜底通道（宿主内置搜索/抓取）也调用失败；
  2. 质量门禁未达标但用户明确豁免放行（须记入 `user_confirmations`）。

## 留痕字段

每轮调研结束，向 run manifest 写回：`capability_profile`、`channels_used`、`channel_failures`、`fallback_actions`、`strong_source_count`、`evidence_table_count`、`degraded_run`。
