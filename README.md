# patent-workflow：专利交底书 skill 家族

专利交底书全流程工具箱，`/patent` 一个入口路由全部能力。本仓库是**唯一真源**，改动后运行 `deploy.ps1` 同步生效。

由旧版单体 patent-workflow（6 个互相耦合的 skill、三处重复定义、强依赖外部 CLI）重构而来，2026-07 重构目标：职责单一、依赖可选、宿主中立。旧版完整备份在 `_backup_20260708/`。

## 家族结构（8 个 skill）

```
patent                总路由 + 全流程编排 + 门禁脚本 + run manifest
├── patent-research       调研（零依赖版：多子代理并行 + 宿主内置搜索）
├── patent-research-cli   调研（增强版：smart-search CLI 驱动，装了自动优先）
├── patent-prior-art      专利检索 + 验证 + 背景包/IPR 审查包
├── patent-style          模板解析 + 风格提取 + 初始化层缓存（一次初始化长期复用）
├── patent-draft          5 部分分块写作 + 附图三件套 + docx 出稿 + 交付检查
├── patent-review         四视角对抗审查（一致性/IPR/技术/语言），只审不改、汇报后用户决策
└── patent-deslop         专利文本去 AI 味（独立随叫随到）
```

共享真源（`skills/patent/references/`）：

| 文件 | 作用 |
|---|---|
| `search-protocol.md` | 数采两层能力模型（发现/验证），provider 分级与降档规则 |
| `research-pack-contract.md` | 两个 research skill 的统一产出契约 |
| `HANDOFF_CONTRACT.md` | 各步骤交接的最小字段 |
| `RUN_MANIFEST_TEMPLATE.md` | 运行清单模板 |

## 核心设计：依赖全部可选，数采能力不降

门禁只约束**产出质量**（证据条数/强来源数/CN-only/时效/候选数量），不约束用了哪些通道：

- 发现层：`smart-search` CLI（可选）→ 搜索 MCP（可选）→ **宿主内置搜索（兜底，恒可用）**
- 验证层：`smart-search fetch`（可选）→ 浏览器 MCP（可选）→ **宿主内置抓取（兜底，恒可用）**
- 发散/扩词由会话模型自行完成，无外部推理依赖
- 附图 `.drawio` 由模型直接生成 XML（零 CLI）；`.png` 渲染 `mmdc` 可用则用，否则明示降级
- 产出不达标的正确动作是**换词重检加大迭代**，不是要求装工具

裸机（无任何 CLI/MCP）可走通全流程；装了增强工具自动升档。`degraded_run` 只在兜底通道也失败或用户豁免门禁时为 true。

## 全流程管线

```
开局（首问领域 + manifest + 能力探测）
→ patent-style（冷启动才跑，否则复用缓存）
→ patent-research(-cli)     --gate research
→ 方向收敛（用户确认，第二处也是最后一处默认停顿）
→ patent-prior-art          --gate prior-art
→ patent-draft 写作段        --gate draft
→ patent-review             审查汇报 → 用户决策修改（自改/委托/豁免）→ 复审
                            （委托代改留痕过 --gate review）
→ patent-draft 导出段        --gate deliver
→ 交付完成
```

## 门禁命令

脚本自定位，任意工作目录可跑：

```bash
python ~/.claude/skills/patent/scripts/run_phase_gates.py --gate research   --workspace . --manifest artifacts/run_manifest.md
python ~/.claude/skills/patent/scripts/run_phase_gates.py --gate prior-art  --workspace . --manifest artifacts/run_manifest.md
python ~/.claude/skills/patent/scripts/run_phase_gates.py --gate draft      --workspace . --manifest artifacts/run_manifest.md
python ~/.claude/skills/patent/scripts/run_phase_gates.py --gate review     --workspace . --manifest artifacts/run_manifest.md
python ~/.claude/skills/patent/scripts/run_phase_gates.py --gate deliver    --workspace . --deliver-dir "<dir>" --patent-title "<title>" --manifest artifacts/run_manifest.md
```

prior-art 门禁自动采用 `artifacts/prior_art/relevance_terms.json`（由 patent-prior-art 按本轮领域生成的打分词表），解决旧版换领域打分失真的问题。

## 部署

**Claude Code**（本机）：

```powershell
pwsh -File deploy.ps1          # 同步 8 个 skill 到 ~/.claude/skills/
pwsh -File deploy.ps1 -DryRun  # 预览
```

**多宿主部署（Codex / Hermes 等）**：skill 正文为宿主中立纯指令（参照 ponytail 模式）——不绑定特定宿主 API，多子代理描述为「并行子代理 → solo 多轮」能力梯度，门禁脚本 stdlib-only Python。把 `skills/` 下各目录复制到对应宿主的技能/提示目录即可，无需改内容。

## 维护约定

1. **只改仓库，不直接改 `~/.claude/skills/`**——deploy 用 `/MIR` 镜像同步，目标端手改会被覆盖。
2. 每条规则只在一个 skill 里定义，其他位置引用；新增规则前先确认归属。
3. 改完跑 `deploy.ps1`；改了 Python 脚本先 `py_compile` 再部署。
4. 旧版 6 skill 的完整备份在 `_backup_20260708/`，可随时对照或回滚。
