---
name: patent-research-cli
description: |
  专利创新点调研（smart-search CLI 增强版）。用本机 smart-search CLI 的多源聚合与
  一键深度调研（规划→发现→抓取→综合）完成创新方向挖掘，速度快、来源广。
  触发方式：/patent-research-cli、「用 smart-search 调研专利」，或由 patent 路由在
  探测到 CLI 可用时自动选择。前置条件：本机已安装 smart-search CLI；
  不可用时立即移交 patent-research（零依赖版），产出契约完全一致。
---

# patent-research-cli：创新点调研（smart-search 版）

与 `patent-research` 共享唯一产出真源 [../patent/references/research-pack-contract.md](../patent/references/research-pack-contract.md)。本 skill 只是执行引擎不同：多源发现与抓取由 smart-search CLI 完成。

## Step 0：前置探测（一次）

```bash
smart-search doctor --format json
```

- 命令不存在或 `ok: false` 且无法按 `error` 指引快速修复 → **立即移交**：改用 `patent-research` 执行本次调研，并在 run manifest 记录 `fallback_actions: smart-search unavailable -> patent-research`。不重试、不要求用户安装。

## Step 1-3：范围确认、主题发散、问题拆分

与 `patent-research` 的 Step 1-3 完全相同（发散由主模型完成；≥ 8 个研究问题）。

## Step 4：CLI 调研执行

按问题类型选命令（全部 `--format json`，超时用 CLI 的 `--timeout` 而非 shell 层超时）：

| 场景 | 命令 |
|---|---|
| 一键深度调研（首选） | `smart-search research "<主题+核心问题>" --budget deep --format json --evidence-dir artifacts/research/evidence` |
| 中文/国内政策/行业动态 | `smart-search zhipu-search "<查询>" --count 8 --format json` |
| 广域补充 | `smart-search search "<查询>" --extra-sources 2 --format json` |
| 精准域名/论文/官方页 | `smart-search exa-search "<查询>" --num-results 5 --include-text --format json` |
| 关键页面正文抓取 | `smart-search fetch "<URL>" --format markdown` |

执行策略：

1. 优先跑一次 `research --budget deep` 覆盖主线问题；其 `evidence` 结果直接作为证据候选。
2. 对未覆盖的研究问题用 `zhipu-search` / `search` / `exa-search` 定向补查；关键结论来源必须 `fetch` 正文（fetch_before_claim）。
3. 超时处理：`error_type: network_error` 且含 `timed out` → 最多重试 3 次（`--timeout 180 --extra-sources 1`），全失败则该查询降级为 `exa-search` 发现 + `fetch` 直读，记 `channel_failures`。
4. CLI 中途连续失败 2 次 → 剩余问题整体移交 `patent-research` 的调研轮次完成，已获证据保留。

## Step 5：汇总与收敛

与 `patent-research` 的 Step 5 完全相同：去重 → 补齐 ≥ 8 条证据 → 收敛 2-3 个方向 → 落盘 `artifacts/research/phase_02_research_pack.json` → 输出汇报层 Markdown → 跑 `--gate research` 门禁。

注意：`smart-search` 返回的 `extra_sources` 与未 `fetch` 的搜索摘要不得直接计入 `evidence[]`，需抓取正文后方可入证（契约的 excerpt 必须来自已抓取内容）。

## 禁止事项

与 `patent-research` 完全一致；另加：

- 禁止暴露 API key（doctor 输出已脱敏，原样转述即可）。
- 禁止静默降级——任何 CLI 失败都要在汇报层 `channel_failures` / `fallback_actions` 里可见。
