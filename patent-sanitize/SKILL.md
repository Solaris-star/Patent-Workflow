---
name: patent-sanitize
description: |
  专利文本脱敏。机密项目信息进入公开专利文本前的三件套：build-map（扫描项目生成敏感词
  映射，用户逐条确认后固化）、apply（按映射上位化改写为专利语言）、audit（泄密扫描只报
  不改）。配套确定性门禁 validate_sanitize.py 挂入交付门禁。
  触发方式：/patent-sanitize、「脱敏」「泄密检查」「保密审查」「这篇能不能公开」
  「内部代号处理」。被 patent-mine 强制前置调用，patent-draft 交付前调用，也可独立使用。
---

# patent-sanitize：专利文本脱敏

**为什么必须**：专利申请文本会公开，一次泄密不可撤回。从机密项目挖掘的内容必须完成「内部信息 → 上位化专利语言」转换后才能进入撰写管线。

**核心边界**：上位化不等于删特征——技术特征保留，只抹具体实现指纹；「什么算机密」由用户裁决（build-map 只出建议稿，**用户逐条确认是唯一固化途径**，禁止全自动固化）。

## 数据位与保管纪律（硬规则）

含密件统一放源项目的 `<项目根>/.patent-private/`：

```
.patent-private/
├── sensitive_map.json    # 敏感词映射（本文件自身即含密件）
├── mining_raw.json       # patent-mine 的原始挖掘产物（如有）
└── sanitize_log.json     # apply 的替换留痕（原文→改后）
```

**三不原则**：不进 git（检查项目 `.gitignore` 是否含 `.patent-private/`，缺则仅提示用户添加）、不复制敏感映射进 run workspace、不进交付目录。`workflow_cli.py init/resume --sensitive-map <PATH>` 只把所选路径写入 run manifest，不读取、复制或计算映射文件内容哈希，也不把新选择的 map 纳入 `material_paths`、`material_hashes` 或 `material_registry`。workflow state 中的 `selection_path_sha256`（若存在）仅由所选路径字符串派生，不是文件内容哈希。mine 血统的 research 门禁，以及已声明敏感映射的 export 和 deliver 检查，都须显式重选与 manifest 一致的路径；缺参或路径不匹配时失败关闭，不读取 map。匹配后 validator 原位读取所选 map。此路径引用例外只适用于敏感映射，不放宽其他外部输入、相对路径或符号链接保护。

## 模式一：build-map（建映射）
1. **确定性信号扫描**（regex）：IPv4、域名、Windows/Unix 路径、邮箱、仓库/桶名。
2. **语义信号识别**（模型通读代码与文档）：内部系统/模块代号（非通用词的专名、花名、缩写）、客户/合作方名称、真实性能指标句（带具体数字的准确率/耗时/成本）、人名。
3. 产出**建议稿**：逐条列出 词条 / 类别 / 出现位置样例 / 建议动作，向用户展示。
4. **用户逐条确认**（keep / replace（给替换词）/ delete 条目）→ 固化为 sensitive_map.json。实际运行须由宿主针对当前 map 和范围取得用户确认；哈希只绑定内容和范围，不认证确认者身份。

以下 JSON 是**合成验证器结构示例**。confirmed_by_user: true 仅演示字段结构，confirmation_scope 明确标注为合成文档示例；不得复制此确认或哈希作为真实用户授权。生产 map 必须在用户逐条确认后按最终内容、范围和时间生成新的确认绑定。

```json
{
  "map_type": "sensitive_map",
  "schema_version": 1,
  "confirmed_by_user": true,
  "confirmation_scope": "synthetic-documentation-example-only; not a real user confirmation",
  "confirmed_at": "2026-10-08T00:00:00Z",
  "entries": [
    {
      "id": "SM-SYN-01",
      "term": "SYN-MODULE-ALPHA",
      "aliases": [
        "SYN-ALPHA"
      ],
      "category": "internal_codename",
      "action": "generalize",
      "match": "literal",
      "replacement": "所述示例处理模块",
      "case_sensitive": false
    },
    {
      "id": "SM-SYN-02",
      "term": "SYN-NETWORK-RANGE",
      "category": "infra",
      "action": "delete",
      "match": "regex",
      "pattern": "\\b198\\.51\\.100\\.(?:\\d{1,3})\\b"
    }
  ],
  "confirmation_sha256": "09f79fb934129f691e95d3aea5bc476b0101a7581919e5bbe96f9776c1442338"
}
```

类别：`internal_codename | client_name | infra | person_name | real_metric | other`；动作：`generalize | delete | mark_exemplary（仅用于与真实申请材料明确隔离、显著标注为合成的文档/测试示例；不得用于保留或重标真实未核实数值）`。

## 模式二：apply（上位化改写）

输入：文本/JSON + 已确认的 map。按上位化规则表逐条改写（规则单一真源：[references/generalization-rules.md](references/generalization-rules.md)），核心原则：

