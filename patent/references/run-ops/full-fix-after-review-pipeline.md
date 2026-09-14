# 审查后全量代改流水线（2026-07-23）

## 触发

用户在五视角审查后说：「你改吧」「全部修复」「委托代改」且未限定子集 → 按审查 top_issues **全量**改，不只改 high。

## 本案样本

- 标题：一种多智能体协调对齐与失败回滚方法及系统
- 路径：`<patent_output_dir>/一种多智能体协调对齐与失败回滚方法及系统/`
- 改前分：一致性 88 / IPR 74
- 备份：`artifacts/revision/backup_20260723/`

## 顺序

1. 备份 md/docx/part_03/05/facts_ledger  
2. 改合并主稿  
3. 回写 parts + merged + facts_ledger（约束去重）  
4. python-docx 重生：Title / H1×5 / H2×3(A、B、C)  
5. 自动校验全过  
6. `phase_10_edit_plan.json` + `phase_10_post_fix_check_report.md`  
7. 告知「可复审」

## 可复用补丁句式

**必要特征开篇**  
其必要技术特征在于：将角色对齐、交接对齐与偏离对齐组织为持续运行的分层对齐控制环，并在失败路径上将检查点、副作用清单、逆序幂等补偿与可恢复执行图回写闭环，而不是仅对任务进行重决策或重规划。

**R/C**  
- `R＝Nu／N`（N>0；N=0→0）  
- `C＝min（1，Nc／Nmax）`；冲突含角色绑定 / 交接字段 / 前后结论  

**合法检查点**  
角色与交接对齐均通过 + 补偿映射完整 + 执行图版本号与主链兼容  

**并发**  
检查点与对齐日志携带执行图版本号，按节点标识串行提交；版本冲突拒绝写回并触发重新对齐  

**补偿失败**  
补偿失败或外部不可补偿 → 停止补偿链 → 冻结节点 → 人工接管/安全降级  

## docx 映射

| md | docx style |
|---|---|
| `# 标题` | Title |
| `## 一…五` | Heading 1 |
| `### A/B/C` | Heading 2 |
| `D＝…` 独占行 | Normal 居中 |

自检：`Heading 2` 计数 = 3，且均以 `A、` `B、` `C、` 开头。

## 与 external skill 的关系

- `patent-review-fix-patterns` 在 external_dirs，autonomous `skill_manage` **不能** patch  
- 同类教训写入本文件 + `patent-run-ops` §15；源仓可写时再回灌 external