# 审查会话样本：Agent 工具调用结果核验（2026-07-22）

## 案名

一种面向工具调用幻觉的Agent结果核验方法及系统

## 触发

`/patent-review` + WebUI 上传 docx → 委托代改 → 用户「复审」+ 纠正文件名

## 权威输入

- 上传 docx（优先）
- 案件目录 md/docx/artifacts（对照）

## 类级可复用发现

1. **旧审计过松**：phase_08 曾 94、phase_09 曾 82；以上传 docx 重审后一致性 52、IPR 66。旧报告对着较干净 md，未抠章节/裸 mermaid/三态图文。
2. **附图假交付**：docx 裸 mermaid；`facts_ledger.figure_registry` 指向不存在的 mmd。
3. **三态 vs 二分图**：正文「一致/不一致/部分一致」，图1 仅是否一致。
4. **背景集合漂移**：A2 两件专利，A3 评三件；公开日「2026年」不完整；A1 首句「（LLM）」残缺。
5. **IPR mixed**：feature 矩阵关键特征多为 ×，仍不得写新颖性无条件通过；创造性写组合抗辩。
6. **时序矛盾**：S1 工具前拦截 vs S2 工具完成后返回——Agent 核验类标配必查。
7. **上下位漂移**：系统段漏「部分一致」；实施例突然出现权重评分。

## 章节编号注意

本案 docx 用公司模板（A1/B1 +「专利附图」）。不要把公司模板本身当 high；真 high 是残句、集合不一致、附图工件、时序、三态图文。

## 并行执行

- 一致性 / IPR 分路稳；三视角打包易超时。
- 完整输出：`~/.hermes/cache/delegation/subagent-summary-*.txt`
- 工程 agent 缺失时可写 `phase_08b_tech_feas_lang_notes.md`

## 落盘

- `artifacts/audit/phase_08_consistency_audit_report.md`
- `artifacts/audit/phase_09_ipr_review_report.md`
- `artifacts/audit/phase_08b_tech_feas_lang_notes.md`
- 代改后：`artifacts/revision/phase_10_edit_plan.json`、`phase_10_structured_diff.json`、`phase_10_post_fix_check_report.md`

## 若用户点「你改」优先序

1. 补 A1 首句；A2 列齐对比文件；著录补全（引用格式跟 patent-run-ops §7）
2. 重画图1 三态 + 落 mmd；图2 外部实体化；修正 ledger
3. 拆清调用前旁路 / 调用后核验时序
4. 对齐部分一致触发条件；评分写进发明内容或删实施例
5. 统一「自述」；五章回引图号
6. 语言：「进一步地」、有益效果列表腔 → patent-deslop
7. 章节体例仅在用户要求统一交付约定时改 A/B/C
8. **导出后 rename 为 `…技术专利交底书.{md,docx}`**

## 代改复审与命名（本轮增量）

### 代改闭环验收

| 检查 | 通过形态 |
|---|---|
| 图1 | S1–S6 + 三态（一致/不一致/部分一致） |
| 时序 | 旁路记录并放行 → 执行 → 调用后核验 → 失败门禁 |
| 触发 | 发明内容/系统/S6 同写「不一致或部分一致」 |
| 评分 | S5 与比对模块均有权重→三态，或两端都无 |
| 术语 | 无「自报」；统一「自述」 |
| 回引 | 「如图1所示」「如图2所示」 |
| 工件 | `附图/fig_*.mmd` + ledger 路径有效 |
| 充分公开 | 模板字段/学习回退/示例阈值/禁盲重放/补偿/Proxy |

复审后本案：一致性 **52→88 pass**，IPR **66→80 pass**（novelty/inventiveness 仍警告，因 mixed）。

### 交付文件名（用户纠正）

- ✅ `<标题>技术专利交底书.md` / `.docx`
- ❌ `…技术交底书.docx`（缺「专利」）
- ❌ `交底书_<标题>.md`（仅过程名）

`generate_docx.py` 默认输出名常缺「专利」——导出后立刻 `mv`；旧名进 `versions/`。复审报告与用户汇报路径必须用纠正后的终稿名。

### 汇报拆三类

- A 委托 high 已修 → 已解决 + 分数  
- B mixed 证据边界 → 单独说  
- C 可选 low（如「调用拦截模块」改名旁路记录）→ 未委托  
