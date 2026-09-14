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

**定位与免责（硬规则）**：本 skill 产出**技术论证工作稿**，每份输出头部带固定声明（见 [references/OA_REPLY_TEMPLATE.md](references/OA_REPLY_TEMPLATE.md)）：*本工作稿仅为技术论证辅助材料，不构成法律意见；答复定稿、期限核算与提交以专利代理师为准。* 答复期限只**转述**通知书记载日期，不做推定计算。

## 工作区与 oa_manifest（老案新事件）

OA 是已交付案件的新事件——**不复活已关闭的写作 run**。工作区：

- 原写作 workspace 还在 → 在其中新建 `artifacts/oa/<oa_id>/`（顺手可用 facts_ledger 与五 part 原稿作论证素材）；
- 不在 → 任意新目录同样可跑（最少只需交底书/公开文本 + 通知书）。

状态用独立 `oa_manifest.json` 管理（不建 run manifest、不挂五大 gate）：

```json
{
  "doc_type": "oa_manifest",
  "oa_id": "OA-<申请号>-<次数>",
  "application_number": "…",
  "patent_title": "…",
  "notice_type": "第一次审查意见通知书",
  "notice_date": "（转述通知书记载）",
  "reply_deadline_as_stated": "（仅转述，不推定）",
  "rejected_claims": [{"claim": 1, "articles": ["A22.3"]}],
  "cited_documents": [{
    "id": "D1", "publication_number": "CN…A",
    "fulltext_status": "fetched|abstract_only|user_pdf|missing",
    "source": "cnipa|google_patents|user_pdf",
    "examiner_cited_paragraphs": ["[0032]-[0041]"]
  }],
  "status": "parsed|d_files_ready|matrix_done|argued|red_teamed|handed_to_attorney",
  "vault_case_id": null,
  "sensitive_map_path": null
}
```

有 vault 时回链：开始时 `update-case <id> --status oa_pending`，工作稿移交后 `--status oa_replied`；无 vault 零影响。

**涉密血统继承（硬规则）**：原案 run manifest 可定位且声明了 `sensitive_map_path` → oa_manifest 必须继承该字段；原 manifest 不可得但案件疑似 mine 血统（vault 案件记录、用户告知）→ 先向用户确认 map 位置再继续。继承了 map 的 OA，Step 7 移交前对全部对外产物（工作稿/feature_matrix/claim_amendment/docx）跑 `validate_sanitize.py --map <该路径> --files …`，命中即回改——OA 工作稿同样会离开本机，不受 deliver 门禁保护，这一步就是它的替代闸。

## Step 1：解析通知书

输入：通知书 PDF/文本（宿主 PDF 能力优先，`python -m pypdf` 兜底）。提取 → `notice_extract.md`：

通知书类型与次数、发文日、**驳回条款**（专利法 22.2 新颖性 / 22.3 创造性 / 26.3 充分公开 / 26.4 支持 / 2.2 客体等）、**引用对比文件**（D1/D2/D3 公开号 + 审查员引用的具体段落号）、审查员对区别特征的认定与评述逻辑链（逐条原文摘录，后续逐条回应）。

## Step 2：拉取对比文件全文

复用 patent-prior-art 的三级通道（优先级与纪律照搬）：

1. CNIPA 脚本：`python <patent-skill-dir>/scripts/cnipa/cnipa_epub_search.py <公开号>`
2. playwright MCP / browser-cdp 现场操作国知局详情页
3. `patents.google.com/patent/<公开号>/zh` 静态抓取（说明书全文通常可得）
4. 用户提供官方 PDF（`user_pdf`）

落盘 `d_files/d1_<公开号>.md`。**evidence_granularity 纪律平移**：只拿到摘要时 `fulltext_status: abstract_only`，对应论证显式降置信，禁止伪装 claims 级对比；拿不到时 `missing` 并向用户请求 PDF。

## Step 3：特征对比表

`feature_matrix.json`——本申请权利要求逐特征 × 各 D 文件（**与 ipr_pack 的 feature_to_prior_art_matrix 同构**，为 Step 5 复用 agent 铺路；原案 workspace 还在时可直接读 `artifacts/prior_art/phase_05_ipr_pack.json` 作底稿对照）：

```json
{"matrix": [{
  "claim": 1, "feature_id": "F1", "feature": "…",
  "d1": {"disclosed": "yes|no|partial", "paragraphs": ["[0035]"], "note": "…"},
  "d2": {"disclosed": "no"},
  "examiner_position": "…",
  "our_position": "agree|contest",
  "contest_reason": "…"
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

复用 **patent-ipr-examiner** agent（其输入契约与 feature_matrix 同构），附加动态指令：「你现在审的是 OA 答复论证草案，以审查员立场找论证漏洞：哪条区别特征认定站不住、哪条结合启示否认牵强、哪处技术问题重界定越过说明书记载」。发现的漏洞回改 argument_draft。agent 缺失 → 动态指令子代理 → solo 逐条自审（家族惯例梯度）。

## Step 6：权利要求修改建议

`claim_amendment.md`：修改方向（合并从权/补入说明书特征缩限）+ 修改前后对照 + **每处修改标注说明书依据段落**（专利法 33 条防修改超范围——这是 ipr-examiner 第 8 项的镜像应用）。

## Step 7：汇总移交

按 OA_REPLY_TEMPLATE 汇总 `OA答复要点工作稿.md`（可选 docx 导出）。移交清单：工作稿 + feature_matrix + d_files 全文 + 未决问题列表（需要代理师法律判断的点单独列出）。

## 禁止事项

1. 不给「必然授权/必然驳回」结论；不推定答复期限。
2. D 文件无全文时不做 claims 级披露断言。
3. 禁止编造 D 文件段落号与内容——所有段落引用必须来自已抓取文本。
4. 技术问题重界定不得越过本申请说明书的记载范围。
