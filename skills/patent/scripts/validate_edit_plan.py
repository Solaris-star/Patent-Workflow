#!/usr/bin/env python3
"""Validate Phase 10 edit plan artifact.

Usage:
  python validate_edit_plan.py artifacts/revision/phase_10_edit_plan.json

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


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate phase_10_edit_plan.json structure")
    ap.add_argument("input", help="Path to phase_10_edit_plan.json")
    ap.add_argument("--output", help="Optional path to write validation summary JSON")
    ap.add_argument("--require-acceptance-check", action="append", default=[], help="Acceptance check key that must appear (repeatable)")
    args = ap.parse_args()

    now = datetime.now(timezone.utc)
    inp = Path(args.input)

    errors: list[str] = []
    _require(inp.exists(), f"Input file not found: {inp}", errors)
    if errors:
        print(json.dumps({
            "validator": "validate_edit_plan.py",
            "generatedAt": now.isoformat(),
            "inputPath": str(inp),
            "passed": False,
            "errors": errors,
        }, ensure_ascii=False, indent=2))
        return 2

    try:
        data = json.loads(inp.read_text(encoding="utf-8"))
    except Exception as e:
        print(json.dumps({
            "validator": "validate_edit_plan.py",
            "generatedAt": now.isoformat(),
            "inputPath": str(inp.resolve()),
            "passed": False,
            "errors": [f"JSON parse error: {e}"],
        }, ensure_ascii=False, indent=2))
        return 2

    _require(data.get("doc_type") == "edit_plan", "doc_type must be 'edit_plan'", errors)
    _require(data.get("phase") == "phase_10", "phase must be 'phase_10'", errors)

    edits = _as_list(data.get("edits"))
    _require(len(edits) >= 1, "edits must be non-empty", errors)

    acceptance = _as_list(data.get("acceptance_checks"))
    _require(len(acceptance) >= 1, "acceptance_checks must be non-empty", errors)

    # Default recommended keys (soft gate but can be made hard via --require-acceptance-check)
    recommended = {
        "rerun_phase_08_consistency_audit",
        "rerun_phase_09_ipr_review",
    }

    for k in args.require_acceptance_check:
        if k and k not in acceptance:
            errors.append(f"acceptance_checks missing required key: {k}")

    edit_ids = set()
    for i, e in enumerate(edits):
        if not isinstance(e, dict):
            errors.append(f"edits[{i}] must be object")
            continue
        eid = (e.get("edit_id") or "").strip()
        etype = (e.get("type") or "").strip()
        problem = (e.get("problem") or "").strip()
        instruction = (e.get("change_instruction") or "").strip()
        risk = (e.get("risk_if_not_fixed") or "").strip()

        _require(bool(eid), f"edits[{i}].edit_id missing", errors)
        _require(bool(etype), f"edits[{i}].type missing", errors)
        _require(bool(problem), f"edits[{i}].problem missing", errors)
        _require(bool(instruction), f"edits[{i}].change_instruction missing", errors)
        _require(risk in ("high", "medium", "low"), f"edits[{i}].risk_if_not_fixed must be high|medium|low", errors)

        target = _as_dict(e.get("target"))
        _require(bool((target.get("section") or "").strip()), f"edits[{i}].target.section missing", errors)

        if eid:
            if eid in edit_ids:
                errors.append(f"duplicate edit_id: {eid}")
            edit_ids.add(eid)

    summary = {
        "validator": "validate_edit_plan.py",
        "generatedAt": now.isoformat(),
        "inputPath": str(inp.resolve()),
        "counts": {
            "edits": len(edits),
            "acceptance_checks": len(acceptance),
        },
        "recommended_acceptance_checks": sorted(recommended),
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
