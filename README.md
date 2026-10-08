# 软件专利协作流程

面向软件专利技术交底书的协作流程：整理材料、检索证据、形成交底稿、完成审查与修订、交付可追溯文件。本项目是专利协作工具，不是研发项目管理系统。

## 快速开始

需要 Python 3.10 或更新版本。从仓库根目录运行：

~~~powershell
python patent/scripts/workflow_cli.py init --manifest artifacts/run_manifest.md --output-dir "<用户明确给出的绝对交付目录>" --final-markdown "<该交付目录>/final.md" --mode full_research --disclosure "<local-disclosure.md>" --search-brief "<requested-scope>"
python patent/scripts/workflow_cli.py status --manifest artifacts/run_manifest.md
~~~

初始化不会覆盖已有 manifest。恢复中断任务先查看 status 中的缺失材料、下一步和是否等待用户，再运行 resume。`export` 会重新运行当前模式的有效路由门禁与审查，并做导出前包检查，再从 manifest 绑定的终稿生成 DOCX。导出成功只表示 DOCX 已生成并待交付检查；随后还要单独运行 `check --gate deliver`，不能把生成状态当作流程完成。

~~~powershell
python patent/scripts/workflow_cli.py status --workspace . --manifest artifacts/run_manifest.md
python patent/scripts/workflow_cli.py resume --workspace . --manifest artifacts/run_manifest.md
python patent/scripts/workflow_cli.py export --workspace . --manifest artifacts/run_manifest.md
# 仅在明确要替换现有 DOCX 时添加 --overwrite
~~~

`export` 输出 `generated_pending_delivery_check` 且 `workflow_complete: false`。之后的 deliver 门禁检查 manifest 绑定的输出目录、终稿 Markdown、DOCX、最新审查版本和少于 25 个字的题名（最多 24 字）：

~~~powershell
python patent/scripts/workflow_cli.py check --workspace . --manifest artifacts/run_manifest.md --gate deliver
~~~

清单声明 `sensitive_map_path` 的 run 必须在 `export` 和之后的 deliver 检查中都显式重选同一路径：

~~~powershell
python patent/scripts/workflow_cli.py export --workspace . --manifest artifacts/run_manifest.md --sensitive-map "<manifest 中相同的绝对路径>"
python patent/scripts/workflow_cli.py check --workspace . --manifest artifacts/run_manifest.md --gate deliver --sensitive-map "<manifest 中相同的绝对路径>"
~~~

`init/resume --sensitive-map` 只登记路径引用；未重选、路径不匹配或未配置必需参数时，命令在读取 map 前失败。导出阶段验证 map 当前内容与确认绑定，并分别扫描最终 Markdown 和生成的 DOCX。匹配后 validator 原位读取，不复制 map。该路径引用例外不放宽其他外部路径或符号链接保护。

## 工作阶段

| 阶段 | 主要产物 | 验证 |
|---|---|---|
| 调研 | phase_02_research_pack.json | --gate research |
| Prior art | phase_04_evidence_pack.json plus a background_pack; IPR pack only when explicitly requested | --gate prior-art |
| 撰写 | 五段正文、facts_ledger.json、Mermaid 源文件 | --gate draft |
| 审查与修订 | 一致性/IPR 报告、review_status.json，需要回改时另有 edit_plan 与 structured_diff | --gate review |
| 交付 | 最终 Markdown、DOCX、附图源文件和健康报告 | --gate deliver |

### 按模式执行的门禁

| 模式 | --gate all 的顺序 |
|---|---|
| full_research | research → prior-art → draft → review → deliver |
| titled_evidence | prior-art → draft → review → deliver |
| draft_review | review → deliver |

draft_review 不包含 prior-art 门禁。若现有稿需要正式补证，先取得固定题名、披露材料和明确检索范围，再用 resume --mode titled_evidence 切换路径；切换会使依赖旧路径的结论待复核。状态和失效范围按当前选定模式的有效门禁计算，未激活的门禁不阻断该模式。不能把可选的手工检索说成该模式已通过 prior-art 门禁。

