---
name: smart-search
description: 通过本地 smart-search CLI 进行多源网络调研、文档检索、深度搜索。用于需要实时搜索、事实核查、URL 抓取、文档查询、深度调研的场景。
keywords: [search, web search, research, deep research, 搜索, 调研, 深度搜索, 资料, 查询, fetch, exa, zhipu, context7]
---

# Smart Search

通过本地 `smart-search` CLI 执行网络调研。skill 决定路由，CLI 执行搜索，JSON/Markdown 提供证据。

## 何时激活

- 用户说「搜一下」「查一下」「搜索」「调研」「帮我找」「look up」「search for」「research」
- 需要当前/实时网络信息（新闻、行情、最新文档）
- 需要事实核查或多源交叉验证
- 需要抓取指定 URL 的页面内容
- 需要查找库/框架/API 文档
- 用户说「深度搜索」「深度调研」「deep search」「deep research」
- 需要中文/国内资源搜索
- 小说写作中需要查阅历史、武术、文化等资料

## 前置检查

首次使用或不确定配置时：

```bash
smart-search doctor --format json
```

如果返回 `ok: false`，按 `error` 字段指引运行 `smart-search setup` 或 `smart-search config set KEY VALUE`。

## 核心命令速查

### 1. 快速搜索（默认首选）

广域搜索，获取综合回答 + 来源列表：

```bash
smart-search search "查询内容" --format json
smart-search search "查询内容" --extra-sources 2 --format json
smart-search search "查询内容" --validation balanced --timeout 90 --format json
```

- `--extra-sources N`：额外从 Tavily/Firecrawl 拉取候选来源（默认 0，建议 1-3）
- `--format content`：只输出回答正文，适合人类阅读
- `--format json`：结构化输出，适合 agent 解析
- `--timeout N`：超时秒数（默认 60）

### 2. 中文/国内搜索

中文内容、国内政策、公告、当前新闻优先用 Zhipu：

```bash
smart-search zhipu-search "中国AI政策最新动态" --count 5 --format json
smart-search z "武当太极拳源流" --format json
```

### 3. 文档/API/库检索

SDK、框架、API 文档优先用 Context7：

```bash
smart-search context7-library "react" "hooks" --format json
smart-search context7-docs "/facebook/react" "useEffect cleanup" --format json
smart-search c7 "langchain" "agent" --format json
```

### 4. 精准来源发现（Exa）

官方域名、论文、产品页、低噪发现：

```bash
smart-search exa-search "OpenAI Responses API" --num-results 5 --include-text --format json
smart-search exa-search "太极拳历史" --include-domains zh.wikipedia.org --num-results 5 --format json
smart-search exa-similar "https://example.com/article" --num-results 5 --format json
```

### 5. URL 抓取

抓取指定页面完整内容：

```bash
smart-search fetch "https://example.com/article" --format markdown
smart-search f "https://docs.python.org/3/library/asyncio.html" --format markdown
```

### 6. 站点结构探索

文档站点结构映射：

```bash
smart-search map "https://docs.example.com" --max-depth 1 --limit 50 --format json
```

### 7. 意图路由诊断

查看查询会被路由到哪个能力，不执行搜索：

```bash
smart-search route "React useEffect API docs" --format markdown
```

## 深度搜索模式

当用户要求「深度搜索」「深度调研」「deep research」「多源核查」时使用。

### 方式 A：离线规划 + 手动执行

先生成研究计划，再逐步执行：

```bash
smart-search deep "研究问题" --budget deep --format json
```

返回 `research_plan`，包含 `decomposition`（子问题分解）、`capability_plan`（能力规划）、`steps`（执行步骤）。然后按 `steps` 中的命令逐步执行。

### 方式 B：一键执行（推荐）

CLI 自动完成 规划→发现→抓取→缺口检查→综合：

