#!/usr/bin/env python3
"""Validate Phase 10 structured diff artifact.

Usage:
  python validate_structured_diff.py artifacts/revision/phase_10_structured_diff.json \
    --edit-plan artifacts/revision/phase_10_edit_plan.json

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


def _load_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate phase_10_structured_diff.json structure")
    ap.add_argument("input", help="Path to phase_10_structured_diff.json")
    ap.add_argument("--edit-plan", help="Optional path to phase_10_edit_plan.json for linked_edit_id validation")
    ap.add_argument("--output", help="Optional path to write validation summary JSON")
    args = ap.parse_args()

    now = datetime.now(timezone.utc)
    inp = Path(args.input)

    errors: list[str] = []
    _require(inp.exists(), f"Input file not found: {inp}", errors)

    edit_ids = set()
    if args.edit_plan:
        ep = Path(args.edit_plan)
        _require(ep.exists(), f"Edit plan not found: {ep}", errors)
        if ep.exists():
            try:
                ep_data = _load_json(ep)
                for e in _as_list(ep_data.get("edits")):
                    if isinstance(e, dict) and (e.get("edit_id") or "").strip():
                        edit_ids.add((e.get("edit_id") or "").strip())
            except Exception as e:
                errors.append(f"Edit plan JSON parse error: {e}")

    if errors and not inp.exists():
        print(json.dumps({
            "validator": "validate_structured_diff.py",
            "generatedAt": now.isoformat(),
            "inputPath": str(inp),
            "passed": False,
            "errors": errors,
        }, ensure_ascii=False, indent=2))
        return 2

    try:
        data = _load_json(inp)
    except Exception as e:
        print(json.dumps({
            "validator": "validate_structured_diff.py",
            "generatedAt": now.isoformat(),
            "inputPath": str(inp.resolve()),
            "passed": False,
            "errors": [f"JSON parse error: {e}"] + errors,
        }, ensure_ascii=False, indent=2))
        return 2

    _require(data.get("doc_type") == "structured_diff", "doc_type must be 'structured_diff'", errors)
    _require(data.get("phase") == "phase_10", "phase must be 'phase_10'", errors)

    items = _as_list(data.get("diff_items"))
    _require(len(items) >= 1, "diff_items must be non-empty", errors)

    for i, it in enumerate(items):
        if not isinstance(it, dict):
            errors.append(f"diff_items[{i}] must be object")
            continue

        kind = (it.get("change_kind") or "").strip()
        loc = _as_dict(it.get("location"))
        before = (it.get("before_excerpt") or "")
        after = (it.get("after_excerpt") or "")
        linked = (it.get("linked_edit_id") or "").strip()

        _require(kind in ("add", "delete", "replace", "move"), f"diff_items[{i}].change_kind invalid", errors)
        _require(bool((loc.get("section") or "").strip()), f"diff_items[{i}].location.section missing", errors)
        _require(bool(linked), f"diff_items[{i}].linked_edit_id missing", errors)

        if edit_ids and linked and linked not in edit_ids:
            errors.append(f"diff_items[{i}].linked_edit_id not found in edit plan: {linked}")

        if kind in ("delete", "replace", "move"):
            _require(bool(before.strip()), f"diff_items[{i}].before_excerpt required for {kind}", errors)
        if kind in ("add", "replace", "move"):
            _require(bool(after.strip()), f"diff_items[{i}].after_excerpt required for {kind}", errors)

    # plan→diff coverage: every approved edit must have at least one diff item,
    # otherwise "每条落实后记" is an unaudited promise (approve 10, record 1 → pass)
    uncovered: list[str] = []
    if edit_ids:
        linked_ids = {(it.get("linked_edit_id") or "").strip()
                      for it in items if isinstance(it, dict)}
        uncovered = sorted(edit_ids - linked_ids)
        _require(not uncovered,
                 f"edit plan entries with no diff item (plan→diff coverage): {', '.join(uncovered)}",
                 errors)

    summary = {
        "validator": "validate_structured_diff.py",
        "generatedAt": now.isoformat(),
        "inputPath": str(inp.resolve()),
        "counts": {
            "diff_items": len(items),
            "edit_plan_linked_ids": len(edit_ids),
            "uncovered_edit_ids": len(uncovered),
        },
        "passed": len(errors) == 0,
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
