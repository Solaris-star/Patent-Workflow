# Delivery checklist

Use this checklist for a software-patent collaboration package. It validates package integrity and version alignment; it does not make a legal assessment.

## Bind the package to the reviewed version

- [ ] The supplied delivery directory matches the absolute `output_dir` recorded in the run manifest.
- [ ] The title in the manifest, final Markdown, and DOCX is identical and contains at most 24 characters.
- [ ] The final Markdown is inside the delivery directory and is the exact file recorded in `review_status.json`.
- [ ] `review_status.json` hashes the final Markdown and current `facts_ledger.json`; hashes still match.
- [ ] The latest consistency and IPR review states are explicit. Reports are evidence for the review, not a substitute for its status.
- [ ] Every unresolved high-severity issue has a specific user decision and scope recorded against its stable issue ID.
- [ ] A completed review and a post-fix validation are represented separately. A no-change review may set revision validation to `not_required`.
- [ ] Export reran the active route checks and current review before generating the DOCX.
- [ ] The DOCX generation result is treated as pending; the separate post-export `deliver` gate has run against the complete package.

## Check files and content

- [ ] The package contains the final Markdown and its matching DOCX.
- [ ] All five main draft sections contain actual text; they are not headings or placeholders alone.
- [ ] Facts, source, feature, evidence, paragraph, and figure references resolve to stable IDs.
- [ ] Each registered figure has an editable `.mmd` source. Raster or vector exports are required only when the manifest selects `mermaid_and_images`.
- [ ] In image mode, every image is referenced in the delivered Markdown, exists in the delivery directory, and is embedded in the DOCX.
- [ ] DOCX text retains the title, main content, figures, and evidence citations, without raw Markdown or math delimiters.
- [ ] Markdown paragraphs, table cells, and inline equations are present in the DOCX; supported equations use OMML. Unsupported math syntax fails export and must be rewritten before delivery.
- [ ] The DOCX renderer passed, or its unavailable status is explicitly recorded as `not_run`.
- [ ] For a declared `sensitive_map_path`, explicitly pass the same manifest path to both `workflow_cli.py export --sensitive-map <same path>` and the later `workflow_cli.py check --gate deliver --sensitive-map <same path>`. Export validates the current map contents and confirmation binding and scans the final Markdown and generated DOCX; missing or mismatched selections fail before the map is read.

## Interpret results

`checks_passed` means the checks that ran found no failure. DOCX generation returns `generated_pending_delivery_check` and does not complete the workflow. `workflow_complete` is true only after all required steps and the post-export deliver gate ran and passed. If LibreOffice rendering is `not_run`, the delivery is not complete. Offline structural checks do not guarantee legal novelty, validity, or grant.