| 类别 | 默认动作 |
|---|---|
| 内部系统/模块代号 | → 功能性上位词（SYN-MODULE-ALPHA → 所述示例处理模块），**全文一致** |
| 具体阈值/魔法数 | → 「预设阈值」「预设时长」 |
| 真实项目指标 | 只有来源可追溯且已获授权时才能保留；否则删除，文档示例改用明显标注的合成占位值。不得把真实但未经核实的数据改标为「示例性数据」后保留。 |
| 客户名/合作方 | → 「第三方平台」「外部系统」 |
| 域名/IP/路径/仓库名 | → 删除或「远程服务端」「本地存储」 |
| 人名 | → 删除或「操作人员」 |

产出：脱敏后文本 + `sanitize_log.json`（每条替换的 entry_id / 位置 / 原文→改后，**只写 `.patent-private/`**）。改写后立刻用 validate_sanitize 自检一遍（词条残留 = 改写不合格）。

## 模式三：audit（泄密扫描，只报不改）

- **有 map**：`python <patent-skill-dir>/scripts/validate_sanitize.py --map <map> --files <文件…>`（或 `--scan-dir <目录>`），输出 JSON 摘要；每条 map 命中仅含 `target_index`、`entry_index` 和 `match_count`，不含命中词、文件路径或上下文摘录。
- **无 map**（独立场景「帮我查这篇有没有泄密」）：加 `--heuristics` 运行内置 IP/域名/路径/邮箱等规则；`heuristicHits` 仅含目标索引、命中类别和数量，不含命中内容、文件路径或上下文。规则检查不作语义判断或泄漏裁决，只提供人工复核提示。

- validator 的 passed / checks_passed 与 confirmation_binding_valid 只报告结构、确认绑定和已登记词条扫描结果；启发式命中为提示。零命中不等于语义泄密审查、人工保密复核或法律认证，所需人工复核仍须实际完成。

## 清单驱动的映射检查

`validate_sanitize.py`（stdlib-only，与家族 validator 同风格）：`.md/.mmd/.txt/.json/.drawio` 直扫，`.docx` 用 zipfile 解包扫 `word/` 下全部 xml；**目标文本 ∩ map 词条（含 aliases 与 regex pattern）= 空集才 pass**，exit 0/2 + JSON summary。

manifest 已记录 output_dir、final_markdown_path 与题名时，先导出，再单独检查完整交付包：

```
python <patent-skill-dir>/scripts/workflow_cli.py export --workspace <run workspace> --sensitive-map <与 manifest 记录一致的 map 绝对路径>
python <patent-skill-dir>/scripts/workflow_cli.py check --workspace <run workspace> --gate deliver --sensitive-map <同一路径>
```

**manifest 声明与旧副本**：可用 `workflow_cli.py init/resume --sensitive-map <绝对路径>` 将路径引用写入清单；`init_run_manifest.py --update --sensitive-map-path <路径>` 仍可用于直接写入字段。mine 血统的 research 门禁以及已声明映射的 export、deliver 检查都必须显式传入与清单相同的 `--sensitive-map` 路径。export 会重新验证当前内容及确认绑定，并对最终 Markdown 和生成的 DOCX 分别扫描；缺少重选或路径不匹配时在读取 map 前失败，匹配后 validator 才原位读取。导出成功只代表生成 DOCX，状态仍为 `generated_pending_delivery_check`；随后 deliver 门禁才做整包检查，LibreOffice 渲染不可用时记为 `not_run` 且流程未完成。旧 run 目录若留有旧版复制的 map（例如 `inputs/registered/sensitive_map/`）或旧的 `material_paths.sensitive_map` 记录，不会自动清理。需要先由用户确认并人工审视，再另行决定是否移除；不得自动删除。

## 与家族的接口

1. **patent-mine（强制卡点）**：无已确认 map 不开挖；`mining_raw.json` → apply → 同构 research pack → validate_sanitize 过检后才准进 `--gate research`。
2. **patent-draft（交付前）**：涉密 run 导出前**必须**跑一次 audit 并人工过目（非建议）；export 和之后的 deliver 门禁都带 `--sensitive-map`。
3. **独立使用**：任意专利文本的泄密检查/脱敏改写，随叫随到。

## 边界与局限

- **validate_sanitize 是字面词表交集检查**——同义改写、英文缩写、拼音变体，以及「架构拓扑/参数组合本身即密」的语义级泄密均不在其能力内；map 没登记的概念它也查不出。「确定性 pass」只等于「词条零残留」，不等于安全。补偿手段：build-map 阶段宁多勿漏（把变体全录进 aliases），涉密 run 交付前的 audit 人工过目是**必做步骤而非建议**。
- 不改技术方案实质；术语改写须与 facts_ledger.terminology 同步（由调用方负责登记上位词）。
- **图片像素内的文字无法确定性扫描**——附图源文件（.mmd/.drawio 为文本可扫）覆盖大部分风险；成品 png/svg 中的文字在宿主有视觉能力时由 audit 模式人工看图兜底，此局限必须向用户明示。
- 本 skill 不保管密钥/凭据类内容——发现 API key/密码直接要求用户从源头移除并轮换，不做「脱敏后保留」。
