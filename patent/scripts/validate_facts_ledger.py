#!/usr/bin/env python3
"""Validate source, feature, draft-part, and figure traceability."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from workflow_common import TITLE_MAX_CHARS, is_within, manifest_field_text, sha256_file


def _list(value: object) -> list:
    return value if isinstance(value, list) else []


def _dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _resolved(value: str, base_dir: Path) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def _lexically_within(value: str, base_dir: Path) -> Path | None:
    """Resolve `..` lexically so outside paths are rejected before filesystem access."""
    path = Path(value)
    if not path.is_absolute():
        path = base_dir / path
    candidate = Path(os.path.abspath(os.fspath(path)))
    root = Path(os.path.abspath(os.fspath(base_dir)))
    try:
        candidate_root = os.path.normcase(os.path.commonpath((str(candidate), str(root))))
        expected_root = os.path.normcase(str(root))
    except ValueError:
        return None
    return candidate if candidate_root == expected_root else None


def _part_files(parts_dir: Path) -> dict[str, list[Path]]:
    found: dict[str, list[Path]] = {}
    for number in range(1, 6):
        found[f"part_{number:02d}"] = sorted(parts_dir.glob(f"part_{number:02d}_*.md"))
    return found


def validate_ledger(
    data: object,
    *,
    base_dir: Path,
    figure_delivery_mode: str = "mermaid_only",
    evidence_pack_path: Path | None = None,
    require_main_parts: bool = False,
    require_docx_visible_mermaid: bool = False,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["facts ledger must be a JSON object"]
    if data.get("ledger_type") != "facts_ledger":
        errors.append("ledger_type must be 'facts_ledger'")

    terminology = _list(data.get("terminology"))
    constraints = _list(data.get("constraints_and_effects"))
    figures = _list(data.get("figure_registry"))
    features = _list(data.get("feature_registry"))
    sources = _list(data.get("source_registry"))
    if not terminology:
        errors.append("terminology must be non-empty")
    if not constraints:
        errors.append("constraints_and_effects must be non-empty")
    if not figures:
        errors.append("figure_registry must be non-empty")
    if not features:
        errors.append("feature_registry must be non-empty")
    if not sources:
        errors.append("source_registry must be non-empty")

    for index, item in enumerate(terminology):
        row = _dict(item)
        if not isinstance(item, dict):
            errors.append(f"terminology[{index}] must be an object")
            continue
        if not str(row.get("term", "")).strip():
            errors.append(f"terminology[{index}].term is required")
        if not str(row.get("definition", "")).strip():
            errors.append(f"terminology[{index}].definition is required")

    source_by_id: dict[str, dict] = {}
    figure_source_by_id: dict[str, dict] = {}
    evidence_ids: set[str] = set()
    evidence_feature_ids: set[str] = set()
    evidence_pack_loaded = False
    for index, item in enumerate(sources):
        if not isinstance(item, dict):
            errors.append(f"source_registry[{index}] must be an object")
            continue
        source_id = str(item.get("source_id", "")).strip()
        source_type = str(item.get("source_type", "")).strip()
        if not source_id:
            errors.append(f"source_registry[{index}].source_id is required")
        elif source_id in source_by_id:
            errors.append(f"duplicate source_id: {source_id}")
        else:
            source_by_id[source_id] = item
        if source_type not in {"material", "code", "external_evidence", "disclosure_paragraph", "figure"}:
            errors.append(f"source_registry[{index}].source_type is invalid")
        if source_type in {"material", "code", "disclosure_paragraph", "figure"}:
            path = str(item.get("path", "")).strip()
            digest = str(item.get("sha256", "")).strip()
            source_path = _lexically_within(path, base_dir) if path else None
            source_is_file = False
            if not path or source_path is None:
                errors.append(f"source_registry[{index}] source path must remain inside the case workspace")
            else:
                source_path = source_path.resolve()
                if not is_within(source_path, base_dir):
                    errors.append(f"source_registry[{index}] source path must remain inside the case workspace")
                elif not source_path.is_file():
                    errors.append(f"source_registry[{index}] source path is missing")
                else:
                    source_is_file = True
            if not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
                errors.append(f"source_registry[{index}].sha256 must be a SHA-256 digest")
            elif source_is_file and source_path is not None:
                if sha256_file(source_path).casefold() != digest.casefold():
                    errors.append(f"source_registry[{index}] source hash is stale")
        if source_type == "external_evidence" and not str(item.get("evidence_id", "")).strip():
            errors.append(f"source_registry[{index}].evidence_id is required for external evidence")
        if source_type == "disclosure_paragraph" and not str(item.get("paragraph_id", "")).strip():
            errors.append(f"source_registry[{index}].paragraph_id is required")
        if source_type == "figure" and not str(item.get("figure_id", "")).strip():
            errors.append(f"source_registry[{index}].figure_id is required")
        elif source_type == "figure":
            figure_id = str(item.get("figure_id", "")).strip()
            if figure_id in figure_source_by_id:
                errors.append(f"duplicate figure source mapping: {figure_id}")
            else:
                figure_source_by_id[figure_id] = item

    resolved_evidence_pack = evidence_pack_path.resolve() if evidence_pack_path else None
    if resolved_evidence_pack and not is_within(resolved_evidence_pack, base_dir):
        errors.append("evidence pack path must remain inside the case workspace")
    elif resolved_evidence_pack and resolved_evidence_pack.is_file():
        try:
            evidence_data = json.loads(resolved_evidence_pack.read_text(encoding="utf-8"))
            if not isinstance(evidence_data, dict):
                errors.append("evidence pack must be a JSON object")
            else:
                evidence_pack_loaded = True
                for item in _list(evidence_data.get("evidence")):
                    if isinstance(item, dict) and item.get("evidence_id"):
                        evidence_ids.add(str(item["evidence_id"]).strip())
                for item in _list(evidence_data.get("scheme_features")):
                    if isinstance(item, dict) and item.get("feature_id"):
                        evidence_feature_ids.add(str(item["feature_id"]).strip())
        except Exception:
            errors.append("evidence pack could not be parsed")
    elif resolved_evidence_pack:
        errors.append("evidence pack was not found")
    if evidence_pack_loaded:
        for index, item in enumerate(sources):
            if (
                isinstance(item, dict)
                and item.get("source_type") == "external_evidence"
                and str(item.get("evidence_id", "")).strip() not in evidence_ids
            ):
                errors.append(f"source_registry[{index}] external evidence_id does not resolve in evidence_pack")

    paragraph_ids = {
        str(item.get("paragraph_id", "")).strip()
        for item in sources
        if isinstance(item, dict) and item.get("source_type") == "disclosure_paragraph"
    }
    figure_source_ids = {
        str(item.get("figure_id", "")).strip()
        for item in sources
        if isinstance(item, dict) and item.get("source_type") == "figure"
    }
    feature_ids: set[str] = set()
    feature_pattern = re.compile(r"^F-[A-Z0-9][A-Z0-9._-]*$")
    allowed_evidence_kinds = {"implemented_fact", "source_claim", "inference", "pending_confirmation"}
    for index, item in enumerate(features):
        if not isinstance(item, dict):
            errors.append(f"feature_registry[{index}] must be an object")
            continue
        feature_id = str(item.get("feature_id", "")).strip()
        if not feature_pattern.fullmatch(feature_id):
            errors.append(f"feature_registry[{index}].feature_id must use stable F-... form")
        elif feature_id in feature_ids:
            errors.append(f"duplicate feature_id: {feature_id}")
        else:
            feature_ids.add(feature_id)
        if not str(item.get("statement", "")).strip():
            errors.append(f"feature_registry[{index}].statement is required")
        kind = str(item.get("evidence_kind", "")).strip()
        if kind not in allowed_evidence_kinds:
            errors.append(f"feature_registry[{index}].evidence_kind is invalid")
        if kind == "pending_confirmation" and item.get("status") != "pending":
            errors.append(f"feature_registry[{index}] pending confirmation must have status='pending'")
        if kind != "pending_confirmation" and not isinstance(item.get("status"), str):
            errors.append(f"feature_registry[{index}].status must distinguish confirmed/source-stated facts")
        elif kind != "pending_confirmation" and item.get("status") not in {"confirmed", "source_stated"}:
            errors.append(f"feature_registry[{index}].status must distinguish confirmed/source-stated facts")
        source_refs = _list(item.get("source_ids"))
        if not source_refs:
            errors.append(f"feature_registry[{index}].source_ids must not be empty")
        for source_id in source_refs:
            if not isinstance(source_id, str) or source_id not in source_by_id:
                errors.append(f"feature_registry[{index}] references an unknown source_id")
        for evidence_id in _list(item.get("evidence_ids")):
            if not isinstance(evidence_id, str) or (evidence_pack_loaded and evidence_id not in evidence_ids):
                errors.append(f"feature_registry[{index}] references an unknown evidence_id")
        for paragraph_id in _list(item.get("paragraph_ids")):
            if not isinstance(paragraph_id, str) or paragraph_id not in paragraph_ids:
                errors.append(f"feature_registry[{index}] references an unknown paragraph_id")
        for figure_id in _list(item.get("figure_ids")):
            if not isinstance(figure_id, str) or figure_id not in figure_source_ids:
                errors.append(f"feature_registry[{index}] references an unknown figure_id")
    if evidence_pack_loaded and feature_ids != evidence_feature_ids:
        errors.append("facts_ledger feature IDs do not match evidence_pack scheme_features")

    seen_figure_ids: set[str] = set()
    for index, item in enumerate(figures):
        if not isinstance(item, dict):
            errors.append(f"figure_registry[{index}] must be an object")
            continue
        figure_id = str(item.get("figure_id", "")).strip()
        caption = str(item.get("caption", "")).strip()
        if not figure_id or not caption:
            errors.append(f"figure_registry[{index}] requires figure_id and caption")
        if figure_id in seen_figure_ids:
            errors.append(f"duplicate figure_id: {figure_id}")
        seen_figure_ids.add(figure_id)
        artifacts = _dict(item.get("artifacts"))
        mmd = str(artifacts.get("mmd", "")).strip()
        mmd_path = _resolved(mmd, base_dir) if mmd else None
        if (
            not mmd
            or Path(mmd).suffix.lower() != ".mmd"
            or not mmd_path
            or not is_within(mmd_path, base_dir)
            or not mmd_path.is_file()
        ):
            errors.append(f"figure_registry[{index}] requires an existing .mmd source")
        if figure_id not in figure_source_ids:
            errors.append(f"figure_registry[{index}] must map to a figure source_registry entry")
        figure_source = figure_source_by_id.get(figure_id)
        if figure_source and mmd:
            source_path = _resolved(str(figure_source.get("path", "")), base_dir)
            artifact_path = _resolved(mmd, base_dir)
            if source_path != artifact_path:
                errors.append(f"figure_registry[{index}].artifacts.mmd must match its figure source path")
        if figure_delivery_mode == "mermaid_and_images":
            image = str(artifacts.get("image", "")).strip()
            image_path = _resolved(image, base_dir) if image else None
            if not image_path or not is_within(image_path, base_dir) or not image_path.is_file():
                errors.append(f"figure_registry[{index}] requires an image in mermaid_and_images mode")
        if require_docx_visible_mermaid and item.get("mermaid_source_embedded_in_docx") is not True:
            errors.append(f"figure_registry[{index}].mermaid_source_embedded_in_docx must be true")

    if figure_delivery_mode not in {"mermaid_only", "mermaid_and_images"}:
        errors.append("figure_delivery_mode must be mermaid_only or mermaid_and_images")

    if require_main_parts:
        if not (base_dir / "artifacts" / "run_manifest.md").is_file():
            errors.append("run manifest is required when validating the five-part draft")
        else:
            manifest_text = (base_dir / "artifacts" / "run_manifest.md").read_text(encoding="utf-8", errors="replace")
            title = manifest_field_text(manifest_text, "final_title") or manifest_field_text(manifest_text, "working_title")
            if not title:
                errors.append("run manifest must declare a final or working title")
        parts_dir = base_dir / "artifacts" / "draft"
        for part_key, matches in _part_files(parts_dir).items():
            nonempty = [path for path in matches if path.is_file() and path.stat().st_size > 0]
            if len(nonempty) != 1:
                errors.append(f"{part_key} must have exactly one non-empty Markdown file")
            elif not any(
                line.strip() and not line.lstrip().startswith("#")
                and line.strip().casefold() not in {"tbd", "todo", "待补充", "待确认", "模板内容"}
                for line in nonempty[0].read_text(encoding="utf-8", errors="replace").splitlines()
            ):
                errors.append(f"{part_key} must contain actual section content, not headings alone")
        part04_files = _part_files(parts_dir)["part_04"]
        if len(part04_files) == 1 and part04_files[0].is_file():
            part04_text = part04_files[0].read_text(encoding="utf-8", errors="replace")
            for figure in figures:
                if isinstance(figure, dict):
                    for label in (str(figure.get("figure_id", "")).strip(), str(figure.get("caption", "")).strip()):
                        if label and label not in part04_text:
                            errors.append("part_04 does not reference every registered figure")
                            break

    manifest_path = base_dir / "artifacts" / "run_manifest.md"
    if manifest_path.is_file():
        text = manifest_path.read_text(encoding="utf-8", errors="replace")
        title = manifest_field_text(text, "final_title") or manifest_field_text(text, "working_title")
        if title and len(title) > TITLE_MAX_CHARS:
            errors.append(f"patent title must be at most {TITLE_MAX_CHARS} characters (got {len(title)})")
        if title and not title.strip():
            errors.append("patent title must not be empty")
        mode = manifest_field_text(text, "figure_delivery_mode")
        if mode and mode != figure_delivery_mode:
            errors.append("figure delivery mode does not match the run manifest")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate facts ledger and traceability")
    parser.add_argument("input")
    parser.add_argument("--base-dir", default=".")
    parser.add_argument("--evidence-pack")
    parser.add_argument("--figure-delivery-mode", choices=["mermaid_only", "mermaid_and_images"])
    parser.add_argument("--require-main-parts", action="store_true")
    parser.add_argument("--require-docx-visible-mermaid", action="store_true")
    parser.add_argument("--check-draft-format", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()
    inp = Path(args.input)
    base_dir = Path(args.base_dir)
    mode = args.figure_delivery_mode
    if not mode:
        manifest = base_dir / "artifacts" / "run_manifest.md"
        mode = manifest_field_text(manifest.read_text(encoding="utf-8"), "figure_delivery_mode") if manifest.is_file() else None
        mode = mode or "mermaid_only"
    errors: list[str] = []
    try:
        data = json.loads(inp.read_text(encoding="utf-8"))
        errors = validate_ledger(
            data,
            base_dir=base_dir,
            figure_delivery_mode=mode,
            evidence_pack_path=Path(args.evidence_pack) if args.evidence_pack else None,
            require_main_parts=args.require_main_parts or args.check_draft_format,
            require_docx_visible_mermaid=args.require_docx_visible_mermaid,
        )
    except FileNotFoundError:
        errors = ["facts ledger input file was not found"]
    except Exception:
        errors = ["facts ledger could not be parsed"]

    summary = {
        "validator": "validate_facts_ledger.py",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "inputPath": str(inp.resolve()),
        "figure_delivery_mode": mode,
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
