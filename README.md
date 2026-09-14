# Patent-Workflow

面向中国发明专利技术交底书的端到端工作流：选题调研 → 方向收敛 → 查新检索（CNIPA / Google Patents）→ 分块撰写 → 多视角审查 → 终稿交付，全程阶段门禁（gate）驱动。

## 架构

```
patent/               主入口：阶段路由与全流程编排
├── references/       交接契约 / manifest 模板 / 检索协议 / run-ops 纪律
└── scripts/          阶段门禁与验证器（python3.10+）
patent-research-cli/  smart-search CLI 调研
patent-research/      通用调研
patent-style/         模板/文风分析（指纹缓存复用）
patent-prior-art/     查新与对比文献
patent-draft/         分块撰写与 docx 导出
patent-review/        一致性审计 + IPR 审查（含公式格式与数理正确性）
patent-sanitize/      脱敏检查
patent-vault/         选题库 / 案件管理（vault.py）
patent-mine/          存量项目挖掘
patent-oa/            审查意见答复
agents/               审查 agent 提示词（一致性审计 / 技术审查）
```

## 阶段门禁

| 阶段 | 输入 | 门禁 |
|---|---|---|
| research | `phase_02_research_pack.json` | `--gate research` |
| prior-art | 候选池 + 证据包 | `--gate prior-art` |
| draft | 5 part + facts_ledger + 附图 | `--gate draft` |
| review | 审计/IPR 报告 | `--gate review` |
| deliver | 终稿 docx + 健康检查 | `--gate deliver` |

```bash
python3 scripts/run_phase_gates.py --gate <stage> --workspace . --manifest artifacts/run_manifest.md
```

## 核心纪律

1. **双参考物**：`技术交底书框架.docx` = 段落架构唯一权威（三子节描述性标题、无 A1/B1 编号、无替代方案/其他事项/注意事项）；参考授权专利全文 = 文风基准。
2. **不编造**：实施效果无实测不量化；未验证专利不引用；虚构专利号 = 最高违规。
3. **审查只审不改**，代改须备份 + facts_ledger/merged/docx 联动 + edit_plan 留痕。
4. **style 缓存指纹复用**：`(template, reference)` 指纹一致直接复用 `artifacts/style/` 四件。
5. **交付布局**：`<标题>/` 根放终稿 md/docx + `附图/`（mmd+png）；过程产物全下沉 `artifacts/`。

详见 `patent/SKILL.md` 与 `patent/references/`。

## License

MIT
