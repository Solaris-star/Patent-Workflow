---
name: patent-research
description: |
  专利创新点调研（开箱即用版，零外部依赖）。多子代理并行分工研究问题，使用宿主内置
  网页搜索/抓取能力完成交叉领域发现、创新方向挖掘、证据收集与方向收敛。
  触发方式：/patent-research、「专利调研」「找创新点」「选题调研」「交叉领域发现」。
  本机装有 smart-search CLI 时优先改用 patent-research-cli（能力等价、速度更快）；
  本 skill 是无任何 CLI/MCP 时的默认调研路径，产出契约与 CLI 版完全一致。
---

# patent-research：创新点调研（多子代理版）

为专利选题提供有证据支撑的创新方向。产出契约、质量门禁与 `patent-research-cli` 完全一致，唯一真源见 [../patent/references/research-pack-contract.md](../patent/references/research-pack-contract.md)；通道选择协议见 [../patent/references/search-protocol.md](../patent/references/search-protocol.md)。

## Step 1：确认研究范围

从用户请求或 run manifest 读取：`objective`、`domain_scope`、`fixed_topic_or_title`、`constraints`、`application_scenario`。缺领域且属于全流程 → 由 patent 路由的首问补齐，本 skill 独立使用时自行问一次。

## Step 2：主题发散（主模型直接完成）

- 无固定题目：生成 3-7 个候选主题簇（核心问题 + 预期创新空间 + 与用户约束的匹配点）。用户未给领域时先做交叉领域发现：组合两个领域给出 2 个最有交叉专利前景的组合与理由。
- 有固定题目：只生成该题目下的 2-3 个创新切入轴，不扩池。

发散、扩词、假设生成全部由当前模型自行完成，不依赖任何外部推理服务。

## Step 3：拆研究问题

把任务拆成 **≥ 8 个**研究问题（门禁要求），覆盖四类：

1. 当前行业正在发生什么（现状与趋势）
2. 已有主流方法是什么（技术基线）
3. 哪些痛点仍未被很好解决（机会空隙）
4. 哪些方向像「可专利化差异」而非常规工程拼装（新颖性预判）

每个问题分配 `id`（RQ1…RQn）。

## Step 4：并行调研（能力梯度，宿主中立）

**梯度 1 —— 宿主支持并行子代理**（Claude Code 的 Task/Agent 机制、Codex/Hermes 的等价原生机制）：

- 按研究问题分组派发子代理，每个子代理负责 2-3 个相邻问题，3-4 个子代理并行。
- 子代理指令模板：
  ```
  角色：专利调研员。研究问题：{RQx: 问题文本}
  要求：
  1. 用宿主内置网页搜索发现候选来源，中文优先、中英混合扩展；
  2. 对支撑结论的关键页面必须抓取正文（fetch_before_claim），只有搜索摘要的来源标记「未验证候选」；
  3. 每个问题至少产出 2 条证据：{evidence_id, url, excerpt(原文摘录≥50字符), source_tier(L1-L4), claim, date}；
  4. 优先 L1-L2 来源（官方文档/标准/论文/专利库/正式产品文档）；
  5. 返回纯 JSON：{ "findings": [证据数组], "insights": [对所负责问题的回答要点], "dead_ends": [搜过但无果的方向] }
  ```
- 子代理彼此独立，不共享中间结论（保证证据来源多样性）。

**梯度 2 —— 宿主无并行能力（自动降级，不询问用户）**：

- 主模型按问题分组顺序执行同样的调研轮次，每轮独立完成「搜索 → 抓取 → 记证据」，轮与轮之间不复用未经验证的推断。

两条梯度的证据格式与数量要求完全相同；门禁不关心用的哪条。

## Step 5：汇总与收敛

1. 合并去重各路证据，剔除 URL 不可访问或摘录不足 50 字符的条目；不足 8 条 → **换词重检**（同义词、场景词、英文对照词）补齐，而不是降低标准。
2. 收敛 2-3 个技术主轴明确不同的候选方向（或固定题目下的创新切入轴），给出推荐方向与题名种子。
3. 组装并落盘 `artifacts/research/phase_02_research_pack.json`（结构严格按契约文件）。
4. 输出汇报层 Markdown（Research Scope / Channels / Evidence Table / Candidate Directions / Recommendation / Needs Patent Verification）。
5. 跑门禁：`python <patent-skill-dir>/scripts/run_phase_gates.py --gate research --workspace . --manifest artifacts/run_manifest.md`，未过先自行补证据重跑，最多 3 轮后仍不过才向用户说明缺口。

## 禁止事项

1. 禁止编造专利号、论文、产品、日期、指标。
2. 禁止把未抓取验证的 URL 写进 `evidence[]`。
3. 禁止在本 skill 内断言某专利可作背景引用——那是 `patent-prior-art` 的职责，此处只列 `claims_requiring_patent_verification`。
4. 禁止把同一技术轴的轻微改写包装成多个候选方向。
