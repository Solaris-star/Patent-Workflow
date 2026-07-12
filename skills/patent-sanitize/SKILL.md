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

**三不原则**：不进 git（检查项目 `.gitignore` 是否含 `.patent-private/`，缺则提示用户添加——只提示不代改）、不复制进 run workspace、不进交付目录。门禁与 audit 通过路径引用读取。

## 模式一：build-map（建映射）

1. **确定性信号扫描**（regex）：IPv4、域名、Windows/Unix 路径、邮箱、仓库/桶名。
2. **语义信号识别**（模型通读代码与文档）：内部系统/模块代号（非通用词的专名、花名、缩写）、客户/合作方名称、真实性能指标句（带具体数字的准确率/耗时/成本）、人名。
3. 产出**建议稿**：逐条列出 `词条 / 类别 / 出现位置样例 / 建议动作`，向用户展示。
4. **用户逐条确认**（keep / replace（给替换词）/ delete 条目）→ 固化为 `sensitive_map.json`（`confirmed_by_user: true`）。未经确认的 map（`confirmed_by_user: false`）**禁止用于 apply**。

```json
{
  "map_type": "sensitive_map",
  "schema_version": 1,
  "confirmed_by_user": true,
  "entries": [
    {
      "id": "SM1",
      "term": "Phoenix-Gateway",
      "aliases": ["phoenix-gw", "凤凰网关"],
      "category": "internal_codename",
      "action": "generalize",
      "match": "literal",
      "replacement": "所述接入网关模块",
      "case_sensitive": false
    },
    {
      "id": "SM2",
      "term": "内网网段",
      "category": "infra",
      "action": "delete",
      "match": "regex",
      "pattern": "\\b10\\.(?:\\d{1,3}\\.){2}\\d{1,3}\\b"
    }
  ]
}
```

类别：`internal_codename | client_name | infra | person_name | real_metric | other`；动作：`generalize | delete | mark_exemplary`。

## 模式二：apply（上位化改写）

输入：文本/JSON + 已确认的 map。按上位化规则表逐条改写（规则单一真源：[references/generalization-rules.md](references/generalization-rules.md)），核心原则：

| 类别 | 默认动作 |
|---|---|
| 内部系统/模块代号 | → 功能性上位词（「Phoenix-Gateway」→「所述接入网关模块」），**全文一致** |
| 具体阈值/魔法数 | → 「预设阈值」「预设时长」 |
| 真实性能指标 | → 删除，或保留量级并标「示例性数据，需实际测试」（与 patent-draft 数据真实性规则同源） |
| 客户名/合作方 | → 「第三方平台」「外部系统」 |
| 域名/IP/路径/仓库名 | → 删除或「远程服务端」「本地存储」 |
| 人名 | → 删除或「操作人员」 |

产出：脱敏后文本 + `sanitize_log.json`（每条替换的 entry_id / 位置 / 原文→改后，**只写 `.patent-private/`**）。改写后立刻用 validate_sanitize 自检一遍（词条残留 = 改写不合格）。

## 模式三：audit（泄密扫描，只报不改）

- **有 map**：`python <patent-skill-dir>/scripts/validate_sanitize.py --map <map> --files <文件…>`（或 `--scan-dir <目录>`），输出违规清单（词条/文件/上下文摘录）。
- **无 map**（独立场景「帮我查这篇有没有泄密」）：加 `--heuristics` 跑内置 IP/域名/路径/邮箱模式 + 模型对可疑代号与真实指标句做语义判断。输出定位为**建议清单**而非裁决——交底书正文本就不该出现任何 URL/IP/路径，启发式命中即值得人工过目。

## 确定性门禁（deliver 挂钩）

`validate_sanitize.py`（stdlib-only，与家族 validator 同风格）：`.md/.mmd/.txt/.json/.drawio` 直扫，`.docx` 用 zipfile 解包扫 `word/` 下全部 xml；**目标文本 ∩ map 词条（含 aliases 与 regex pattern）= 空集才 pass**，exit 0/2 + JSON summary。

交付门禁约定：

```
python <patent-skill-dir>/scripts/run_phase_gates.py --gate deliver … --sensitive-map <项目>/.patent-private/sensitive_map.json
```

**manifest 声明即强制**：run manifest 写了非空 `sensitive_map_path` 而 deliver 门禁未带 `--sensitive-map` → 门禁直接 fail（防「忘带参数静默漏检」）。未涉密的 run 不写该字段，行为与从前完全一致。

## 与家族的接口

1. **patent-mine（强制卡点）**：无已确认 map 不开挖；`mining_raw.json` → apply → 同构 research pack → validate_sanitize 过检后才准进 `--gate research`。
2. **patent-draft（交付前）**：涉密 run 交付前跑一次 audit；deliver 门禁带 `--sensitive-map`。
3. **独立使用**：任意专利文本的泄密检查/脱敏改写，随叫随到。

## 边界与局限

- 不改技术方案实质；术语改写须与 facts_ledger.terminology 同步（由调用方负责登记上位词）。
- **图片像素内的文字无法确定性扫描**——附图源文件（.mmd/.drawio 为文本可扫）覆盖大部分风险；成品 png/svg 中的文字在宿主有视觉能力时由 audit 模式人工看图兜底，此局限必须向用户明示。
- 本 skill 不保管密钥/凭据类内容——发现 API key/密码直接要求用户从源头移除并轮换，不做「脱敏后保留」。
