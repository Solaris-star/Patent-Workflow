# Review and revision traceability contract

Revision records connect each finding to a user-authorized correction and the re-review of the changed material. A stable issue ID is carried through review_status, approved_issue_scope, each edit-plan entry, each structured-diff item, and the post-fix review. Do not assign a new ID just because an issue moves to another artifact or review round.

## Review findings and version fingerprints

The review report and artifacts/audit/review_status.json use one record per issue:

~~~json
{
  "doc_type": "review_status",
  "review_completed": true,
  "issues": [
    {
      "issue_id": "ISSUE-01",
      "severity": "medium",
      "disposition": "open",
      "summary": "Synthetic issue statement"
    }
  ],
  "reviewed_materials": {
    "final_markdown_path": "artifacts/delivery/Synthetic Patent Draft.md",
    "files": {
      "artifacts/delivery/Synthetic Patent Draft.md": "<sha256>",
      "artifacts/draft/facts_ledger.json": "<sha256>"
    }
  },
  "revision_validation": "pending"
}
~~~

ISSUE-... IDs are unique in the report. Hash every reviewed source whose change could affect a conclusion, including the current final Markdown and the applicable evidence/facts records. Before reusing a conclusion, compare these hashes to the current files. If a source changed, mark dependent conclusions pending re-review; do not silently retain the earlier result.

High-severity unresolved issues cannot pass by report presence. Mark them resolved after review, or record an issue-specific user_waiver with confirmed_by_user true, a concrete decision, and an explicit scope. A generic disclaimer is not a waiver.

## User-authorized scope and edit plan

The edit plan records the user authorization with the exact finding IDs and an understandable scope. The scope is not inferred from edit count or word count.

~~~json
{
  "doc_type": "edit_plan",
  "phase": "phase_10",
  "approved_issue_scope": {
    "approval_id": "APPROVAL-01",
    "confirmed_by_user": true,
    "confirmed_at": "2026-10-08T00:00:00Z",
    "scope": "Correct the specifically listed wording and traceability issues in the synthetic draft.",
    "issue_ids": ["ISSUE-01"]
  },
  "edits": [
    {
      "edit_id": "EDIT-01",
      "issue_ids": ["ISSUE-01"],
      "type": "clarify",
      "problem": "Synthetic issue statement",
      "change_instruction": "Clarify the cited statement without adding technical facts.",
      "risk_if_not_fixed": "medium",
      "target": {"section": "Synthetic section"}
    }
  ],
  "acceptance_checks": ["ISSUE-01 is resolved without adding technical facts"]
}
~~~

The validator requires every plan issue ID to exist in the review report and the edit IDs to exactly cover the approved issue IDs. Each edit is linked to one or more finding IDs. Newly proposed protection scope or technical facts need a separate explicit user approval; the issue approval does not silently expand. Existing authorization may be reused for the same exact scope by retaining its approval record and IDs; there is no edit-count threshold for authorization.

## Structured diff and re-review

Every diff item carries the same issue IDs and the linked edit ID. The diff must cover every planned edit and may not introduce an issue outside the approved scope.

~~~json
{
  "doc_type": "structured_diff",
  "phase": "phase_10",
  "diff_items": [
    {
      "linked_edit_id": "EDIT-01",
      "issue_ids": ["ISSUE-01"],
      "change_kind": "replace",
      "location": {"section": "Synthetic section"},
      "before_excerpt": "Synthetic original wording",
      "after_excerpt": "Synthetic corrected wording"
    }
  ]
}
~~~

After edits, rerun the applicable consistency and IPR reviews against current material hashes. The new review status preserves issue IDs and records each disposition after re-review. When authorized changes were made, revision_validation is passed only with a post-fix verification report containing `checks_passed: true`, a `material_hashes` map matching `reviewed_materials.files`, and an `issue_outcomes` map matching the latest dispositions. When no changes were authorized, revision_validation is not_required and the revision sub-check is skipped. A report file alone does not demonstrate that the review ran, that its scope was authorized, or that its conclusions are current.

## Offline validation

~~~powershell
python patent/scripts/validate_edit_plan.py artifacts/revision/phase_10_edit_plan.json --review-status artifacts/audit/review_status.json
python patent/scripts/validate_structured_diff.py artifacts/revision/phase_10_structured_diff.json --edit-plan artifacts/revision/phase_10_edit_plan.json
~~~

These validators check identifiers, scope continuity, artifact references, and hashes stated in the workflow. They do not judge legal sufficiency, determine novelty, or guarantee patentability or grant.
