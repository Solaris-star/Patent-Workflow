---
name: patent
description: "软件专利协作流程：本地材料整理、按需查新、交底书撰写、审查修订与交付。"
---

# 软件专利协作流程

此工作流服务于软件专利交底书协作，不用于管理研发项目。核心对象是专利材料、技术特征、证据、审查问题、用户决策和可追溯交付版本。

## 先判定任务路径

| 用户已有材料 | 路径 | 不重复进行 |
|---|---|---|
| 只有主题或初始材料 | full_research | 先调研，再查新、撰写和审查 |
| 已确定主题或题名，需要补证 | titled_evidence | 不重新选题；按请求的检索深度补证 |
| 已有交底稿 | draft_review | 先复用并校验现有材料，直接审查或按要求修订 |

只有在主题、材料边界、交付目录或授权范围缺失且会影响工作时才向用户询问。重复询问前检查 manifest 中的确认记录。新增保护范围、技术事实或未解决风险仍须用户判断；字数、改动数量或相似度都不能代替授权。

## 初始化和恢复

从仓库根目录通过 patent/scripts/workflow_cli.py 使用 init、status、resume、check、export。初始化需要用户明确的绝对输出目录，不覆盖已有 manifest 或案件材料。恢复时复用已验证的材料，记录阶段历史、当前阶段、缺失材料、下一步和是否等待用户。

workflow_mode 使用 full_research、titled_evidence 或 draft_review。search_depth 按用户请求记录为 light、balanced 或 deep；没有请求配额时不硬凑检索数量。

## 本地数据边界

专利材料、案件文件和脱敏映射默认留在本地。任何材料离开本地、进入第三方模型、MCP、搜索或消息服务前，先向用户说明材料、目的地和用途并获得当次明确确认。未确认时不外发、不调用相关服务。不得新增发送行为。

脱敏映射只有在 confirmed_by_user 为 true，并有 confirmed_at、confirmation_scope 和结构完整的 entries 后才可用于扫描。未确认时在读取待扫描文件前失败。扫描结果只返回条目 ID 与计数，不输出命中原文或上下文。

## 阶段契约

1. 调研：保存研究问题、来源、日期、核验状态和失败渠道；结构检查不证明法律新颖性。
2. 查新：沿用 evidence_pack，使用稳定 evidence_id 和 feature_id；候选数量由请求决定。没有已核验结果时记录真实无结果及检索轨迹，不编造引用。
3. 背景材料：交付 background_pack，说明实际引用的来源、最接近材料和差异。IPR 包仅在 manifest 的 ipr_requested 为 true 时要求。
4. 撰写：五段 Markdown、facts_ledger、feature_registry、来源映射和 Mermaid 图源文件。通过 --gate draft 检查实际文件。
5. 审查：一致性审查和 IPR 审查都要明确完成。issue 使用稳定 ISSUE-... ID，贯穿报告、获准范围、修订计划、差异、复审和豁免。
6. 修订：只有与用户已批准 issue 范围一致的修复可以复用原授权。新事实或新增保护范围须记录具体用户决定。修订后的材料哈希改变时，旧结论自动待复核。
7. 交付：先由 `workflow_cli.py export` 通过导出前检查并生成 DOCX，再用 `workflow_cli.py check --gate deliver` 单独检查完整包。manifest 中声明的实际输出目录必须与交付目录相同；终稿 Markdown、DOCX、最新版 review_status 和源文件须指向同一版本。DOCX 已生成仍是待 deliver 检查状态。

## 题名与附图

- 题名最多 24 个字。统一由共享常量与校验器执行，所有文档遵守同一上限。
- 默认附图配置是 mermaid_only：交付实际引用的 .mmd 源文件，DOCX 可读地包含 Mermaid 源码，不要求 PNG 或 DOCX 位图。
- 用户明确要求位图时，将 figure_delivery_mode 设为 mermaid_and_images；只校验终稿实际引用的图片和 DOCX 图片关系，不以 ZIP 中存在任意 media 文件代替引用检查。

## 审查与交付判定

review_status.json 必须明确 consistency_review 和 ipr_review 已完成，记录 issue disposition、具体高严重度用户豁免，并保存被审材料的 SHA-256。仅有报告文件不代表审查通过。无获准回改时 revision_validation 为 not_required，回改校验状态为 skipped；有回改时必须有有效 edit_plan、structured_diff 和 post-fix 检查。

结果字段含 checks_passed、workflow_complete、skipped、not_run、review_completed 和 revision_validation。checks_passed 只表示已执行检查通过；DOCX 生成返回 `generated_pending_delivery_check` 且 `workflow_complete: false`，只有后续 deliver 整包检查通过才可完成流程。缺少 LibreOffice 渲染会记录 `not_run`，不能声称全流程完成。切换 full_research、titled_evidence、draft_review 时，当前状态和失效范围只按选定模式的有效门禁计算，非活动门禁不阻断该模式。

离线校验只确认结构、引用、版本、日期和声明状态，不提供法律新颖性、授权或不侵权保证。

## 宿主 Agent 与依赖

门禁脚本只依赖 Python 3.10+ 标准库。DOCX 导出需要 python-docx；渲染检查使用本机 LibreOffice，未安装时为 not_run。CNIPA 浏览器检索需要可选 Playwright 与 Chromium。宿主 Agent 的检索工具、外部服务或专用 skills 只有在用户授权后才可处理案件材料；验证器本身不会调用模型或网络。
