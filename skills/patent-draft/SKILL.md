---
name: patent-draft
description: |
  专利交底书分块撰写与交付出稿引擎。从 5 部分分块写作（技术领域/背景技术/发明内容/
  附图说明/具体实施方式）到附图三件套、docx 合并嵌图、命名清理、交付健康检查的完整链路。
  触发方式：/patent-draft、「写交底书」「分块撰写」「生成docx」「导出终稿」「出附图」
  「修改第X部分」。可独立使用（含只导出场景：已有 md 帮我出 docx），
  也被 patent 全流程编排在写作与交付两步调用。
---

# patent-draft：分块撰写与交付出稿

两段式入口，按用户意图或流程位置进入：

- **写作段**：分块写 5 部分 + facts_ledger + 附图三件套 → `--gate draft`
- **导出段**：docx 合并 + 嵌图 + 命名 + 清理 → `--gate deliver`（全流程中在 patent-review 通过后执行）

交付细则清单见 [references/DELIVERY_CHECKLIST.md](references/DELIVERY_CHECKLIST.md) 与 [references/FIGURE_DELIVERY_CHECKLIST.md](references/FIGURE_DELIVERY_CHECKLIST.md)，宣告完成前逐项过。

## 写作段

### 装配写作输入

开写前收齐（缺项按注明方式降级）：

| 输入 | 来源 | 缺失时 |
|---|---|---|
| 选定方向 + 工作题名 | run manifest | 询问用户 |
| background_pack（≥2 篇已验证专利 + closest_prior_art + major_differences） | patent-prior-art | **阻塞**——背景技术必须引用已验证专利，不得编造 |
| template_rules.json / style_profile.md | patent-style | 用内置默认规范（本文件的结构与用语规则） |
| research_pack 的 outline_skeleton 与 evidence | patent-research | 仅影响素材丰富度，不阻塞 |

### 写作前检查（一次完成）

1. **选题合理性**：应用场景真实存在、方案安全合规。
2. **差异化**：与 background_pack 中专利的技术特征重复度 ≤ 30%，区别特征能落到 major_differences。
3. **创新示例真实性**：列举的创新示例先想清楚现有技术是否已实现、真实场景是否存在，不编造伪创新。
4. **题名校核**：发明名称 ≤ 25 字。

### 5 部分结构与字数（专利模式固定，不生成权利要求书——那是代理师的活）

| 分块 | 文件 | 字数 |
|---|---|---|
| 一、技术领域 | `part_01_技术领域.md` | 50-100 |
| 二、背景技术 | `part_02_背景技术.md` | 300-800 |
| 三、发明内容 | `part_03_发明内容.md` | 1200-2000（其中技术方案 800-1500） |
| 四、附图说明 | `part_04_附图说明.md` | 100-300（不含 Mermaid 代码块） |
| 五、具体实施方式 | `part_05_具体实施方式.md` | 1500-3000 |

**默认连续生成全部 5 块再统一交 patent-review**；用户明确要求逐块确认时才逐块停。每块生成后立即落盘并同步更新 facts_ledger，字数不达标当场重写或扩写。

### 分部规范（精编）

**背景技术**：引用 background_pack 中 2-3 篇已验证专利，格式「中国发明专利 CNxxxxxxA（公开日 xxxx 年 xx 月 xx 日，申请人：xxx）公开了……」；缺陷分析用「然而/同时/此外」转折，禁用「其缺陷在于/缺点是」；连贯段落，禁列表。

**发明内容**：要解决的技术问题 → 技术方案 → 有益效果。技术方案逐特征写实现方式、模块/步骤间连接关系与数据流，禁笼统描述；有益效果必须能回指技术特征，禁无实验支撑的编造数据（如「准确率 91%」）——确需数据时标注「示例性数据，需实际测试」。

**附图说明**：每张图一句「图 X 为……」；**紧跟该图的 Mermaid 源码可见代码块**（渲染异常时的兜底，门禁校验此项）。

**具体实施方式**：只写 2 个实施例——方法实施例（结合流程图按步骤展开，每步含实现细节与嵌入式示例）+ 系统实施例（结合架构图写模块组成/连接/工作原理）；用「本发明实施例提供……」「本发明实施例还提供……」连贯段落，禁「实施例一、实施例二」列表体；实施例必须与本发明技术领域直接相关，禁止从参考专利搬运无关示例；结尾固定套话「以上所述，仅为本发明的具体实施方式，但本发明的保护范围并不局限于此……」。

