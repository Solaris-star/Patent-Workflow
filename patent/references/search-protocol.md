# Search protocol

This protocol supports software-patent collaboration workflows. It records the search requested by the user and preserves evidence provenance; it does not guarantee legal novelty or grant.

## Select scope before searching

Record the workflow mode (`full_research`, `titled_evidence`, or `draft_review`), jurisdiction, date window, requested sources, and search depth in the case manifest. Use `light`, `balanced`, or `deep` as a scope choice. Do not convert a search-depth choice into a fixed minimum number of records.

Reuse existing records only when their source links, publication dates, verification states, feature links, and version hashes still match. When source material changes, mark affected conclusions pending re-review.

## Provider and data boundary

Use an available provider only when the user requested the search and the provider is suitable for that data. Before any case-specific terms, source material, or files leave the local workspace, obtain confirmation covering the material, destination, and purpose. Record that confirmation in the manifest. Do not upload full source files by default.

Record which channels were used, unavailable, degraded, or failed. Keep successful results when a separate query fails. Do not retry indefinitely. Stop when a service requires CAPTCHA or security verification, returns access denied/403, or otherwise blocks the request. Never bypass a security check or spoof the browser to evade it.

## Evidence and comparisons

- Give each query a stable log entry with source, time, and outcome.
- Give each evidence source a unique `E-...` ID and link it to stable `F-...` feature IDs.
- Record URL, excerpt, publication date or `unknown`, freshness, verification state, and verification method/date when verified.
- Keep source claims distinct from confirmed implementation facts, inference, and questions for the user.
- Compare features only against verified sources. The background pack identifies the closest verified source and explains the evidence-linked differences.
- Create IPR materials only when `ipr_requested: true` is recorded by the user-configured workflow.
- Do not invent identifiers or sources, or add records merely to satisfy a count.

## Status and interpretation

The evidence-pack and background-pack validators are offline structural checks. They do not fetch URLs, prove source authenticity, determine novelty, assess legal validity, or promise patentability or grant. Preserve missing evidence as a visible limitation and let the user decide whether to expand the search.
