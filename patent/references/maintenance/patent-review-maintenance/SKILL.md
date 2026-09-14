---
name: patent-review-maintenance
description: "Use when extending or repairing the patent-review skill family, especially when adding a new audit dimension or changing reviewer output contracts."
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [patent, review, skill-maintenance, audit-contracts]
    related_skills: [patent-review, patent-workflow-conventions]
---

# Patent Review Skill Maintenance

## Overview

维护专利交底书审查能力时，新增一项审查要求不能只改总路由文案。必须把审查范围、专属审查员清单、JSON 输出契约、报告模板和部署副本视为一个整体，避免“skill 声称支持、实际 agent 没执行”的假增强。

本 skill 适用于公式审查、图文一致性、证据粒度、可行性等审查维度的新增与修复。它记录的是维护方法，不替代具体的专利审查规则。

## 触发条件

- 用户要求增强、修复或扩展 `patent-review`。
- 用户指出总 skill 与 reviewer agent 的实际检查项不一致。
- 新增审查维度、评分字段、状态字段或报告模板字段。
- 审查员部署路径、软链接或真源副本需要同步修复。

## 标准闭环

1. 先读当前总 skill、相关 reviewer agent 和报告模板，确认真实文件路径与所有副本，不凭记忆改。
2. 把新能力拆成职责边界：谁负责技术正确性，谁负责文档内部一致性，谁负责格式/渲染，避免两个 reviewer 重复或互相漏审。
3. 更新技术 reviewer 的逐项清单。新增项必须包含检查动作、证据要求、无法核验时的状态，而不是只有一句“注意检查”。
4. 更新 reviewer 的结构化输出。输出至少应能区分：未适用、已核验、被材料阻塞；评分维度也要独立，不能用一个旧字段代替多个新维度。
5. 更新一致性 reviewer 的清单与输出，覆盖跨章节引用、符号、编号、范围、单位和导出渲染等文档级问题。
6. 更新报告模板，使审查结果有落盘位置。新增字段要有说明，列表型字段要明确每项的定位、证据和结论。
7. 更新总 skill 的分工、派发输入、汇总规则、评分口径和复审纪律。明确源文件与导出文件缺失时不能假装完成。
8. 同步真源和已部署副本；修复失效软链接或部署引用后再验证，不要只看编辑成功提示。
9. 做确定性验收：关键 marker 存在、源/副本字节一致、模板字段无重复、diff 无空白错误、部署后的 reviewer 文件可读。

## 状态纪律

- `not_applicable`：完整清点后确认该审查维度不适用，例如全文没有公式；必须记录搜索范围。
- `checked`：材料齐全且完成了对应检查。
- `blocked`：存在待审对象但缺少导出件、变量定义、实验数据或其他必要材料；必须列出缺失材料与待验证结论。
- 不得把“没有发现问题”写成“已经证明正确”。

## 公式审查维护示例

公式新增审查至少分成两条线：

- 技术线：格式可交付性、变量/单位/取值域、量纲、代数关系、运算优先级、定义域、边界条件和最小数值例核算。
- 一致性线：公式编号与正文引用、符号跨章节统一、约束说明统一、Markdown/LaTeX 到 docx 的渲染一致性。

公式格式、内部一致性和数理正确性必须分别结论。不能因为公式排版正常，就默认数理正确；也不能因为数学关系看起来合理，就默认 docx 已正确渲染。

## 常见坑

- 只改总 skill 的表格，忘了 reviewer agent 的逐项清单。
- 给 agent 加了检查项，却没给 JSON 输出和报告模板落盘字段。
- 只保留 `formula_symbol_score`，导致渲染质量和数理正确性没有独立结论。
- 缺少 docx 或其他导出件时仍报告“渲染已通过”。
- 模板补丁重复插入字段或整个小节。
- 编辑了外部只读 skill 后误以为当前库已经持久化；遇到外部托管路径应报告权限边界，或把可复用维护方法保存到本技能。

## 验收清单

- [ ] 总 skill 的职责分工已更新
- [ ] 技术 reviewer 的检查清单与 JSON 契约已更新
- [ ] 一致性 reviewer 的检查清单与 JSON 契约已更新
- [ ] 报告模板字段已更新且无重复
- [ ] `not_applicable` / `checked` / `blocked` 语义已定义
- [ ] 真源与部署副本一致
- [ ] reviewer 引用可读且指向实际文件
- [ ] 关键 marker 检查通过
- [ ] diff 检查通过

## 支持文件

- `references/formula-review-contract.md`：公式专项审查的分工、状态和输出字段速查。
