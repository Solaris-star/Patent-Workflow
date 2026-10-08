# 审查到回改的闭环

审查报告为每个问题分配稳定 ISSUE-... ID，并记录严重度、位置、证据、处置和所审材料哈希。高严重度未解决项必须修复，或由用户对具体 issue 作有范围和风险说明的豁免。

回改前，edit_plan 记录用户批准的 issue ID 与具体范围。每个 edit 和 structured_diff 项沿用相同 ID。对已批准问题的修复可复用授权的仅限于不新增事实或保护范围的范围；其他决定仍交由用户判断。

回改后重新审查当前版本并更新 review_status。未批准回改时可以记录 revision_validation=not_required 与 skipped；报告文件存在本身不代表检查通过。
