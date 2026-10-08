#!/usr/bin/env python3
"""Validate an explicitly requested IPR pack against verified source records.

This offline validator checks schema and traceability only; it is not legal
advice and cannot determine patentability, novelty, freedom to operate, or grant
likelihood.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

FEATURE_RE = re.compile(r"^F-[A-Z0-9][A-Z0-9._-]*$")
ID_RE = re.compile(r"^[A-Z0-9][A-Z0-9._-]*$")


def _list(value: object) -> list:
    return value if isinstance(value, list) else []


def _obj(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _read(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def validate(ipr_pack: object, evidence_pack: object, *, requested: bool) -> tuple[list[str], dict]:
    errors: list[str] = []
    counts = {"assessments": 0, "features": 0, "evidence_refs": 0, "verified_evidence_refs": 0}
    if not requested:
        errors.append("IPR validation is disabled unless the run explicitly sets ipr_requested=true")
    if not isinstance(ipr_pack, dict):
        return errors + ["IPR pack must be a JSON object"], counts
    if ipr_pack.get("pack_type") != "ipr_pack" or ipr_pack.get("phase") != "phase_05":
        errors.append("pack_type/phase must identify a phase_05 ipr_pack")
    if not isinstance(evidence_pack, dict) or evidence_pack.get("pack_type") != "evidence_pack":
        errors.append("the canonical evidence_pack is required")
        evidence_pack = {}

    source_records = {
        str(item.get("evidence_id", "")).strip(): item
        for item in _list(evidence_pack.get("evidence"))
        if isinstance(item, dict) and str(item.get("evidence_id", "")).strip()
    }
    verified_ids = {
        evidence_id for evidence_id, item in source_records.items()
        if item.get("verification_status") == "verified"
    }
    usable_ids = {
        evidence_id for evidence_id, item in source_records.items()
        if item.get("verification_status") == "verified"
        and isinstance(item.get("freshness"), str)
        and item.get("freshness") in {"fresh", "valid"}
        and item.get("conclusion_use") == "usable"
    }
    feature_ids = {
        str(item.get("feature_id", "")).strip()
        for item in _list(evidence_pack.get("scheme_features"))
        if isinstance(item, dict) and FEATURE_RE.fullmatch(str(item.get("feature_id", "")).strip())
    }

    assessments = ipr_pack.get("assessments")
    if not isinstance(assessments, list) or not assessments:
        errors.append("assessments must be a non-empty list for a requested IPR pack")
        assessments = []
    assessment_ids: set[str] = set()
    covered_features: set[str] = set()
    evidence_refs: set[str] = set()
    verified_refs: set[str] = set()
    for index, item in enumerate(assessments):
        if not isinstance(item, dict):
            errors.append(f"assessments[{index}] must be an object")
            continue
        assessment_id = str(item.get("assessment_id", "")).strip()
        if not ID_RE.fullmatch(assessment_id):
            errors.append(f"assessments[{index}].assessment_id must be a stable identifier")
        elif assessment_id in assessment_ids:
            errors.append(f"duplicate assessment_id: {assessment_id}")
        else:
            assessment_ids.add(assessment_id)
        if not str(item.get("scope", "")).strip():
            errors.append(f"assessments[{index}].scope is required")
        status = item.get("status")
        if not isinstance(status, str) or status not in {"reviewed", "no_evidence", "pending"}:
            errors.append(f"assessments[{index}].status must be reviewed, no_evidence, or pending")
        if not str(item.get("summary", "")).strip():
            errors.append(f"assessments[{index}].summary is required")

        refs = item.get("feature_ids")
        if not isinstance(refs, list) or not refs:
            errors.append(f"assessments[{index}].feature_ids must cite affected stable features")
            refs = []
        for feature_id in refs:
            if not isinstance(feature_id, str) or feature_id not in feature_ids:
                errors.append(f"assessments[{index}] references an unknown feature_id")
            else:
                covered_features.add(feature_id)

        source_refs = item.get("evidence_ids")
        if not isinstance(source_refs, list):
            errors.append(f"assessments[{index}].evidence_ids must be a list")
            source_refs = []
        if status == "reviewed" and not source_refs:
            errors.append(f"assessments[{index}] reviewed status requires traceable source evidence")
        if isinstance(status, str) and status in {"no_evidence", "pending"} and not str(item.get("limitations", "")).strip():
            errors.append(f"assessments[{index}] requires limitations when no complete evidence review exists")
        for evidence_id in source_refs:
            if not isinstance(evidence_id, str) or evidence_id not in source_records:
                errors.append(f"assessments[{index}] references an unknown evidence_id")
                continue
            evidence_refs.add(evidence_id)
            if evidence_id not in verified_ids:
                errors.append(f"assessments[{index}] cites evidence not marked verified")
            else:
                verified_refs.add(evidence_id)
                if evidence_id not in usable_ids:
                    errors.append(f"assessments[{index}] cites evidence not usable for current conclusions")
            source_features = _list(source_records[evidence_id].get("feature_ids"))
            if not any(feature_id in source_features for feature_id in refs):
                errors.append(f"assessments[{index}] source evidence is not mapped to an assessed feature")

    if feature_ids and covered_features != feature_ids:
        errors.append("requested IPR assessments must cover every feature in the canonical evidence pack")
    counts.update({
        "assessments": len(assessments),
        "features": len(covered_features),
        "evidence_refs": len(evidence_refs),
        "verified_evidence_refs": len(verified_refs),
    })
    return errors, counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate explicitly requested IPR pack structure")
    parser.add_argument("input")
    parser.add_argument("--evidence-pack", required=True)
    parser.add_argument("--ipr-requested", action="store_true", help="Explicit opt-in from run configuration")
    parser.add_argument("--output")
    args = parser.parse_args()
    ipr_path = Path(args.input)
    evidence_path = Path(args.evidence_pack)
    try:
        errors, counts = validate(_read(ipr_path), _read(evidence_path), requested=args.ipr_requested)
    except FileNotFoundError:
        errors, counts = ["IPR pack or evidence pack was not found"], {}
    except (OSError, json.JSONDecodeError):
        errors, counts = ["IPR pack or evidence pack could not be read as JSON"], {}
    summary = {
        "validator": "validate_ipr_pack.py",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "inputPath": str(ipr_path.resolve()),
        "evidencePackPath": str(evidence_path.resolve()),
        "ipr_requested": args.ipr_requested,
        "checks_passed": not errors,
        "structure_only": True,
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