passed / checks_passed 表示已运行的检查通过；workflow_complete 表示所有必需阶段和导出后的整包检查均完成。缺少交付参数、渲染工具或材料时，会分别记录为 skipped 或 not_run，不能据此宣称流程完成。缺少 LibreOffice 时渲染状态为 not_run，deliver 门禁不会标记完成。没有获准回改时，回改校验可以合法跳过；审查完成状态仍须由明确的 review_status.json 证明。

## 统一规则

- 题名最多 24 个字。工作稿和终稿都按同一规则检查。
- 附图默认交付 Mermaid .mmd 源码，不要求 PNG，也不要求 DOCX 中含位图。确需图片时，在 manifest 显式设置 figure_delivery_mode: mermaid_and_images，并检查正文实际引用的图片。
- 五段正文、事实台账、证据包、审查 issue、修订计划、差异和终稿之间使用稳定 ID 与 SHA-256 版本指纹追溯。
- 离线验证只检查结构、引用、状态与版本一致性；不判断材料语义、发明事实真伪、技术方案实质或保护范围。Agent 与人工 reviewer 负责语义和事实核对；保护范围及未决风险由用户决定。没有独立 reviewer 能力时，必须如实标记为单一会话审查。
- 输入 Markdown 保持原位。DOCX 先写临时文件并验证；默认拒绝覆盖已有文件，明确传入 `--overwrite` 才原子替换。命令输出实际文件路径，可安全重复导出。

## 运行环境与依赖

- 门禁与结构校验器仅使用 Python 标准库。
- DOCX 导出和文档文本检查需要可选的 `python-docx`；缺少时状态为 not_run 或明确失败。
- DOCX 页面渲染使用本机 LibreOffice；缺少时状态为 not_run，不会伪装成通过。
- CNIPA 网页检索是可选能力，需要 Playwright 与 Chromium。`pypdf`、smart-search CLI 和 Mermaid CLI 都不是本仓库的必需依赖；如宿主未提供则相应能力标记不可用。遇到网站安全验证、验证码或拒绝访问时停止，不规避验证。
- 本仓库只提供两份 reviewer 提示文件，不会部署或自动启动代理。宿主 Agent、浏览器或检索工具只有在实际可用且本次材料外发已获明确确认后才能使用；代码不会自行调用模型、外部检索服务或发送案件材料。
- 外部检索命令会把查询词发送到对应服务。若查询由案件材料派生，先明确告诉用户查询内容、目的地和用途并取得本次确认；没有确认时保持离线。

## 本地数据边界

材料、案件文件和脱敏映射默认留在本地。任何材料或含有材料信息的查询要发送给第三方模型、MCP、搜索服务或消息服务之前，必须先向用户说明具体材料、目的地和用途，并取得针对该次发送的明确确认。没有确认时不外发、不调用相关服务。脱敏映射须记录 confirmed_by_user: true、确认时间、确认范围及与映射内容绑定的 SHA-256；校验器不会输出匹配到的敏感原文。该哈希绑定内容，不证明确认者身份。

## 公开发布前检查

运行 python patent/scripts/check_public_release.py --root .。检查会验证公开示例清单和文件哈希、扫描当前文本文件（含 `.mmd`）中的邮箱与凭据类内容，并仅报告文件位置与规则名，不回显匹配值。清单完整不等于语义保密审查通过；人工发布审查仍是独立记录，工具不会认证其真实性或保证发布安全。公开演示只使用明确虚构、无真实技术细节的内容。该检查不扫描或改写 Git 历史，也不代表清理了历史提交。

## 许可

MIT

## 并发与审计边界

`workflow_cli.py` 和直接运行的 `run_phase_gates.py` 会按工作区锁串行操作；导出将审查版本、所选脱敏映射快照、最终 Markdown 和 DOCX 哈希绑定到审计记录，并在发布窗口检测到变化时撤销新输出或恢复旧文件。锁不约束独立外部程序在发布后的写入。详见[导出快照与并发边界](patent/references/export-snapshot-boundary.md)。