# 题名与审查汇报坑（本会话提炼）

## 坏题名 vs 好题名

坏（28 字，用户当场打回）：
`一种多乘客并发意图下的分层资源仲裁与可回退执行方法及系统`

好（13 字，用户确认）：
`一种车载多音区指令仲裁方法`

样例字数锚点（已采专利）：
- 车载音频焦点的仲裁方法及装置 → 14
- 智能座舱的语音交互方法及系统 → 14
- 车载多音区语音交互系统及方法 → 14

规则：≤22；先数再报；对齐样例；少术语。

## 方向讲解

- 三行：场景 → 系统做什么 → 输出什么
- **禁止**「不是 A 而是 B」及同类对比腔

## 审查「残余」话术

用户委托 high 代改后，若只说「还有 medium 残余」会被理解成 **没改完**。

正确拆分：
1. 委托 high 正文项：已/未解决（逐条）
2. abstract_only / mixed 等证据边界：与正文脱钩
3. 未委托的 medium/low：标明范围外

## `/patent-review` 上传稿（2026-07-22）

- 权威 = 用户上传 docx，不是案件旧 md
- 旧 phase_08/09 禁止照抄；推翻高分要一句话说明原因
- 公司模板 A1/B1/「专利附图」≠ 自动 high；真 high = 裸 mermaid、三态图文、背景集合、时序、上下位漂移
- mixed 粒度新颖性不得无条件通过
- 完整子代理 JSON 读 `~/.hermes/cache/delegation/subagent-summary-*.txt`
- 会话样本：`review-session-agent-verify.md`

## 附图

- 只强制 mmd 入 part_04；mmd 即编辑源
- 不强制 drawio；png 仅嵌图
- 用户说「为什么还要 drawio」= 先核现行门禁，勿用旧三件套口径顶嘴

## smart-search 空 sources

现象：`ok=true` 但 `sources_count=0`，只有 content 综述。
处理：查询强制要 URL + `--parallel`；fetch 挂了用 jina/直连。详见 smart-search-patent.md。
