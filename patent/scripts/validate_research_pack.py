#!/usr/bin/env python3
"""Validate the offline structure of a Phase 2 research pack.

No result-count quota is imposed by default. This script checks that supplied
records are traceable; it does not verify sources or assess legal novelty.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ID_RE = re.compile(r"^[A-Z0-9][A-Z0-9._-]*$")
FEATURE_RE = re.compile(r"^F-[A-Z0-9][A-Z0-9._-]*$")
FRESHNESS = {"fresh", "valid", "stale", "unknown", "historical", "not_applicable"}
VERIFICATION = {"verified", "unverified", "needs_review", "failed"}
CONCLUSION_USE = {"usable", "pending_reverification", "context_only"}


def _choice(value: object, allowed: set[str]) -> bool:
    return isinstance(value, str) and value in allowed


def _list(value: object) -> list:
    return value if isinstance(value, list) else []


def _url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _date(value: object, *, unknown: bool = False) -> bool:
    if unknown and value == "unknown":
        return True
    if not isinstance(value, str) or not value.strip():
        return False
    raw = value.strip()
    try:
        date.fromisoformat(raw[:10])
        return True
    except ValueError:
        try:
            datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return True
        except ValueError:
            return False


def validate(data: object) -> tuple[list[str], dict]:
    errors: list[str] = []
    counts = {
        "research_questions": 0, "outline_skeleton": 0, "evidence": 0, "verified_evidence": 0,
        "usable_for_current_conclusions": 0, "pending_reverification": 0,
    }
    if not isinstance(data, dict):
        return ["research pack must be a JSON object"], counts
    if data.get("pack_type") != "research_pack":
        errors.append("pack_type must be 'research_pack'")
    if data.get("phase") != "phase_02":
        errors.append("phase must be 'phase_02'")

    questions = data.get("research_questions")
    outline = data.get("outline_skeleton")
    evidence = data.get("evidence")
    for name, value in (("research_questions", questions), ("outline_skeleton", outline), ("evidence", evidence)):
        if not isinstance(value, list) or not value:
            errors.append(f"{name} must be a non-empty list; no arbitrary item quota is applied")
    questions = _list(questions)
    outline = _list(outline)
    evidence = _list(evidence)

    question_ids: set[str] = set()
    for index, item in enumerate(questions):
        if not isinstance(item, dict):
            errors.append(f"research_questions[{index}] must be an object")
            continue
        question_id = str(item.get("id", "")).strip()
        if not ID_RE.fullmatch(question_id):
            errors.append(f"research_questions[{index}].id must be a stable non-empty identifier")
        elif question_id in question_ids:
            errors.append(f"duplicate research question id: {question_id}")
        else:
            question_ids.add(question_id)
        if not str(item.get("question", "")).strip():
            errors.append(f"research_questions[{index}].question is required")

    evidence_by_id: dict[str, dict] = {}
    for index, item in enumerate(evidence):
        if not isinstance(item, dict):
            errors.append(f"evidence[{index}] must be an object")
            continue
        evidence_id = str(item.get("evidence_id", "")).strip()
        if not ID_RE.fullmatch(evidence_id):
            errors.append(f"evidence[{index}].evidence_id must be a stable non-empty identifier")
        elif evidence_id in evidence_by_id:
            errors.append(f"duplicate evidence_id: {evidence_id}")
        else:
            evidence_by_id[evidence_id] = item
        if not _url(item.get("url")):
            errors.append(f"evidence[{index}].url must be an http(s) URL")
        if not str(item.get("excerpt", "")).strip():
            errors.append(f"evidence[{index}].excerpt is required")
        publication_date = item.get("publication_date", item.get("date"))
        if not _date(publication_date, unknown=True):
            errors.append(f"evidence[{index}].publication_date must be ISO date/datetime or 'unknown'")
        freshness = item.get("freshness")
        if not _choice(freshness, FRESHNESS):
            errors.append(f"evidence[{index}].freshness must state its age assessment")
        verification = item.get("verification_status")
        if not _choice(verification, VERIFICATION):
            errors.append(f"evidence[{index}].verification_status must be explicit")
        if verification == "verified":
            counts["verified_evidence"] += 1
            if not _date(item.get("verified_at")):
                errors.append(f"evidence[{index}].verified_at is required for verified evidence")
            if not str(item.get("verification_method", "")).strip():
                errors.append(f"evidence[{index}].verification_method is required for verified evidence")
        if publication_date == "unknown" and _choice(freshness, {"fresh", "valid"}):
            errors.append(f"evidence[{index}] cannot claim fresh/valid status with an unknown publication date")
        conclusion_use = item.get("conclusion_use")
        if not _choice(conclusion_use, CONCLUSION_USE):
            errors.append(
                f"evidence[{index}].conclusion_use must be usable, pending_reverification, or context_only"
            )
        elif conclusion_use == "usable":
            if verification != "verified" or not _choice(freshness, {"fresh", "valid"}):
                errors.append(
                    f"evidence[{index}] cannot support a current conclusion until task-specific re-verification"
                )
            else:
                counts["usable_for_current_conclusions"] += 1
        elif conclusion_use == "pending_reverification":
            counts["pending_reverification"] += 1
        feature_ids = item.get("feature_ids")
        if feature_ids is not None:
            if not isinstance(feature_ids, list):
                errors.append(f"evidence[{index}].feature_ids must be a list when present")
            else:
                for feature_id in feature_ids:
                    if not isinstance(feature_id, str) or not FEATURE_RE.fullmatch(feature_id):
                        errors.append(f"evidence[{index}].feature_ids must use stable F-... identifiers")

    feature_catalog = data.get("scheme_features", [])
    if not isinstance(feature_catalog, list):
        errors.append("scheme_features must be a list when present")
        feature_catalog = []
    feature_ids: set[str] = set()
    for index, feature in enumerate(feature_catalog):
        if not isinstance(feature, dict):
            errors.append(f"scheme_features[{index}] must be an object")
            continue
        feature_id = str(feature.get("feature_id", "")).strip()
        if not FEATURE_RE.fullmatch(feature_id):
            errors.append(f"scheme_features[{index}].feature_id must use stable F-... form")
        elif feature_id in feature_ids:
            errors.append(f"duplicate scheme feature id: {feature_id}")
        else:
            feature_ids.add(feature_id)
        refs = feature.get("evidence_ids")
        if not isinstance(refs, list):
            errors.append(f"scheme_features[{index}].evidence_ids must be a list")
            continue
        for evidence_id in refs:
            source = evidence_by_id.get(evidence_id) if isinstance(evidence_id, str) else None
            if source is None:
                errors.append(f"scheme_features[{index}] references an unknown evidence_id")
            elif feature_id not in _list(source.get("feature_ids")):
                errors.append(f"research feature/evidence mapping is inconsistent for {feature_id}")
    if feature_ids:
        for evidence_id, item in evidence_by_id.items():
            for feature_id in _list(item.get("feature_ids")):
                if feature_id not in feature_ids:
                    errors.append(f"evidence {evidence_id} references an unknown scheme feature")

    section_ids: set[str] = set()
    for index, section in enumerate(outline):
        if not isinstance(section, dict):
            errors.append(f"outline_skeleton[{index}] must be an object")
            continue
        section_id = str(section.get("section_id", "")).strip()
        if not section_id:
            errors.append(f"outline_skeleton[{index}].section_id is required")
        elif section_id in section_ids:
            errors.append(f"duplicate outline section id: {section_id}")
        else:
            section_ids.add(section_id)
        if not str(section.get("title", "")).strip():
            errors.append(f"outline_skeleton[{index}].title is required")
        if not str(section.get("intent", "")).strip():
            errors.append(f"outline_skeleton[{index}].intent is required")
        for question_id in _list(section.get("covers_questions")):
            if not isinstance(question_id, str) or question_id not in question_ids:
                errors.append(f"outline_skeleton[{index}] references an unknown research question")
        for evidence_id in _list(section.get("evidence_ids")):
            if not isinstance(evidence_id, str) or evidence_id not in evidence_by_id:
                errors.append(f"outline_skeleton[{index}] references an unknown evidence_id")

    counts.update({"research_questions": len(questions), "outline_skeleton": len(outline), "evidence": len(evidence)})
    counts["structure_valid"] = not errors
    counts["conclusion_ready"] = not errors and counts["usable_for_current_conclusions"] > 0
    return errors, counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Phase 2 research-pack structure")
    parser.add_argument("input")
    parser.add_argument("--output")
    parser.add_argument("--min-questions", type=int, default=0, help="Optional caller-requested threshold")
    parser.add_argument("--min-outline", type=int, default=0, help="Optional caller-requested threshold")
    parser.add_argument("--min-evidence", type=int, default=0, help="Optional caller-requested threshold")
    args = parser.parse_args()
    inp = Path(args.input)
    try:
        data = json.loads(inp.read_text(encoding="utf-8"))
        errors, counts = validate(data)
        for key, value in (("research_questions", args.min_questions), ("outline_skeleton", args.min_outline), ("evidence", args.min_evidence)):
            if value and counts[key] < value:
                errors.append(f"{key} is below caller-requested threshold {value}")
    except FileNotFoundError:
        errors, counts = ["research pack was not found"], {}
    except (OSError, json.JSONDecodeError):
        errors, counts = ["research pack could not be read as JSON"], {}
    summary = {
        "validator": "validate_research_pack.py",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "inputPath": str(inp.resolve()),
        "checks_passed": not errors,
        "structure_only": True,
        "structure_valid": counts.get("structure_valid", not errors),
        "conclusion_ready": counts.get("conclusion_ready", False),
        "workflow_complete": counts.get("conclusion_ready", False),
        "legal_novelty_assessed": False,
        "uniform_expiry_days_applied": False,
        "counts": counts,
        "requested_thresholds": {
            "min_questions": args.min_questions,
            "min_outline": args.min_outline,
            "min_evidence": args.min_evidence,
        },
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
