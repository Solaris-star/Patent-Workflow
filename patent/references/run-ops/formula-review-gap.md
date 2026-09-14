# Review 公式审查 + 写作纯文本公式（2026-07-23 更新）

## Review 能力状态

| 层 | 状态 |
|---|---|
| `patent-review` 主 skill | 一致性：符号/渲染/约束；技术：格式 + 数理；分工强制 + `not_applicable/blocked` |
| CONSISTENCY 模板 | `formula_*` 字段 + `formula_rendering_score` / `formula_constraint_score` + 公式审计记录 |
| `patent-tech-reviewer` | 已增强：清点/格式/变量/量纲/边界/最小数值例 + `formula_audit` |
| `patent-consistency-auditor` | 已增强：符号 + **渲染规范** + 约束跨段一致 |

跑 review：无公式两视角写 `not_applicable`；有公式不可用外观通顺代替数理正确。

## 写作/导出铁律（用户纠偏 2026-07-23）

1. **源 md 禁止依赖 `$$LaTeX$$` 导出**——`generate_docx.py` 常残留 `\cdot`/`\in`/`\min`。
2. 用纯文本：`D＝w1·R＋w2·Vn＋w3·C` + 定义段 + 手算例。
3. **标题/交付禁英文**：`Agent`→「智能体」；docx 抽查无 `Agent`。
4. docx 抽查：`$$` / `\` 命令 任一命中 → 回源修。
5. 已坏的 docx 真公式 → `patent-workflow-host-ops/references/docx-formula-repair.md`。

## 相关

- 交付拉平：`delivery-flatten-and-naming.md`
- 题名禁英文：`patent-run-ops` SKILL §1（若未补全见本文件写作铁律）
