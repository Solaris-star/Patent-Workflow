---
name: patent-prior-art
description: "Plan and validate traceable prior-art evidence for a software-patent collaboration workflow."
---

# Software patent prior-art research

Use this skill to collect and compare evidence for a software-patent subject. The CLI prior-art gate is included in full_research and titled_evidence only. The draft_review route has review and delivery gates, not prior-art. If an existing-draft review needs a formal evidence gate, switch with resume --mode titled_evidence and provide the confirmed title, local disclosure, and scoped search request. Read the manifest and existing packs first; reuse only materials whose source, date, verification state, feature links, and hashes remain current.

## Research scope

- Follow the requested jurisdiction, date window, sources, and search depth from the manifest.
- Search depth is `light`, `balanced`, or `deep`; it controls how broadly to search and document, not a result count.
- Build query terms from the selected software-patent subject. Record query text, source, timestamp, and result state.
- Do not invent patent numbers, citations, query results, or verification claims. An identifier's shape is not evidence of authenticity.
- If the requested search cannot be completed, preserve partial results and record each failed or unavailable channel.

## Search provider behavior

Use the provider the user requested or an available source authorized for the task. Before sending case-specific terms or materials outside the local workspace, confirm the data, destination, and purpose with the user. Do not send source files to a search provider unless that transfer is explicitly confirmed.

The CNIPA batch script may retain successful keyword results when other keywords fail. Retry only classified transient failures with a small configured limit. Stop on CAPTCHA, security verification, access denial, or HTTP 403. Do not spoof browser identity, bypass a challenge, or switch to an evasive mode. Record a safe failure status and let the user choose another permitted route.

## Evidence records

Keep the existing `phase_04_evidence_pack.json` as the canonical evidence store. Give features stable `F-...` IDs and sources unique `E-...` IDs. Link evidence and features in both directions. For every evidence item, record a source URL, a short excerpt, publication date or `unknown`, freshness, verification status, and feature IDs. A verified item also records when and how it was verified.

Separate implemented facts, source claims, inference, and pending confirmation. Keep unverified sources labeled as such and do not use them to make verified background comparisons. Record partial search results and limits in `search_trace`.

The background pack identifies the closest verified source and compares every registered feature using cited evidence IDs. Do not pad a search to reach a quota. If evidence is insufficient, record the gap and keep conclusions unresolved.

Create and validate an IPR pack only when the manifest explicitly sets `ipr_requested: true`. Its existence or record count does not establish legal clearance.

## Offline validation

~~~powershell
python patent/scripts/validate_evidence_pack.py artifacts/prior_art/phase_04_evidence_pack.json
python patent/scripts/validate_background_pack.py artifacts/prior_art/phase_05_background_pack.json --evidence-pack artifacts/prior_art/phase_04_evidence_pack.json
~~~

Add `--ipr-requested` to the IPR validator only when the run manifest explicitly requests that work. Validators check structure and recorded provenance; they do not establish source authenticity, novelty, patentability, validity, freedom to operate, or grant likelihood.
