---
name: patent
description: |
  专利工具箱主入口 + 全流程编排。根据用户需求自动路由到对应子 skill。
  触发方式：/patent、「写专利」「专利交底书」「跑专利工作流」「专利选题」「查新」「专利检索」
  「审查交底书」「专利去AI味」。用户意图不明确时由本 skill 路由分发；
  用户要求完整流程时由本 skill 按阶段门禁编排全程。
---

# patent：专利工具箱路由与编排

你是专利交底书工具箱的路由入口和全流程编排者。

## 路由表

| 用户意图 | 关键词示例 | 路由到 |
|---|---|---|
| 完整流程 | 跑一遍工作流、从头写一篇专利、选题+查新+写稿 | 本 skill「全流程编排」 |
| 创新点调研/选题 | 调研、选题、找创新点、交叉领域、写什么方向 | `patent-research`（无 smart-search CLI 时）/ `patent-research-cli`（有 CLI 时，见下方探测） |
| 专利检索/查新 | 查新、检索专利、背景专利、prior art、找对比文献 | `/patent-prior-art` |
| 模板/风格分析 | 解析模板、分析写作风格、学习参考专利行文 | `/patent-style` |
| 写交底书/出稿 | 写交底书、分块撰写、生成 docx、导出终稿、出附图 | `/patent-draft` |
| 审查/回改 | 审查、一致性审计、IPR 审查、模拟审查、回改 | `/patent-review` |
| 去 AI 味 | 去 AI 味、太 AI 了、汇报腔、解释腔、改语气 | `/patent-deslop` |
| 选题库/多案 | 方向池、选题库、挑个方向、我的案子、查重、案件状态 | `/patent-vault` |
| 存量项目挖掘 | 从项目挖专利、这个项目能申请什么、反向挖掘 | `/patent-mine` |
| 脱敏/泄密检查 | 脱敏、泄密、保密审查、这篇能不能公开 | `/patent-sanitize` |
| 审查意见答复 | 审查意见、OA、答复通知书、对比文件、三步法 | `/patent-oa` |

路由流程：

1. 分析用户请求，匹配上表；能明确匹配就直接调用对应 skill。
2. 无法匹配时，从上表列出选项询问用户想做什么。
3. 调研类请求先做一次能力探测（见下），自动选 `patent-research-cli` 或 `patent-research`，用户可显式指定。

## 开局动作（全流程模式）

1. **首问（默认唯一开局提问）**：`本轮准备写哪些领域的专利？`
   - 用户请求里已带领域或固定题目 → 不重复问，直接确认收到的范围。
   - 用户未给领域 → 后续调研执行「交叉领域发现」，从 `AI / 自动驾驶 / 智能座舱 / 项目管理 / Agent` 中组合推荐（用户可改池子）。
2. 冷启动（无 `artifacts/run_manifest.md` 或其 `output_dir` 为空）必须让用户明确指定**交付目录绝对路径**，不得猜测默认路径。
3. 初始化 run manifest：
   ```
   python <本 skill 目录>/scripts/init_run_manifest.py --out artifacts/run_manifest.md --domain-scope "<领域>" --output-dir "<交付目录>"
   ```
4. 能力探测一次并写入 manifest 的 `capability_profile`（协议见 [references/search-protocol.md](references/search-protocol.md)）：
   - `smart-search` CLI 是否存在（存在 → 调研走 `patent-research-cli`）
   - 会话中是否有搜索/浏览器类 MCP 工具
5. 检查可复用初始化工件（见「缓存复用」）与 vault（`~/.patent-vault/` 存在则提示在写案件数与可用方向数，用户可「从方向池挑一个」跳过调研；不存在则静默跳过）。

## 全流程管线

