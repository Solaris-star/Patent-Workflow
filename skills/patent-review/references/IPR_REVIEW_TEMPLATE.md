# IPR 模拟审查报告模板

本模板用于 `patent-review` 的 IPR 模拟审查输出骨架。

## 基本信息

- `ipr_review_report_path`:
- `patent_title`:
- `review_round`:
- `review_input_path`:
- `run_manifest_path`:
- `review_scope`:

## 证据基础

- `prior_art_refs`:
- `prior_art_pack_ref`:
- `evidence_basis`:
- `evidence_granularity`: `claims_verified` / `abstract_only` / `mixed`

## 评分（100 分制，建议口径）

> 评分目的：对“可授权性风险”做可读的量化表达，用于迭代优先级排序；不等同于真实审查结论。

- `scoring_scale`: `0-100`
- `overall_score`:  

### 分项评分（0-25）

- `novelty_score`:            # 新颖性（相对已检索 prior-art 的冲突风险）
- `inventiveness_score`:      # 创造性（区别特征是否显著、是否容易被组合推出）
- `practicality_score`:       # 实用性（可实施性、落地条件是否具备）
- `clarity_score`:            # 清楚性（术语/边界/必要技术特征是否清晰可检索）

### 9 法定项逐项结论（必须，与 patent-ipr-examiner 输出的 statutory_results 同口径）

- `statutory_results`:            # 每项：通过 / 警告 / 驳回风险 / 不适用
  - `授权客体`（A2）:
  - `新颖性`（A22.2）:            # 无 ipr_pack 时只能填「待检索验证」，禁止「通过」
  - `创造性`（A22.3）:
  - `实用性`（A22.4）:
  - `充分公开`（A26.3）:
  - `权利要求支持`（A26.4）:
  - `单一性`（A31）:
  - `修改超范围`（A33）:
  - `诚实信用`（A20）:
- `formal_review`:                # 形式审查：章节完整 / 名称 ≤25 字 / 用语规范

### 支持性风险（等级 + 触发原因）

- `support_risk`: `low` / `medium` / `high`
- `support_risk_reasons`:     # 列表：缺少实施例支撑/缺少必要结构/范围过宽等

### 评分阈值建议（可选）

- `pass_threshold_suggested`: 70
- `pass_fail_suggested`: `pass` / `fail`

### Top 风险点（必须）

- `top_risks`:
  - `risk`: 
    `severity`: `high` / `medium` / `low`
    `impact`:   # 可能导致：新颖性否定/创造性否定/不清楚/不支持/不可实施
    `evidence_or_reason`: # 指向 prior-art / 章节段落 / 缺失点
    `fix_suggestion`: 

