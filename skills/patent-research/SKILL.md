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

**梯度 1 —— 预定义 scout 子代理（首选）**：宿主的用户级 agent 目录已部署 4 个专属侦察员（随家族 `deploy.ps1` 一并安装，无需单独初始化）。**按正交维度分工并行派发**，每个 scout 收到：`domain_scope`、与其维度相关的研究问题、`freshness_window`（默认 18 个月；AI/自动驾驶等快演化领域沿用此值，用户可改）：

| agent | 维度 | 为创新点提供 |
|---|---|---|
| `patent-industry-scout` | 行业动态/竞品/量产/工程痛点 | 机会空隙 |
| `patent-academic-scout` | 论文/预印本/会议/综述 | 技术基线与前沿、工程化空隙 |
| `patent-landscape-scout` | 方向级专利密度侦察 | 拥挤度与白地信号 |
| `patent-regulation-scout` | 标准/法规/监管动向 | 合规驱动的创新空间 |

每个 scout 自带**防偷懒配额**（≥4 轮检索、≥3 篇正文抓取、每问题 ≥2 证据、search_log/dead_ends 必填）与**时效自校验**（每条证据必须带日期并分级 fresh/valid/stale，stale 占比 >50% 必须重搜后才许返回），定义见各 agent 文件。

**梯度 2 —— 预定义 agent 缺失**（未跑 deploy 或非 Claude Code 宿主）：用宿主的通用子代理机制并行派发，指令按上表维度现场组装，配额与时效要求原样写入指令。

**梯度 3 —— 宿主无并行能力**：主模型按四个维度顺序执行调研轮次，每轮独立完成「搜索 → 抓取 → 记证据」，配额与时效要求不变。

三条梯度的证据格式与数量要求完全相同；门禁不关心用的哪条。

## Step 5：汇总、校验与收敛

1. **抽查防伪**（防偷懒第四道闸）：每个 scout 的证据抽 1-2 条实际访问 URL，核对 excerpt 真实存在；抽查失败的 scout 其全部证据降级为未验证并重派。
2. **时效审计**：统计合并后证据的日期分布；支撑「现状/前沿/竞品动向」的证据中 `stale`（> freshness_window）占比超 30% → 对应维度定向重搜。**超过 18 个月的资料只允许作为技术基线/历史背景使用，且必须显式标注**。
3. 合并去重，剔除 URL 不可访问或摘录不足 50 字符的条目；不足 8 条 → **换词重检**（同义词、场景词、英文对照词）补齐，而不是降低标准。
4. 收敛 2-3 个技术主轴明确不同的候选方向（或固定题目下的创新切入轴）——综合四维度信号：机会空隙（industry）× 工程化空隙（academic）× 白地（landscape）× 合规驱动（regulation），给出推荐方向与题名种子。
5. 组装并落盘 `artifacts/research/phase_02_research_pack.json`（结构严格按契约文件，evidence 带 date 与 freshness）。
6. 输出汇报层 Markdown（Research Scope / Channels / Evidence Table / Candidate Directions / Recommendation / Needs Patent Verification）。
7. 跑门禁：`python <patent-skill-dir>/scripts/run_phase_gates.py --gate research --workspace . --manifest artifacts/run_manifest.md`，未过先自行补证据重跑，最多 3 轮后仍不过才向用户说明缺口。

## 禁止事项

1. 禁止编造专利号、论文、产品、日期、指标。
2. 禁止把未抓取验证的 URL 写进 `evidence[]`。
3. 禁止在本 skill 内断言某专利可作背景引用——那是 `patent-prior-art` 的职责，此处只列 `claims_requiring_patent_verification`。
4. 禁止把同一技术轴的轻微改写包装成多个候选方向。
