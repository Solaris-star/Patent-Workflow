#!/usr/bin/env python3
"""Validate background research references against the canonical evidence pack."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

FEATURE_RE = re.compile(r"^F-[A-Z0-9][A-Z0-9._-]*$")


def _list(value: object) -> list:
    return value if isinstance(value, list) else []


def _obj(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _read(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def validate(background: object, evidence_pack: object) -> tuple[list[str], dict]:
    errors: list[str] = []
    counts = {"background_sources": 0, "feature_comparisons": 0, "covered_features": 0}
    if not isinstance(background, dict):
        return ["background pack must be a JSON object"], counts
    if background.get("pack_type") != "background_pack" or background.get("phase") != "phase_05":
        errors.append("pack_type/phase must identify a phase_05 background_pack")
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

    closest = str(background.get("closest_source_evidence_id", "")).strip()
    if not closest:
        errors.append("closest_source_evidence_id is required")
    elif closest not in source_records:
        errors.append("closest_source_evidence_id does not resolve to the canonical evidence_pack")
    elif closest not in verified_ids:
        errors.append("closest source must have verification_status='verified'")
    elif closest not in usable_ids:
        errors.append("closest source is structurally recorded but not usable for current conclusions")

    refs = background.get("evidence_ids")
    if not isinstance(refs, list) or not refs:
        errors.append("evidence_ids must list the actual sources used in the background comparison")
        refs = []
    seen_sources: set[str] = set()
    for evidence_id in refs:
        if not isinstance(evidence_id, str) or evidence_id not in source_records:
            errors.append("background evidence_ids contains an unknown evidence_id")
            continue
        if evidence_id in seen_sources:
            errors.append(f"background evidence_ids repeats {evidence_id}")
        seen_sources.add(evidence_id)
        if evidence_id not in verified_ids:
            errors.append(f"background source {evidence_id} is not verified")
        elif evidence_id not in usable_ids:
            errors.append(f"background source {evidence_id} is not usable for current conclusions")
    if closest and closest not in seen_sources:
        errors.append("closest source must also appear in evidence_ids")

    comparisons = background.get("feature_comparisons")
    if not isinstance(comparisons, list) or not comparisons:
        errors.append("feature_comparisons must identify actual differences for the researched features")
        comparisons = []
    compared_features: set[str] = set()
    for index, item in enumerate(comparisons):
        if not isinstance(item, dict):
            errors.append(f"feature_comparisons[{index}] must be an object")
            continue
        feature_id = str(item.get("feature_id", "")).strip()
        if not FEATURE_RE.fullmatch(feature_id) or feature_id not in feature_ids:
            errors.append(f"feature_comparisons[{index}].feature_id must resolve to a canonical F-... feature")
        elif feature_id in compared_features:
            errors.append(f"duplicate feature comparison: {feature_id}")
        else:
            compared_features.add(feature_id)
        if not str(item.get("difference", "")).strip():
            errors.append(f"feature_comparisons[{index}].difference must describe the observed difference")
        comparison_refs = item.get("evidence_ids")
        if not isinstance(comparison_refs, list) or not comparison_refs:
            errors.append(f"feature_comparisons[{index}].evidence_ids must be non-empty")
            comparison_refs = []
        for evidence_id in comparison_refs:
            if not isinstance(evidence_id, str) or evidence_id not in source_records:
                errors.append(f"feature_comparisons[{index}] references an unknown evidence_id")
            elif evidence_id not in verified_ids:
                errors.append(f"feature_comparisons[{index}] cites unverified evidence")
            elif evidence_id not in seen_sources:
                errors.append(f"feature_comparisons[{index}] cites evidence omitted from background.evidence_ids")
            elif feature_id not in _list(source_records[evidence_id].get("feature_ids")):
                errors.append(f"feature_comparisons[{index}] evidence is not mapped to its feature")
    if feature_ids and compared_features != feature_ids:
        errors.append("background comparisons must cover every stable feature in the evidence pack")

    counts.update({
        "background_sources": len(seen_sources),
        "feature_comparisons": len(comparisons),
        "covered_features": len(compared_features),
    })
    return errors, counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate background pack against verified evidence IDs")
    parser.add_argument("input")
    parser.add_argument("--evidence-pack", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    background_path = Path(args.input)
    evidence_path = Path(args.evidence_pack)
    try:
        errors, counts = validate(_read(background_path), _read(evidence_path))
    except FileNotFoundError:
        errors, counts = ["background pack or evidence pack was not found"], {}
    except (OSError, json.JSONDecodeError):
        errors, counts = ["background pack or evidence pack could not be read as JSON"], {}
    summary = {
        "validator": "validate_background_pack.py",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "inputPath": str(background_path.resolve()),
        "evidencePackPath": str(evidence_path.resolve()),
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
