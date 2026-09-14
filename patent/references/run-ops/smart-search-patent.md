# smart-search 专利调研真值

## 命令真相（勿抄旧文档）

| 想做的事 | 正确命令 | 注意 |
|---|---|---|
| 规划拆题 | `smart-search deep "..." --budget deep --format json` | **不执行** search/fetch |
| 真搜 | `smart-search search "..." --parallel --extra-sources 5 --format json --timeout 180` | 开 grok+gemini |
| 抓正文 | `smart-search fetch "<url>" --format markdown` | 依赖 Tavily 链；挂了换通道 |
| 勿用 | `smart-search research` | 部分版本 invalid choice |

## 要证据必有 URL

1. 查询正文写死：每个结论附可点击原文 URL / `patents.google.com/patent/CN...`
2. 若 `sources=[]` 仅有 `content`：从 content 抽 URL，或换词重搜
3. 入 research pack 前必须抓到 ≥50 字 excerpt（fetch_before_claim）

## fetch 失败兜底

- jina：`https://r.jina.ai/<url>`
- arXiv：export API / ar5iv html
- 专利：Google Patents 页面 + jina

禁止把空 fetch 或未验证摘要写进 `evidence[]`。

## 专利检索补充

- CNIPA 脚本需 playwright chromium；缺浏览器时降级 Google Patents 浏览器检索
- prior-art 门禁：CN-only、≤1.5 年、相关分阈值、≥5 篇 final
