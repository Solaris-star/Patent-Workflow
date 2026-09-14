---
name: patent-style
description: |
  专利写作初始化层：模板/参考专利预处理 + 模板规范解析 + 参考专利风格提取 + 工件缓存。
  解析交底书模板产出 template_rules.json，分析参考专利产出 style_profile.md，
  一次初始化、长期复用（源文件指纹判断）。
  触发方式：/patent-style、「解析模板」「分析这篇专利的写作风格」「提取文档结构」
  「学习参考专利的行文方式」。冷启动或更换模板/参考件时由 patent 全流程编排调用。
---

# patent-style：模板解析与风格提取（初始化层）

把「项目初始化层」做成一次性投入：预处理源文件 → 解析模板规范 → 提取参考风格 → 固化为可复用工件。

## 缓存协议（先查后跑）

项目由 `(template_source, reference_patent_source)` 唯一确定。执行前先算源文件指纹（文件大小 + 修改时间，或内容哈希）并与 run manifest 的 `source_fingerprints` 比对：

- **指纹一致且四件工件齐全** → 直接复用，记 `initialization_reused: true`，本 skill 结束。
- 指纹变化 / 工件缺损 / 用户明确要求刷新 → 重跑对应部分，更新指纹。

可复用工件（统一放 `artifacts/style/`）：

| 工件 | 内容 |
|---|---|
| `template_outline.txt` | 模板抽取文本 |
| `reference_patent_text.txt` | 参考专利抽取文本 |
| `template_rules.json` | 模板写作规范（结构化） |
| `style_profile.md` | 参考专利风格画像 |

## Step 1：材料预处理

- `.docx` / `.md`：直接读取。
- `.pdf`：用宿主的 PDF 读取能力抽取全文（Claude Code 直接 Read；不支持的宿主用 `python -m pypdf` 等本地手段）。
- 抽取文本落盘为 `template_outline.txt` / `reference_patent_text.txt`。
- 用户未提供模板 → 记 `template_not_provided: true`；未提供参考专利 → 记 `reference_patent_not_provided: true`。两者都缺时本层整体跳过，下游 patent-draft 使用内置默认规范。

## Step 2：模板解析（产出 template_rules.json）

对模板逐章节提取：章节名称、写作目的、必须包含的要素、推荐结构、应避免事项、示例段落。

```json
{
  "templateName": "专利技术交底书模板",
  "sections": [
    {
      "name": "技术领域",
      "purpose": "界定专利保护的技术边界",
      "required": ["所属技术领域", "应用场景"],
      "structure": "1-2 段连贯文字",
      "avoid": ["列表形式", "过于宽泛的描述"],
      "example": "本发明涉及XX技术领域，尤其涉及一种……"
    }
  ],
  "globalRules": {
    "language": "规范书面语，避免口语化",
    "formatting": "章节编号用中文数字（一、二、三）"
  }
}
```

## Step 3：风格提取（产出 style_profile.md）

对参考专利提取六个维度，输出 Markdown 风格画像：

1. 各章节叙述方式（连贯段落 vs 列表）
2. 逻辑推进方式（问题→方案→效果）
3. 用语习惯（规范用语、连接词、转折方式，如「所述XX步骤包括…」「然而」）
4. 详略分配（技术方案 vs 实施方式篇幅比）
5. 实施例组织方式（按时间线 vs 按模块）
6. 句式特征（长短句比例、主动/被动语态）

```markdown
## 风格画像 - <参考专利号>

### 背景技术
- 连贯段落叙述，先描述现状，再引用具体专利（带段落号）
- 缺陷分析用「然而」「但是」转折，不用「其缺陷在于」

### 技术方案
- 先系统权利要求后方法权利要求；模块描述用「XX模块，用于…」

### 具体实施方式
- 2 个实施例（方法 + 系统）；方法按时间线、系统按架构层次叙述
```

## Step 4：收尾

1. 更新 run manifest：`source_fingerprints`、`initialization_reused: false`、四件工件路径。
2. 向用户展示解析摘要（章节数、关键风格发现），确认是否需要调整分析维度——用户无异议即结束，不设默认等待。

## 边界

- 本 skill 只产出规范与风格工件，不写正文（patent-draft 的职责）、不检索专利（patent-prior-art 的职责）。
- 长文档分段分析后汇总；非标准文档给通用结构分析并提示无法识别标准章节。
