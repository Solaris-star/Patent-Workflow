# 残留 medium 代改 + closest claims 升级（样本）

来源：2026-07-22 《一种面向工具调用幻觉的Agent结果核验方法及系统》复审后 residual 委托。

## 触发

用户点名：新颖性 mixed、创造性组合抗辩、模块改名、删除示例阈值（0.90/0.40）。

## Closest claims 抓取

```bash
# smart-search fetch 常 empty（tavily/firecrawl）
curl -fsSL --max-time 90 \
  "https://r.jina.ai/https://patents.google.com/patent/CN121009015A/zh" \
  -o artifacts/prior_art/details/CN121009015A_jina.md
```

必须看到 `## Claims` / `权利要求` 与独立权全文，才可标该篇 `claims_verified`。

## CN121009015A 对照摘要（样本）

| 本发明特征 | CN121009015A claims | 覆盖 |
|---|---|---|
| 旁路记录并放行后核验 | 执行前专家审核，可拒绝 | 部分/路径不同 |
| 提取 Agent 自述断言 | 无 | × |
| 独立真实系统观测源 | 无 | × |
| 三态比对 | 无 | × |
| 结果门禁/重试/补偿 | 指令链 + 异常回滚重载 | 部分（≠状态核验） |

## ipr_pack 最小更新字段

```json
{
  "evidence_granularity": "mixed",
  "claims_verified_refs": ["CN121009015A"],
  "ipr_upgrade_note": "closest 已 claims 级；其余仍摘要级",
  "review_patent_pool[].evidence_level": "claims_verified|abstract_or_description"
}
```

## 正文必改句（Agent 核验类）

1. 必要技术特征：独立观测源 + 不得以自述作为通过依据  
2. S4：采集通道与自述通道相互独立  
3. 模块：`调用旁路记录模块`（图2 同步）；保留 `拦截与重试模块`  
4. S5：删除 0.90/0.40，仅关键维度通过逻辑映射三态  

## 交付名

`<标题>技术专利交底书.md/.docx`（含「专利」）。