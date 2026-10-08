#!/usr/bin/env python3
"""Validate a phase_10 structured diff against its approved edit plan."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ISSUE_RE = re.compile(r"^ISSUE-[A-Z0-9][A-Z0-9._-]*$")


def _list(value: object) -> list:
    return value if isinstance(value, list) else []


def _obj(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _load(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _infer_edit_plan(diff_path: Path) -> Path | None:
    candidate = diff_path.parent / "phase_10_edit_plan.json"
    return candidate if candidate.is_file() else None


def validate(diff: object, plan: object) -> tuple[list[str], dict]:
    errors: list[str] = []
    counts = {"diff_items": 0, "linked_edit_ids": 0, "issue_ids": 0, "uncovered_edits": 0}
    if not isinstance(diff, dict):
        return ["structured diff must be a JSON object"], counts
    if diff.get("doc_type") != "structured_diff" or diff.get("phase") != "phase_10":
        errors.append("doc_type/phase must identify a phase_10 structured_diff")
    if not isinstance(plan, dict):
        errors.append("edit plan is required to verify issue and edit continuity")
        plan = {}

    planned_edits: dict[str, set[str]] = {}
    planned_issue_ids: set[str] = set()
    approval = _obj(plan.get("approved_issue_scope", plan.get("user_approval")))
    authorized_ids = {
        value for value in _list(approval.get("issue_ids"))
        if isinstance(value, str) and ISSUE_RE.fullmatch(value)
    }
    edits = _list(plan.get("edits"))
    for index, edit in enumerate(edits):
        if not isinstance(edit, dict):
            errors.append(f"edit plan edits[{index}] must be an object")
            continue
        edit_id = str(edit.get("edit_id", "")).strip()
        refs = edit.get("issue_ids")
        if not isinstance(refs, list) or not refs:
            errors.append(f"edit plan edits[{index}].issue_ids must be non-empty")
            refs = []
        issue_set: set[str] = set()
        for issue_id in refs:
            if not isinstance(issue_id, str) or not ISSUE_RE.fullmatch(issue_id):
                errors.append(f"edit plan edits[{index}] contains an invalid issue_id")
                continue
            issue_set.add(issue_id)
            planned_issue_ids.add(issue_id)
            if issue_id not in authorized_ids:
                errors.append(f"edit {edit_id} is outside the approved issue scope")
        if not edit_id:
            errors.append(f"edit plan edits[{index}].edit_id is required")
        elif edit_id in planned_edits:
            errors.append(f"duplicate edit_id in plan: {edit_id}")
        else:
            planned_edits[edit_id] = issue_set
    if authorized_ids != planned_issue_ids:
        errors.append("edit plan issue IDs do not exactly cover the approved issue scope")

    items = _list(diff.get("diff_items"))
    if not items:
        errors.append("diff_items must contain at least one recorded change")
    if not isinstance(diff.get("diff_items"), list):
        errors.append("diff_items must be a list")

    diff_edit_ids: set[str] = set()
    diff_issue_ids: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"diff_items[{index}] must be an object")
            continue
        kind = str(item.get("change_kind", "")).strip()
        location = _obj(item.get("location"))
        linked = str(item.get("linked_edit_id", "")).strip()
        refs = item.get("issue_ids")
        if kind not in {"add", "delete", "replace", "move"}:
            errors.append(f"diff_items[{index}].change_kind is invalid")
        if not str(location.get("section", "")).strip():
            errors.append(f"diff_items[{index}].location.section is required")
        if not linked:
            errors.append(f"diff_items[{index}].linked_edit_id is required")
        elif linked not in planned_edits:
            errors.append(f"diff_items[{index}].linked_edit_id does not resolve to an edit plan entry")
        else:
            diff_edit_ids.add(linked)
        if not isinstance(refs, list) or not refs:
            errors.append(f"diff_items[{index}].issue_ids must carry stable review issue IDs")
            refs = []
        item_issue_ids: set[str] = set()
        for issue_id in refs:
            if not isinstance(issue_id, str) or not ISSUE_RE.fullmatch(issue_id):
                errors.append(f"diff_items[{index}].issue_ids contains an invalid issue ID")
                continue
            if issue_id in item_issue_ids:
                errors.append(f"diff_items[{index}] repeats issue_id {issue_id}")
            item_issue_ids.add(issue_id)
            diff_issue_ids.add(issue_id)
            if issue_id not in authorized_ids:
                errors.append(f"diff_items[{index}] includes an issue outside the approved scope")
        if linked in planned_edits and item_issue_ids != planned_edits[linked]:
            errors.append(f"diff_items[{index}] issue_ids do not match linked edit {linked}")

        before = item.get("before_excerpt", "")
        after = item.get("after_excerpt", "")
        if kind in {"delete", "replace", "move"} and not str(before).strip():
            errors.append(f"diff_items[{index}].before_excerpt is required for {kind}")
        if kind in {"add", "replace", "move"} and not str(after).strip():
            errors.append(f"diff_items[{index}].after_excerpt is required for {kind}")

    uncovered_edits = sorted(set(planned_edits) - diff_edit_ids)
    if uncovered_edits:
        errors.append("edit plan entries lack diff items: " + ", ".join(uncovered_edits))
    if planned_issue_ids != diff_issue_ids:
        errors.append("structured diff issue IDs must exactly cover the edit plan issue IDs")

    counts.update({
        "diff_items": len(items),
        "linked_edit_ids": len(diff_edit_ids),
        "issue_ids": len(diff_issue_ids),
        "uncovered_edits": len(uncovered_edits),
    })
    return errors, counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate structured diff coverage by issue")
    parser.add_argument("input")
    parser.add_argument("--edit-plan")
    parser.add_argument("--output")
    args = parser.parse_args()
    diff_path = Path(args.input)
    plan_path = Path(args.edit_plan) if args.edit_plan else _infer_edit_plan(diff_path)
    try:
        diff = _load(diff_path)
        plan = _load(plan_path) if plan_path and plan_path.is_file() else None
        errors, counts = validate(diff, plan)
    except FileNotFoundError:
        errors, counts = ["structured diff or edit plan was not found"], {}
    except (OSError, json.JSONDecodeError):
        errors, counts = ["structured diff or edit plan could not be read as JSON"], {}
    summary = {
        "validator": "validate_structured_diff.py",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "inputPath": str(diff_path.resolve()),
        "editPlanPath": str(plan_path.resolve()) if plan_path else None,
        "checks_passed": not errors,
        "counts": counts,
        "passed": not errors,
        "errors": errors,
    }
    result = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.output:
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(result, encoding="utf-8")
    else:
        print(result)
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
