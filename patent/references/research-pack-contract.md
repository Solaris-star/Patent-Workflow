# Research and evidence pack contracts

These JSON artifacts preserve the existing research_pack and evidence_pack as the workflow sources of truth. They add provenance fields and references; they do not create a second fact database. Use synthetic or case-local source data only. Never copy case material into repository examples.

## Phase 2 research pack

Path: artifacts/research/phase_02_research_pack.json

~~~json
{
  "pack_type": "research_pack",
  "phase": "phase_02",
  "research_questions": [
    {"id": "RQ-01", "question": "A question in the requested research scope"}
  ],
  "outline_skeleton": [
    {
      "section_id": "S-01",
      "title": "Research finding",
      "intent": "Explain the evidence and limits",
      "covers_questions": ["RQ-01"],
      "evidence_ids": ["E-01"]
    }
  ],
  "evidence": [
    {
      "evidence_id": "E-01",
      "url": "https://example.com/source",
      "excerpt": "Synthetic excerpt used to demonstrate the record shape.",
      "claim": "A source-stated claim, not an established fact",
      "publication_date": "2026-07-15",
      "freshness": "fresh",
      "verification_status": "verified",
      "verified_at": "2026-10-08T00:00:00Z",
      "verification_method": "Source page opened and metadata checked",
      "conclusion_use": "usable"
    }
  ]
}
~~~

The research pack must have non-empty question, outline, and evidence arrays. The validators impose no count quotas beyond a usable record. Optional --min-questions, --min-outline, and --min-evidence flags are caller-requested thresholds; default is zero. Evidence IDs are unique within a pack. Every outline reference must resolve to an actual question or evidence record.

Each evidence item records a publication date or the explicit value unknown, a task-specific freshness label, verification_status, and conclusion_use. `conclusion_use` is `usable`, `pending_reverification`, or `context_only`; only verified evidence with a known publication date and a current task-specific freshness assessment may be marked usable. Allowed verification statuses are verified, unverified, needs_review, and failed. A verified record also has verified_at and verification_method. Unknown publication dates cannot be labeled fresh or valid. Excerpts may be short; no character count is used as a proxy for quality. There is no universal expiry window: re-check freshness for the requested question, jurisdiction, and date scope.

## Phase 4 canonical evidence pack

Path: artifacts/prior_art/phase_04_evidence_pack.json

~~~json
{
  "pack_type": "evidence_pack",
  "phase": "phase_04",
  "patent_candidate_pool_path": "artifacts/prior_art/phase_04_patent_candidate_pool.json",
  "search_trace": {
    "patent_search_queries": ["synthetic example query"],
    "final_relevant_patent_count": 1
  },
  "final_relevant_patents": [{"evidence_id": "E-01"}],
  "scheme_features": [
    {
      "feature_id": "F-01",
      "statement": "Synthetic feature statement",
      "evidence_kind": "source_claim",
      "status": "source_stated",
      "evidence_ids": ["E-01"]
    }
  ],
  "evidence": [
    {
      "evidence_id": "E-01",
      "url": "https://example.com/source",
      "excerpt": "Synthetic excerpt used to demonstrate the record shape.",
      "publication_date": "2026-07-15",
      "freshness": "fresh",
      "verification_status": "verified",
      "verified_at": "2026-10-08T00:00:00Z",
      "verification_method": "Source page opened and metadata checked",
      "conclusion_use": "usable",
      "feature_ids": ["F-01"],
      "is_auxiliary": false
    }
  ],
  "evidence_alignment": [
    {"feature_id": "F-01", "evidence_ids": ["E-01"]}
  ]
}
~~~

Stable feature IDs use F-... and evidence IDs are unique. Each source record maps to one or more registered feature IDs; each feature lists the same supporting evidence IDs. evidence_kind distinguishes implemented_fact, source_claim, inference, and pending_confirmation. A pending feature has status pending; other kinds have confirmed or source_stated status. Feature references and optional evidence_alignment references must resolve in both directions.

Evidence records require an HTTP(S) source URL, a non-empty excerpt, a publication_date (or date) in ISO form or unknown, a task-specific freshness label, verification_status, and conclusion_use. `usable` requires verified status and a fresh/valid assessment for this task; uncertain, stale, or unverified records remain pending or context only. No default patent-count, alignment-count, or excerpt-length quota is applied. Optional --min-final and --min-alignments flags apply only when the caller explicitly requests those thresholds. An unsuccessful or degraded search should be described in search_trace; do not invent citations to satisfy a quota.

## Phase 5 background pack

Path: artifacts/prior_art/phase_05_background_pack.json

~~~json
{
  "pack_type": "background_pack",
  "phase": "phase_05",
  "closest_source_evidence_id": "E-01",
  "evidence_ids": ["E-01"],
  "feature_comparisons": [
    {
      "feature_id": "F-01",
      "evidence_ids": ["E-01"],
      "difference": "Synthetic comparison statement; explain what the source says and what remains distinct or unknown."
    }
  ]
}
~~~

The background validator requires the closest source and every comparison source to resolve to the canonical evidence_pack and have verification_status verified with conclusion_use usable. Each compared feature must exist in scheme_features and be linked to the cited evidence. Every feature is covered; differences are explicit. A source count or patent-like identifier is not proof of authenticity.

## Optional IPR pack

Path: artifacts/prior_art/phase_05_ipr_pack.json. Create and validate this pack only when the run manifest explicitly records ipr_requested: true. The validation CLI additionally requires --ipr-requested so a pack cannot pass via an accidental invocation.

~~~json
{
  "pack_type": "ipr_pack",
  "phase": "phase_05",
  "assessments": [
    {
      "assessment_id": "IPR-01",
      "scope": "A defined review question",
      "feature_ids": ["F-01"],
      "evidence_ids": ["E-01"],
      "status": "reviewed",
      "summary": "Synthetic evidence summary",
      "limitations": "This structure check does not validate the legal analysis."
    }
  ]
}
~~~

Each assessment links stable feature IDs and only verified, currently usable evidence IDs. Status is reviewed, no_evidence, or pending. Incomplete/no-evidence assessments state their limitations; they do not imply clearance. No IPR result is produced unless explicitly requested.

## Commands and limits

~~~powershell
python patent/scripts/validate_research_pack.py artifacts/research/phase_02_research_pack.json
python patent/scripts/validate_evidence_pack.py artifacts/prior_art/phase_04_evidence_pack.json
python patent/scripts/validate_background_pack.py artifacts/prior_art/phase_05_background_pack.json --evidence-pack artifacts/prior_art/phase_04_evidence_pack.json
python patent/scripts/validate_ipr_pack.py artifacts/prior_art/phase_05_ipr_pack.json --evidence-pack artifacts/prior_art/phase_04_evidence_pack.json --ipr-requested
~~~

These are offline structure and stated-provenance checks. They do not open the source URLs, establish source authenticity, assess legal novelty or non-obviousness, guarantee patentability, or promise a grant.
