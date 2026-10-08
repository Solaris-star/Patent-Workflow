---
name: patent-oa
description: |
  审查意见通知书（OA）答复辅助。解析国知局审查意见、拉取对比文件全文、产出特征对比表、
  三步法差异论证草案与权利要求修改建议——定位为给专利代理师/IPR 的技术论证工作稿，
  不是正式法律文件。
  触发方式：/patent-oa、「审查意见」「OA答复」「答复通知书」「驳回」「对比文件 D1」
  「三步法」「创造性争辩」。独立于写作主管线（老案新事件），有 vault 时回链案件状态。
---

# patent-oa：审查意见答复辅助

**定位与免责（硬规则）**：示例 JSON 仅示意字段，所有示例值均为虚构占位符。本 skill 产出**技术论证工作稿**，每份输出头部带固定声明（见 [references/OA_REPLY_TEMPLATE.md](references/OA_REPLY_TEMPLATE.md)）：*本工作稿仅为技术论证辅助材料，不构成法律意见；答复定稿、期限核算与提交以专利代理师为准。* 答复期限只**转述**通知书记载日期，不做推定计算。

## 工作区与 oa_manifest（老案新事件）

下方 manifest 中的题名、编号、法律条款标记和段落号均为**明确合成占位**，不来自真实申请人、客户、案件或专利文本。真实值只能从用户授权的案件材料提取。

OA 是已交付案件的新事件——**不复活已关闭的写作 run**。工作区：

- 原写作 workspace 还在 → 在其中新建 `artifacts/oa/<oa_id>/`（顺手可用 facts_ledger 与五 part 原稿作论证素材）；
- 不在 → 任意新目录同样可跑（最少只需交底书/公开文本 + 通知书）。

状态用独立 `oa_manifest.json` 管理（不建 run manifest、不挂五大 gate）：

```json
{
  "doc_type": "oa_manifest",
  "synthetic_example": true,
  "oa_id": "OA-SYN-0001",
  "application_number": "SYN-APP-0001",
  "patent_title": "【合成示例】任务状态对齐方法",
  "notice_type": "第一次审查意见通知书（合成示例）",
  "notice_date": "YYYY-MM-DD",
  "reply_deadline_as_stated": "YYYY-MM-DD（仅为占位，按通知书记载转述）",
  "rejected_claims": [{"claim": 1, "articles": ["SYN-LEGAL-REF-01"]}],
  "cited_documents": [{
    "id": "D1", "publication_number": "SYN-PUB-0001",
    "fulltext_status": "abstract_only",
    "source": "user_pdf",
    "examiner_cited_paragraphs": ["SYN-PAR-0001"]
  }],
  "status": "parsed",
  "vault_case_id": null,
  "sensitive_map_path": null
}
```

有 vault 时回链：开始时 `update-case <id> --status oa_pending`，工作稿移交后 `--status oa_replied`；无 vault 零影响。

**涉密血统继承（硬规则）**：原案 run manifest 可定位且声明了 `sensitive_map_path` → oa_manifest 必须继承该路径引用；原 manifest 不可得但案件疑似 mine 血统（vault 案件记录、用户告知）→ 先向用户确认 map 位置再继续。Step 7 移交前，对全部对外产物（工作稿/feature_matrix/claim_amendment/docx）运行 `validate_sanitize.py --map <该路径> --files …` 前，先请用户显式重选/确认与 oa_manifest 完全一致的路径；不得只依据旧 manifest 自动读取。validator 在原位置读取所选 map，不复制；未确认或路径不一致时停止，不运行 validator。OA 工作稿同样会离开本机、不受 deliver 门禁保护，所以需完成此项本地复核。

## Step 1：解析通知书

输入：通知书 PDF/文本（使用宿主实际可用的 PDF 读取器；否则仅在本机已安装 pypdf 时本地解析。本仓库不安装该依赖；都不可用时标记不可用并请求可访问的本地文本，不自动安装或上传文件）。提取 → notice_extract.md：

通知书类型与次数、发文日、驳回条款、引用对比文件及审查员对区别特征的评述逻辑链；只保留最短必要且已获授权的摘录并记录通知书页码/段落。未获准或无法核对时准确转述并标记待核，不复制整段通知书。

