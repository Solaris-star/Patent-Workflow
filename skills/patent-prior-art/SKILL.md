---
name: patent-prior-art
description: |
  中国专利检索与验证，交底书背景专利包与审查级 prior-art 包的唯一真源。
  搜索并核验中国发明/实用新型/外观设计专利，输出可核验的专利号、标题、摘要、
  验证来源，产出背景专利包（放行写作）与 IPR 审查包（放行模拟审查）。
  触发方式：/patent-prior-art、「查新」「专利检索」「背景专利」「prior art」
  「找对比文献」「核验这个专利号」。可独立使用，也被 patent 全流程编排调用。
---

# patent-prior-art：专利检索、验证与审查包

本 skill 是背景专利验证与 prior-art 审查包的唯一真源。核心原则：**未验证，不引用**。

**检索主路径：浏览器自动化直上国知局官方检索系统**（playwright MCP / browser-cdp）——官方源检索+验证一步到位，最简单有效。无浏览器通道时才落到搜索+抓取兜底（协议见 [../patent/references/search-protocol.md](../patent/references/search-protocol.md) 的对象特化例外）。门禁标准与走哪条通道无关。

## 验证来源优先级

1. 国家知识产权局公开数据（CNIPA）
2. Google Patents
3. 其他可核验公开平台
4. 用户提供的官方 PDF（补充验证，标 `document_verified`）

验证状态：`verified`（公开数据库验证）/ `document_verified`（用户 PDF 验证）/ `unverified`（禁止进入任何输出包）。
证据粒度：`claims_verified` / `abstract_only` / `mixed`（历史旧值 `abstract` 一律归一化为 `abstract_only`）。

### 检索通道优先级

| 优先级 | 通道 | 说明 |
|---|---|---|
| **1（主路径首选）** | **内置 CNIPA 检索脚本** | `python <patent-skill-dir>/scripts/cnipa/cnipa_epub_search.py 词1 词2 …`（脚本化 Playwright 查询国知局官方公布站 epub.cnipa.gov.cn）。stdout 单行 `EPUB_HITS_JSON:` + JSON 数组（标题/公开号/摘要，按公开号去重）。检索词一段一查按空白拆分，语义化检索单位须在生成命令前拆好。官方源，**检索即验证**（`verificationSource: cnipa`）。前置：`pip install playwright` + `python -m playwright install chromium`；WAF 等待可调 `EPUB_WAF_MAX_WAIT_SEC` |
| 2（主路径备用） | 浏览器自动化现场操作国知局 | 脚本不可用（未装 playwright python 依赖）但有 playwright MCP / browser-cdp 时：打开国知局检索入口，输入检索式 → 收集命中 → 详情页取全字段，同为 `verificationSource: cnipa` |
| 3（兜底） | 搜索发现 + Google Patents 验证 | 无任何浏览器能力时：smart-search 通用入口或宿主内置搜索发现候选（`site:patents.google.com` 限定词提高命中率），抓取 `patents.google.com/patent/CN…` 静态页逐条核验（`verificationSource: google_patents`） |

执行要点：优先级 1 探测 = 脚本文件存在且 `python -c "import playwright"` 成功；遇验证码/WAF 长阻塞向用户说明（browser-cdp 复用登录态可基本免人机验证），不可静默跳过官方源——降级到 3 时必须在 `search_failures` 记录原因。

## 检索工作流

### Step 1：明确目标

从 run manifest 或用户请求读取：技术领域、应用场景、`selected_direction` / 固定题目、是否需要 IPR 审查包。

### Step 2：生成检索式与打分词表

1. 组合核心技术词 × 同义词 × 应用场景词 × 领域限定词，中文优先，必要时中英混合；每条检索式记录意图与目标平台（进 `search_query_log`）。
2. **落盘领域自适应打分词表** `artifacts/prior_art/relevance_terms.json`（门禁自动采用，解决换领域打分失真）：
   ```json
   {
     "project_terms": ["<应用域/场景词，如：自动驾驶、接管、人机共驾>"],
     "ai_terms": ["<技术手段词，如：大模型、强化学习、多模态>"],
     "constraint_terms": ["<本方向区别特征词，如：意图预测、置信度仲裁>"],
     "negative_terms": ["<明显无关的邻域词>"],
     "weights": {"project": 18, "ai": 18, "constraint": 18, "negative": 10, "cn_bonus": 10}
   }
   ```

### Step 3：检索与扩池

按「检索通道优先级」执行：首选 CNIPA 脚本逐组检索词跑 `cnipa_epub_search.py` 并解析 `EPUB_HITS_JSON`（摘要缺失的重点候选再补抓详情）；脚本不可用时浏览器现场操作国知局；最后才落搜索 + Google Patents 兜底。目标字段：title / 申请号 / 公开号 / 日期 / 摘要 / 申请人。

