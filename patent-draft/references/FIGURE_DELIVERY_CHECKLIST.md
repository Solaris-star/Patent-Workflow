# Figure delivery checklist

## Source of truth

- [ ] Every figure has a stable figure ID and caption in the facts ledger.
- [ ] Every registered figure has a non-empty `.mmd` Mermaid source in the delivery directory.
- [ ] The relevant draft section refers to each registered figure ID or caption.
- [ ] The figure source and its references are included in the hashes for the reviewed version.

## Delivery mode

The default is `mermaid_only`: preserve the editable `.mmd` and include Mermaid source in the DOCX. Do not require PNG, SVG, draw.io, or VSDX files in this mode.

When the user requests rendered figures, set `figure_delivery_mode: mermaid_and_images` in the manifest:

- [ ] Each declared rendered image exists and is referenced by the delivered Markdown.
- [ ] Each referenced image is embedded in the exported DOCX through an image relationship.
- [ ] The image relationship points to a real package member; checking only for files under `word/media` is insufficient.
- [ ] The DOCX text and render health are checked separately from the existence of the source files.

If a local rendering tool is unavailable, record `not_run` and leave workflow completion false. Do not describe the render as successful.
