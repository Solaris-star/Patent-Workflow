---
name: modular-writer
description: "Phase 5 正文撰写。消费 Phase 0 制品（template_structure_rules.json / reference_style_profile.json / compliance_rules.json）和 Phase 2 制品（patent_candidate_pool / evidence_pack）"
version: "3.0"
user-invocable: false
allowed-tools: Read, Write, Edit, Glob, Grep
---

# modular-writer — Phase 5 正文撰写

## 数据流

```
Phase 0 制品                      Phase 2 制品
├── template_structure_rules.json → 章节标题、子节编号、附图要求
├── reference_style_profile.json  → 起手句、衔接词、句式笔法
└── compliance_rules.json         → 禁止项、约束条件

                                   ├── patent_candidate_pool.json → 候选方向、对比分析
                                   └── evidence_pack.json         → CN 专利号、摘要、URL
                                          ↓
                                   正文撰写（Phase 5）
                                          ↓
                                   分块文件（part_01~05）→ Phase 6 审计
```

## 门禁（Phase 5 开始前强制执行）

Agent 在撰写正文之前，**必须**按顺序执行以下 Read：

1. `Read` `artifacts/preprocess/template_structure_rules.json` — 提取：章节名称、子节编号、图要求
2. `Read` `artifacts/preprocess/reference_style_profile.json` — 提取：起手句格式、步骤总述句式、背景句式、发明句式、实施例句式
3. `Read` `artifacts/preprocess/compliance_rules.json` — 提取：禁止项、硬性约束
4. `Read` `artifacts/prior_art/phase_02_patent_candidate_pool.json` — 提取：选定方向的对比分析
5. `Read` `artifacts/prior_art/phase_02_evidence_pack.json` — 提取：CN 专利号、摘要理解、公开源 URL

## 撰写规则

### 结构 → 来自 `template_structure_rules.json`

Agent 从 `template_structure_rules.json` 的 `sections` 数组中读取章节信息：
- `id` — 章节标识
- `name` — 章节标题（**原文照搬**，不得改写为其他标题）
- `order` — 排列顺序

提取时排除 `id` 为 `part_01`~`part_04` 以及 `part_21` 之后的辅助模板（审计报告模板、IPR 报告模板、Manifest 模板等），仅保留正文撰写所需的章节（`part_05`~`part_20`）。

### 风格 → 来自 `reference_style_profile.json`

从以下字段提取笔法规范：
- `required_patterns` — 起手句、步骤总述句、过渡句
- `reference_style_rules` — 技术领域句式、背景句式、发明内容句式、实施例句式、附图句式
- `forbidden_tone` — 禁止的语气
- `writing_principles` — 写作原则

`usage_boundary` 规定了参考专利的边界：**仅提取表达风格，不得复用参考专利的技术内容。**

### 约束 → 来自 `compliance_rules.json`

从规则列表中提取硬性限制。包括但不限于：
- 章节标题原文照搬
- 子节编号不可修改
- 附图格式要求
- 禁止输出的内容类型

### 内容 → 来自 Phase 2 制品

- 从 `evidence_pack.json` 提取每件 CN 专利的：专利号、标题、摘要理解、公开源 URL
- 每条引用的现有技术末尾附 URL
- 基于摘要理解撰写技术描述，不得杜撰

### 附图 → 来自 `template_structure_rules.json` 的图要求

- 从 `sections` 中提取图数量要求和类型要求
- 每图一组：标题行 → 描述段落 → mermaid 代码块
- 节点标签使用简短中文

## 输出规范

写入 `part_01_技术领域.md` ~ `part_05_具体实施方式.md` 到 workspace 根目录。

**禁止写入交付正文的内容**（从 `compliance_rules.json` 和 `template_structure_rules.json` 的 forbidden/usage_boundary 字段提取）：
- 文档头部元数据块
- 权利要求书
- 自检清单
- 仓库/技能脚注
- 参考专利的技术事实

## Agent 自检清单

- [ ] 已 Read 全部 5 个强制文件
- [ ] 章节标题与 `template_structure_rules.json` 一致（原文照搬）
- [ ] 子节编号与 `template_structure_rules.json` 一致
- [ ] 起手句/步骤总述/过渡句 符合 `reference_style_profile.json`
- [ ] 背景句式 符合 `reference_style_rules.background`
- [ ] 发明句式 符合 `reference_style_rules.invention_content`
- [ ] 实施例句式 符合 `reference_style_rules.embodiment`
- [ ] 每条引用专利附 URL
- [ ] 无 `compliance_rules.json` 禁止项
- [ ] 4+ 张 mermaid 图