**候选不足或相关性弱时自动换词重检**（同义词、场景词、申请人、分类号辅助词、近义应用域），不得拿低相关专利凑数，不得把新闻/博客/产品页当专利候选——非专利页面只能作外围证据（`is_auxiliary: true`）辅助扩词与背景判断。

### Step 4：验证核对

- 主路径（国知局）：详情页字段即官方验证，标 `verificationSource: cnipa`，附详情页 `sourceUrl`。
- 兜底路径：每条拟输出专利抓取 Google Patents 详情页核对号码、标题、日期一致后标 `verificationSource: google_patents`。

虚构专利号 = 最高违规。

### Step 5：落盘两个门禁工件

**候选池** `artifacts/prior_art/phase_04_patent_candidate_pool.json`：

```json
{ "patents": [ {
    "title": "一种……方法及系统",
    "publicationNumber": "CN119XXXXXXA",
    "applicationNumber": "",
    "filingDate": "2025-06-01",
    "publicationDate": "2025-09-12",
    "abstract": "……",
    "keywords": ["…"],
    "scenario": "…",
    "url": "https://…",
    "applicant": "…",
    "validationStatus": "verified",
    "verificationSource": "cnipa"
} ] }
```

**证据包** `artifacts/prior_art/phase_04_evidence_pack.json`：

```json
{
  "pack_type": "evidence_pack",
  "phase": "phase_04",
  "patent_candidate_pool_path": "artifacts/prior_art/phase_04_patent_candidate_pool.json",
  "final_relevant_patents": ["CNxxx1", "CNxxx2", "CNxxx3", "CNxxx4", "CNxxx5"],
  "search_trace": {
    "patent_search_queries": [{"query": "…", "intent": "…", "sources": ["cnipa"]}],
    "final_relevant_patent_count": 5
  },
  "evidence": [
    {"evidence_id": "PE1", "url": "https://…", "excerpt": "专利页原文摘录≥50字符…", "is_auxiliary": false},
    {"evidence_id": "AX1", "url": "https://…", "excerpt": "行业文章摘录（外围证据）…", "is_auxiliary": true}
  ],
  "evidence_alignment": [
    {"claim": "本方案区别特征X未被现有技术披露", "evidence_ids": ["PE1", "AX1"]}
  ]
}
```

门禁硬标准（`--gate prior-art` 自动裁决）：候选池 CN-only、时效 ≤ 1.5 年、相关分达阈、`finalRelevantPatents ≥ 5`；证据包 `evidence_alignment ≥ 3` 且每条至少引用 1 条非辅助专利证据。未过 → 回到 Step 3 换词重检。

### Step 6：产出交接包

两包均落盘（跨会话不蒸发；下游 review/oa 按固定路径读取）：`artifacts/prior_art/phase_05_background_pack.json` 与 `artifacts/prior_art/phase_05_ipr_pack.json`。

**背景专利包 background_pack**（放行写作的门禁）：

- `background_patents`：≥ 2 篇已验证专利的显式数组（title / titlePattern / publicationNumber / abstract / validationStatus / verificationSource / sourceUrl / usableAsBackground）
- `closest_prior_art`：最接近的现有技术（必须指明哪一篇）
- `major_differences`：拟写方案与现有技术的主要差异点
- `title_pattern_samples`：题名模式样例（如「一种……方法及系统」），无法提取时说明原因
- `readyForBackgroundSection: true`（不满足 ≥ 2 篇已验证时必须为 false）

**审查级 prior-art 包 ipr_pack**（放行 IPR 模拟审查的门禁）：

- `search_query_log`：完整检索式日志
- `review_patent_pool`：默认 5 篇对比文献池；只能稳定拿到 3-4 篇时显式写 `ipr_degraded_reason`
- `feature_to_prior_art_matrix`：特征对比矩阵
- `novelty_evidence_table`：新颖性证据表
- `evidence_granularity`：`claims_verified` / `abstract_only` / `mixed`——只能拿到摘要时必须如实降级标注，禁止伪装成 claims 级对比
- `readyForIPRReview: true`

两包解耦：只齐 background_pack 时 workflow 可进入正文写作，但不得进入 IPR 模拟审查；一次拿齐则输出 `full_review_pack`。

## 禁止事项

1. 禁止虚构专利号；禁止把无法核验的命中包装成可引用专利。
2. 禁止把新闻/博客/产品页/论坛页写入最终专利候选。
3. 禁止隐藏检索失败、抓取失败或 claims 缺失。
4. 禁止越权决定正文结构与风格（那是 patent-style / patent-draft 的职责）。
5. 禁止 `unverified` 条目进入背景技术；禁止 `abstract_only` 证据伪装高置信 IPR 证据。
