#!/usr/bin/env python3
"""Initialize a run manifest markdown file from the patent skill's RUN_MANIFEST_TEMPLATE.md.

The template self-locates relative to this script (works from any working directory).

Usage:
  python init_run_manifest.py --out artifacts/run_manifest.md \
    --domain-scope "AI/自动驾驶" --output-dir "D:\\deliver\\patent_xxx"

Exit codes:
  0 = created/overwritten
  2 = failed
"""

import argparse
import uuid
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_TEMPLATE = Path(__file__).resolve().parent.parent / "references" / "RUN_MANIFEST_TEMPLATE.md"


def _iso_now():
    return datetime.now(timezone.utc).isoformat()


def _replace_line(text: str, key: str, value: str) -> str:
    """Replace '- `key`:' line with '- `key`: value' (first occurrence only)."""
    needle = f"- `{key}`:"
    if needle not in text:
        return text
    return text.replace(needle, f"- `{key}`: {value}", 1)


def main() -> int:
    ap = argparse.ArgumentParser(description="Initialize patent run manifest")
    ap.add_argument("--template", default=str(DEFAULT_TEMPLATE), help="Path to RUN_MANIFEST_TEMPLATE.md")
    ap.add_argument("--out", default="artifacts/run_manifest.md", help="Output manifest path")
    ap.add_argument("--run-id", help="Optional run_id; if omitted, generates a UUID")
    ap.add_argument("--domain-scope", help="Optional domain scope")
    ap.add_argument("--output-dir", help="Optional output/delivery dir (absolute path)")
    ap.add_argument("--overwrite", action="store_true", help="Overwrite existing out file")
    args = ap.parse_args()

    tpl = Path(args.template)
    out = Path(args.out)

    if not tpl.exists():
        raise SystemExit(f"Template not found: {tpl}")

    if out.exists() and not args.overwrite:
        raise SystemExit(f"Manifest already exists (use --overwrite to replace): {out}")

    text = tpl.read_text(encoding="utf-8")

    run_id = args.run_id or str(uuid.uuid4())
    now = _iso_now()

    text = _replace_line(text, "run_id", run_id)
    text = _replace_line(text, "started_at", now)
    text = _replace_line(text, "last_updated", now)
    text = _replace_line(text, "current_step", "开局")

    if args.domain_scope:
        text = _replace_line(text, "domain_scope", args.domain_scope)
    if args.output_dir:
        text = _replace_line(text, "output_dir", args.output_dir)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(str(out.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
