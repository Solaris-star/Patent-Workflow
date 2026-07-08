#!/usr/bin/env python3
"""Validate facts_ledger.json produced during Phase 7 (modular drafting).

This validator is used by patent-workflow to gate Phase 8/11.

It validates:
- ledger structure (terminology, figure_registry, constraints/effects)
- figure artifact completeness: image + mmd + editable (drawio/vsdx at least 1)
- (optional) a declared flag that Mermaid source is embedded visibly in docx after figure notes

Usage:
  python validate_facts_ledger.py artifacts/draft/facts_ledger.json

Exit codes:
  0 = pass
  2 = fail
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def _require(cond: bool, msg: str, errors: list[str]):
    if not cond:
        errors.append(msg)


def _as_list(x):
    return x if isinstance(x, list) else []


def _as_dict(x):
    return x if isinstance(x, dict) else {}


def _exists(rel_path: str, base_dir: Path) -> bool:
    if not rel_path:
        return False
    p = Path(rel_path)
    if not p.is_absolute():
        p = base_dir / p
    return p.exists()


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate facts_ledger.json structure for gates")
    ap.add_argument("input", help="Path to artifacts/draft/facts_ledger.json")
    ap.add_argument("--base-dir", default=".", help="Base directory for resolving relative artifact paths")
    ap.add_argument("--output", help="Optional path to write validation summary JSON")
    ap.add_argument("--require-docx-visible-mermaid", action="store_true", help="Require mermaid_source_embedded_in_docx == true for all figures")
    args = ap.parse_args()

    now = datetime.now(timezone.utc)
    inp = Path(args.input)
    base_dir = Path(args.base_dir)

    errors: list[str] = []
    _require(inp.exists(), f"Input file not found: {inp}", errors)
    if errors:
        summary = {
            "validator": "validate_facts_ledger.py",
            "generatedAt": now.isoformat(),
            "inputPath": str(inp),
            "passed": False,
            "errors": errors,
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 2

    try:
        data = json.loads(inp.read_text(encoding="utf-8"))
    except Exception as e:
        summary = {
            "validator": "validate_facts_ledger.py",
            "generatedAt": now.isoformat(),
            "inputPath": str(inp.resolve()),
            "passed": False,
            "errors": [f"JSON parse error: {e}"],
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 2

    ledger_type = (data.get("ledger_type") or "").strip()
    _require(ledger_type == "facts_ledger", "ledger_type must be 'facts_ledger'", errors)

    terminology = _as_list(data.get("terminology"))
    figure_registry = _as_list(data.get("figure_registry"))
    constraints = _as_list(data.get("constraints_and_effects"))

    _require(len(terminology) >= 1, "terminology must be non-empty", errors)
    _require(len(figure_registry) >= 1, "figure_registry must be non-empty", errors)
    _require(len(constraints) >= 1, "constraints_and_effects must be non-empty", errors)

    for i, t in enumerate(terminology):
        if not isinstance(t, dict):
            errors.append(f"terminology[{i}] must be object")
            continue
        term = (t.get("term") or "").strip()
        definition = (t.get("definition") or "").strip()
        _require(bool(term), f"terminology[{i}].term missing", errors)
        _require(bool(definition), f"terminology[{i}].definition missing", errors)

    missing_artifacts = 0
    for i, fig in enumerate(figure_registry):
        if not isinstance(fig, dict):
            errors.append(f"figure_registry[{i}] must be object")
            continue
        fid = (fig.get("figure_id") or "").strip()
        caption = (fig.get("caption") or "").strip()
        _require(bool(fid), f"figure_registry[{i}].figure_id missing", errors)
        _require(bool(caption), f"figure_registry[{i}].caption missing", errors)

        artifacts = _as_dict(fig.get("artifacts"))
        img = (artifacts.get("image") or "").strip()
        mmd = (artifacts.get("mmd") or "").strip()
        editable = _as_list(artifacts.get("editable"))

        if not _exists(img, base_dir):
            missing_artifacts += 1
            errors.append(f"figure_registry[{i}] missing image artifact: {img}")
        if not _exists(mmd, base_dir):
            missing_artifacts += 1
            errors.append(f"figure_registry[{i}] missing mmd artifact: {mmd}")

        editable_ok = False
        for p in editable:
            if isinstance(p, str) and p.strip() and _exists(p.strip(), base_dir):
                editable_ok = True
                break
        _require(editable_ok, f"figure_registry[{i}] missing editable artifact (drawio/vsdx): {editable}", errors)

        if args.require_docx_visible_mermaid:
            flag = fig.get("mermaid_source_embedded_in_docx")
            _require(flag is True, f"figure_registry[{i}].mermaid_source_embedded_in_docx must be true", errors)

    summary = {
        "validator": "validate_facts_ledger.py",
        "generatedAt": now.isoformat(),
        "inputPath": str(inp.resolve()),
        "passed": len(errors) == 0,
        "counts": {
            "terminology": len(terminology),
            "figure_registry": len(figure_registry),
            "constraints_and_effects": len(constraints),
        },
        "errors": errors,
    }

    out = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(out, encoding="utf-8")
    else:
        print(out)

    return 0 if summary["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
