#!/usr/bin/env python3
"""Assert that a markdown run manifest contains a valid absolute output_dir.

Rationale:
- Cold-start policy requires explicitly user-provided delivery directory.
- We need a programmatic, auditable gate.

This script is intentionally strict and lightweight (stdlib only).

Usage:
  python skills/patent-workflow/scripts/assert_output_dir_in_manifest.py artifacts/run_manifest.md

Exit codes:
  0 = ok
  2 = invalid
"""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract_output_dir(md: str) -> str | None:
    # Match line: - `output_dir`: <value>
    m = re.search(r"^\s*-\s*`output_dir`\s*:\s*(.+?)\s*$", md, flags=re.MULTILINE)
    if not m:
        return None
    v = m.group(1).strip()
    # treat placeholders/comments as empty
    if v in {"", "<output_dir>", "TBD", "TODO"}:
        return ""
    return v


def _is_abs_path(p: str) -> bool:
    # Windows absolute path like C:\... or UNC \\server\share
    if os.path.isabs(p):
        return True
    # Be explicit: on Windows, os.path.isabs covers drive + UNC; keep fallback anyway
    if re.match(r"^[A-Za-z]:\\", p):
        return True
    if p.startswith("\\\\"):
        return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description="Assert output_dir exists in run manifest and is absolute")
    ap.add_argument("manifest", help="Path to markdown run manifest")
    ap.add_argument("--out", help="Optional output path for JSON summary")
    args = ap.parse_args()

    manifest_path = Path(args.manifest)
    summary = {
        "validator": "assert_output_dir_in_manifest.py",
        "generatedAt": _utc_now(),
        "inputPath": str(manifest_path),
        "passed": False,
        "output_dir": None,
        "errors": [],
    }

    if not manifest_path.exists():
        summary["errors"].append(f"Manifest not found: {manifest_path}")
    else:
        md = manifest_path.read_text(encoding="utf-8")
        out_dir = _extract_output_dir(md)
        summary["output_dir"] = out_dir

        if out_dir is None:
            summary["errors"].append("Missing required line: - `output_dir`: <ABSOLUTE_PATH>")
        elif out_dir == "":
            summary["errors"].append("output_dir is empty/placeholder; user must explicitly provide an absolute path")
        elif not _is_abs_path(out_dir):
            summary["errors"].append(f"output_dir is not an absolute path: {out_dir}")

    summary["passed"] = len(summary["errors"]) == 0

    text = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        print(text)

    return 0 if summary["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
