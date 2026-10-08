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

# patent-mine：存量项目反向挖掘（所有示例值均为合成占位符）

从「已经做出来的东西」里挖可专利点。产出与 [../patent/references/research-pack-contract.md](../patent/references/research-pack-contract.md) 完全同构，经 `--gate research` 后走既有管线（prior-art → draft → review → deliver），manifest 记 `research_origin: mine`。

**含密纪律（最高优先）**：项目内容视为机密。原始挖掘产物只存源项目 `<项目根>/.patent-private/`，**永不写入 run workspace**（run 的 `artifacts/` 会随交付下沉，含密件进去就是泄密通道）。

## 前置硬卡点：sensitive_map

开挖前检查 `<项目根>/.patent-private/sensitive_map.json`：

- 不存在或 `confirmed_by_user: false` → **先跳转 `patent-sanitize` 的 build-map 模式**，用户逐条确认固化后才回来开挖。无一例外。
- 声明用脚本写入而非手改 markdown（手写漏行/格式歪 = 全部脱敏检查静默失效）：
  ```
  python <patent-skill-dir>/scripts/init_run_manifest.py --update --out artifacts/run_manifest.md --research-origin mine --sensitive-map-path <map 绝对路径>
  ```
声明即强制两处兜底：mine 血统缺声明或 map 文件缺失时研究门禁直接 fail；使用 `workflow_cli.py` 时，`init/resume --sensitive-map <map 绝对路径>` 只登记路径引用，不读取、复制或哈希映射文件内容，map 不进入 `material_paths` / `material_hashes`。mine research 检查必须显式运行 `workflow_cli.py check --workspace <run workspace> --gate research --sensitive-map <manifest 中同一路径>`；缺少重选或路径不匹配时失败关闭、不读取 map，匹配后 validator 原位读取。其他外部路径和符号链接保护保持不变。

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

**可选公开对照检索**（通道按 [../patent/references/search-protocol.md](../patent/references/search-protocol.md)）：只在用户要求且明确批准本次外发后执行；按范围查找有助于比较的公开来源，不设来源数量目标，也不据此断言「没有现有技术」。逐条记录来源与局限。该项只作初步对照，正式查新仍由 patent-prior-art 的 prior-art 门禁完成。

**检索外发确认**：发送由案件材料派生的查询前，先向用户说明准确查询内容、目的地和用途，并取得本次明确确认；把确认写入 manifest。没有确认时不发送，记录外部检索不可用。使用通用表述并排除 map 中的代号、指标、路径、域名和客户信息只是额外防护，不能代替用户授权。

## Step 4：落盘含密原始产物

`<项目根>/.patent-private/mining_raw.json`：

```json
{
  "pack_type": "mining_raw",
  "project_root": "SYNTHETIC_PROJECT_ROOT",
  "scanned_at": "SYNTHETIC_TIMESTAMP",
  "scan_coverage": {"files_read": 0, "dirs_covered": [], "skipped": []},
  "candidate_points": [{
    "point_id": "SYNTHETIC_POINT_01",
    "dimension": "SYNTHETIC_DIMENSION",
    "title_seed_raw": "SYNTHETIC_TITLE_SEED",
    "technical_problem": "SYNTHETIC_TECHNICAL_PROBLEM",
    "solution_summary_raw": "SYNTHETIC_SOLUTION_SUMMARY",
    "non_obviousness_argument": "SYNTHETIC_ARGUMENT",
    "measurable_effect": "SYNTHETIC_EFFECT",
    "three_checks": {"problem_is_technical": true, "non_obvious": true, "effect_objective": true},
    "local_evidence": [{"path": "SYNTHETIC_LOCAL_PATH", "lines": "SYNTHETIC_LINE_RANGE", "note": "SYNTHETIC_NOTE"}],
    "public_baseline_check": [{"url": "https://example.invalid/synthetic-source", "excerpt": "SYNTHETIC_EXCERPT", "date": "SYNTHETIC_DATE", "verdict": "SYNTHETIC_VERDICT"}],
    "confidence": "high|medium|low"
  }],
  "rejected_points": [{"point_id": "MPx", "reason_code": "common_engineering|business_not_technical|unmeasurable", "note": "…"}]
}
```

## Step 5：脱敏出管线

1. 调 `patent-sanitize` apply：对候选点的全部文本字段做上位化改写（`sanitize_log.json` 留在含密区）。
2. 组装**同构 research pack** 写入 run workspace 的 `artifacts/research/phase_02_research_pack.json`：
   - research_questions：记录与用户范围相关且可回答的问题，不设条数目标；
   - outline_skeleton：按实际材料组织相关结构，不为凑齐预设章节扩写；
   - evidence：只记录经授权检索并实际取得的来源，按契约填写日期与核验状态；无来源时如实保留缺口并停止，不编造以通过门禁。local_evidence 含密，永不进 pack。
3. 泄密确定性自检（必过才许进管线）：
   ```
   python <patent-skill-dir>/scripts/validate_sanitize.py --map <项目>/.patent-private/sensitive_map.json --files artifacts/research/phase_02_research_pack.json
   ```
跑 `workflow_cli.py check --workspace <run workspace> --gate research --sensitive-map <manifest 中同一路径>`；匹配后再进入汇报与方向收敛。直接运行 `validate_sanitize.py --map ...` 的独立扫描也须由用户明确选择 map 路径；它读取原文件且不能替代清单路径匹配门禁。
5. 落选点经用户确认后入 vault 方向池（`origin: mine`，脱敏后表述，**必带 `origin_sensitive_map_path`**——add-direction 对缺失该字段的 mine 方向直接拒绝，血统不因入池中转而丢失）；vault 未初始化则按 patent-vault「未初始化引导」问一次，拒绝即跳过。

## 禁止事项

1. 含密件（mining_raw / sanitize_log / sensitive_map）不出 `.patent-private/`；汇报层不出现内部代号。
2. 不把常规工程实践包装成专利点——三问是一票否决不是打分项。
3. 快查不冒充查新；`public_baseline_check` 的 verdict 不得写成「无现有技术」这类查新结论。
4. 发现密钥/凭据类内容：立即提醒用户从源头移除并轮换，不纳入任何产物。
5. map 词条（内部代号/真实指标/路径/客户名）禁止出现在任何外发检索 query 里。
