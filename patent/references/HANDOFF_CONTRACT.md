# 交接契约（HANDOFF_CONTRACT）

各步骤进入下一步前的最小交接字段。字段写入 `artifacts/run_manifest.md`。

## 开局 → 调研

- `domain_scope`（用户给定或待交叉发现）
- `fixed_topic_or_title`（可为空）
- `output_dir`（冷启动必须由用户明确给出的绝对路径）
- `capability_profile`（本轮能力探测结果）
- `source_fingerprints`（有模板/参考件时）

## 初始化层（patent-style）→ 写作可用

四件工件就绪或显式跳过：

- `template_rules.json` 就绪 / 复用命中 / `template_not_provided = true`
- `style_profile.md` 就绪 / 复用命中 / `reference_patent_not_provided = true`
- `initialization_reused` 已记录

## 存量挖掘（patent-mine）→ 方向收敛

- `phase_02_research_pack.json`（脱敏后同构产出）已落盘且 `--gate research` 通过（该 gate 对 mine 血统强制校验 `sensitive_map_path` 非空且文件存在）
- `sensitive_map_path` 已用 `init_run_manifest.py --update` 写入 manifest（map 须 `confirmed_by_user: true`；禁止手改 markdown 声明）
- `validate_sanitize.py` 对 pack 过检通过
- 含密件（mining_raw / sanitize_log）均在源项目 `.patent-private/`，未进 workspace
- 落选点入 vault 时带 `origin_sensitive_map_path`（血统锚点，挑选时继承进新 manifest）

## 调研（patent-research / -cli）→ 方向收敛

- `phase_02_research_pack.json` 已落盘且 `--gate research` 通过
- `candidate_directions`（2-3 个）或固定题目下的 `candidate_innovation_axes`
- `recommended_direction`
- `claims_requiring_patent_verification`
- `channels_used` / `channel_failures` / `degraded_run`

## 方向收敛 → 查新（patent-prior-art）

- `selected_direction`（用户确认）
- `working_title`（工作题名，≤ 25 字）
- vault 存在时：撞车检测已执行且结论已向用户明示；`vault_case_id` 已登记（可选字段）

## 查新 → 写作（patent-draft）

- `phase_04_patent_candidate_pool.json` + `phase_04_evidence_pack.json` 已落盘且 `--gate prior-art` 通过
- `background_pack` 就绪并落盘 `artifacts/prior_art/phase_05_background_pack.json`（≥ 2 篇已验证背景专利 + `closest_prior_art` + `major_differences`）
- `ipr_pack` 状态（就绪 / 降级原因）——就绪时落盘 `artifacts/prior_art/phase_05_ipr_pack.json`；只影响能否进 IPR 审查，不阻塞写作

## 写作 → 审查（patent-review）

- 5 个 part md 完成 + `facts_ledger.json` 落盘且 `--gate draft` 通过
- 附图三件套（image + mmd + editable）文件真实存在

## 审查 → 终稿导出

- 一致性审计报告 + IPR 审查报告落盘（`artifacts/audit/`），问题清单已向用户汇报
- 最新一轮审查无 high 项，或用户豁免已记入 `user_confirmations`
- 若发生委托代改：`edit_plan` + `structured_diff` 留痕齐全且 `--gate review` 通过，复审报告落盘
- `final_title`（最终题名）

## 终稿导出 → 宣告完成

- `--gate deliver` 通过（文件名、嵌图、附图完整性、报告齐全）
- 交付目录只保留唯一正式 docx，过程件已下沉 `artifacts/`