## Step 2：拉取对比文件全文

复用 patent-prior-art 的来源通道（仅当本次宿主确实提供且用户请求时使用）：案件派生查询、通知书或材料发送给外部服务前，必须按 search-protocol 取得本次明确确认。

1. CNIPA 脚本：`python <patent-skill-dir>/scripts/cnipa/cnipa_epub_search.py <公开号>`
2. playwright MCP / browser-cdp 现场操作国知局详情页
3. `patents.google.com/patent/<公开号>/zh` 静态抓取（说明书全文通常可得）
4. 用户提供官方 PDF（`user_pdf`）

落盘 `d_files/d1_<公开号>.md`。**evidence_granularity 纪律平移**：只拿到摘要时 `fulltext_status: abstract_only`，对应论证显式降置信，禁止伪装 claims 级对比；拿不到时 `missing` 并向用户请求 PDF。

## Step 3：特征对比表

feature_matrix.json — 本申请权利要求逐特征 × 各 D 文件（与 ipr_pack 的 feature_to_prior_art_matrix 同构；下方所有值与段落定位均为合成占位）。

```json
{"matrix": [{
  "claim": 1, "feature_id": "F-SYN-001", "feature": "SYN-FEATURE-001",
  "d1": {"disclosed": "partial", "paragraphs": ["SYN-PAR-001"], "note": "synthetic placeholder"},
  "d2": {"disclosed": "no"},
  "examiner_position": "synthetic placeholder",
  "our_position": "contest",
  "contest_reason": "synthetic placeholder"
}]}
```

每格判断必须回指 D 文件具体段落号——**禁止空对空**；`abstract_only` 的 D 文件只能给 partial/unknown 级判断。

## Step 4：论证草案（answering 的主战场）

按驳回类型写 `argument_draft.md`（方法论细则见 [references/oa-argument-guide.md](references/oa-argument-guide.md)）：

- **创造性（22.3，三步法）**：(a) 最接近现有技术的确定——同意审查员选择或有据质疑；(b) 区别特征与**实际解决的技术问题**重新界定（审查员常把技术问题上位化过宽，把问题拉回说明书记载的具体效果）；(c) 非显而易见性——D1+D2 结合启示是否真实存在（技术领域、解决问题、作用是否一致）、结合障碍、预料不到的技术效果。
- **新颖性（22.2）**：逐特征单独对比，一个特征未被单篇披露即不丧失新颖性；抓「隐含公开」的过度解读。
- **充分公开/支持（26.3/26.4）**：回指说明书具体段落证明记载充分。

每条论证：结论 + D 文件段落回指 + 本申请说明书段落回指。

## Step 5：答复预演（对抗自检）

仓库只保存 agents/patent-consistency-auditor.md 和 agents/patent-tech-reviewer.md 两份 reviewer 提示词，不会自动部署或启动代理。它们分别提供文档一致性和技术可实现性视角，不是 OA 专属 examiner agent。宿主实际支持两路独立 reviewer、且用户授权的最少必要材料可分别提供时，可以并行；否则在当前会话按两种视角顺序复核并注明单会话。审查员视角是分析方法，不表示存在额外的 examiner 代理。提供材料时仅限本次已授权的通知书必要摘录、对比文件相关段落、feature matrix 和论证段落；向外部服务传送仍须先确认具体内容、目的地和用途。

## Step 6：权利要求修改建议

在 claim_amendment.md 中记录修改方向（如合并从属权利要求或补入说明书已有特征）、修改前后对照，以及每处修改对应的原始说明书依据段落（专利法第 33 条的超范围风险须由代理师判断）。

## Step 7：汇总移交

按 OA_REPLY_TEMPLATE 汇总 `OA答复要点工作稿.md`（可选 docx 导出）。移交清单：工作稿 + feature_matrix + d_files 全文 + 未决问题列表（需要代理师法律判断的点单独列出）。

## 禁止事项

1. 不给「必然授权/必然驳回」结论；不推定答复期限。
2. D 文件无全文时不做 claims 级披露断言。
3. 禁止编造 D 文件段落号与内容——所有段落引用必须来自已抓取文本。
4. 技术问题重界定不得越过本申请说明书的记载范围。