**全文用语**：专利规范用语（「所述」「本实施例」「其特征在于」），禁对外文档用语（「进一步」「客户」「贵方」）；术语全文统一（登记进 facts_ledger.terminology）。

### facts_ledger（持续落盘 `artifacts/draft/facts_ledger.json`）

```json
{
  "ledger_type": "facts_ledger",
  "terminology": [{"term": "意图仲裁模块", "aliases": [], "definition": "……"}],
  "figure_registry": [{
    "figure_id": "图1",
    "caption": "系统架构图",
    "artifacts": {
      "image": "附图/fig_01_系统架构.png",
      "mmd": "附图/fig_01_系统架构.mmd",
      "editable": ["附图/fig_01_系统架构.drawio"]
    },
    "mermaid_source_embedded_in_docx": true
  }],
  "constraints_and_effects": [{"constraint": "……", "effect": "……", "source_part": "part_03"}]
}
```

每写/改一个 part 同步更新，不得最后补账。门禁 `--gate draft` 校验：三区非空、图三件套文件真实存在、mermaid 内嵌标记为 true。

### 附图三件套（写作段内完成，零 CLI 依赖可达成）

每张图三个文件同前缀存放 `附图/`（`fig_01_XXX.*`），禁止另设 final/、drawings/ 等目录：

1. **`.mmd`**（逻辑源，必须）：`graph TD/LR` 开头，节点 ID 用字母数字（A1、B2），避免 `subgraph`/`style`（ProcessOn 兼容）；同时以可见代码块嵌入 part_04。
2. **`.drawio`**（可编辑源，必须）：**由模型直接生成 draw.io XML 文件**（mxGraph 格式为公开纯文本，无需任何 CLI）；节点布局给出明确坐标，白底黑字。
3. **`.png`/`.svg`**（嵌图文件，必须）：能力梯度——本机 `mmdc` 可用（`mmdc -i fig.mmd -o fig.png -b white`）→ 优先；不可用则从 `.drawio`/在线渲染兜底；全部不可行时明确告知用户需手工渲染这一步，**不得静默跳过**。

复杂流程图（多分支/多回路）不信任 Mermaid 自动布局的成品质量：以 `.drawio` 为成品真源导出图片，`.mmd` 仅作逻辑兜底。图号、文件名、正文「如图X所示」、part_04 描述四者一一对应（联动规则见 FIGURE_DELIVERY_CHECKLIST）。

### 联动修改与版本

- 单块修改 > 100 字 → 分析对其余 part 的跨块影响（新技术特征？方案变更？图需更新？），输出联动修改建议清单待用户确认。
- 每次修改前把当前版本备份到 `versions/`（保留近 5 版），支持回滚。

## 导出段

前置：全流程中须 `--gate review` 已通过；独立使用（用户只要出稿）时提示未审查风险后可继续。

1. **合并**：按序拼接 5 个 part，附图说明保留每图的 Mermaid 代码块；插入正文图引用。
2. **生成 docx**（能力梯度）：宿主 docx 能力（如 Claude Code 的 docx skill / python-docx / pandoc，按可用性择一）；标题样式统一，附图图片真实嵌入对应位置。
3. **命名**：`<最终题名>技术交底书.docx`，题名来自 run manifest 的 `final_title`，禁止占位名。
4. **交付结构**：交付根目录唯一正式 docx + `附图/`（三件套）+ `artifacts/`（过程件下沉）；旧版/修订版/`bak`/`tmp`/评价件 docx 全部清理，过程性 .md 默认保留在 `artifacts/` 供追溯（用户要求洁净交付时归档进 `artifacts/archive/`）。
5. **健康检查门禁**：
   ```
   python <patent-skill-dir>/scripts/run_phase_gates.py --gate deliver --workspace . --deliver-dir "<交付目录>" --patent-title "<最终题名>" --manifest artifacts/run_manifest.md
   ```
   自动校验：文件名匹配、docx `word/media/` 非空（图真嵌入）、审计/IPR 报告存在、图三件套齐全。未过先自查修复重跑。
6. **可选 IM 交付**：用户经 Discord/飞书等渠道沟通时，发送终稿 docx + 「一致性评分 + IPR 评分 + Top3 风险」摘要。
