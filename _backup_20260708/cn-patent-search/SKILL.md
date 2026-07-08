---
name: cn-patent-search
description: 中国专利检索与验证技能。用于搜索并验证中国发明、实用新型、外观设计专利，输出可核验的专利号、标题、摘要、验证来源，以及可直接服务于交底书的“背景专利包 + 审查级 prior-art 包”。适用于专利检索、查新、背景技术准备、竞品专利分析、引用专利核验，以及 patent-workflow 中的背景专利验证与 IPR 审查证据准备。该技能是交底书流程中背景专利验证与 prior-art 审查包的唯一真源。
---

# CN Patent Search

## 角色定位

本技能负责：

1. 检索中国专利。
2. 验证专利是否真实存在。
3. 输出可直接进入交底书背景技术的背景专利包。
4. 按需输出可供 IPR 模拟审查使用的审查级 prior-art 包。
5. 给出与拟写方案之间的主要差异点和证据基础。

本技能不负责：

- 决定交底书正文结构。
- 决定参考专利的行文风格。
- 代替 `deep-research` 做行业创新调研。

## 核心原则

1. 未验证，不引用。
2. 背景专利至少返回专利号、标题、摘要。
3. 审查级 prior-art 包必须保留检索式、命中集合与证据粒度说明。
4. 优先使用权利要求或官方正文片段做对比；若只能用摘要，必须显式降级。
5. 本技能是背景专利验证与 prior-art 审查包唯一真源。

## 验证来源优先级

优先使用：

1. 国家知识产权局公开数据。
2. Google Patents。
3. 其他可核验公开平台。
4. 用户提供的官方 PDF，可作为补充验证来源。

如果用户提供 PDF，且能清晰识别公开/申请信息，可标记为 `document_verified`；若同时被公开数据库命中，可标记为 `verified`。

## 标准输出字段

每条可用专利至少包含：

- `title`
- `applicationNumber` 或 `publicationNumber`
- `abstract`
- `validationStatus`
- `verificationSource`

推荐补充：

- `publicationDate`
- `applicant`
- `sourceUrl`
- `usableAsBackground`
- `isClosestPriorArt`
- `evidenceGranularity`
- `titlePattern`

## 专利交底书模式输出契约

当服务于 `patent-workflow` 或专利交底书任务时，必须同时输出两层结果：

### A. 背景专利包

```json
{
  "pack_mode": "background_pack|full_review_pack",
  "backgroundPatentCount": 2,
  "background_patents": [
    {
      "title": "示例专利标题",
      "titlePattern": "一种……方法及系统",
      "publicationNumber": "CNxxxxxxxxx",
      "abstract": "摘要",
      "validationStatus": "verified",
      "verificationSource": "cnipa",
      "sourceUrl": "https://...",
      "usableAsBackground": true
    }
  ],
  "closest_prior_art": "CNxxxxxxxxx",
  "title_pattern_samples": [
    "一种……方法及系统",
    "一种……控制方法",
    "一种……评估系统"
  ],
  "major_differences": [
    "差异点 1",
    "差异点 2"
  ],
  "readyForBackgroundSection": true
}
```

### B. 审查级 prior-art 包

```json
{
  "pack_mode": "ipr_pack|full_review_pack",
  "search_query_log": [
    {
      "query": "检索式",
      "intent": "检索目的",
      "sources": ["cnipa", "google_patents"]
    }
  ],
  "review_patent_pool_count": 5,
  "review_patent_pool": ["CNxxxx1", "CNxxxx2"],
  "evidence_granularity": "claims_verified|abstract_only|mixed",
  "feature_to_prior_art_matrix": [],
  "novelty_evidence_table": [],
  "search_failures": [],
  "ipr_degraded_reason": "",
  "readyForIPRReview": true
}
```

强制规则：

1. 至少返回 2 篇已验证背景专利，否则 `readyForBackgroundSection` 必须为 `false`。
2. `background_patents` 必须是显式数组，不能只给数量而不交付可核验条目。
3. 默认构建 5 篇审查级对比文献池；若只能稳定拿到 3-4 篇，必须显式写明 `ipr_degraded_reason`。
4. 必须指出哪一篇是 `closest_prior_art`。
5. 必须给出与拟写方案之间的 `major_differences`。
6. 在交底书模式下，默认应补充 `title_pattern_samples`；如确实无法稳定提取，必须在输出中明确说明缺失原因，由下游手工补足命名参照。
7. 只有输出审查级 prior-art 包时，才强制要求 `search_query_log`、`feature_to_prior_art_matrix`、`novelty_evidence_table` 完整齐备。
8. 不得把未验证专利塞进背景技术或审查包凑数。
9. 若审查证据只能基于摘要，必须把 `evidence_granularity` 标记为 `abstract_only` 或 `mixed`，不得伪装成 claims 级对比。
10. 若历史模板、旧脚本或人工整理结果仍出现旧值 `abstract`，本技能在输出前必须归一化为 `abstract_only`，不得继续向 workflow 传播漂移枚举。

