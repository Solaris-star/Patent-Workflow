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

通道选择遵循 [../patent/references/search-protocol.md](../patent/references/search-protocol.md)：有 smart-search CLI 用 CLI（`zhipu-search` 中文检索 + `fetch` 验证优先），没有就用宿主内置搜索/抓取——门禁标准完全相同。

## 验证来源优先级

1. 国家知识产权局公开数据（CNIPA）
2. Google Patents
3. 其他可核验公开平台
4. 用户提供的官方 PDF（补充验证，标 `document_verified`）

验证状态：`verified`（公开数据库验证）/ `document_verified`（用户 PDF 验证）/ `unverified`（禁止进入任何输出包）。
证据粒度：`claims_verified` / `abstract_only` / `mixed`（历史旧值 `abstract` 一律归一化为 `abstract_only`）。

### 验证源 × 通道可达性（实际执行指引）

| 验证源 | 页面性质 | 可达通道 |
|---|---|---|
| Google Patents（`patents.google.com/patent/CN…`） | 静态，可直接抓取 | 任意验证层通道均可，含裸机内置抓取兜底——**无浏览器通道时的主力验证源**，CN 专利数据齐全（号码/日期/摘要/claims） |
| CNIPA 官方检索系统 | 动态页 + 可能需验证码 | 仅浏览器类 MCP（playwright / browser-cdp）可达；**无浏览器通道时不要反复尝试直接抓取**，改用 Google Patents 验证并如实记录 `verificationSource: google_patents` |
| 其他专利平台摘要页 | 多为静态 | fetch 类通道可达，作补充核验 |

发现层同理：检索式优先交给可用的中文检索通道（smart-search 的 `zhipu-search` 对 CN 专利覆盖好）；裸机时用内置搜索加 `site:patents.google.com` 等限定词提高专利命中率。

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

对每条检索式执行检索，把命中专利汇入候选池。**候选不足或相关性弱时自动换词重检**（同义词、场景词、申请人、分类号辅助词、近义应用域），不得拿低相关专利凑数，不得把新闻/博客/产品页当专利候选——非专利页面只能作外围证据（`is_auxiliary: true`）辅助扩词与背景判断。

### Step 4：逐条验证

每条拟输出专利至少完成一种有效验证（抓取专利库详情页确认号码、标题、日期一致），记录 `verificationSource` 与 `sourceUrl`。虚构专利号 = 最高违规。

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
