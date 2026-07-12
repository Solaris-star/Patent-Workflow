---
name: patent-mine
description: |
  存量项目反向挖掘专利点。从用户现有项目（代码/README/技术文档）按七维框架挖掘候选
  专利点，经三问检验与公开对照快查后，强制脱敏输出与 research pack 同构的工件，
  直接接入查新→写作既有管线。
  触发方式：/patent-mine、「从项目挖专利」「这个项目能申请什么专利」「反向挖掘」
  「代码里找创新点」「挖掘专利点」。区别于 patent-research 的「领域→方向」正向调研，
  本 skill 做「资产→挖掘」。
---

# patent-mine：存量项目反向挖掘

从「已经做出来的东西」里挖可专利点。产出与 [../patent/references/research-pack-contract.md](../patent/references/research-pack-contract.md) 完全同构，经 `--gate research` 后走既有管线（prior-art → draft → review → deliver），manifest 记 `research_origin: mine`。

**含密纪律（最高优先）**：项目内容视为机密。原始挖掘产物只存源项目 `<项目根>/.patent-private/`，**永不写入 run workspace**（run 的 `artifacts/` 会随交付下沉，含密件进去就是泄密通道）。

## 前置硬卡点：sensitive_map

开挖前检查 `<项目根>/.patent-private/sensitive_map.json`：

- 不存在或 `confirmed_by_user: false` → **先跳转 `patent-sanitize` 的 build-map 模式**，用户逐条确认固化后才回来开挖。无一例外。
- 把 `sensitive_map_path`（绝对路径）写入 run manifest——这会激活 deliver 门禁的脱敏强制检查（声明即强制）。

## Step 1：项目侦察

1. 读 README / docs / 架构说明（理解项目做什么、技术栈、模块版图）。
2. 定位创新密度高的区域：入口与核心流程文件、名字里带 scheduler/pipeline/fallback/cache/arbiter/sync 类关键词的模块、注释里写着「trick / hack / 优化 / 特殊处理」的地方。
3. 按 [references/mining-dimensions.md](references/mining-dimensions.md) 的信号清单定向深读。
4. **大仓库能力梯度**（>千级文件）：宿主支持并行子代理时，按目录分片派发「素材提取员」（只提取候选信号：文件/行号/机制摘要，**不做维度裁决**），主模型统一裁决；无并行能力则按目录分批顺序读。

## Step 2：七维挖掘

对照七维框架逐维过一遍项目（细则与信号清单见 references/mining-dimensions.md）：

架构组合 / 数据流策略 / 调度协同 / 降级容错 / 交互方式 / 性能手段 / 跨域移植。

每个候选点记录：所属维度、解决的技术问题、方案机制摘要、本地证据（文件+行号）。

## Step 3：三问检验 + 公开对照快查

**三问一票否决**（任一不过即淘汰进 rejected_points，注明理由）：

1. 解决的是**技术**问题，而非业务/管理/流程问题？
2. 手段**非显而易见**——本领域技术人员按常规做法不会自然走到这一步？（常规工程拼装直接淘汰）
3. 效果**可客观描述**——可测量、可对比、不依赖编造数据？

**公开对照快查**（存活点逐个做，通道按 [../patent/references/search-protocol.md](../patent/references/search-protocol.md)）：每点检索 2-3 条公开证据（论文/竞品文档/开源实现/技术博客），抓取正文确认「公开世界还没有一模一样的做法」或找出最接近的公开方案作差异锚点。快查 ≠ 正式查新——正式查新仍由 patent-prior-art 在下一步完成。

## Step 4：落盘含密原始产物

`<项目根>/.patent-private/mining_raw.json`：

```json
{
  "pack_type": "mining_raw",
  "project_root": "…",
  "scanned_at": "…",
  "scan_coverage": {"files_read": 0, "dirs_covered": [], "skipped": []},
  "candidate_points": [{
    "point_id": "MP1",
    "dimension": "degradation_fallback",
    "title_seed_raw": "（含内部代号的原始表述）",
    "technical_problem": "…",
    "solution_summary_raw": "…（含真实路径/代号/指标）",
    "non_obviousness_argument": "…",
    "measurable_effect": "…",
    "three_checks": {"problem_is_technical": true, "non_obvious": true, "effect_objective": true},
    "local_evidence": [{"path": "src/…", "lines": "40-88", "note": "…"}],
    "public_baseline_check": [{"url": "https://…", "excerpt": "≥50 字符…", "date": "…", "verdict": "…"}],
    "confidence": "high|medium|low"
  }],
  "rejected_points": [{"point_id": "MPx", "reason_code": "common_engineering|business_not_technical|unmeasurable", "note": "…"}]
}
```

## Step 5：脱敏出管线

1. 调 `patent-sanitize` apply：对候选点的全部文本字段做上位化改写（`sanitize_log.json` 留在含密区）。
2. 组装**同构 research pack** 写入 run workspace 的 `artifacts/research/phase_02_research_pack.json`：
   - `research_questions`（≥8）：由各候选点的三问展开（每点 2-3 问）；
   - `outline_skeleton`（≥5）：按「背景痛点 / 现有公开方案 / 候选方案 / 差异 / 效果」组织；
   - `evidence`（≥8）：**全部来自公开对照快查的 http URL 证据**（3-5 点 × 2-3 条自然达标，带 date/freshness）——`local_evidence` 含密，永不进 pack。
3. 泄密确定性自检（必过才许进管线）：
   ```
   python <patent-skill-dir>/scripts/validate_sanitize.py --map <项目>/.patent-private/sensitive_map.json --files artifacts/research/phase_02_research_pack.json
   ```
4. 跑 `--gate research`；通过后输出汇报层（候选点表：维度 / 三问结论 / 公开对照结论 / 推荐排序，**全部用脱敏后表述**），进入方向收敛。
5. 落选点经用户确认后入 vault 方向池（`origin: mine`，脱敏后表述）；vault 未初始化则按 patent-vault「未初始化引导」问一次，拒绝即跳过。

## 禁止事项

1. 含密件（mining_raw / sanitize_log / sensitive_map）不出 `.patent-private/`；汇报层不出现内部代号。
2. 不把常规工程实践包装成专利点——三问是一票否决不是打分项。
3. 快查不冒充查新；`public_baseline_check` 的 verdict 不得写成「无现有技术」这类查新结论。
4. 发现密钥/凭据类内容：立即提醒用户从源头移除并轮换，不纳入任何产物。
