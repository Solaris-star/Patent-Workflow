# Patent Workflow

**AI-driven patent disclosure drafting workflow with structured phase gates.**

An orchestrator-driven pipeline that transforms ideas into CN patent disclosures through 10 gated stages: material preprocessing → scope confirmation → innovation mining → direction convergence → prior art search → drafting → consistency audit → IPR simulation review → revision loop → final delivery (`.docx` + `.zip`).

## 🤖 One-Click Setup (Copy to your AI Agent)

> Paste this into Claude Code, Cursor, Codex, or any coding agent:

```
Clone this repo and set up the Patent Workflow on my machine:

1. git clone https://github.com/asdfqqwe/Patent-Workflow.git && cd Patent-Workflow
2. pip install -r requirements.txt
3. Clone and install smart-search-cli:
   git clone https://github.com/asdfqqwe/smart-search-cli.git /tmp/smart-search-cli
   cd /tmp/smart-search-cli && pip install -e . && cd -
4. Configure smart-search API backends in ~/.smart-search/config.yaml
   (Grok, GLM5, Tavily — at least 2 needed).
   Get API keys from your LLM provider and run `smart-search doctor` to verify.
5. Docx generation is bundled (scripts/generate_docx.py).
   For better formatting: brew/winget/apt install pandoc (optional).
6. Verify: python scripts/orchestrate.py --workspace . --manifest artifacts/run_manifest.md --from-phase 0 --dry-run
```

## Architecture

```
orchestrate.py (single entry point)
  ├── validators/preflight_validator.py    ← pre-run checks
  ├── state machine loop
  │   ├── validators/handoff_validator.py  ← handoff validation (hard block)
  │   ├── user input nodes                 ← --batch / --interactive
  │   ├── executors/phase_XX_*.py          ← phase executors
  │   └── validators/gate_runner.py        ← gate runner
  └── state snapshots + trace log
```

**Phases:**

| # | Phase | Mode |
|---|-------|------|
| 0 | Material Preprocessing & Manifest Init | Script |
| 1 | Scope Confirmation | User Input |
| 2 | Candidate Mining & Patent Search | Agent-native (parallel sub-agents) |
| 3 | Direction Convergence | User Input |
| 4 | Internal Patent Review | Script |
| 5 | Draft Writing | Script (modular writer) |
| 6 | Consistency Audit | Script |
| 7 | IPR Simulation Review | Script |
| 8 | Post-Review Revision & Re-review Loop | Script |
| 9 | Final Delivery (docx + zip) | Script |

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Initialize a new run manifest
python scripts/init_run_manifest.py \
    --out artifacts/run_manifest.md \
    --domain-scope "Your Domain"

# Cold start (from phase 0)
python scripts/orchestrate.py \
    --workspace /path/to/project \
    --manifest artifacts/run_manifest.md \
    --from-phase 0

# Resume from a phase
python scripts/orchestrate.py \
    --workspace /path/to/project \
    --manifest artifacts/run_manifest.md \
    --from-phase 3

# Dry run (print plan, no execution)
python scripts/orchestrate.py \
    --from-phase 0 --dry-run

# Validate only (check current state)
python scripts/orchestrate.py \
    --workspace /path/to/project \
    --manifest artifacts/run_manifest.md \
    --validate-only
```

## Key Design Principles

- **Gate-enforced progression**: Every phase has mandatory handoff validation. No gate pass = no advance.
- **State machine**: Phase advancement, handoff checks, gates all executed by `orchestrate.py`. Agent cannot skip steps from memory.
- **Fresh start safety**: Starting from `--from-phase 0` automatically clears previous domain scope, forcing re-confirmation.
- **Domain isolation**: All executors read `domain_scope` from the manifest. No hardcoded domain defaults.
- **Agent-native Phase 2**: Patent search and candidate mining uses parallel sub-agents with smart-search for deep multi-source research.
- **Full audit trail**: Trace logs, snapshots, and manifest state recorded at every phase.

## Environment Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `PATENT_RESEARCH_CACHE_ROOT` | Research cache directory | `$XDG_CACHE_HOME/patent-workflow/research-cache/` or `~/.cache/patent-workflow/research-cache/` |
| `PATENT_WORKFLOW_RESEARCH_CACHE_DIR` | Alternative cache dir (overrides above) | — |
| `PATENT_DOCX_SCRIPT` | Optional: path to a custom docx generator script | Bundled `scripts/generate_docx.py` |
| `PATENT_WORKFLOW_DEBUG` | Enable debug logging | `false` |

## Dependencies

**Python (required):**
```bash
pip install -r requirements.txt   # pdfplumber, pypdf, python-docx
```

**Phase 2 — Patent Search:**
- **[smart-search-cli](https://github.com/asdfqqwe/smart-search-cli)** (Grok + GLM5 + Tavily)
- Requires API keys for ≥2 backends → see [smart-search-cli docs](https://github.com/asdfqqwe/smart-search-cli)

**Phase 9 — DOCX (auto-selects first available):**
1. **Bundled** `scripts/generate_docx.py` — uses `python-docx`, zero extra install
2. **pandoc** — `brew install pandoc` / `winget install pandoc` / `apt install pandoc`
3. **LibreOffice** + pandoc — last resort

## File Structure

```
patent-workflow/
├── SKILL.md                    # Full specification
├── HANDOFF_CONTRACT.md         # Phase handoff rules
├── DELIVERY_CHECKLIST.md       # Delivery checklist
├── CONSISTENCY_AUDIT_TEMPLATE.md
├── IPR_REVIEW_TEMPLATE.md
├── RUN_MANIFEST_TEMPLATE.md
├── FIGURE_DELIVERY_CHECKLIST.md
├── scripts/
│   ├── orchestrate.py          # Main orchestrator (single entry point)
│   ├── init_run_manifest.py    # Manifest initializer
│   ├── run_phase_gates.py      # Gate runner CLI
│   ├── research_cache.py       # SQLite research cache
│   ├── executors/              # Phase executors
│   │   ├── base_executor.py
│   │   ├── phase_0_executor.py # Preprocessing
│   │   ├── phase_4_executor.py # Prior art search
│   │   ├── phase_5_executor.py # Draft writing
│   │   ├── phase_6_executor.py # Consistency audit
│   │   ├── phase_7_executor.py # IPR simulation
│   │   ├── phase_8_executor.py # Revision loop
│   │   └── phase_9_executor.py # Delivery
│   ├── validators/             # Validation modules
│   │   ├── preflight_validator.py
│   │   ├── handoff_validator.py
│   │   └── gate_runner.py
│   └── tests/                  # Test suite
└── stages/                     # Phase flow diagrams (PNG)
```

## License

MIT
