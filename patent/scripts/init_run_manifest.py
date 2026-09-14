#!/usr/bin/env python3
"""Initialize (or update) a run manifest markdown file from RUN_MANIFEST_TEMPLATE.md.

The template self-locates relative to this script (works from any working directory).

Usage:
  python init_run_manifest.py --out artifacts/run_manifest.md \
    --domain-scope "AI/自动驾驶" --output-dir "D:\\deliver\\patent_xxx"

  # patch fields into an EXISTING manifest (the scripted way to declare a
  # sensitive run — never hand-edit these lines):
  python init_run_manifest.py --update --out artifacts/run_manifest.md \
    --research-origin mine --sensitive-map-path "D:\\proj\\.patent-private\\sensitive_map.json"

Exit codes:
  0 = created/overwritten/updated
  2 = failed
"""

import argparse
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass

DEFAULT_TEMPLATE = Path(__file__).resolve().parent.parent / "references" / "RUN_MANIFEST_TEMPLATE.md"


def _iso_now():
    return datetime.now(timezone.utc).isoformat()


def _set_line(text: str, key: str, value: str) -> str:
    """Set '- `key`:' line to '- `key`: value' (first occurrence), replacing any
    previous value and trailing template comment."""
    pattern = re.compile(rf"^(\s*-\s*`{re.escape(key)}`\s*:).*$", flags=re.MULTILINE)
    if not pattern.search(text):
        return text
    return pattern.sub(lambda m: f"{m.group(1)} {value}", text, count=1)


def main() -> int:
    ap = argparse.ArgumentParser(description="Initialize or update patent run manifest")
    ap.add_argument("--template", default=str(DEFAULT_TEMPLATE), help="Path to RUN_MANIFEST_TEMPLATE.md")
    ap.add_argument("--out", default="artifacts/run_manifest.md", help="Manifest path")
    ap.add_argument("--run-id", help="Optional run_id; if omitted, generates a UUID")
    ap.add_argument("--domain-scope", help="Optional domain scope")
    ap.add_argument("--output-dir", help="Optional output/delivery dir (absolute path)")
    ap.add_argument("--research-origin", choices=["normal", "vault_pool", "mine"],
                    help="Provenance of the research pack")
    ap.add_argument("--vault-direction-origin", choices=["research", "mine"],
                    help="Origin of the picked vault direction (mine = sensitive lineage)")
    ap.add_argument("--sensitive-map-path",
                    help="Absolute path to the confirmed sensitive_map.json; declaring it "
                         "arms the deliver-gate leak check and the research-gate mine check")
    ap.add_argument("--update", action="store_true",
                    help="Patch fields into an existing manifest instead of creating one")
    ap.add_argument("--overwrite", action="store_true", help="Overwrite existing out file (create mode)")
    args = ap.parse_args()

    out = Path(args.out)

    def _die(msg: str) -> int:
        print(msg, file=sys.stderr)
        return 2

    if args.update:
        if not out.exists():
            return _die(f"Manifest not found (cannot --update): {out}")
        text = out.read_text(encoding="utf-8")
    else:
        tpl = Path(args.template)
        if not tpl.exists():
            return _die(f"Template not found: {tpl}")
        if out.exists() and not args.overwrite:
            return _die(f"Manifest already exists (use --overwrite to replace): {out}")
        text = tpl.read_text(encoding="utf-8")
        text = _set_line(text, "run_id", args.run_id or str(uuid.uuid4()))
        text = _set_line(text, "started_at", _iso_now())
        text = _set_line(text, "current_step", "开局")

    text = _set_line(text, "last_updated", _iso_now())
    if args.domain_scope:
        text = _set_line(text, "domain_scope", args.domain_scope)
    if args.output_dir:
        text = _set_line(text, "output_dir", args.output_dir)
    if args.research_origin:
        text = _set_line(text, "research_origin", args.research_origin)
    if args.vault_direction_origin:
        text = _set_line(text, "vault_direction_origin", args.vault_direction_origin)
    if args.sensitive_map_path:
        text = _set_line(text, "sensitive_map_path", args.sensitive_map_path)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(str(out.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