```bash
smart-search research "研究问题" --budget deep --format json
smart-search research "研究问题" --budget standard --format markdown
smart-search rs "比较 Tavily 和 Firecrawl 的优劣" --budget deep --format json
```

- `--budget quick|standard|deep`：搜索深度
- `--fallback auto|off`：同能力内是否允许降级
- `--evidence-dir PATH`：证据文件保存目录

### 深度搜索证据策略

**fetch_before_claim**：关键结论必须有抓取的页面内容支撑。

1. 用 `search` / `zhipu-search` / `exa-search` 发现候选来源
2. 用 `fetch` 抓取关键页面
3. 只有抓取到的内容才能作为结论依据
4. 未抓取的来源标记为「未验证候选」

## Provider 路由选择指南

| 意图 | 首选命令 | 说明 |
|------|----------|------|
| 广域搜索 | `search` | 综合回答 + 来源，默认首选 |
| 中文/国内/政策/新闻 | `zhipu-search` | 中文语料覆盖好 |
| 文档/API/SDK/框架 | `context7-library` / `context7-docs` | 文档专用，优先于 Exa |
| 官方域名/论文/低噪 | `exa-search` | 精准域名过滤 |
| 相似页面发现 | `exa-similar` | 已知 URL → 相邻来源 |
| 页面抓取 | `fetch` | 支持 Tavily→Jina→Firecrawl 链 |
| 站点结构 | `map` | Tavily 站点地图 |
| 垂直领域（CVE/金融/法律） | `anysearch-search` | 实验性，先查 `anysearch-domains` |

## 超时重试策略

`search` 返回 `ok: false` + `error_type: network_error` + 含 `timed out` 时：

1. 最多重试 3 次，`--timeout 180 --extra-sources 1`，间隔 ~5 秒
2. 用 `--format json --output PATH` 保存每次结果
3. 首次 `ok: true` 即停止
4. 全部超时 → 降级为来源优先模式：`exa-search` 发现来源 → `fetch` 关键 URL → 标明 `source_mode: fallback`

## 小说写作调研模式

为小说写作查阅资料时的典型用法：

```bash
# 历史/文化背景
smart-search search "明朝厌胜术 民间巫术" --format content
smart-search zhipu-search "中国古代横练功夫 铁布衫 金钟罩" --count 10 --format json

# 武术/功法资料
smart-search search "传统武术横练功法训练方法" --extra-sources 2 --format json
smart-search exa-search "iron shirt qigong training" --include-text --format json

# 地理/风俗
smart-search zhipu-search "古代城西集市 市井生活" --format json

# 深度调研（例如世界观设定参考）
smart-search research "中国古代民间祟物传说 厌祟习俗 驱邪方法" --budget deep --format markdown
```

## 安全准则

- 不暴露 API key，`doctor` 输出会自动脱敏
- 不把 `extra_sources` 当作已验证证据，需 `fetch` 后才可引用
- 如果 `doctor` 或命令失败，报告错误和恢复步骤，不静默降级
- 用 CLI 的 `--timeout` 而非 shell 层面的 timeout 命令
- JSON 输出保持可解析，保留命令行和来源 URL

## 别名速查

| 完整命令 | 别名 |
|----------|------|
| `search` | `s` |
| `fetch` | `f` |
| `exa-search` | `exa`, `x` |
| `exa-similar` | `xs` |
| `zhipu-search` | `z`, `zp` |
| `context7-library` | `c7`, `ctx7` |
| `context7-docs` | `c7d`, `c7docs` |
| `deep` | `dr` |
| `research` | `rs` |
| `route` | `rt` |
| `map` | `m` |
| `doctor` | `d` |
| `config` | `cfg` |

## 相关 Skill

- `exa-search` — Exa MCP 直连（不通过 CLI）
- `deep-research` — Firecrawl + Exa 组合深度调研
- `brave-search` — Brave Search API
- `duckduckgo-search` — DuckDuckGo 免费搜索
