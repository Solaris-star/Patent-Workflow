#!/usr/bin/env python3
"""Structurally validate review records, report hashes, issue links, and versions.

This validator does not authenticate who created a report, judge semantic
review quality, or establish legal sufficiency. Hashes bind declared files to
their current bytes; the host remains responsible for genuine user decisions.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from workflow_common import canonical_json_sha256, is_within, sha256_file

ISSUE_ID_RE = re.compile(r"^ISSUE-[A-Z0-9][A-Z0-9._-]*$")
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
REVIEW_TYPES = {
    "consistency_review": "consistency_review_report",
    "ipr_review": "ipr_review_report",
}
GENERIC_VALUES = {"all", "everything", "yes", "y", "ok", "approved", "*", "n/a"}


def _resolve_path(value: object, workspace: Path) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    path = Path(value.strip()).expanduser()
    return (path if path.is_absolute() else workspace / path).resolve()


def _allowed_material_path(path: Path, workspace: Path, output_dir: Path | None) -> bool:
    return is_within(path, workspace) or bool(output_dir and is_within(path, output_dir))


def _normalized_hashes(
    value: object,
    workspace: Path,
    output_dir: Path | None,
    *,
    report_name: str,
    errors: list[str],
) -> dict[str, str]:
    if not isinstance(value, dict) or not value:
        errors.append(f"{report_name} files must be a non-empty path-to-SHA-256 object")
        return {}
    normalized: dict[str, str] = {}
    for raw_path, digest in value.items():
        path = _resolve_path(raw_path, workspace)
        if path is None or not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            errors.append(f"{report_name} entries must use valid paths and SHA-256 digests")
            continue
        if not _allowed_material_path(path, workspace, output_dir):
            errors.append(f"{report_name} references a path outside the workspace and configured output directory")
            continue
        key = os.path.normcase(str(path))
        if key in normalized:
            errors.append(f"{report_name} contains duplicate normalized paths")
        normalized[key] = digest.casefold()
    return normalized


def material_version_sha256(material_hashes: dict[str, str]) -> str:
    return canonical_json_sha256(dict(sorted(material_hashes.items())))


def _parse_time(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def _validate_report(
    key: str,
    review: object,
    *,
    workspace: Path,
    output_dir: Path | None,
    expected_materials: dict[str, str],
    expected_version: str,
    errors: list[str],
) -> dict[str, tuple[str, str]]:
    issue_records: dict[str, tuple[str, str]] = {}
    if not isinstance(review, dict) or review.get("status") != "completed":
        errors.append(f"{key}.status must be explicitly 'completed'")
        return issue_records
    if review.get("report_type") != key:
        errors.append(f"{key}.report_type must be '{key}'")
    report_path = _resolve_path(review.get("report_path"), workspace)
    if report_path is None or not is_within(report_path, workspace) or not report_path.is_file():
        errors.append(f"{key}.report_path must identify a structured JSON report inside the workspace")
        return issue_records
    declared_hash = review.get("report_sha256")
    if not isinstance(declared_hash, str) or not SHA256_RE.fullmatch(declared_hash):
        errors.append(f"{key}.report_sha256 must be a SHA-256 digest")
    elif sha256_file(report_path).casefold() != declared_hash.casefold():
        errors.append(f"{key} report hash does not match its current bytes")
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        errors.append(f"{key} report must be readable structured JSON")
        return issue_records
    expected_type = REVIEW_TYPES[key]
    if not isinstance(report, dict) or report.get("doc_type") != expected_type:
        errors.append(f"{key} report doc_type must be '{expected_type}'")
        return issue_records
    if report.get("report_type") != key:
        errors.append(f"{key} report report_type must be '{key}'")
    if not isinstance(report.get("review_id"), str) or not report["review_id"].strip():
        errors.append(f"{key} report review_id is required")
    if not _parse_time(report.get("completed_at")):
        errors.append(f"{key} report completed_at must be an ISO-8601 timestamp")
    if not isinstance(report.get("scope"), str) or not report["scope"].strip():
        errors.append(f"{key} report scope is required")
    report_materials = report.get("reviewed_materials")
    report_hashes = report_materials.get("files") if isinstance(report_materials, dict) else None
    normalized_report_hashes = _normalized_hashes(
        report_hashes, workspace, output_dir, report_name=f"{key} report reviewed_materials", errors=errors,
    )
    if normalized_report_hashes != expected_materials:
        errors.append(f"{key} report material hashes do not match the current review version")
    if not isinstance(report_materials, dict) or report_materials.get("version_sha256") != expected_version:
        errors.append(f"{key} report version hash does not match the current reviewed materials")
    report_issues = report.get("issues")
    if not isinstance(report_issues, list):
        errors.append(f"{key} report issues must be a list, including an empty list")
        return issue_records
    for index, issue in enumerate(report_issues):
        if not isinstance(issue, dict):
            errors.append(f"{key} report issues[{index}] must be an object")
            continue
        issue_id = issue.get("issue_id")
        severity = issue.get("severity")
        disposition = issue.get("disposition")
        summary = issue.get("summary", issue.get("finding", issue.get("problem")))
        if not isinstance(issue_id, str) or not ISSUE_ID_RE.fullmatch(issue_id):
            errors.append(f"{key} report issues[{index}].issue_id must use stable ISSUE-... form")
            continue
        if issue_id in issue_records:
            errors.append(f"{key} report repeats issue_id {issue_id}")
        if not isinstance(severity, str) or severity not in {"high", "medium", "low"}:
            errors.append(f"{key} report issues[{index}].severity is invalid")
        if not isinstance(disposition, str) or disposition not in {"resolved", "open", "waived"}:
            errors.append(f"{key} report issues[{index}].disposition is invalid")
        if not isinstance(summary, str) or not summary.strip():
            errors.append(f"{key} report issues[{index}].summary is required")
        issue_records[issue_id] = (str(severity), str(disposition))
    return issue_records


def _validate_waivers(
    issues: list[dict[str, Any]],
    raw_waivers: object,
    *,
    material_version: str,
    errors: list[str],
) -> None:
    waivers: dict[str, dict[str, Any]] = {}
    if raw_waivers is None:
        raw_waivers = []
    if not isinstance(raw_waivers, list):
        errors.append("user_waivers must be a list of explicit issue-scoped decisions")
        raw_waivers = []
    for index, waiver in enumerate(raw_waivers):
        if not isinstance(waiver, dict):
            errors.append(f"user_waivers[{index}] must be an object")
            continue
        ids = waiver.get("issue_ids")
        scope = waiver.get("scope")
        reasons = waiver.get("accepted_risks")
        valid_ids = (
            isinstance(ids, list) and bool(ids)
            and all(isinstance(item, str) and ISSUE_ID_RE.fullmatch(item) for item in ids)
            and len(set(ids)) == len(ids)
        )
        if not valid_ids:
            errors.append(f"user_waivers[{index}].issue_ids must explicitly list stable issue IDs")
            continue
        if waiver.get("decision") != "accept_specific_risk":
            errors.append(f"user_waivers[{index}].decision must be 'accept_specific_risk'")
        if waiver.get("confirmed_by_user") is not True:
            errors.append(f"user_waivers[{index}] requires host-recorded user confirmation")
        if not _parse_time(waiver.get("confirmed_at")):
            errors.append(f"user_waivers[{index}].confirmed_at must be an ISO-8601 timestamp")
        if not isinstance(waiver.get("approval_reference"), str) or not waiver["approval_reference"].strip():
            errors.append(f"user_waivers[{index}].approval_reference is required")
        if waiver.get("material_version_sha256") != material_version:
            errors.append(f"user_waivers[{index}] must be bound to the current material version")
        scoped_ids = scope.get("issue_ids") if isinstance(scope, dict) else None
        limitations = scope.get("limitations") if isinstance(scope, dict) else None
        if (
            not isinstance(scope, dict)
            or scope.get("kind") != "issue_set"
            or scoped_ids != ids
            or not isinstance(limitations, list)
            or not limitations
            or any(not isinstance(item, str) or not item.strip() or item.strip().casefold() in GENERIC_VALUES
                   for item in limitations)
        ):
            errors.append(f"user_waivers[{index}].scope must enumerate the exact issue set and specific limitations")
        if not isinstance(reasons, dict) or set(reasons) != set(ids):
            errors.append(f"user_waivers[{index}].accepted_risks must provide a reason for every listed issue")
            continue
        for issue_id in ids:
            reason = reasons.get(issue_id)
            if not isinstance(reason, str) or not reason.strip() or reason.strip().casefold() in GENERIC_VALUES:
                errors.append(f"user_waivers[{index}] needs a specific accepted-risk reason for {issue_id}")
            if issue_id in waivers:
                errors.append(f"issue {issue_id} has duplicate user waivers")
            waivers[issue_id] = waiver
    for issue in issues:
        if issue.get("severity") == "high" and issue.get("disposition") == "waived":
            if issue.get("issue_id") not in waivers:
                errors.append(f"high-severity issue {issue.get('issue_id')} needs a version-bound, issue-specific user waiver")


def validate_review_status(
    data: object,
    *,
    workspace: Path,
    require_revision: bool = False,
    output_dir: Path | None = None,
) -> tuple[list[str], dict]:
    errors: list[str] = []
    result = {
        "review_completed": False,
        "workflow_complete": False,
        "revision_validation": "not_run",
        "review_fresh": False,
        "review_version_sha256": None,
        "unresolved_high_issue_ids": [],
        "semantic_review_assessed": False,
        "identity_authenticated": False,
    }
    if not isinstance(data, dict):
        return ["review status must be a JSON object"], result
    workspace = workspace.resolve()
    output_dir = output_dir.resolve() if output_dir else None
    if data.get("doc_type") != "review_status":
        errors.append("doc_type must be 'review_status'")
    if data.get("review_completed") is not True:
        errors.append("review_completed must be explicitly true")

    materials = data.get("reviewed_materials")
    if not isinstance(materials, dict):
        errors.append("reviewed_materials must be an object")
        materials = {}
    material_hashes = _normalized_hashes(
        materials.get("files"), workspace, output_dir,
        report_name="reviewed_materials", errors=errors,
    )
    fresh = bool(material_hashes)
    for normalized_path, expected_hash in material_hashes.items():
        path = Path(normalized_path)
        if not path.is_file():
            errors.append("a reviewed material is missing; review must be repeated")
            fresh = False
            continue
        if sha256_file(path).casefold() != expected_hash:
            errors.append("a reviewed material changed; affected conclusions are pending re-review")
            fresh = False
    final_markdown = _resolve_path(materials.get("final_markdown_path"), workspace)
    if final_markdown is None:
        errors.append("reviewed_materials.final_markdown_path is required")
        fresh = False
    elif not _allowed_material_path(final_markdown, workspace, output_dir):
        errors.append("reviewed final Markdown must be inside the workspace or configured output directory")
        fresh = False
    elif not final_markdown.is_file():
        errors.append("reviewed final Markdown was not found")
        fresh = False
    elif os.path.normcase(str(final_markdown)) not in material_hashes:
        errors.append("final Markdown must be included in reviewed_materials.files")
        fresh = False
    version_hash = material_version_sha256(material_hashes) if material_hashes else ""
    result["review_version_sha256"] = version_hash or None
    if materials.get("version_sha256") != version_hash or not version_hash:
        errors.append("reviewed_materials.version_sha256 must match its normalized file hashes")
        fresh = False

    report_issues: dict[str, tuple[str, str]] = {}
    for key in REVIEW_TYPES:
        current = _validate_report(
            key, data.get(key), workspace=workspace, output_dir=output_dir,
            expected_materials=material_hashes, expected_version=version_hash,
            errors=errors,
        )
        for issue_id, record in current.items():
            if issue_id in report_issues and report_issues[issue_id] != record:
                errors.append(f"review reports disagree on issue {issue_id}")
            report_issues[issue_id] = record

    issues = data.get("issues")
    if not isinstance(issues, list):
        errors.append("issues must be a list, including an empty list when none were found")
        issues = []
    seen_issue_ids: set[str] = set()
    normalized_issues: list[dict[str, Any]] = []
    for index, issue in enumerate(issues):
        if not isinstance(issue, dict):
            errors.append(f"issues[{index}] must be an object")
            continue
        issue_id = issue.get("issue_id")
        if not isinstance(issue_id, str) or not ISSUE_ID_RE.fullmatch(issue_id):
            errors.append(f"issues[{index}].issue_id must use stable ISSUE-... form")
            continue
        if issue_id in seen_issue_ids:
            errors.append(f"duplicate issue_id: {issue_id}")
        seen_issue_ids.add(issue_id)
        severity = issue.get("severity")
        disposition = issue.get("disposition")
        if not isinstance(severity, str) or severity not in {"high", "medium", "low"}:
            errors.append(f"issues[{index}].severity must be high, medium, or low")
        if not isinstance(disposition, str) or disposition not in {"resolved", "open", "waived"}:
            errors.append(f"issues[{index}].disposition must be resolved, open, or waived")
        if severity == "high" and disposition == "open":
            result["unresolved_high_issue_ids"].append(issue_id)
            errors.append(f"high-severity issue {issue_id} needs a concrete user waiver or resolution")
        normalized_issues.append(issue)
    if set(report_issues) != seen_issue_ids:
        errors.append("review status issue IDs must match the stable issue IDs in the structured reports")
    for issue in normalized_issues:
        issue_id = issue.get("issue_id")
        if issue_id in report_issues and (
            report_issues[issue_id][0] != str(issue.get("severity"))
            or report_issues[issue_id][1] != str(issue.get("disposition"))
        ):
            errors.append(f"review status disposition does not match structured report for {issue_id}")
    _validate_waivers(
        normalized_issues, data.get("user_waivers"), material_version=version_hash, errors=errors,
    )
    result["review_fresh"] = fresh and not any("report" in error or "hash" in error for error in errors)

    revision = data.get("revision_validation")
    if not isinstance(revision, str) or revision not in {"passed", "not_required", "pending", "failed"}:
        errors.append("revision_validation must be passed, not_required, pending, or failed")
        revision = "not_run"
    result["revision_validation"] = revision
    if require_revision and revision != "passed":
        errors.append("authorized revisions require revision_validation='passed'")
    if revision == "passed":
        post_fix_report = _resolve_path(data.get("post_fix_report_path"), workspace)
        if post_fix_report is None or not is_within(post_fix_report, workspace) or not post_fix_report.is_file():
            errors.append("post-fix verification report must be found inside the workspace")
        else:
            try:
                report = json.loads(post_fix_report.read_text(encoding="utf-8"))
                if not isinstance(report, dict) or report.get("checks_passed") is not True:
                    errors.append("post-fix verification report does not confirm checks_passed")
                else:
                    report_hashes = report.get("material_hashes")
                    if not isinstance(report_hashes, dict):
                        nested = report.get("reviewed_materials")
                        report_hashes = nested.get("files") if isinstance(nested, dict) else None
                    post_hashes = _normalized_hashes(
                        report_hashes, workspace, output_dir,
                        report_name="post-fix report materials", errors=errors,
                    )
                    if not material_hashes or post_hashes != material_hashes:
                        errors.append("post-fix report hashes do not match the current reviewed materials")
                    expected_outcomes = {
                        str(issue.get("issue_id", "")): str(issue.get("disposition", ""))
                        for issue in normalized_issues
                    }
                    outcomes = report.get("issue_outcomes")
                    if not isinstance(outcomes, dict) or outcomes != expected_outcomes:
                        errors.append("post-fix report issue_outcomes must match the latest review issue dispositions")
            except (OSError, UnicodeError, json.JSONDecodeError):
                errors.append("post-fix verification report is not readable JSON")

    result["review_completed"] = data.get("review_completed") is True and not errors
    result["workflow_complete"] = result["review_completed"] and revision in {"passed", "not_required"}
    return errors, result


def main() -> int:
    parser = argparse.ArgumentParser(description="Structurally validate review reports and current material versions")
    parser.add_argument("input", help="Path to artifacts/audit/review_status.json")
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--output-dir", help="Explicit configured delivery directory; may be outside workspace")
    parser.add_argument("--require-revision", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()
    input_path = Path(args.input)
    workspace = Path(args.workspace).resolve()
    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else None
    try:
        data = json.loads(input_path.read_text(encoding="utf-8"))
        errors, state = validate_review_status(
            data, workspace=workspace, output_dir=output_dir,
            require_revision=args.require_revision,
        )
    except FileNotFoundError:
        errors, state = ["review status was not found"], {
            "review_completed": False, "workflow_complete": False, "revision_validation": "not_run",
            "review_fresh": False, "unresolved_high_issue_ids": [], "semantic_review_assessed": False,
            "identity_authenticated": False, "review_version_sha256": None,
        }
    except Exception:
        errors, state = ["review status could not be parsed"], {
            "review_completed": False, "workflow_complete": False, "revision_validation": "not_run",
            "review_fresh": False, "unresolved_high_issue_ids": [], "semantic_review_assessed": False,
            "identity_authenticated": False, "review_version_sha256": None,
        }
    summary = {
        "validator": "validate_review_status.py",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        **state,
        "checks_passed": not errors,
        "passed": not errors,
        "errors": errors,
    }
    output = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.output:
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(output, encoding="utf-8")
    else:
        print(output)
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
