---
name: patent-research-cli
description: Use optional research CLIs for scoped, source-backed software patent collaboration. Select a full-research, fixed-title evidence-gap, or existing-draft review path from the run manifest. Reuse verified local evidence, honor the requested search depth, and do not invent minimum source counts.
---

# Patent research CLI

This skill supports research steps in the software patent collaboration workflow. It does not manage software development tasks. The run manifest is the source of truth for workflow mode, title, search scope, requested depth, existing artifacts, and user decisions. Command paths, titles, and query text below are synthetic placeholders only.

## Choose the workflow path

1. **Full research**: use when the user has not settled a title and asks to explore a software patent opportunity. Start from the invention disclosure and an explicit research brief. Search and verify evidence at the depth recorded in the manifest, then carry the feature mapping into title selection and drafting.
2. **Fixed-title evidence supplement**: use when the title is already selected. Keep that title unchanged, inspect verified evidence first, identify concrete gaps, and search only within the requested scope. Do not restart broad discovery unless asked.
3. **Existing-draft review**: use when the user supplies a draft for independent review. The draft_review CLI route runs review and delivery only. If the user requests a formal prior-art gate for an identified gap, switch to titled_evidence with a confirmed title, disclosure, and scoped search request.

Set one of these modes when starting a run:

~~~sh
python patent/scripts/workflow_cli.py init --workspace cases/SYNTHETIC_RUN --mode full_research --disclosure input/SYNTHETIC_DISCLOSURE.md --search-brief "SYNTHETIC_SEARCH_SCOPE" --search-depth balanced
python patent/scripts/workflow_cli.py init --workspace cases/SYNTHETIC_RUN --mode titled_evidence --title "SYNTHETIC_TITLE_01" --disclosure input/SYNTHETIC_DISCLOSURE.md --search-brief "SYNTHETIC_EVIDENCE_GAP"
python patent/scripts/workflow_cli.py init --workspace cases/SYNTHETIC_REVIEW --mode draft_review --draft input/SYNTHETIC_DRAFT.md
~~~

The CLI gate sequence is mode-specific: full_research runs research → prior-art → draft → review → deliver; titled_evidence runs prior-art → draft → review → deliver; draft_review runs review → deliver. check --gate all follows that sequence. On a mode switch, checkpoint status and invalidation are scoped to the selected mode's active gates; inactive gates do not block that route. Supply the required inputs for the selected route and refresh any conclusions invalidated by the switch before continuing.

Before export, `workflow_cli.py export` reruns the active route checks and current review, then performs its pre-export checks and generates the DOCX. For a declared `sensitive_map_path`, pass `--sensitive-map` with that same path; export validates the current map contents and confirmation binding, then scans both the final Markdown and generated DOCX. Omitting or changing the path fails before the map is read. Export returns `generated_pending_delivery_check` with `workflow_complete: false`; run `workflow_cli.py check --gate deliver` afterward for the separate package check, passing the same map path again when configured. A missing LibreOffice renderer is `not_run` and prevents workflow completion.

If the run already exists, inspect it with status and recover its checkpoint with resume. Resume records stage history and reports missing materials; it does not regenerate or replace case files.

~~~sh
python patent/scripts/workflow_cli.py status --workspace cases/local-run
python patent/scripts/workflow_cli.py resume --workspace cases/local-run
~~~

## Search depth and evidence

The manifest accepts light, balanced, or deep search depth. Use the depth the user requested; if none was given, use balanced and record the choice. A depth is an effort preference, not a required result count. Stop when the scoped question has adequate, verified support or when the available sources have been exhausted. Record limitations and failed channels instead of padding the evidence pack.

Optional smart-search usage:

~~~sh
smart-search doctor --format json
smart-search deep "<SYNTHETIC_APPROVED_SCOPE>" --budget deep --format json --evidence-dir artifacts/research/evidence
smart-search search "<SYNTHETIC_APPROVED_QUERY>" --parallel --format json --timeout 180
smart-search fetch "<source URL>" --format markdown
~~~

The deep command creates a plan; it does not perform the searches. Execute only the queries needed for the approved scope. Capture each usable source with a stable evidence ID, date, verification status, and the features or disclosure passages it supports. Reuse a matching, still-current research pack when its source hashes and scope match; re-check sources whose content or freshness has changed.

Do not claim that an offline structural check establishes novelty, inventiveness, patentability, or grant likelihood. The validators check record structure and traceability only.

## Local data boundary

Keep disclosure files, unpublished technical details, draft text, and private mappings in the local case workspace. Before any case material or query containing it leaves that workspace for an external CLI, browser, or service, require a recorded user confirmation naming the material, destination, and purpose. If that confirmation is absent, keep the work local and mark external research unavailable. Never print credentials, private mapping values, or full source documents into logs.

## CNIPA keyword batch

The optional Playwright adapter uses ordinary browser defaults. It performs a bounded retry only for transient failures and saves per-keyword successes and errors when an output path is supplied. If CNIPA returns HTTP 403 or presents a verification challenge, stop the remaining batch and retain the completed results. Do not bypass the challenge.

~~~sh
python patent/scripts/cnipa/cnipa_epub_search.py --max-retries 2 --output artifacts/research/cnipa_batch.json "SYNTHETIC_KEYWORD_01" "SYNTHETIC_KEYWORD_02"
~~~

The output path is local to the case workspace. Existing output is protected unless the user explicitly uses the overwrite option. The batch has no fixed keyword or result quota.
