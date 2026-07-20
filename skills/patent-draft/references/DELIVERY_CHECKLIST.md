# 交付前总检查清单（DELIVERY_CHECKLIST）

在宣告「专利技术交底书已完成交付」之前逐项检查。可选步骤按「若触发则必须留痕/满足门禁」原则核对。

## 一、流程留痕

- [ ] `artifacts/run_manifest.md` 已创建并持续更新（当前步骤、门禁结果、关键工件路径）。
- [ ] `capability_profile` 已记录本轮能力探测结果。
- [ ] 初始化层源文件指纹与 `initialization_reused` 已记录。
- [ ] `research_scope_key` 与 `research_reused` 已记录。
- [ ] 若有降级或通道失败：`degraded_run` / `channel_failures` / `fallback_actions` 已如实记录。

## 二、领域与题名

- [ ] 用户未指定领域时：调研阶段已执行交叉领域发现，并给出推荐组合 + 证据 URL + 理由。
- [ ] 方向与题名已收敛且经用户确认；`final_title` ≤ 22 字，已写入 manifest（供文件命名）。

## 三、初始化层（可选步骤）

- [ ] 冷启动且用户提供模板/参考件时：已由 `patent-style` 完成预处理与工件固化，或已复用缓存（留痕）。

## 四、调研与查新

- [ ] 已向用户展示创新点研究摘要（含证据链 URL），`--gate research` 通过。
- [ ] 已向用户展示背景专利与审查包摘要，`--gate prior-art` 通过。
- [ ] 检索留有查询词清单、通道使用记录、URL 明细与失败原因。
- [ ] 中国专利候选与外围网页证据已明确区分，普通网页未计入最终专利结果集。

## 五、写作与审查门禁

- [ ] 5 部分全部完成且字数达标，`--gate draft` 通过。
- [ ] 一致性审计完成并展示摘要（评分 + 口径），报告落盘 `artifacts/audit/`。
- [ ] IPR 模拟审查完成并展示摘要（评分 + Top3 风险点），报告落盘 `artifacts/audit/`。
- [ ] 若有回改：`--gate review` 通过，且回改后已复跑审计/IPR 关键项并落盘复查报告。
- [ ] 交付语气检查：无解释腔、汇报腔、AI 生成腔（必要时已过 `patent-deslop`）。

## 六、附图与交付目录

- [ ] 交付目录为用户本轮明确指定的绝对路径（未指定时不得猜测）。
- [ ] 附图三件套齐全（详见 FIGURE_DELIVERY_CHECKLIST 全部条目）。
- [ ] 终稿 docx `word/media/` 非空（图片真嵌入）。
- [ ] 交付根目录只保留唯一正式 docx；旧版、修订版、`bak`、`trialbak`、`tmp`、评价件已清理。
- [ ] 过程性文档已下沉 `artifacts/`，未与正式终稿并列。

## 七、命名与交付

- [ ] 终稿命名：`<最终题名>技术交底书.docx`。
- [ ] `--gate deliver` 通过（健康报告落盘 `artifacts/delivery/`）。
- [ ] 若经 IM 渠道沟通：已发送终稿 docx 及「一致性评分 + IPR 评分 + Top3 风险」摘要。
