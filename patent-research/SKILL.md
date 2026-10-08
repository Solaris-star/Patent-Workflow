---
name: patent-research
description: |
  为软件专利协作流程制定范围内的证据调研，支持完整调研、已定题补证和已有稿审查。
  复用当前材料，按用户要求的检索深度执行；不凑问题、来源或检索轮次配额。
  触发方式：/patent-research、「专利调研」「补证」「审查现有稿」。
---

# 软件专利协作调研

本 skill 指导宿主完成调研，不自带搜索服务或自动启动代理。证据格式沿用 [research-pack-contract.md](../patent/references/research-pack-contract.md)，检索边界见 [search-protocol.md](../patent/references/search-protocol.md)。

## 选择路径

- **完整调研**：题名尚未确定，用户要求探索软件专利主题。从披露材料和明确范围开始。
- **已定题补证**：题名已确认，先检查当前材料和已核验来源，只补具体证据缺口，不重启宽泛选题。
- **已有稿审查**：先阅读草稿及其来源；只为明确的问题或证据缺口补充调研。

读取 run manifest 和已有 research/evidence/background packs。来源、日期、核验状态、feature 映射或版本哈希变化时，标记相关结论待复核。

## 范围、检索与证据

遵循 manifest 中的司法辖区、日期范围、来源偏好和 `light` / `balanced` / `deep` 检索深度。检索深度决定投入程度，不代表结果数量。问题数量、检索轮次、候选方向、专利或论文数量及摘录长度均没有统一配额；停在用户问题得到有依据的回答、指定范围已查完或可用渠道耗尽的位置。记录不足和失败渠道，不编造材料补数。

本仓库不含已部署的 scout agent，也不提供自动部署脚本；仓库仅保存两份可供宿主参考的 reviewer 提示词：agents/patent-consistency-auditor.md 与 agents/patent-tech-reviewer.md。提示词本身不会启动代理。只有宿主确实支持独立 reviewer 调用且材料范围已获授权时才调用；两路独立调用均受支持且职责可分时可并行，否则在当前会话按视角顺序复核，并标注单会话结果。smart-search CLI、浏览器、MCP 或 Playwright 都是可选宿主能力，需实际可用并获准；不随此 skill 安装或自动启动。

任何由案件材料派生的查询或文件要离开本机之前，先让用户明确确认具体内容、目的地和用途。没有确认时不发送，记录为外部检索不可用；可以继续做本地结构整理，但不要声称已完成外部查新。

每条证据记录稳定 evidence ID、HTTP(S) 来源、摘录、发布日期或 `unknown`、task-specific freshness、核验状态、核验时间与方法，以及所支持的稳定 `F-...` feature ID。区分已实现事实、来源说法、推断和待确认项。只有已核验且对当前问题仍有效的证据标记 `conclusion_use: usable`；其余设为 `pending_reverification` 或 `context_only`。

freshness 依本次问题、司法辖区和时间范围判断；不套用统一固定期限。专利号码、文献数量、URL 形状或结构校验通过都不能证明来源真实。未检索或未核验的内容不得用于新颖性、授权或可实施性的确定结论。

## 整理与验证

将实际提出的研究问题、相关正文结构和证据写回现有 `phase_02_research_pack.json`；只保留与用户范围有关的内容，列表需有真实记录，但不为达到数量而扩写。Phase 4 prior-art evidence pack 和 facts_ledger 是后续特征追溯的统一来源，不要另外建立平行事实数据库。

离线校验器只检查结构、日期字段、引用、映射和声明哈希；不判断法律新颖性、创造性、可专利性或授权概率。验证失败时报告具体缺口；只有用户要求且渠道已获授权时才继续外部检索。

若要把未选方向写入已启用的 patent-vault，先逐条让用户确认，且只写脱敏后表述。vault 未初始化时遵循 patent-vault 自己的引导规则；不要因流程默认初始化或保存案件数据。