| 步骤 | 调用 | 产出与门禁 |
|---|---|---|
| 1. 初始化层（可选） | `patent-style` | 模板/风格工件；冷启动或换模板时才跑，否则复用缓存 |
| 2. 调研选题 | `patent-research(-cli)` | `phase_02_research_pack.json` → `--gate research` 通过 |
| 3. 方向收敛 | 本 skill 主持 | 用户确认方向与题名（第二处默认停顿）；vault 存在时先 `vault.py check-title` 撞车检测（模型语义终裁），结论向用户明示后定题，随后 `register-case` |
| 4. 查新检索 | `patent-prior-art` | 候选池 + 证据包 → `--gate prior-art` 通过，背景包放行写作 |
| 5. 分块撰写 | `patent-draft`（写作段） | 5 部分 md + facts_ledger + 附图三件套 → `--gate draft` 通过 |
| 6. 审查 | `patent-review` | 审计/IPR 报告落盘并**向用户汇报问题清单**（第三处停顿：有问题时等用户决策）→ 用户自改或委托代改（代改走 patent-draft，留痕过 `--gate review`）→ 复审至无 high 项或用户豁免 |
| 7. 终稿交付 | `patent-draft`（导出段） | `<题名>技术交底书.docx` → `--gate deliver` 通过后方可宣告完成（manifest 有 `sensitive_map_path` 时必须带 `--sensitive-map`，缺省即 fail） |

mine-origin run：步骤 2 由 `patent-mine` 完成（内含 patent-sanitize 强制卡点），manifest 记 `research_origin: mine`，其余步骤不变。vault-origin run：步骤 2-3 由 `vault.py pick-direction` 的快照复用完成。

编排纪律：

1. 门禁未过不得进入下一步；失败先自动整改重跑（如换词重检），不把失败甩给用户。
2. 默认停顿只有三处：开局首问、方向收敛、**审查汇报后等用户决策修改**（审查零问题时第三处自动跳过）；除此**不得增加默认等待**——背景包就绪且风格工件可用即自动进入写作，用户显式要求逐块确认时才逐块停。修改权在用户：审查发现的问题由用户决定自改、委托代改或豁免（豁免记入 `user_confirmations`）。
3. 每步完成后更新 run manifest：`current_step`、`last_passed_gate`、工件路径、`user_confirmations`（只记真实发生的用户决策）；vault 存在时顺带 `vault.py update-case`。
4. 交接字段要求见 [references/HANDOFF_CONTRACT.md](references/HANDOFF_CONTRACT.md)。

## 门禁命令速查

脚本自定位，任意工作目录可跑；`<dir>` = 本 skill 的 `scripts/` 目录：

```
python <dir>/run_phase_gates.py --gate research   --workspace . --manifest artifacts/run_manifest.md
python <dir>/run_phase_gates.py --gate prior-art  --workspace . --manifest artifacts/run_manifest.md
python <dir>/run_phase_gates.py --gate draft      --workspace . --manifest artifacts/run_manifest.md
python <dir>/run_phase_gates.py --gate review     --workspace . --manifest artifacts/run_manifest.md
python <dir>/run_phase_gates.py --gate deliver    --workspace . --deliver-dir "<交付目录>" --patent-title "<题名>" --manifest artifacts/run_manifest.md
python <dir>/run_phase_gates.py --gate all        --workspace . --manifest artifacts/run_manifest.md
```

prior-art 门禁支持领域自适应打分词表（解决换领域必挂的问题）：由 `patent-prior-art` 在检索时生成 `artifacts/prior_art/relevance_terms.json`，门禁自动采用；无此文件时退回内置 legacy 词表。

## 缓存复用（精简两级）

**初始化层**（长期复用）：`(template_source, reference_patent_source)` 的指纹未变 → 直接复用 `template_outline.txt`、`reference_patent_text.txt`、`template_rules.json`、`style_profile.md`；指纹变化、用户要求刷新或工件缺损才重跑 `patent-style`。命中与否记入 manifest（`initialization_reused`、`source_fingerprints`）。

**研究层**（短期复用）：`research_scope_key`（domain + topic + constraints）相同且工件生成 ≤ 30 天 → 直接复用 research pack；否则重跑。只记 `research_scope_key` 与 `research_reused: true/false` 两个字段。

单篇内容工件（题名、草稿、审查结果、背景包）**默认不跨 run 复用**；用户明确要求沿用时记入 `user_confirmations`。

## 宿主适配

本家族全部 skill 为宿主中立设计（参照 ponytail 模式）：正文只描述行为与能力优先级，不绑定特定宿主 API；门禁脚本为 stdlib-only Python，任何能执行 shell 的 agent 均可运行。涉及并行子代理的 skill（patent-research、patent-review）内置「并行 → solo 多轮」能力梯度，宿主不支持并行时自动降级，输出契约不变。
