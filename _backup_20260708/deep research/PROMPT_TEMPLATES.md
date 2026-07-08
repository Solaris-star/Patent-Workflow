# Deep Research Prompt Templates

## 1) User Request Template

**Topic**: <topic or A/B/C choice>

**Goal**: <decision, report, shortlist, or innovation discovery>

**If no fixed topic**: set `fixed_topic_or_title` to empty or `exploratory`; the skill must run topic-cluster divergence via `grok` + `deepseek` before narrowing.

**Use case**:
- users/scale:
- latency/throughput:
- data:

**Constraints**:
- region/compliance:
- budget:
- stack:

**Evaluation priorities**:
- performance / cost / ecosystem / control / speed / novelty

**Freshness window**:

**Output**:

## 2) Provider Checklist

- [ ] Pick discovery channels: Brave / DDG / Exa
- [ ] Confirm Grok + DeepSeek are enabled by default; only skip if a chain actually failed or is unavailable
- [ ] Define fallback order if one external-brain chain is unavailable
- [ ] Pick verification path: built-in web / Firecrawl / Playwright
- [ ] Decide whether Obsidian archiving is required
- [ ] Decide whether parallel delegation is useful

## 3) Main-Agent Checklist

- [ ] Write a one-paragraph decision or research statement
- [ ] Generate 3-5 query angles
- [ ] If using external brains, prefer `scripts/external_brain_dispatch.ps1`
- [ ] Collect candidate URLs from selected providers
- [ ] Deduplicate URLs
- [ ] If one chain fails, switch to the fallback plan and log the failure
- [ ] Read the best sources deeply
- [ ] Separate facts, inference, and uncertainty
- [ ] Cite decision-driving claims

## 4) Subagent Prompt Skeleton

Use only when delegation is allowed. Launch with `spawn_agent`.

```text
You are a retrieval subagent.
Provider: <brave|ddg|exa|grok|deepseek>
Topic: <topic>
Questions:
1. ...
2. ...
3. ...

Return structured output only:
- provider
- status
- queries_used
- results[] with title, url, snippet
- claims[] only for provider=grok or provider=deepseek
- candidate_urls[] for provider=grok or provider=deepseek
- fallback_taken
- errors[]

If using the dispatcher, also return:
- brain_chain_status
- channel_failures
- fallback_actions
```

## 5) Decision Output Skeleton

### Executive Summary

### Recommendation
- Pick:
- Why:
- When not to pick:

### Comparison Table
| Criteria | A | B | C |
|---|---|---|---|
| Fit to use case |  |  |  |
| Performance |  |  |  |
| Cost |  |  |  |
| Ecosystem |  |  |  |
| Ops complexity |  |  |  |
| Risks |  |  |  |

### Evidence Highlights
1. Claim - Source

### Open Questions

## 6) Patent Ideation Output Skeleton

### Candidate Directions
| Direction | Novelty | Practicality | Reasonableness | Summary |
|---|---|---|---|---|
| A |  |  |  |  |
| B |  |  |  |  |
| C |  |  |  |  |

### Claims Requiring Later Patent Verification
- 
