#!/usr/bin/env python3
"""Validate an edit plan against the review report and explicit issue scope."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ISSUE_RE = re.compile(r"^ISSUE-[A-Z0-9][A-Z0-9._-]*$")
EDIT_RE = re.compile(r"^EDIT-[A-Z0-9][A-Z0-9._-]*$")


def _list(value: object) -> list:
    return value if isinstance(value, list) else []


def _object(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _infer_review_status(plan_path: Path) -> Path | None:
    resolved = plan_path.resolve()
    for ancestor in resolved.parents:
        candidate = ancestor / "audit" / "review_status.json"
        if ancestor.name == "artifacts" and candidate.is_file():
            return candidate
        candidate = ancestor / "artifacts" / "audit" / "review_status.json"
        if candidate.is_file():
            return candidate
    return None


def _approval(plan: dict) -> dict:
    value = plan.get("approved_issue_scope", plan.get("user_approval"))
    return _object(value)


def validate(plan: object, review: object | None) -> tuple[list[str], dict]:
    errors: list[str] = []
    counts = {"edits": 0, "issue_ids": 0, "approved_issue_ids": 0, "review_issue_ids": 0}
    if not isinstance(plan, dict):
        return ["edit plan must be a JSON object"], counts
    if plan.get("doc_type") != "edit_plan" or plan.get("phase") != "phase_10":
        errors.append("doc_type/phase must identify a phase_10 edit_plan")

    approval = _approval(plan)
    if approval.get("confirmed_by_user") is not True:
        errors.append("approved_issue_scope.confirmed_by_user must be explicitly true")
    if not str(approval.get("scope", "")).strip():
        errors.append("approved_issue_scope.scope must describe the user-approved boundary")
    approved_at = approval.get("confirmed_at", approval.get("approved_at"))
    try:
        if not isinstance(approved_at, str) or not approved_at.strip():
            raise ValueError
        datetime.fromisoformat(approved_at.strip().replace("Z", "+00:00"))
    except ValueError:
        errors.append("approved_issue_scope.confirmed_at must be an ISO date or datetime")
    approval_id = str(approval.get("approval_id", "")).strip()
    if not approval_id:
        errors.append("approved_issue_scope.approval_id is required to preserve authorization provenance")
    approved_raw = approval.get("issue_ids")
    if not isinstance(approved_raw, list) or not approved_raw:
        errors.append("approved_issue_scope.issue_ids must explicitly list approved issue IDs")
        approved_raw = []
    approved_ids: set[str] = set()
    for issue_id in approved_raw:
        if not isinstance(issue_id, str) or not ISSUE_RE.fullmatch(issue_id):
            errors.append("approved_issue_scope.issue_ids must use stable ISSUE-... IDs")
        elif issue_id in approved_ids:
            errors.append(f"approved_issue_scope repeats issue_id {issue_id}")
        else:
            approved_ids.add(issue_id)

    edits = _list(plan.get("edits"))
    if not edits:
        errors.append("edits must contain at least one planned edit")
    acceptance = _list(plan.get("acceptance_checks"))
    if not acceptance:
        errors.append("acceptance_checks must contain at least one check")
    for index, check in enumerate(acceptance):
        if not isinstance(check, str) or not check.strip():
            errors.append(f"acceptance_checks[{index}] must be a non-empty string")

    edit_ids: set[str] = set()
    issue_ids: set[str] = set()
    edits_by_id: dict[str, dict] = {}
    for index, edit in enumerate(edits):
        if not isinstance(edit, dict):
            errors.append(f"edits[{index}] must be an object")
            continue
        edit_id = str(edit.get("edit_id", "")).strip()
        if not EDIT_RE.fullmatch(edit_id):
            errors.append(f"edits[{index}].edit_id must use stable EDIT-... form")
        elif edit_id in edit_ids:
            errors.append(f"duplicate edit_id: {edit_id}")
        else:
            edit_ids.add(edit_id)
            edits_by_id[edit_id] = edit
        for field in ("type", "problem", "change_instruction", "risk_if_not_fixed"):
            if not str(edit.get(field, "")).strip():
                errors.append(f"edits[{index}].{field} is required")
        risk = edit.get("risk_if_not_fixed")
        if not isinstance(risk, str) or risk not in {"high", "medium", "low"}:
            errors.append(f"edits[{index}].risk_if_not_fixed must be high, medium, or low")
        target = _object(edit.get("target"))
        if not str(target.get("section", "")).strip():
            errors.append(f"edits[{index}].target.section is required")
        refs = edit.get("issue_ids")
        if not isinstance(refs, list) or not refs:
            errors.append(f"edits[{index}].issue_ids must link each edit to reviewed issue IDs")
            refs = []
        seen: set[str] = set()
        for issue_id in refs:
            if not isinstance(issue_id, str) or not ISSUE_RE.fullmatch(issue_id):
                errors.append(f"edits[{index}].issue_ids must use stable ISSUE-... IDs")
            elif issue_id in seen:
                errors.append(f"edits[{index}] repeats issue_id {issue_id}")
            else:
                seen.add(issue_id)
                issue_ids.add(issue_id)
                if issue_id not in approved_ids:
                    errors.append(f"edit {edit_id} exceeds the user-approved issue scope: {issue_id}")
        if edit.get("scope_expansion") is True or _list(edit.get("new_technical_facts")):
            extra_approval = _object(edit.get("additional_user_approval"))
            extra_at = extra_approval.get("confirmed_at", extra_approval.get("approved_at"))
            try:
                if not isinstance(extra_at, str) or not extra_at.strip():
                    raise ValueError
                datetime.fromisoformat(extra_at.strip().replace("Z", "+00:00"))
                valid_extra_time = True
            except ValueError:
                valid_extra_time = False
            extra_issue_ids = extra_approval.get("issue_ids")
            valid_extra_ids = (
                isinstance(extra_issue_ids, list)
                and bool(extra_issue_ids)
                and all(isinstance(value, str) and ISSUE_RE.fullmatch(value) for value in extra_issue_ids)
            )
            if (
                extra_approval.get("confirmed_by_user") is not True
                or not str(extra_approval.get("approval_id", "")).strip()
                or not str(extra_approval.get("scope", "")).strip()
                or not valid_extra_time
                or not valid_extra_ids
                or not seen.issubset(set(extra_issue_ids or []))
            ):
                errors.append(f"edits[{index}] adds scope or technical facts without a separate explicit user approval")

    if issue_ids != approved_ids:
        errors.append("edit issue IDs must exactly cover approved_issue_scope.issue_ids")

    review_issue_ids: set[str] = set()
    if not isinstance(review, dict):
        errors.append("review_status is required to link edits to reported issues")
    else:
        issues = review.get("issues")
        if not isinstance(issues, list):
            errors.append("review_status.issues must be a list")
        else:
            for index, issue in enumerate(issues):
                if not isinstance(issue, dict):
                    errors.append(f"review_status.issues[{index}] must be an object")
                    continue
                issue_id = str(issue.get("issue_id", "")).strip()
                if not ISSUE_RE.fullmatch(issue_id):
                    errors.append(f"review_status.issues[{index}].issue_id must use stable ISSUE-... form")
                elif issue_id in review_issue_ids:
                    errors.append(f"duplicate review issue_id: {issue_id}")
                else:
                    review_issue_ids.add(issue_id)
            for issue_id in approved_ids:
                if issue_id not in review_issue_ids:
                    errors.append(f"approved issue {issue_id} does not appear in review_status")

    counts.update({
        "edits": len(edits),
        "issue_ids": len(issue_ids),
        "approved_issue_ids": len(approved_ids),
        "review_issue_ids": len(review_issue_ids),
    })
    return errors, counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate issue-scoped phase_10 edit plan")
    parser.add_argument("input")
    parser.add_argument("--review-status", help="Review report that supplied the stable issue IDs")
    parser.add_argument("--output")
    parser.add_argument("--require-acceptance-check", action="append", default=[])
    args = parser.parse_args()
    input_path = Path(args.input)
    review_path = Path(args.review_status) if args.review_status else _infer_review_status(input_path)
    errors: list[str] = []
    counts: dict = {}
    try:
        plan = _load_json(input_path)
        review = _load_json(review_path) if review_path and review_path.is_file() else None
        errors, counts = validate(plan, review)
        acceptance = _list(_object(plan).get("acceptance_checks"))
        for key in args.require_acceptance_check:
            if key not in acceptance:
                errors.append(f"acceptance_checks is missing caller-required key: {key}")
    except FileNotFoundError:
        errors = ["edit plan or review status was not found"]
    except (OSError, json.JSONDecodeError):
        errors = ["edit plan or review status could not be read as JSON"]
    summary = {
        "validator": "validate_edit_plan.py",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "inputPath": str(input_path.resolve()),
        "reviewStatusPath": str(review_path.resolve()) if review_path else None,
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
