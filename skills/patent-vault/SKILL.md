---
name: patent-vault
description: |
  专利选题库与多案资产管理。跨 run 持久索引：research 落选方向进方向池下轮复用、
  已写题名登记与新题撞车检测、多案状态视图（写作中/审查中/已交付/OA 中）、交付历史。
  触发方式：/patent-vault、「方向池」「选题库」「挑个方向」「我的案子」「写过哪些题」
  「查重」「撞车检测」「案件状态」「交付历史」。被 patent 路由与 patent-research 挂钩调用；
  vault 未初始化时全家族对接点静默跳过，零影响。
---

# patent-vault：选题库与多案管理

跨 run 的持久资产索引。**只登记不执行**：不做调研/检索/写作；查重脚本只粗筛、语义裁决归模型；不存含密内容（mine 来源方向必须以脱敏后表述入池）。与 story 家族 `.active-book` 的差异：patent 每案独占一个 workspace，vault 是索引不是切换器。

## 数据位与探测

数据根三级解析（`vault.py` 内置，全平台一致）：`--vault-dir` 参数 → 环境变量 `PATENT_VAULT_DIR` → `~/.patent-vault/redirect.txt` 重定向 → 默认 `~/.patent-vault/`。

```
~/.patent-vault/
├── directions_pool.json     # 方向池
├── cases.json               # 案件登记（vault 内题名的唯一真源）
├── titles_used.json         # 仅存 vault 体系外导入的历史题名
└── research_snapshots/      # 落选方向对应的 research pack 整包快照
```

探测 = `cases.json` 存在且可解析，一轮 workflow 只探测一次。首次启用：`python <本 skill>/scripts/vault.py init`。

**未初始化引导（本节是家族唯一真源，其他 skill 遇未初始化按此处理）**：

- **用户主动进入本 skill**（/patent-vault 或方向池/查重/案件类意图）→ 不报错：说明「vault 未初始化；init 只在 `~/.patent-vault/` 建三个 JSON 索引文件，不影响任何现有 run」并询问，同意 → `vault.py init` 后**继续用户原本要做的操作**，拒绝 → 结束并说明该功能 init 前不可用。
- **其他 skill 的挂钩点**（patent 开局探测、research/mine 落选方向入池等）→ **每 run 只问一次**：「要不要初始化选题库？落选方向可积累复用，下轮直接挑；跳过不影响本轮流程」。同意 → init 后照常执行挂钩；拒绝 → 本轮余下挂钩全部静默跳过，有 manifest 时记 `vault_opted_out: true`（后续步骤见此标记不再问）。
- **存在但不可解析**（文件损坏）→ 不适用本节：如实报错待用户处置，**禁止自动重建覆盖**。

## 四类操作

### 1. 方向池

- **登记落选方向**（patent-research 收敛后挂钩）：用户确认方向后，把**未选中**的候选经用户同意入池——先把本轮 research pack 复制为 `research_snapshots/<run_id>.json`，再逐个 `vault.py add-direction --json-file <临时json>`（字段：title_seed / summary / domain_scope / origin: research|mine / source_run{run_id, workspace, research_snapshot} / rejected_reason / key_evidence）。**含中文的 JSON 一律走 `--json-file` 而非 stdin 管道**（避免控制台编码污染）；**mine 来源必须已脱敏**。
- **时效**：`valid_days` 默认 180 天（方向池存的是「机会空隙判断」，比 research pack 的 30 天证据窗口宽）；`list --pool` 时现算状态 available/expired。
- **挑选入 run**：`vault.py pick-direction <id> --target-workspace <新 workspace>` —— 快照自动复制为新 workspace 的 `artifacts/research/phase_02_research_pack.json`，照常过 `--gate research`（门禁零特例）；manifest 记 `research_origin: vault_pool`、`research_reused: true`。挑选动作本身即完成「方向收敛」停顿。
- **过期方向不禁选但强制复核**：`revalidation_required: true` 时，以该方向为 fixed_topic 跑一轮 patent-research 定向复核（重验现状类证据）后才进 prior-art；复核通过用 add-direction 同结构更新 `revalidated_at`。

### 2. 题名撞车检测

```
python <本 skill>/scripts/vault.py check-title "一种基于意图仲裁的接管方法"
```

脚本做**粗筛**（题名归一化：去套话词「一种/方法及系统」等 + bigram Jaccard ≥ 0.35，查重域 = cases ∪ titles_used ∪ 方向池），输出 `collision_candidates`。**模型必须对候选做语义终裁**（技术主轴是否同一），粗筛宁松勿紧——脚本报 0 候选也不代表语义上无撞车，高风险领域可再人工列近期题名核对。撞车结论向用户明示后再定题。

时机：方向收敛定工作题名时（patent 编排挂钩）+ 用户随时手动查。

### 3. 案件登记与状态流转

状态机：`direction_selected → prior_art → drafting → in_review → delivered → oa_pending → oa_replied`，旁路 `abandoned`。

- 方向确认后：`vault.py register-case`（stdin JSON：title / domain_scope / workspace / run_id / output_dir / direction_id）。
- 每过一个门禁顺带：`vault.py update-case <case_id> --status <新状态> --event gate_<name>_passed`（patent 编排纪律的一部分，vault 缺席时跳过）。
- 交付时：`--status delivered --set delivered_at=<日期> --set deliverable=<docx 路径>`。

### 4. 查看

```
vault.py list --pool [--status available]    # 方向池（含现算时效）
vault.py list [--status drafting|delivered]  # 案件视图
vault.py import-titles                       # stdin 批量导入 vault 启用前的历史题名
```

## 入池纪律（硬规则）

1. mine 来源方向：入池表述必须是脱敏后版本（含密表述只存在于源项目 `.patent-private/`）。
2. 方向 ≠ 题名：入池的是技术主轴（title_seed 是种子不是定稿题名），定稿题名只登记在 cases。
3. 入池经用户确认——落选方向也可能含用户不想留档的内容，逐条列出待确认后写入。
4. 并发注意：vault.py 全部原子写，但两个会话同时改同一文件仍可能互覆——多会话并行写专利时错开 vault 写入时机。

## 边界

不做语义查重终裁（模型职责）、不做调研执行（research/mine 职责）、不做 workspace 内容管理（各 run 自治）、不存储任何含密原文。
