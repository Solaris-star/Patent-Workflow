#!/usr/bin/env python3
"""Validate the structure and traceability of the canonical Phase 4 evidence pack.

This is an offline structural check. It does not verify source authenticity or
establish novelty, patentability, or grant likelihood.
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
EVIDENCE_KINDS = {"implemented_fact", "source_claim", "inference", "pending_confirmation"}
FRESHNESS = {"fresh", "valid", "stale", "unknown", "historical", "not_applicable"}
VERIFICATION = {"verified", "unverified", "needs_review", "failed"}
CONCLUSION_USE = {"usable", "pending_reverification", "context_only"}


def _list(value: object) -> list:
    return value if isinstance(value, list) else []


def _obj(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _valid_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _valid_date(value: object, *, allow_unknown: bool = False) -> bool:
    if allow_unknown and value == "unknown":
        return True
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        date.fromisoformat(value.strip()[:10])
        return True
    except ValueError:
        try:
            datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            return True
        except ValueError:
            return False


def _is_choice(value: object, choices: set[str]) -> bool:
    return isinstance(value, str) and value in choices


def validate(data: object) -> tuple[list[str], dict]:
    errors: list[str] = []
    counts = {
        "evidence": 0, "features": 0, "alignments": 0, "verified": 0,
        "usable_for_current_conclusions": 0, "pending_reverification": 0,
    }
    if not isinstance(data, dict):
        return ["evidence pack must be a JSON object"], counts

    if data.get("pack_type") != "evidence_pack":
        errors.append("pack_type must be 'evidence_pack'")
    if data.get("phase") != "phase_04":
        errors.append("phase must be 'phase_04'")
    if not str(data.get("patent_candidate_pool_path", "")).strip():
        errors.append("patent_candidate_pool_path is required")

    search_trace = _obj(data.get("search_trace"))
    if not search_trace:
        errors.append("search_trace must be an object, including when a search was degraded")
    queries = search_trace.get("patent_search_queries")
    if not isinstance(queries, list):
        errors.append("search_trace.patent_search_queries must be a list")
    declared_count = search_trace.get("final_relevant_patent_count")
    patents = data.get("final_relevant_patents")
    if patents is not None and not isinstance(patents, list):
        errors.append("final_relevant_patents must be a list when present")
    elif isinstance(patents, list) and isinstance(declared_count, int) and declared_count != len(patents):
        errors.append("search_trace.final_relevant_patent_count does not match final_relevant_patents length")

    features = _list(data.get("scheme_features"))
    evidence = _list(data.get("evidence"))
    alignments = _list(data.get("evidence_alignment"))
    if not features:
        errors.append("scheme_features must identify the features considered in this search")
    if not evidence:
        errors.append("evidence must contain at least one source record; do not fabricate records to meet a count")
    if data.get("evidence_alignment") is not None and not isinstance(data.get("evidence_alignment"), list):
        errors.append("evidence_alignment must be a list when present")

    feature_by_id: dict[str, dict] = {}
    for index, item in enumerate(features):
        if not isinstance(item, dict):
            errors.append(f"scheme_features[{index}] must be an object")
            continue
        feature_id = str(item.get("feature_id", "")).strip()
        if not FEATURE_RE.fullmatch(feature_id):
            errors.append(f"scheme_features[{index}].feature_id must use stable F-... form")
        elif feature_id in feature_by_id:
            errors.append(f"duplicate feature_id: {feature_id}")
        else:
            feature_by_id[feature_id] = item
        if not str(item.get("statement", item.get("description", ""))).strip():
            errors.append(f"scheme_features[{index}].statement is required")
        kind = item.get("evidence_kind")
        status = item.get("status")
        if not _is_choice(kind, EVIDENCE_KINDS):
            errors.append(f"scheme_features[{index}].evidence_kind is invalid")
        if kind == "pending_confirmation" and status != "pending":
            errors.append(f"scheme_features[{index}] pending confirmation must have status='pending'")
        if (
            _is_choice(kind, EVIDENCE_KINDS - {"pending_confirmation"})
            and not _is_choice(status, {"confirmed", "source_stated"})
        ):
            errors.append(f"scheme_features[{index}].status must distinguish confirmed/source-stated facts")
        refs = item.get("evidence_ids")
        if not isinstance(refs, list):
            errors.append(f"scheme_features[{index}].evidence_ids must be a list")

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
        if not _valid_url(item.get("url")):
            errors.append(f"evidence[{index}].url must be an http(s) URL")
        if not str(item.get("excerpt", "")).strip():
            errors.append(f"evidence[{index}].excerpt is required")

        publication_date = item.get("publication_date", item.get("date"))
        if not _valid_date(publication_date, allow_unknown=True):
            errors.append(f"evidence[{index}].publication_date must be ISO date/datetime or 'unknown'")
        freshness = item.get("freshness")
        if not _is_choice(freshness, FRESHNESS):
            errors.append(f"evidence[{index}].freshness must state its age assessment")
        verification = item.get("verification_status")
        if not _is_choice(verification, VERIFICATION):
            errors.append(f"evidence[{index}].verification_status must be explicit")
        if verification == "verified":
            counts["verified"] += 1
            if not _valid_date(item.get("verified_at")):
                errors.append(f"evidence[{index}].verified_at is required for verified evidence")
            if not str(item.get("verification_method", "")).strip():
                errors.append(f"evidence[{index}].verification_method is required for verified evidence")
        if publication_date == "unknown" and _is_choice(freshness, {"fresh", "valid"}):
            errors.append(f"evidence[{index}] cannot claim fresh/valid status with an unknown publication date")
        conclusion_use = item.get("conclusion_use")
        if not _is_choice(conclusion_use, CONCLUSION_USE):
            errors.append(
                f"evidence[{index}].conclusion_use must be usable, pending_reverification, or context_only"
            )
        elif conclusion_use == "usable":
            if verification != "verified" or not _is_choice(freshness, {"fresh", "valid"}):
                errors.append(
                    f"evidence[{index}] cannot be used in a current conclusion until its task-specific status is verified"
                )
            else:
                counts["usable_for_current_conclusions"] += 1
        elif conclusion_use == "pending_reverification":
            counts["pending_reverification"] += 1

        refs = item.get("feature_ids")
        if not isinstance(refs, list) or not refs:
            errors.append(f"evidence[{index}].feature_ids must link the source to one or more stable features")
        else:
            for feature_id in refs:
                if not isinstance(feature_id, str) or feature_id not in feature_by_id:
                    errors.append(f"evidence[{index}] references an unknown feature_id")

    for feature_id, feature in feature_by_id.items():
        refs = feature.get("evidence_ids")
        if not isinstance(refs, list):
            continue
        seen_refs: set[str] = set()
        for evidence_id in refs:
            if not isinstance(evidence_id, str) or evidence_id not in evidence_by_id:
                errors.append(f"feature {feature_id} references an unknown evidence_id")
                continue
            if evidence_id in seen_refs:
                errors.append(f"feature {feature_id} repeats evidence_id {evidence_id}")
            seen_refs.add(evidence_id)
            source_features = _list(evidence_by_id[evidence_id].get("feature_ids"))
            if feature_id not in source_features:
                errors.append(f"feature/evidence mapping is inconsistent for {feature_id} and {evidence_id}")
        for evidence_id, source in evidence_by_id.items():
            if feature_id in _list(source.get("feature_ids")) and evidence_id not in refs:
                errors.append(f"evidence {evidence_id} maps to {feature_id} but the feature omits that evidence_id")

    for index, item in enumerate(alignments):
        if not isinstance(item, dict):
            errors.append(f"evidence_alignment[{index}] must be an object")
            continue
        feature_id = str(item.get("feature_id", "")).strip()
        if feature_id not in feature_by_id:
            errors.append(f"evidence_alignment[{index}] references an unknown feature_id")
        refs = item.get("evidence_ids")
        if not isinstance(refs, list) or not refs:
            errors.append(f"evidence_alignment[{index}].evidence_ids must be a non-empty list")
        else:
            for evidence_id in refs:
                if not isinstance(evidence_id, str) or evidence_id not in evidence_by_id:
                    errors.append(f"evidence_alignment[{index}] references an unknown evidence_id")
                elif feature_id and feature_id not in _list(evidence_by_id[evidence_id].get("feature_ids")):
                    errors.append(f"evidence_alignment[{index}] evidence does not map to its feature_id")

    counts.update({"evidence": len(evidence), "features": len(features), "alignments": len(alignments)})
    return errors, counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Phase 4 evidence-pack structure and traceability")
    parser.add_argument("input")
    parser.add_argument("--output")
    parser.add_argument("--min-final", type=int, default=0, help="Optional caller-requested candidate threshold")
    parser.add_argument("--min-alignments", type=int, default=0, help="Optional caller-requested alignment threshold")
    args = parser.parse_args()
    inp = Path(args.input)
    errors: list[str] = []
    counts: dict = {"evidence": 0, "features": 0, "alignments": 0, "verified": 0}
    try:
        data = json.loads(inp.read_text(encoding="utf-8"))
        errors, counts = validate(data)
        if args.min_final and len(_list(_obj(data).get("final_relevant_patents"))) < args.min_final:
            errors.append(f"final_relevant_patents length is below requested threshold {args.min_final}")
        if args.min_alignments and counts["alignments"] < args.min_alignments:
            errors.append(f"evidence_alignment length is below requested threshold {args.min_alignments}")
    except FileNotFoundError:
        errors = ["evidence pack was not found"]
    except (OSError, json.JSONDecodeError):
        errors = ["evidence pack could not be read as JSON"]

    structure_valid = not errors
    conclusion_ready = structure_valid and counts["usable_for_current_conclusions"] > 0
    summary = {
        "validator": "validate_evidence_pack.py",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "inputPath": str(inp.resolve()),
        "checks_passed": structure_valid,
        "structure_only": True,
        "structure_valid": structure_valid,
        "conclusion_ready": conclusion_ready,
        "workflow_complete": conclusion_ready,
        "legal_novelty_assessed": False,
        "uniform_expiry_days_applied": False,
        "counts": counts,
        "requested_thresholds": {"min_final": args.min_final, "min_alignments": args.min_alignments},
        "passed": structure_valid,
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
