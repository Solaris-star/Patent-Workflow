# Research Pack 输出契约

`patent-research` 与 `patent-research-cli` 的产出契约完全相同——门禁不关心调研是多子代理并行还是 CLI 一键完成。本文件是两者的唯一真源。

## 落盘工件（必须）

路径固定：`artifacts/research/phase_02_research_pack.json`

```json
{
  "pack_type": "research_pack",
  "phase": "phase_02",
  "research_questions": [
    { "id": "RQ1", "question": "当前行业主流方法是什么？" }
  ],
  "outline_skeleton": [
    {
      "section_id": "S1",
      "title": "背景与痛点",
      "intent": "说明现有技术缺陷",
      "covers_questions": ["RQ1"],
      "evidence_ids": ["E1", "E2"]
    }
  ],
  "evidence": [
    {
      "evidence_id": "E1",
      "url": "https://example.com/page",
      "excerpt": "从已抓取正文中摘录的原文片段，至少 50 个字符，能支撑对应结论……",
      "source_tier": "L2",
      "claim": "该证据支撑的主张",
      "date": "2026-05-01",
      "freshness": "fresh"
    }
  ]
}
```

**硬性字段要求**（`validate_research_pack.py` 逐项校验，缺一即 fail）：

| 字段 | 最低要求 |
|---|---|
| `pack_type` | 必须是 `"research_pack"` |
| `phase` | 必须是 `"phase_02"` |
| `research_questions` | ≥ 8 条，每条含非空 `id` + `question` |
| `outline_skeleton` | ≥ 5 节，每节含非空 `section_id` + `title` + `intent`；`covers_questions` / `evidence_ids` 引用的 ID 必须真实存在 |
| `evidence` | ≥ 8 条，每条含非空 `evidence_id` + http(s) `url` + ≥ 50 字符 `excerpt` |

`source_tier` / `claim` 为推荐字段；**`date` 与 `freshness` 为契约必填**（validator 暂不强制，但缺失即视为调研质量缺陷）：

- `date`：来源页面的发布/提交日期；确实无法确定时填 `"unknown"` 并降权，禁止猜测。
- `freshness`：按 `freshness_window`（默认 18 个月）分级——`fresh`（≤6 个月）/ `valid`（6 个月~窗口内）/ `stale`（超窗口）。
- **时效红线**：支撑「现状/前沿/竞品动向」类结论的证据必须是 `fresh`/`valid`；`stale` 证据只能作技术基线与历史背景，且必须显式标注。AI/自动驾驶等快演化领域严格执行 18 个月窗口。

## 汇报层输出（必须，Markdown）

在最终回复中给出（不进 JSON 门禁，供用户决策与 manifest 留痕）：

```markdown
## Research Scope
- objective / domain_scope / fixed_topic_or_title / application_scenario

## Channels
- channels_used / channel_failures / fallback_actions / degraded_run

## Evidence Table（≥ 3 行核心证据的人类可读摘要）
| Claim | Source URL | Tier | Confidence | Notes |

## Candidate Directions（2-3 个技术主轴明确不同的方向）
| Direction | Novelty | Practicality | Why It May Be Patentable |

## Recommendation
- recommended_direction / recommended_title_seed

## Needs Patent Verification
- claims_requiring_patent_verification（交给 patent-prior-art 核验的主张列表）
```

## 质量规则

1. 无固定题目时：先发散 3-7 个候选主题簇，收敛为 **2-3 个技术主轴明确不同**的候选方向；同一技术轴的轻微改写不得伪装成多个方向。
2. 有固定题目时：只产出该题目下的 2-3 个创新切入轴，不扩大范围。
3. 每个核心结论遵守 fetch_before_claim：结论必须能回指到 `evidence[]` 中已抓取的条目。
4. 主证据优先 L1-L2；L3-L4 只作补充线索。
5. 禁止编造专利号、论文、产品、日期、指标；禁止把未抓取验证的 URL 写入 `evidence[]`。

## 门禁命令

```
python <patent-skill-dir>/scripts/run_phase_gates.py --gate research --workspace . --manifest artifacts/run_manifest.md
```

通过后方可进入方向收敛与 patent-prior-art。
