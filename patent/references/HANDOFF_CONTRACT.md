# Stage Handoff Contract

Each stage updates the same manifest. Handoff records must describe the actual workspace artifacts and user decisions, not planned or inferred work.

## Run scope

- workflow_mode is full_research, titled_evidence, or draft_review.
- search_depth records the requested depth: light, balanced, or deep.
- output_dir is stored as an absolute path resolving to the explicitly selected local delivery directory.
- final_title and working_title are at most 24 characters.
- figure_delivery_mode defaults to mermaid_only. mermaid_and_images is opt-in.
- ipr_requested is true only when the user requested an IPR research pack.
- confirmed user decisions are recorded with their actual scope.

## Evidence and features

- Preserve phase_04_evidence_pack.json and facts_ledger.json as the evidence and fact sources of truth.
- Assign stable feature IDs in the form F-... and stable evidence IDs. Do not create a parallel facts database.
- Link each feature to source IDs, evidence IDs, disclosure paragraph IDs, and figure IDs that actually support it.
- Source types distinguish material, code, external_evidence, disclosure_paragraph, and figure. Material and code sources carry SHA-256 fingerprints.
- Evidence records include a source URL, excerpt, publication date when available, verification status, verification date, and referenced feature IDs.
- Offline validators confirm structure and stated provenance only. They do not establish authenticity, novelty, patentability, or grant likelihood.
- A background pack points to actual verified evidence IDs and identifies the closest source and differences. No source-count target or patent-like number establishes authenticity.
- Create the IPR pack only when ipr_requested is true.

## Draft and figures

- The draft gate checks the actual five Markdown parts under artifacts/draft, facts_ledger, source links, and every registered Mermaid file.
- Mermaid-only is the default: each figure has an existing .mmd source and a visible source block in the generated DOCX. Images are optional.
- In mermaid_and_images mode, every required image must exist in the delivery directory and be referenced by the final Markdown. An unrelated ZIP media entry is not evidence of a valid figure.
- Generate DOCX from the existing Markdown path; retain the source file and report the resolved output path.

## Review and revisions

- Consistency and IPR reports are accompanied by artifacts/audit/review_status.json.
- Review status explicitly records both reviews as completed, issue IDs, severity, disposition, reviewed material paths and SHA-256 fingerprints.
- Any changed reviewed material marks dependent conclusions stale and requires re-review.
- Every edit plan entry and structured diff item carries the same stable issue_id. The plan records user-approved issue scope and approval basis.
- A high-severity unresolved issue needs a concrete, issue-specific user waiver with confirmed_by_user, decision, and scope.
- No authorized edits means revision_validation is not_required and the revision sub-check is skipped. A report file alone never proves review completion or a passing revision.
- Authorized edits require both edit_plan and structured_diff, coverage of each approved issue, and a passed post-fix report tied to the latest hashes.

## Delivery

- --deliver-dir resolves to the exact output_dir in the manifest.
- The final Markdown and canonical DOCX are located inside that directory. Review status names the same final Markdown and its current hash.
- `workflow_cli.py export` reruns the active route checks and current review before DOCX generation. This is the pre-export check; it does not replace package acceptance.
- If `sensitive_map_path` is declared, export requires `--sensitive-map` with the explicitly reselected manifest path. It validates the current map contents and confirmation binding, then scans the final Markdown and generated DOCX. A missing or mismatched path fails before the map is read.
- Export reports `generated_pending_delivery_check` with `workflow_complete: false`. After export, run `workflow_cli.py check --gate deliver` as a separate post-export package check; when a map is declared, pass the same `--sensitive-map` path again.
- Results distinguish checks_passed, workflow_complete, skipped, not_run, review_completed, and revision_validation.
- Missing LibreOffice rendering produces `not_run` and keeps `workflow_complete` false.
- Gate and invalidation state is scoped to the selected workflow mode's active route; gates excluded from that mode do not block its status.

## Privacy boundary

Case files and sensitive mappings remain local until the user confirms the specific material, destination, and purpose of a requested transfer. No handoff step itself sends material.
