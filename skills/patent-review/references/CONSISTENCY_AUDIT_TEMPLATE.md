# 一致性审计报告模板

本模板用于 `patent-review` 的一致性审计输出骨架。

## 基本信息

- `consistency_audit_report_path`:
- `draft_title`:
- `draft_version`:
- `audit_input_path`:
- `run_manifest_path`:

## 审计项结果

- `terminology_consistency`:
- `figure_text_consistency`:
- `formula_variable_consistency`:
- `formula_symbol_rendering_consistency`:
- `formula_constraint_consistency`:
- `module_naming_consistency`:
- `cross_reference_consistency`:
- `section_heading_consistency`:
- `background_style_consistency`:
- `title_readability_consistency`:
- `figure_mapping_consistency`:
- `authorization_tone_consistency`:

## 评分（100 分制，建议口径）

> 评分目的：衡量“文档内部一致性 + 交付可用性”的成熟度，用于决定是否进入 IPR/交付；不等同于法律有效性。

- `scoring_scale`: `0-100`
- `overall_score`: 

### 分项评分（0-10）

- `terminology_score`:                 # 术语一致性
- `figure_text_score`:                 # 图号/图名/正文引用一致性
- `cross_reference_score`:             # 交叉引用一致性（如“如图X所示/步骤Sx/模块Mx”）
- `section_heading_score`:             # 章节标题与目录一致性
- `module_naming_score`:               # 模块/部件命名一致性
- `formula_symbol_score`:              # 变量/常量/下标/索引/编号/引用一致性（如有）
- `formula_rendering_score`:           # md 源文与 docx/导出件的公式格式、可读性、渲染稳定性（如有）
- `formula_constraint_score`:          # 单位、取值域、阈值、归一化、定义域、边界条件在全文的一致性（如有）
- `style_tone_score`:                  # 行文风格一致性（专利感、避免汇报腔/AI腔）
- `deliverable_structure_score`:       # 交付结构一致性（docx/附图工件/artifacts 放置与命名）
- `evidence_citation_score`:           # 背景专利引用/证据链标注一致性
- `figure_artifact_score`:             # 附图工件完整性（mmd 必有且内嵌 part_04；不要求 png 嵌图）

### 公式审计记录（必须）

- `formula_audit_status`: `not_applicable` / `checked` / `blocked`
- `formula_inventory`:                  # 逐项记录公式编号、位置、正文引用和源文件/导出件
  - `formula_id`:
    `location`:
    `references`:
    `source_format`:
    `rendered_artifact`:
    `variables_and_units`:
    `constraints_and_boundaries`:
    `rendering_result`:
    `internal_consistency_result`:
- `formula_rendering_findings`:         # 原始标记、乱码、丢失上下标、断行、空白公式等
- `formula_constraint_findings`:        # 单位、范围、阈值、定义域、边界条件跨段落不一致等
- `formula_audit_note`:                 # 无公式时写明已搜索公式标记/等式/不等式/编号；阻塞时写明缺失材料

### Top 问题（必须）

- `top_issues`:
  - `issue`:
    `severity`: `high` / `medium` / `low`
    `location`: # 章节/文件/图号
    `symptom`:
    `fix_suggestion`:

## 结论

- `pass_fail`: `pass` / `fail`
- `pass_threshold_suggested`: 80
- `pass_fail_suggested`: `pass` / `fail`