## 轻量快路径

为避免完整 IPR 包拖慢正文起草，本技能在专利 workflow 中默认支持两段式输出：

1. `background_pack`
   - 用于放行背景技术写作和正文起草。
   - 最小要求是：`background_patents`、`closest_prior_art`、`major_differences`、`readyForBackgroundSection = true`。
2. `ipr_pack`
   - 用于放行 `IPR 模拟审查`。
   - 最小要求是：`search_query_log`、`review_patent_pool`、`feature_to_prior_art_matrix`、`novelty_evidence_table`、`evidence_granularity`、`readyForIPRReview = true`。
3. 如一次性拿齐全部材料，可直接输出 `full_review_pack`。
4. 若只拿齐 `background_pack`，允许 workflow 先进入正文写作，但不得进入 IPR 模拟审查。

## 工作流

### Step 1：明确检索目标

确认：

- 技术领域。
- 应用场景。
- 是否用于交底书背景技术。
- 是否需要进一步服务 IPR 模拟审查。
- 是否有固定题目或固定方向。

### Step 2：构建检索式

组合：

- 核心技术词。
- 同义词。
- 应用场景词。
- 领域限定词。

并记录：

- `search_query_log`
- 每条检索式的意图
- 使用的平台或来源

### Step 3：执行检索

优先在官方或可核验平台执行搜索。

除背景专利外，需保留一组可供比对的审查级文献池，而不是只保留最终入选的 2 篇背景专利。

### Step 4：逐条验证

对拟输出专利至少做一种有效验证，并记录 `verificationSource`。

### Step 5：提取审查证据

对审查级 prior-art 包中的重点文献，尽量提取：

- 权利要求片段。
- 摘要关键句。
- 正文可定位片段。
- 证据粒度说明。

无法获取 claims 时，必须显式写明降级原因。

### Step 6：整理交底书背景专利包与审查包

输出：

1. 2 篇以上可写入背景技术的专利。
2. 最接近现有技术。
3. 主要差异点。
4. `background_patents` 显式条目数组。
5. 检索式日志。
6. 审查级对比文献池。
7. 特征对比矩阵与新颖性证据表。
8. 是否达到可写状态与可审状态。

## 验证状态定义

- `verified`：已被公开数据库或等效公开来源验证。
- `document_verified`：已被用户提供的官方 PDF 补充验证。
- `unverified`：尚未完成有效验证。

证据粒度建议使用且在 workflow 中应保持精确枚举一致：

- `claims_verified`
- `abstract_only`
- `mixed`

`unverified` 不得进入背景技术引用；`abstract_only` 不得被包装成高置信度 IPR 证据。

兼容说明：

- 旧值 `abstract` 仅允许作为历史输入兼容；标准输出一律使用 `abstract_only`。

## 与 patent-workflow 的交接

只有满足以下条件，才允许进入正文撰写：

1. 已输出 2 篇以上已验证背景专利。
2. 已输出 `background_patents` 显式数组。
3. 已明确 `closest_prior_art`。
4. 已明确 `major_differences`。
5. `readyForBackgroundSection = true`。

只有满足以下条件，才允许进入 IPR 审查：

1. 已输出 `search_query_log`。
2. 已输出 `review_patent_pool`。
3. 已输出 `feature_to_prior_art_matrix` 与 `novelty_evidence_table`。
4. 已明确 `evidence_granularity`。
5. 若 `review_patent_pool_count < 5`，已明确 `ipr_degraded_reason`。
6. `readyForIPRReview = true`。

当服务于完整 `patent-workflow` 时，默认目标是两包都齐，但两者不再强制处于同一关键路径：

1. 写作阶段以 `background_pack` 为门禁。
2. IPR 模拟审查阶段以 `ipr_pack` 为门禁。

若只满足背景专利包、不满足审查级 prior-art 包，则 `patent-workflow` 可以进入正文起草，但不得进入 IPR 模拟审查或宣告流程完整通过。

## 禁止事项

1. 禁止虚构专利号。
2. 禁止把无法核验的命中结果包装成可引用专利。
3. 禁止越权决定正文结构和风格。
4. 禁止在交底书模式下只给散点结果、不整理成背景专利包。
5. 禁止隐藏检索失败、抓取失败或 claims 缺失情况。
