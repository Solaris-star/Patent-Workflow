---
name: patent-research-cli
description: |
  专利创新点调研（smart-search CLI 增强版）。用本机 smart-search CLI 的多源聚合与
  「deep 规划 → 按计划执行搜索/抓取」完成创新方向挖掘，速度快、来源广。
  触发方式：/patent-research-cli、「用 smart-search 调研专利」，或由 patent 路由在
  探测到 CLI 可用时自动选择。前置条件：本机已安装 smart-search CLI；
  不可用时立即移交 patent-research（零依赖版），产出契约完全一致。
---

# patent-research-cli：创新点调研（smart-search 版）

与 `patent-research` 共享唯一产出真源 [../patent/references/research-pack-contract.md](../patent/references/research-pack-contract.md)。本 skill 只是执行引擎不同：多源发现与抓取由 smart-search CLI 完成。

## 核心铁律（本宿主）

1. **`deep` 只出计划，不联网、不产出证据**。禁止把 `deep` 输出当 research pack。
2. **必须先 `deep`，再按计划逐步 `search` / `fetch`**。这是发挥 smart-search 的正确用法。
3. **学术 + 社媒双轨缺一不可**（尤其 X/Twitter 近期讨论与真实需求）。只有论文/报告、没有近期社媒痛点 = 调研不合格，需补跑。
4. 本机 CLI **没有** `research` / `route` 子命令。正确命令见下表。

## Step 0：前置探测（一次）

```bash
smart-search doctor --format json
```

- 命令不存在或关键 provider 全挂且无法快速修复 → **立即移交** `patent-research`，manifest 记 `fallback_actions: smart-search unavailable -> patent-research`。

## Step 1-3：范围确认、主题发散、问题拆分

与 `patent-research` 的 Step 1-3 完全相同（发散由主模型完成；≥ 8 个研究问题）。

问题拆分时**强制覆盖四类 + 社媒需求类**：

1. 行业现状/趋势  
2. 技术基线（论文/标准/产品）  
3. 痛点与机会空隙  
4. 可专利化差异预判  
5. **近期社媒/社区真实吐槽与需求**（X、论坛、产品社区；默认 3–6 个月）

## Step 4：CLI 调研执行（deep 计划 → 执行）

### 4.1 命令真表（以本机 CLI 为准）

| 场景 | 命令 | 注意 |
|---|---|---|
| 离线研究计划（必须先做） | `smart-search deep "<主题+核心问题>" --budget deep --format json --evidence-dir artifacts/research/evidence` | **只出计划**；不支持 `--timeout` |
| 按计划主搜 | `smart-search search "<查询>" --parallel --extra-sources 5 --format json --timeout 180` | 短英文查询更稳；要 URL 时 query 写明 “with source URLs” |
| 社媒/X 专搜 | `smart-search search "site:x.com OR site:twitter.com <topic> pain OR complaint OR need 2025 OR 2026 with source URLs" --parallel --extra-sources 5 --format json --timeout 180` | 至少 2 组 X/社媒查询；失败记 `channel_failures` 并换词重试 |
| 抓正文 | `smart-search fetch "<URL>" --format markdown` | fetch 空时 curl / `https://r.jina.ai/<url>` 兜底 |
| 源优先发现（可选） | `smart-search exa-search "..."` / `zhipu-search` | 仅当 search 路由效果差时用 |

### 4.2 执行策略（强制顺序）

1. **Deep 规划**：跑一次 `deep --budget deep`，落盘 `artifacts/research/deep_plan.json`。
2. **改写计划为可执行查询清单**（主模型完成）：
   - 每个子问题 ≥ 1 条学术/行业查询 + 全盘 ≥ 2 条 X/社媒查询
   - 查询要短、可检索，避免超长中文堆砌
3. **按清单执行 `search`**：优先 `--parallel --extra-sources 5 --timeout 180`。
4. **关键来源必须 `fetch` 正文**（fetch_before_claim）；未抓正文的摘要不得进 `evidence[]`。
5. **社媒证据门槛**：`evidence[]` 中至少 2 条来自 X/Twitter 或明确社媒讨论页（可用 L2/L3，但必须有 URL + ≥50 字 excerpt + date/freshness）。
6. 超时：`timed out` → 最多重试 3 次（`--timeout 180 --extra-sources 1`）；仍失败记 `channel_failures`。
7. CLI 连续失败 2 次 → 剩余问题移交 `patent-research`，已获证据保留。

### 4.3 证据配比建议

- 学术/标准/官方博客：≥ 4  
- 行业分析/产品工程文：≥ 2  
- **X/社媒真实需求与吐槽：≥ 2**  
- 合计 ≥ 8，且支撑「现状/痛点」的条目优先 `fresh`/`valid`

## Step 5：汇总与收敛

与 `patent-research` 的 Step 5 完全相同：去重 → 补齐证据 → 收敛 2-3 个方向 → 落盘 `artifacts/research/phase_02_research_pack.json` → 输出汇报层 Markdown → 跑 `--gate research`。

汇报层 `Channels` 必须写清：

- `deep_plan_path`
- `academic_queries` / `social_queries` 数量
- `channel_failures` / `fallback_actions`

候选方向用白话：**场景 → 系统做什么 → 输出什么**。禁止「不是 A 而是 B」。

## 禁止事项

与 `patent-research` 完全一致；另加：

- 禁止把 `deep` 计划误写成已完成调研。
- 禁止只用学术源、跳过 X/社媒轨。
- 禁止使用不存在的子命令：`research`、`route`。
- 禁止暴露 API key（doctor 输出已脱敏，原样转述即可）。
- 禁止静默降级——任何 CLI 失败都要在汇报层可见。
