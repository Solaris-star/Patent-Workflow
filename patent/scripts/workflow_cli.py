#!/usr/bin/env python3
"""Thin local workflow controls backed by the case run manifest.

This CLI records checkpoints and delegates validation/export to the existing
scripts. It never creates draft materials during resume and never sends data
outside the local workspace.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from workflow_common import (
    DOCX_SUFFIX,
    MODE_CHOICES,
    MODE_GATES,
    atomic_write_text,
    canonical_json_sha256,
    is_within,
    patch_workflow_state,
    read_workflow_state,
    title_error,
    update_manifest_state,
)
from validate_review_status import validate_review_status

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parents[1]
TEMPLATE = REPO_ROOT / "patent" / "references" / "RUN_MANIFEST_TEMPLATE.md"
DEPTH_CHOICES = ("light", "balanced", "deep")
GATE_RESULTS_BEGIN = "<!-- GATE_RESULTS_JSON_BEGIN -->"
GATE_RESULTS_END = "<!-- GATE_RESULTS_JSON_END -->"

STAGE_NEXT_STEP = {
    "intake": "Provide the missing local source materials or scope decision, then resume.",
    "research": "Run source-based research at the requested depth; verify and map useful evidence without target counts.",
    "evidence_gap_research": "Identify evidence gaps for the fixed title, reuse verified sources, and research only the agreed gaps.",
    "evidence_synthesis": "Validate evidence records and map each material feature to its supporting sources.",
    "draft": "Prepare or update the software patent draft from verified facts and cited evidence.",
    "independent_review": "Review the current draft, assign stable issue IDs, and record any user decisions.",
    "delivery": "Run delivery checks against the current reviewed draft and export the requested local artifact.",
    "complete": "The requested workflow checks are complete.",
}

CANONICAL_MATERIAL_FIELDS = {
    "research_pack": "phase_02_research_pack_path",
    "candidate_pool": "phase_04_patent_candidate_pool_path",
    "evidence_pack": "phase_04_evidence_pack_path",
    "background_pack": "phase_05_background_pack_path",
    "ipr_pack": "phase_05_ipr_pack_path",
    "facts_ledger": "facts_ledger_path",
    "final_markdown": "final_markdown_path",
    "review_status": "review_status_path",
}

GATE_INVALIDATION = {
    "disclosure": {"research", "prior-art", "draft", "review", "deliver"},
    "research_request": {"research", "prior-art", "draft", "review", "deliver"},
    "search_request": {"research", "prior-art", "draft", "review", "deliver"},
    "search_brief": {"research", "prior-art", "draft", "review", "deliver"},
    "search_depth": {"research", "prior-art", "draft", "review", "deliver"},
    "workflow_mode": {"research", "prior-art", "draft", "review", "deliver"},
    "output_dir": {"deliver"},
    "research_pack": {"research", "prior-art", "draft", "review", "deliver"},
    "candidate_pool": {"prior-art", "draft", "review", "deliver"},
    "evidence_pack": {"prior-art", "draft", "review", "deliver"},
    "background_pack": {"prior-art", "draft", "review", "deliver"},
    "ipr_pack": {"prior-art", "review", "deliver"},
    "facts_ledger": {"draft", "review", "deliver"},
    "draft": {"draft", "review", "deliver"},
    "final_markdown": {"draft", "review", "deliver"},
    "review_status": {"review", "deliver"},
    "sensitive_map": {"research", "prior-art", "draft", "review", "deliver"},
}
GATE_DOWNSTREAM = {
    "research": {"research", "prior-art", "draft", "review", "deliver"},
    "prior-art": {"prior-art", "draft", "review", "deliver"},
    "draft": {"draft", "review", "deliver"},
    "review": {"review", "deliver"},
    "deliver": {"deliver"},
}


def _active_gate_names(mode: str) -> set[str]:
    return {gate for gate, _stage in MODE_GATES[mode]}


def _normalize_gate_state(state: dict[str, Any], mode: str) -> None:
    """Keep checkpoint completion and invalidation scoped to the active route."""
    active = _active_gate_names(mode)
    completed = {
        str(value) for value in state.get("completed_gates", [])
        if isinstance(value, str) and value in active
    }
    invalidated = {
        str(value) for value in state.get("invalidated_gates", [])
        if isinstance(value, str) and value in active
    }
    completed.difference_update(invalidated)
    state["completed_gates"] = sorted(completed)
    state["invalidated_gates"] = sorted(invalidated)
    # Delivery acceptance is a post-export gate. A missing DOCX or an unavailable
    # renderer keeps delivery pending, but does not make reviewed conclusions stale.
    state["conclusions_need_review"] = bool(invalidated & (active - {"deliver"}))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextlib.contextmanager
def _workspace_operation_lock(workspace: Path):
    """Serialize manifest-backed CLI operations across cooperating processes."""
    workspace.mkdir(parents=True, exist_ok=True)
    lock_path = workspace / ".workflow-cli.lock"
    if lock_path.is_symlink():
        raise ValueError("workflow operation lock path may not be a symbolic link")
    with lock_path.open("a+b") as stream:
        if lock_path.stat().st_size == 0:
            stream.write(b"\0")
            stream.flush()
        deadline = time.monotonic() + 60
        while True:
            try:
                stream.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise ValueError("another workflow operation is still running; retry after it finishes")
                time.sleep(0.05)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _resolve_workspace(value: str) -> Path:
    return Path(value).expanduser().resolve()


def _resolve_under_workspace(value: str, workspace: Path) -> Path:
    raw = Path(value).expanduser()
    return (raw if raw.is_absolute() else workspace / raw).resolve()


def _resolve_selected_input(value: str, workspace: Path) -> Path:
    raw = Path(value).expanduser()
    if raw.is_symlink():
        raise ValueError("selected inputs may not be symbolic links")
    if raw.is_absolute():
        return raw.resolve()
    resolved = (workspace / raw).resolve()
    if not is_within(resolved, workspace):
        raise ValueError("relative input paths must stay inside the selected workspace; use an explicit absolute path")
    return resolved


def _path_reference_key(value: str, workspace: Path) -> str:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = workspace / path
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def _copy_selected_input(source: Path, label: str, workspace: Path) -> tuple[Path, dict[str, str]]:
    """Import an explicitly selected external input; later reads use only this copy."""
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", label):
        raise ValueError("input label is invalid")
    source_key = hashlib.sha256(str(source).casefold().encode("utf-8")).hexdigest()[:16]
    if not source.exists():
        suffix = source.suffix
        pending = workspace / "inputs" / "registered" / label / f"pending-{source_key}" / f"input{suffix}"
        return pending, {
            "source_kind": "external_pending",
            "workspace_path": pending.relative_to(workspace).as_posix(),
            "selection_path_sha256": source_key,
            "sha256": "",
            "selected_at": _now(),
        }
    if source.is_symlink() or not (source.is_file() or source.is_dir()):
        raise ValueError("explicit input must be a regular file or directory, not a symbolic link")
    if source.is_dir():
        for parent, dirs, files in os.walk(source, followlinks=False):
            if any((Path(parent) / name).is_symlink() for name in [*dirs, *files]):
                raise ValueError("selected input directories may not contain symbolic links")
    digest = _fingerprint(source)
    if not digest:
        raise ValueError("selected input could not be fingerprinted")
    target_base = workspace / "inputs" / "registered" / label / digest
    if source.is_dir():
        target = target_base / "tree"
        if target.exists():
            if _fingerprint(target) != digest:
                raise FileExistsError("registered input snapshot conflicts with its content hash")
        else:
            target_base.parent.mkdir(parents=True, exist_ok=True)
            staging = target_base.parent / f".{digest}.staging-{uuid.uuid4().hex}"
            try:
                staged_tree = staging / "tree"
                shutil.copytree(
                    source, staged_tree, symlinks=False,
                    ignore=shutil.ignore_patterns(".git", "__pycache__", ".venv", "venv", "node_modules"),
                )
                if _fingerprint(staged_tree) != digest:
                    raise OSError("registered input copy did not match its source fingerprint")
                try:
                    staging.rename(target_base)
                except FileExistsError:
                    if _fingerprint(target) != digest:
                        raise
            finally:
                if staging.exists():
                    shutil.rmtree(staging, ignore_errors=True)
    else:
        target = target_base / f"input{source.suffix.lower()}"
        if target.exists():
            if _fingerprint(target) != digest:
                raise FileExistsError("registered input snapshot conflicts with its content hash")
        else:
            target_base.mkdir(parents=True, exist_ok=True)
            staging = target_base / f".input-{uuid.uuid4().hex}{source.suffix.lower()}.tmp"
            try:
                shutil.copy2(source, staging)
                if _fingerprint(staging) != digest:
                    raise OSError("registered input copy did not match its source fingerprint")
                try:
                    os.link(staging, target)
                except FileExistsError:
                    if _fingerprint(target) != digest:
                        raise
            finally:
                staging.unlink(missing_ok=True)
    return target, {
        "source_kind": "explicit_external",
        "workspace_path": target.relative_to(workspace).as_posix(),
        "sha256": digest,
        "selected_at": _now(),
    }


def _manifest_path(args: argparse.Namespace) -> tuple[Path, Path]:
    workspace = _resolve_workspace(args.workspace)
    manifest = _resolve_under_workspace(args.manifest, workspace)
    if not is_within(manifest, workspace):
        raise ValueError("manifest must be inside the selected workspace")
    return workspace, manifest


def _set_field(text: str, key: str, value: str) -> str:
    tick = chr(96)
    pattern = re.compile(
        rf"^([ \t]*-[ \t]*(?:{tick}{re.escape(key)}{tick}|{re.escape(key)})[ \t]*:)[ \t]*[^\r\n]*$",
        re.MULTILINE,
    )
    updated, count = pattern.subn(lambda match: f"{match.group(1)} {value}", text, count=1)
    if count:
        return updated
    return text


def _fingerprint(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    if path.is_file():
        return _hash_file(path)
    if not path.is_dir():
        return None
    for parent, dirs, files in os.walk(path, followlinks=False):
        dirs[:] = sorted(
            d for d in dirs
            if d not in {".git", "__pycache__", ".venv", "venv", "node_modules"}
            and not (Path(parent) / d).is_symlink()
        )
        for filename in sorted(files):
            child = Path(parent) / filename
            if child.is_symlink() or not child.is_file():
                continue
            relative = child.relative_to(path).as_posix().encode("utf-8")
            digest.update(relative)
            digest.update(bytes.fromhex(_hash_file(child)))
    return digest.hexdigest()


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sensitive_map_path_key(value: str, workspace: Path) -> str:
    normalized = _path_reference_key(value, workspace)
    return hashlib.sha256(normalized.casefold().encode("utf-8")).hexdigest()[:16]


def _invalidate_sensitive_map_gates(state: dict[str, Any], mode: str | None = None) -> None:
    current_mode = mode or str(state.get("workflow_mode") or "full_research")
    active = _active_gate_names(current_mode)
    affected = GATE_INVALIDATION["sensitive_map"] & active
    completed = {str(item) for item in state.get("completed_gates", []) if isinstance(item, str)}
    invalidated = {str(item) for item in state.get("invalidated_gates", []) if isinstance(item, str)}
    completed.difference_update(affected)
    invalidated.update(affected)
    state["completed_gates"] = sorted(completed)
    state["invalidated_gates"] = sorted(invalidated)
    stale = {str(item) for item in state.get("stale_materials", []) if isinstance(item, str)}
    stale.add("sensitive_map")
    state["stale_materials"] = sorted(stale)
    state["conclusions_need_review"] = bool(affected & (active - {"deliver"}))
    state.pop("sensitive_map_audit", None)


def _strip_legacy_sensitive_map_tracking(
    state: dict[str, Any], fields: dict[str, str | None], workspace: Path,
) -> bool:
    """Drop sensitive-map content tracking before generic path or hash handling.

    Older checkpoints treated the map as an ordinary material and could hash or
    register its contents during status/resume. Keep only an explicit
    path-selection reference. Never inspect the old path while migrating it.
    """
    migrated = False
    material_paths = state.get("material_paths")
    if isinstance(material_paths, dict) and "sensitive_map" in material_paths:
        material_paths = dict(material_paths)
        material_paths.pop("sensitive_map", None)
        state["material_paths"] = material_paths
        migrated = True

    for key in ("material_hashes", "material_registry"):
        container = state.get(key)
        if isinstance(container, dict) and "sensitive_map" in container:
            container = dict(container)
            container.pop("sensitive_map", None)
            state[key] = container
            migrated = True

    approvals = state.get("approved_inputs")
    if isinstance(approvals, dict) and isinstance(approvals.get("sensitive_map"), dict):
        current = approvals["sensitive_map"]
        allowed = {"source_kind", "selection_path_sha256", "selected_at", "workspace_path"}
        cleaned = {key: value for key, value in current.items() if key in allowed}
        if cleaned != current:
            migrated = True
        selected_path = fields.get("sensitive_map_path")
        if selected_path:
            cleaned["source_kind"] = "explicit_path_reference"
            cleaned.setdefault("selection_path_sha256", _sensitive_map_path_key(selected_path, workspace))
            cleaned.setdefault("selected_at", _now())
            path = Path(selected_path).expanduser()
            if not path.is_absolute():
                path = workspace / path
            try:
                cleaned["workspace_path"] = path.resolve().relative_to(workspace).as_posix()
            except ValueError:
                cleaned.pop("workspace_path", None)
        if cleaned:
            approvals = dict(approvals)
            approvals["sensitive_map"] = cleaned
        else:
            approvals = dict(approvals)
            approvals.pop("sensitive_map", None)
        state["approved_inputs"] = approvals

    if migrated:
        mode = str(state.get("workflow_mode") or fields.get("workflow_mode") or "full_research")
        _invalidate_sensitive_map_gates(state, mode)
    return migrated


def _read_manifest(path: Path) -> tuple[str, dict[str, str | None], dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"run manifest not found: {path}")
    text = path.read_text(encoding="utf-8")
    return text, _fields_from_text(text), read_workflow_state(text)


def _fields_from_text(text: str) -> dict[str, str | None]:
    """Read both legacy backtick keys and plain YAML-like keys."""
    fields: dict[str, str | None] = {}
    pattern = re.compile(
        r"(?m)^[ \t]*-[ \t]*(?:`([^`]+)`|([A-Za-z_][A-Za-z0-9_-]*))[ \t]*:[ \t]*(.*)$"
    )
    for match in pattern.finditer(text):
        key = match.group(1) or match.group(2)
        value = re.sub(r"(?:^|\s+)#.*$", "", match.group(3)).strip().strip("`\"").strip()
        if value.casefold() in {"", "tbd", "todo", "none", "null", "n/a", "na", "-"}:
            fields[key] = None
        elif value.startswith("<") and value.endswith(">"):
            fields[key] = None
        else:
            fields[key] = value
    return fields


def _parse_material_args(args: argparse.Namespace, workspace: Path) -> dict[str, str]:
    raw: dict[str, str | None] = {
        "disclosure": getattr(args, "disclosure", None),
        "search_request": getattr(args, "search_request", None),
        "draft": getattr(args, "draft", None),
        "research_pack": getattr(args, "research_pack", None),
        "candidate_pool": getattr(args, "candidate_pool", None),
        "evidence_pack": getattr(args, "evidence_pack", None),
        "background_pack": getattr(args, "background_pack", None),
        "ipr_pack": getattr(args, "ipr_pack", None),
        "facts_ledger": getattr(args, "facts_ledger", None),
        "sensitive_map": getattr(args, "sensitive_map", None),
        "review_status": getattr(args, "review_status", None),
    }
    for item in getattr(args, "material", []) or []:
        if "=" not in item:
            raise ValueError("--material must use LABEL=PATH")
        label, value = item.split("=", 1)
        label = label.strip()
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", label):
            raise ValueError(f"invalid material label: {label!r}")
        if not value.strip():
            raise ValueError(f"material path is empty for {label}")
        raw[label] = value.strip()
    result: dict[str, str] = {}
    approvals: dict[str, dict[str, str]] = {}
    sensitive_map_reference: str | None = None
    for label, value in raw.items():
        if value:
            source = _resolve_selected_input(value, workspace)
            if label == "sensitive_map":
                sensitive_map_reference = str(source)
                path_key = hashlib.sha256(str(source).casefold().encode("utf-8")).hexdigest()[:16]
                approvals[label] = {
                    "source_kind": "explicit_path_reference",
                    "selection_path_sha256": path_key,
                    "selected_at": _now(),
                }
                if is_within(source, workspace):
                    approvals[label]["workspace_path"] = source.relative_to(workspace).as_posix()
                continue
            if is_within(source, workspace):
                result[label] = str(source)
                approvals[label] = {
                    "source_kind": "explicit_workspace",
                    "workspace_path": source.relative_to(workspace).as_posix(),
                    "sha256": _fingerprint(source) or "",
                    "selected_at": _now(),
                }
            else:
                imported, record = _copy_selected_input(source, label, workspace)
                result[label] = str(imported)
                approvals[label] = record
    args._approved_inputs = approvals
    args._sensitive_map_path = sensitive_map_reference
    return result


def _add_canonical_materials(
    material_paths: dict[str, str], fields: dict[str, str | None], workspace: Path
) -> dict[str, str]:
    combined = dict(material_paths)
    output_dir = _resolve_under_workspace(fields["output_dir"], workspace) if fields.get("output_dir") else None
    for label, value in list(combined.items()):
        if label == "sensitive_map":
            continue
        path = Path(value).expanduser().resolve()
        external_output = label == "final_markdown" and output_dir and is_within(path, output_dir)
        if not is_within(path, workspace) and not external_output:
            raise ValueError(f"registered material {label} is outside the workspace; reselect it explicitly to import a copy")
        combined[label] = str(path)
    for label, field in CANONICAL_MATERIAL_FIELDS.items():
        value = fields.get(field)
        if value and (label not in combined or label == "final_markdown"):
            path = _resolve_under_workspace(value, workspace)
            external_output = label == "final_markdown" and output_dir and is_within(path, output_dir)
            if not is_within(path, workspace) and not external_output:
                raise ValueError(
                    f"manifest {field} points outside the workspace; explicitly register an input or configure it under output_dir"
                )
            combined[label] = str(path)
    return combined


def _required_materials(mode: str, title: str | None, search_brief: str | None) -> list[str]:
    if mode == "full_research":
        required = ["disclosure", "search_request"]
    elif mode == "titled_evidence":
        required = ["disclosure", "title", "search_request"]
    else:
        required = ["draft"]
    if "title" in required and title:
        return [item for item in required if item != "title"]
    return required


def _missing_materials(
    required: list[str],
    material_paths: dict[str, str],
    search_brief: str | None,
    title: str | None,
) -> list[dict[str, str]]:
    missing: list[dict[str, str]] = []
    for name in required:
        if name == "title":
            available = bool(title and title.strip())
        elif name == "search_request":
            available = bool(search_brief and search_brief.strip())
            source_path = material_paths.get(name)
            available = available or bool(source_path and Path(source_path).exists())
        else:
            value = material_paths.get(name)
            available = bool(value and Path(value).exists())
        if not available:
            missing.append({"name": name, "reason": "required input is not available"})
    return missing


def _derive_stage(mode: str, completed_gates: set[str], invalidated: set[str], missing: list[dict]) -> str:
    if missing:
        return "intake"
    for gate, stage in MODE_GATES[mode]:
        if gate not in completed_gates or gate in invalidated:
            return stage
    return "complete"


def _stage_snapshot(
    mode: str,
    title: str | None,
    search_brief: str | None,
    material_paths: dict[str, str],
    state: dict[str, Any],
    fields: dict[str, str | None] | None = None,
    workspace: Path | None = None,
) -> dict[str, Any]:
    required = state.get("required_materials")
    if not isinstance(required, list):
        required = _required_materials(mode, title, search_brief)
    missing = _missing_materials(required, material_paths, search_brief, title)
    active = _active_gate_names(mode)
    completed = {
        str(x) for x in state.get("completed_gates", [])
        if isinstance(x, str) and x in active
    }
    invalidated = {
        str(x) for x in state.get("invalidated_gates", [])
        if isinstance(x, str) and x in active
    }
    stage = _derive_stage(mode, completed, invalidated, missing)
    delivery_missing: list[dict[str, str]] = []
    if stage in {"delivery", "complete"}:
        current_fields = fields or {}
        raw_output_dir = current_fields.get("output_dir")
        if not raw_output_dir:
            delivery_missing.append({"name": "output_dir", "reason": "delivery directory is not configured"})
        raw_final = current_fields.get("final_markdown_path")
        if not raw_final:
            delivery_missing.append({"name": "final_markdown_path", "reason": "final Markdown path is not configured"})
        elif workspace and not _resolve_under_workspace(raw_final, workspace).is_file():
            delivery_missing.append({"name": "final_markdown_path", "reason": "final Markdown file is missing"})
        if not title:
            delivery_missing.append({"name": "final_title", "reason": "final title is not configured"})
        if delivery_missing:
            stage = "delivery"
            missing = [*missing, *delivery_missing]
    pending_decisions = state.get("pending_user_decisions", [])
    waiting = bool(missing or pending_decisions)
    next_step = STAGE_NEXT_STEP.get(stage, STAGE_NEXT_STEP["intake"])
    if missing:
        names = ", ".join(item["name"] for item in missing)
        if stage == "delivery":
            next_step = f"Configure the delivery directory, final title, and current Markdown path ({names}); then export and check."
        else:
            next_step = f"Supply the missing inputs ({names}); then resume. No research quota is imposed."
    return {
        "workflow_mode": mode,
        "current_stage": stage,
        "missing_materials": missing,
        "next_step": next_step,
        "waiting_for_user": waiting,
        "completed_gates": sorted(completed - invalidated),
        "invalidated_gates": sorted(invalidated),
        "reused_materials": sorted(
            label for label, value in material_paths.items()
            if Path(value).exists() and label not in {"disclosure", "search_request", "draft"}
        ),
        "search_depth": state.get("search_depth", "balanced"),
        "last_check_result": state.get("last_check_result"),
    }


def _refresh_state(
    state: dict[str, Any],
    fields: dict[str, str | None],
    workspace: Path,
    *,
    input_materials: dict[str, str] | None = None,
    search_brief: str | None = None,
    title: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    _strip_legacy_sensitive_map_tracking(state, fields, workspace)
    mode = str(state.get("workflow_mode") or fields.get("workflow_mode") or "full_research")
    if mode not in MODE_CHOICES:
        raise ValueError(f"unsupported workflow_mode in manifest: {mode}")
    material_paths = state.get("material_paths")
    if not isinstance(material_paths, dict):
        material_paths = {}
    material_paths = {str(k): str(v) for k, v in material_paths.items() if isinstance(v, str)}
    previous_paths = dict(material_paths)
    if input_materials:
        material_paths.update(input_materials)
    material_paths = _add_canonical_materials(material_paths, fields, workspace)
    brief = search_brief if search_brief is not None else state.get("search_brief")
    manifest_title = title if title is not None else fields.get("final_title") or fields.get("working_title")
    if manifest_title and title_error(manifest_title):
        raise ValueError(title_error(manifest_title) or "invalid title")
    required = _required_materials(mode, manifest_title, brief)
    missing = _missing_materials(required, material_paths, brief, manifest_title)

    prior_hashes = state.get("material_hashes")
    if not isinstance(prior_hashes, dict):
        prior_hashes = {}
    current_hashes: dict[str, str] = {
        str(key): value for key, value in prior_hashes.items()
        if isinstance(key, str) and isinstance(value, str)
    }
    prior_registry = state.get("material_registry")
    if not isinstance(prior_registry, dict):
        prior_registry = {}
    registry: dict[str, dict[str, Any]] = {}
    changed: set[str] = set()
    for label, raw_path in material_paths.items():
        path = Path(raw_path).resolve()
        old = prior_registry.get(label)
        old = old if isinstance(old, dict) else {}
        old_path = old.get("path") or previous_paths.get(label)
        previous = old.get("last_present_sha256") or prior_hashes.get(label)
        old_status = old.get("status") or ("present" if previous else "unobserved")
        if old_path and Path(str(old_path)).resolve() != path:
            changed.add(label)
        fingerprint = _fingerprint(path)
        history = old.get("history") if isinstance(old.get("history"), list) else []
        if fingerprint is None:
            if old_status == "present" and previous:
                changed.add(label)
                history = [*history, {
                    "path": str(path),
                    "sha256": previous,
                    "status": "removed",
                    "detected_at": _now(),
                }][-50:]
            baseline = str(previous) if isinstance(previous, str) else ""
            if baseline:
                current_hashes[label] = baseline
            registry[label] = {
                "path": str(path),
                "status": "missing",
                "last_present_sha256": baseline,
                "missing_since": old.get("missing_since") or _now(),
                "history": history,
            }
            continue
        if old_status == "missing":
            changed.add(label)
            history = [*history, {
                "path": str(path),
                "sha256": str(previous or ""),
                "status": "recreated",
                "detected_at": _now(),
            }][-50:]
        elif isinstance(previous, str) and previous and previous != fingerprint:
            changed.add(label)
            history = [*history, {
                "path": str(old_path or path),
                "sha256": previous,
                "status": "changed",
                "detected_at": _now(),
            }][-50:]
        current_hashes[label] = fingerprint
        registry[label] = {
            "path": str(path),
            "status": "present",
            "last_present_sha256": fingerprint,
            "last_seen_at": _now(),
            "history": history,
        }
    if brief:
        current_hashes["search_brief"] = hashlib.sha256(str(brief).encode("utf-8")).hexdigest()
        previous_brief = prior_hashes.get("search_brief")
        if previous_brief and previous_brief != current_hashes["search_brief"]:
            changed.add("search_brief")
    if manifest_title:
        current_hashes["title"] = hashlib.sha256(str(manifest_title).encode("utf-8")).hexdigest()
        previous_title = prior_hashes.get("title")
        if previous_title and previous_title != current_hashes["title"]:
            changed.add("title")
    for label, value in {
        "workflow_mode": mode,
        "search_depth": state.get("search_depth") or fields.get("search_depth") or "balanced",
        "output_dir": fields.get("output_dir"),
    }.items():
        if not value:
            continue
        normalized = str(_resolve_under_workspace(str(value), workspace)) if label == "output_dir" else str(value)
        fingerprint = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        current_hashes[label] = fingerprint
        previous = prior_hashes.get(label)
        if previous and previous != fingerprint:
            changed.add(label)

    active_gates = _active_gate_names(mode)
    completed = {
        str(x) for x in state.get("completed_gates", [])
        if isinstance(x, str) and x in active_gates
    }
    invalidated = {
        str(x) for x in state.get("invalidated_gates", [])
        if isinstance(x, str) and x in active_gates
    }
    for label in changed:
        invalidated.update(
            GATE_INVALIDATION.get(label, active_gates) & active_gates
        )
    stale_materials = {
        str(value) for value in state.get("stale_materials", [])
        if isinstance(value, str)
    } | changed
    state.update({
        "workflow_mode": mode,
        "completed_gates": sorted(completed - invalidated),
        "material_paths": material_paths,
        "material_registry": registry,
        "search_brief": brief,
        "search_depth": state.get("search_depth") or fields.get("search_depth") or "balanced",
        "required_materials": required,
        "missing_materials": missing,
        "material_hashes": current_hashes,
        "stale_materials": sorted(stale_materials),
        "invalidated_gates": sorted(invalidated),
        "waiting_for_user": bool(missing or state.get("pending_user_decisions")),
    })
    _normalize_gate_state(state, mode)
    snapshot = _stage_snapshot(mode, manifest_title, brief, material_paths, state, fields, workspace)
    state.update({
        "current_stage": snapshot["current_stage"],
        "next_step": snapshot["next_step"],
        "waiting_for_user": snapshot["waiting_for_user"],
    })
    snapshot["stale_materials"] = sorted(stale_materials)
    snapshot["conclusions_need_review"] = state["conclusions_need_review"]
    return state, snapshot


def _write_state(path: Path, state: dict[str, Any]) -> None:
    text = path.read_text(encoding="utf-8")
    atomic_write_text(path, patch_workflow_state(text, state))


def _write_gate_summary(path: Path, summary: dict[str, Any]) -> None:
    text = path.read_text(encoding="utf-8")
    fence = chr(96) * 3
    block = (
        f"{GATE_RESULTS_BEGIN}\n{fence}json\n"
        f"{json.dumps(summary, ensure_ascii=False, indent=2)}\n"
        f"{fence}\n{GATE_RESULTS_END}\n"
    )
    if GATE_RESULTS_BEGIN in text and GATE_RESULTS_END in text:
        text = text.split(GATE_RESULTS_BEGIN, 1)[0] + block + text.split(GATE_RESULTS_END, 1)[1].lstrip("\r\n")
    else:
        text = text.rstrip() + "\n\n" + block
    atomic_write_text(path, text)


def _add_input_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--disclosure", help="Local invention disclosure file or folder")
    parser.add_argument("--search-request", help="Local file describing the requested research scope")
    parser.add_argument("--draft", help="Existing draft for independent review")
    parser.add_argument("--research-pack", help="Existing research pack to reuse")
    parser.add_argument("--candidate-pool", help="Existing patent candidate pool to reuse")
    parser.add_argument("--evidence-pack", help="Existing evidence pack to reuse")
    parser.add_argument("--background-pack", help="Existing background evidence pack to reuse")
    parser.add_argument("--ipr-pack", help="Existing IPR pack to reuse")
    parser.add_argument("--facts-ledger", help="Existing facts ledger to reuse")
    parser.add_argument("--sensitive-map", help="Record a reference to the selected sensitive map; the map is never copied")
    parser.add_argument("--final-markdown", help="Final Markdown path")
    parser.add_argument("--review-status", help="Review status JSON path")
    parser.add_argument("--material", action="append", default=[], metavar="LABEL=PATH",
                        help="Additional input to track; sensitive_map is a path-only reference; may be repeated")


def _cmd_init(args: argparse.Namespace) -> int:
    workspace = _resolve_workspace(args.workspace)
    manifest = _resolve_under_workspace(args.manifest, workspace)
    if not is_within(manifest, workspace):
        raise ValueError("manifest must be inside the selected workspace")
    if manifest.exists():
        raise FileExistsError(f"manifest already exists; init will not replace it: {manifest}")
    if args.mode == "titled_evidence" and not args.title:
        raise ValueError("--title is required for titled_evidence mode")
    if args.title and title_error(args.title):
        raise ValueError(title_error(args.title) or "invalid title")
    if args.search_depth not in DEPTH_CHOICES:
        raise ValueError("unsupported search depth")

    inputs = _parse_material_args(args, workspace)
    fields: dict[str, str | None] = {}
    material_paths = _add_canonical_materials(inputs, fields, workspace)
    required = _required_materials(args.mode, args.title, args.search_brief)
    missing = _missing_materials(required, material_paths, args.search_brief, args.title)
    state: dict[str, Any] = {
        "schema_version": 1,
        "workflow_mode": args.mode,
        "search_depth": args.search_depth,
        "current_stage": "intake" if missing else MODE_GATES[args.mode][0][1],
        "stage_history": [{
            "at": _now(), "event": "initialized", "stage": "intake",
            "status": "waiting_for_user" if missing else "ready",
            "details": {"workflow_mode": args.mode, "search_depth": args.search_depth},
        }],
        "completed_gates": [],
        "invalidated_gates": [],
        "material_paths": material_paths,
        "approved_inputs": getattr(args, "_approved_inputs", {}),
        "material_registry": {},
        "material_hashes": {},
        "required_materials": required,
        "missing_materials": missing,
        "search_brief": args.search_brief,
        "next_step": "",
        "waiting_for_user": bool(missing),
        "skipped": [],
        "not_run": [],
        "pending_user_decisions": [],
    }
    for label, raw_path in material_paths.items():
        fingerprint = _fingerprint(Path(raw_path))
        if fingerprint:
            state["material_hashes"][label] = fingerprint
    if args.search_brief:
        state["material_hashes"]["search_brief"] = hashlib.sha256(args.search_brief.encode("utf-8")).hexdigest()
    if args.title:
        state["material_hashes"]["title"] = hashlib.sha256(args.title.encode("utf-8")).hexdigest()
    fields = {}
    template = TEMPLATE.read_text(encoding="utf-8")
    # Gate scripts still consume the stable backtick-key manifest syntax.
    template = re.sub(
        r"(?m)^([ \t]*-[ \t]+)([A-Za-z_][A-Za-z0-9_-]*)([ \t]*:)[ \t]*",
        lambda match: f"{match.group(1)}`{match.group(2)}`{match.group(3)} ",
        template,
    )
    now = _now()
    field_values = {
        "run_id": args.run_id or str(uuid.uuid4()),
        "started_at": now,
        "last_updated": now,
        "current_step": state["current_stage"],
        "workflow_mode": args.mode,
        "search_depth": args.search_depth,
        "final_title": args.title or "",
        "working_title": args.title or "",
    }
    if getattr(args, "_sensitive_map_path", None):
        field_values["sensitive_map_path"] = args._sensitive_map_path
    if args.output_dir:
        output_dir = _resolve_under_workspace(args.output_dir, workspace)
        field_values["output_dir"] = str(output_dir)
    if args.final_markdown:
        final_markdown = _resolve_under_workspace(args.final_markdown, workspace)
        configured_output = _resolve_under_workspace(args.output_dir, workspace) if args.output_dir else None
        if not is_within(final_markdown, workspace) and not (
            configured_output and is_within(final_markdown, configured_output)
        ):
            raise ValueError("external final Markdown must be inside the explicitly configured output_dir")
        field_values["final_markdown_path"] = str(final_markdown)
    for label, input_path in inputs.items():
        if label == "sensitive_map":
            continue
        if label in {"research_pack", "candidate_pool", "evidence_pack", "background_pack", "ipr_pack", "facts_ledger", "review_status"}:
            field_name = CANONICAL_MATERIAL_FIELDS.get(label)
            if field_name:
                field_values[field_name] = input_path
    for key, value in field_values.items():
        template = _set_field(template, key, value)
    template = re.sub(
        r"(?m)^([ \t]+-[ \t]+(?:`depth`|depth):[ \t]*).*$",
        lambda match: match.group(1) + args.search_depth,
        template,
        count=1,
    )
    template_fields = _fields_from_text(template)
    material_paths = _add_canonical_materials(material_paths, template_fields, workspace)
    state["material_paths"] = material_paths
    state["material_hashes"] = {}
    for label, raw_path in material_paths.items():
        fingerprint = _fingerprint(Path(raw_path))
        if fingerprint:
            state["material_hashes"][label] = fingerprint
        state["material_registry"][label] = {
            "path": str(Path(raw_path).resolve()),
            "status": "present" if fingerprint else "missing",
            "last_present_sha256": fingerprint or "",
            "missing_since": None if fingerprint else _now(),
            "history": [],
        }
    for label, value in {
        "workflow_mode": args.mode,
        "search_depth": args.search_depth,
        "output_dir": template_fields.get("output_dir"),
    }.items():
        if value:
            normalized = str(_resolve_under_workspace(value, workspace)) if label == "output_dir" else value
            state["material_hashes"][label] = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    if args.search_brief:
        state["material_hashes"]["search_brief"] = hashlib.sha256(args.search_brief.encode("utf-8")).hexdigest()
    if args.title:
        state["material_hashes"]["title"] = hashlib.sha256(args.title.encode("utf-8")).hexdigest()
    required = _required_materials(args.mode, args.title, args.search_brief)
    state["required_materials"] = required
    state["missing_materials"] = _missing_materials(required, material_paths, args.search_brief, args.title)
    snapshot = _stage_snapshot(
        args.mode, args.title, args.search_brief, material_paths, state,
        template_fields, workspace,
    )
    state.update({
        "current_stage": snapshot["current_stage"],
        "next_step": snapshot["next_step"],
        "waiting_for_user": snapshot["waiting_for_user"],
        "missing_materials": snapshot["missing_materials"],
    })
    template = patch_workflow_state(template, state)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with manifest.open("x", encoding="utf-8", newline="") as stream:
            stream.write(template)
    except FileExistsError:
        raise FileExistsError(f"manifest already exists; init will not replace it: {manifest}")
    print(json.dumps({"status": "initialized", "manifest": str(manifest), **snapshot}, ensure_ascii=False, indent=2))
    return 0


def _load_cli_state(
    args: argparse.Namespace,
    *,
    allow_mode_drift: bool = False,
) -> tuple[Path, Path, str, dict[str, str | None], dict[str, Any]]:
    workspace, manifest = _manifest_path(args)
    text, fields, state = _read_manifest(manifest)
    state_mode = str(state.get("workflow_mode") or "")
    field_mode = str(fields.get("workflow_mode") or "")
    if state_mode and field_mode and state_mode != field_mode and not allow_mode_drift:
        raise ValueError("manifest workflow_mode differs from checkpoint; reconcile explicitly with resume --mode")
    mode = str(state_mode or field_mode or "full_research")
    if mode not in MODE_CHOICES:
        raise ValueError(f"unsupported workflow mode: {mode}")
    return workspace, manifest, text, fields, state


def _cmd_status(args: argparse.Namespace) -> int:
    workspace, manifest, _text, fields, state = _load_cli_state(args)
    migrated_sensitive_map = _strip_legacy_sensitive_map_tracking(state, fields, workspace)
    state, snapshot = _refresh_state(state, fields, workspace)
    if migrated_sensitive_map:
        _write_state(manifest, state)
    payload = {"status": "ok", "manifest": str(manifest), **snapshot}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _cmd_resume(args: argparse.Namespace) -> int:
    workspace, manifest, _text, fields, state = _load_cli_state(
        args, allow_mode_drift=bool(args.mode),
    )
    previous_mode = str(state.get("workflow_mode") or fields.get("workflow_mode") or "full_research")
    _strip_legacy_sensitive_map_tracking(state, fields, workspace)
    selected_mode = args.mode or previous_mode
    if selected_mode not in MODE_CHOICES:
        raise ValueError("unsupported workflow mode")
    state["workflow_mode"] = selected_mode
    fields["workflow_mode"] = selected_mode
    title = args.title or fields.get("final_title") or fields.get("working_title")
    if args.title and title_error(args.title):
        raise ValueError(title_error(args.title) or "invalid title")
    inputs = _parse_material_args(args, workspace)
    approved_inputs = state.get("approved_inputs")
    if not isinstance(approved_inputs, dict):
        approved_inputs = {}
    approved_inputs.update(getattr(args, "_approved_inputs", {}))
    state["approved_inputs"] = approved_inputs
    sensitive_map_reference = getattr(args, "_sensitive_map_path", None)
    if sensitive_map_reference:
        # Explicit reselection authorizes a later in-place check, but resume
        # itself never opens the map. The same path may now contain new terms.
        _invalidate_sensitive_map_gates(state, selected_mode)
        fields["sensitive_map_path"] = sensitive_map_reference
    if args.output_dir:
        fields["output_dir"] = str(_resolve_under_workspace(args.output_dir, workspace))
    if args.final_markdown:
        fields["final_markdown_path"] = str(_resolve_under_workspace(args.final_markdown, workspace))
        final_path = Path(fields["final_markdown_path"]).resolve()
        configured_output = _resolve_under_workspace(fields["output_dir"], workspace) if fields.get("output_dir") else None
        if not is_within(final_path, workspace) and not (
            configured_output and is_within(final_path, configured_output)
        ):
            raise ValueError("external final Markdown must be inside the configured output_dir")
    state, snapshot = _refresh_state(
        state, fields, workspace,
        input_materials=inputs,
        search_brief=args.search_brief,
        title=title,
    )
    text = manifest.read_text(encoding="utf-8")
    if args.mode:
        text = _set_field(text, "workflow_mode", selected_mode)
    if args.title:
        text = _set_field(text, "final_title", args.title)
        text = _set_field(text, "working_title", args.title)
    if args.output_dir:
        text = _set_field(text, "output_dir", fields["output_dir"] or "")
    if getattr(args, "final_markdown", None):
        final_markdown = _resolve_under_workspace(args.final_markdown, workspace)
        text = _set_field(text, "final_markdown_path", str(final_markdown))
    if sensitive_map_reference:
        text = _set_field(text, "sensitive_map_path", sensitive_map_reference)
    for label, input_path in inputs.items():
        field_name = CANONICAL_MATERIAL_FIELDS.get(label)
        if field_name:
            text = _set_field(text, field_name, input_path)
    text = _set_field(text, "current_step", snapshot["current_stage"])
    atomic_write_text(manifest, text)
    update_manifest_state(
        manifest,
        event="resume",
        status="waiting_for_user" if snapshot["waiting_for_user"] else "ready_to_continue",
        stage=snapshot["current_stage"],
        details={
            "missing_materials": [item["name"] for item in snapshot["missing_materials"]],
            "stale_materials": snapshot["stale_materials"],
            "artifacts_modified": False,
            "mode_switch": {"from": previous_mode, "to": selected_mode}
            if previous_mode != selected_mode else None,
        },
        state_updates={
            "workflow_mode": snapshot["workflow_mode"],
            "current_stage": snapshot["current_stage"],
            "completed_gates": state.get("completed_gates", []),
            "material_paths": state["material_paths"],
            "approved_inputs": state["approved_inputs"],
            "sensitive_map_audit": state.get("sensitive_map_audit"),
            "material_hashes": state["material_hashes"],
            "material_registry": state.get("material_registry", {}),
            "required_materials": state["required_materials"],
            "missing_materials": state["missing_materials"],
            "stale_materials": state["stale_materials"],
            "invalidated_gates": state["invalidated_gates"],
            "conclusions_need_review": state.get("conclusions_need_review", False),
            "search_brief": state.get("search_brief"),
            "search_depth": state.get("search_depth"),
            "waiting_for_user": snapshot["waiting_for_user"],
            "next_step": snapshot["next_step"],
        },
    )
    print(json.dumps({"status": "resumed", "manifest": str(manifest), **snapshot,
                      "artifacts_modified": False}, ensure_ascii=False, indent=2))
    return 0


def _gate_summary(stdout: str) -> dict[str, Any]:
    if not isinstance(stdout, str):
        return {}
    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _sensitive_map_validation(summary: dict[str, Any], selected_map: Path, workspace: Path) -> dict[str, Any]:
    wanted = _path_reference_key(str(selected_map), workspace)
    for result in summary.get("gateResults", []):
        if not isinstance(result, dict):
            continue
        for run in result.get("runs", []):
            if not isinstance(run, dict):
                continue
            command = run.get("cmd")
            if not isinstance(command, list) or not any(
                isinstance(part, str) and Path(part).name.casefold() == "validate_sanitize.py"
                for part in command
            ):
                continue
            try:
                map_index = command.index("--map")
                recorded_map = command[map_index + 1]
            except (ValueError, IndexError):
                continue
            if not isinstance(recorded_map, str) or _path_reference_key(recorded_map, workspace) != wanted:
                continue
            validation = _gate_summary(str(run.get("stdout") or ""))
            if validation.get("validator") == "validate_sanitize.py":
                return validation
    return {}


def _sensitive_map_declared_confirmation(path: Path) -> str | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    value = data.get("confirmation_sha256")
    return value if isinstance(value, str) else None


def _run_export_gate_check(
    workspace: Path,
    manifest: Path,
    mode: str,
    selected_map: Path | None,
) -> dict[str, Any]:
    # This internal check runs under the export's existing workspace lock.
    # Calling the public CLI in a child process would deadlock on that lock.
    check_args = argparse.Namespace(
        workspace=str(workspace), manifest=str(manifest), gate="all",
        sensitive_map=str(selected_map) if selected_map else None,
        report=None, overwrite_report=False,
    )
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        return_code = _cmd_check(check_args)
    summary = _gate_summary(captured.getvalue())
    required = [gate for gate, _stage in MODE_GATES[mode]]
    pre_export = [gate for gate in required if gate != "deliver"]
    results = summary.get("gateResults") if isinstance(summary.get("gateResults"), list) else []
    result_names = [item.get("gate") for item in results if isinstance(item, dict)]
    if (
        return_code not in {0, 2}
        or summary.get("runner") != "run_phase_gates.py"
        or summary.get("gate") != "all"
        or summary.get("workflow_mode") != mode
        or summary.get("required_gates") != required
        or result_names != required
        or not isinstance(summary.get("run_id"), str)
        or not summary.get("run_id")
    ):
        raise ValueError("fresh workflow checks did not return a valid route report; no DOCX was written")
    for gate in pre_export:
        result = next((item for item in results if isinstance(item, dict) and item.get("gate") == gate), {})
        if not (
            result.get("status") == "passed"
            and result.get("checks_passed") is True
            and result.get("workflow_complete") is True
            and (gate != "review" or result.get("review_completed") is True)
        ):
            raise ValueError(f"current {gate} checks or review are incomplete; no DOCX was written")
    if not summary.get("review_completed"):
        raise ValueError("current independent review is incomplete; no DOCX was written")
    if selected_map:
        audit = summary.get("sensitive_map_audit")
        if not isinstance(audit, dict) or not (
            audit.get("checks_passed") is True
            and audit.get("confirmation_binding_valid") is True
            and audit.get("confirmation_matches_current_contents") is True
            and audit.get("content_stable_during_check") is True
            and isinstance(audit.get("content_sha256"), str)
        ):
            raise ValueError("current sensitive-map confirmation did not pass; no DOCX was written")
    return summary


def _run_sensitive_map_scan(
    scan_map: Path,
    target: Path,
    workspace: Path,
    *,
    expected_map_sha256: str,
    run_id: str,
    selection_path: Path | None = None,
) -> dict[str, Any]:
    before = _hash_file(scan_map) if scan_map.is_file() else None
    if not before or before != expected_map_sha256:
        raise ValueError("sensitive-map review snapshot changed; no DOCX was written")
    command = [
        sys.executable, str(SCRIPTS_DIR / "validate_sanitize.py"),
        "--map", str(scan_map), "--files", str(target),
    ]
    proc = subprocess.run(
        command, cwd=REPO_ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace", env={**os.environ, "PYTHONUTF8": "1"},
    )
    validation = _gate_summary(proc.stdout)
    after = _hash_file(scan_map) if scan_map.is_file() else None
    current_confirmation = _sensitive_map_declared_confirmation(scan_map)
    passed = bool(
        proc.returncode == 0
        and validation.get("validator") == "validate_sanitize.py"
        and validation.get("passed") is True
        and validation.get("map_confirmed") is True
        and validation.get("confirmation_binding_valid") is True
        and isinstance(validation.get("confirmation_sha256"), str)
        and validation.get("confirmation_sha256") == current_confirmation
        and before == after == expected_map_sha256
    )
    if not passed:
        raise ValueError("sensitive-map snapshot confirmation or artifact scan failed; no DOCX was published")
    return {
        "audit_version": 2,
        "run_id": run_id,
        "selection_path_sha256": _sensitive_map_path_key(
            str(selection_path or scan_map), workspace,
        ),
        "content_sha256": after,
        "confirmation_sha256": current_confirmation,
        "target_sha256": _hash_file(target),
        "target_kind": "markdown" if target.suffix.casefold() == ".md" else "docx",
        "explicit_reselection": True,
        "checks_passed": True,
    }


def _freeze_sensitive_map_snapshot(
    selected_map: Path | None,
    snapshot_dir: Path,
    *,
    expected_sha256: str | None,
) -> Path | None:
    """Copy the explicitly selected map to a private read-only export snapshot."""
    if selected_map is None:
        return None
    before = _hash_file(selected_map) if selected_map.is_file() else None
    if not before or before != expected_sha256:
        raise ValueError("sensitive map changed before an export snapshot could be frozen")
    snapshot = snapshot_dir / "sensitive-map.snapshot.json"
    try:
        with selected_map.open("rb") as source, snapshot.open("xb") as target:
            shutil.copyfileobj(source, target)
        snapshot_sha256 = _hash_file(snapshot)
        after = _hash_file(selected_map) if selected_map.is_file() else None
        if before != snapshot_sha256 or after != before:
            raise ValueError("sensitive map changed while its export snapshot was being frozen")
        snapshot.chmod(0o400)
        return snapshot
    except BaseException:
        snapshot.unlink(missing_ok=True)
        raise


def _validate_current_export_snapshot(
    *,
    manifest: Path,
    manifest_sha256: str,
    markdown: Path,
    markdown_sha256: str,
    review_status: Path,
    review_status_sha256: str,
    review_version_sha256: str,
    workspace: Path,
    output_dir: Path,
    require_revision: bool,
    selected_map: Path | None,
    selected_map_sha256: str | None,
    map_snapshot: Path | None,
) -> None:
    if _hash_file(manifest) != manifest_sha256:
        raise ValueError("workflow manifest changed during DOCX publication; no unreviewed output was kept")
    if _hash_file(markdown) != markdown_sha256:
        raise ValueError("final Markdown changed during DOCX publication; no unreviewed output was kept")
    if selected_map:
        current_map = _hash_file(selected_map) if selected_map.is_file() else None
        snapshot_map = _hash_file(map_snapshot) if map_snapshot and map_snapshot.is_file() else None
        if current_map != selected_map_sha256 or snapshot_map != selected_map_sha256:
            raise ValueError("sensitive map changed during DOCX publication; no unreviewed output was kept")

    status_before = _hash_file(review_status) if review_status.is_file() else None
    if status_before != review_status_sha256:
        raise ValueError("review status changed during DOCX publication; no unreviewed output was kept")
    try:
        data = json.loads(review_status.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("current review status could not be revalidated; no unreviewed output was kept") from exc
    errors, review_state = validate_review_status(
        data, workspace=workspace, output_dir=output_dir,
        require_revision=require_revision,
    )
    status_after = _hash_file(review_status) if review_status.is_file() else None
    if (
        errors
        or status_after != status_before
        or review_state.get("review_completed") is not True
        or review_state.get("review_fresh") is not True
        or review_state.get("workflow_complete") is not True
        or review_state.get("review_version_sha256") != review_version_sha256
    ):
        raise ValueError("review snapshot changed during DOCX publication; no unreviewed output was kept")


def _run_pre_export_health_check(
    *,
    workspace: Path,
    manifest: Path,
    output_dir: Path,
    title: str,
    markdown: Path,
    facts_ledger: Path,
    consistency_report: Path,
    ipr_report: Path,
    review_status: Path,
) -> dict[str, Any]:
    mode = _read_manifest(manifest)[1].get("figure_delivery_mode") or "mermaid_only"
    report_path = workspace / "artifacts" / "delivery" / f".pre-export-{uuid.uuid4().hex}.json"
    command = [
        sys.executable, str(SCRIPTS_DIR / "health_check_delivery_package.py"),
        "--deliver-dir", str(output_dir), "--patent-title", title,
        "--final-markdown", str(markdown), "--facts-ledger", str(facts_ledger),
        "--consistency-report", str(consistency_report), "--ipr-report", str(ipr_report),
        "--review-status", str(review_status), "--manifest", str(manifest),
        "--figure-delivery-mode", mode, "--base-dir", str(workspace),
        "--pre-export", "--out", str(report_path),
    ]
    try:
        proc = subprocess.run(
            command, cwd=REPO_ROOT, capture_output=True, text=True,
            encoding="utf-8", errors="replace", env={**os.environ, "PYTHONUTF8": "1"},
        )
        report = _gate_summary(proc.stdout)
    finally:
        report_path.unlink(missing_ok=True)
    if proc.returncode != 0 or report.get("export_allowed") is not True or report.get("workflow_complete") is not False:
        failed = report.get("errors") if isinstance(report.get("errors"), list) else []
        suffix = "; ".join(str(item) for item in failed)
        raise ValueError("pre-export delivery checks failed" + (f": {suffix}" if suffix else "; no DOCX was written"))
    return report


def _publish_docx(
    temp_docx: Path,
    output: Path,
    *,
    overwrite: bool,
    validate_snapshot: Callable[[], None] | None = None,
) -> None:
    """Publish atomically and roll back if the review snapshot changes in-flight."""
    if validate_snapshot:
        validate_snapshot()

    backup: Path | None = None
    original_sha256: str | None = None
    if overwrite and output.is_file():
        original_sha256 = _hash_file(output)
        backup = output.with_name(f".{output.name}.{uuid.uuid4().hex}.rollback")
        shutil.copy2(output, backup)
        if _hash_file(backup) != original_sha256 or _hash_file(output) != original_sha256:
            backup.unlink(missing_ok=True)
            raise ValueError("existing DOCX changed while preparing safe replacement")

    published = False
    try:
        if overwrite:
            os.replace(temp_docx, output)
        else:
            try:
                os.link(temp_docx, output)
            except FileExistsError:
                raise FileExistsError("DOCX output already exists; pass --overwrite to replace it")
            except OSError as exc:
                raise OSError("could not publish the validated DOCX without replacing another file") from exc
        published = True
        if validate_snapshot:
            validate_snapshot()
    except BaseException:
        if published:
            try:
                if backup is not None and backup.is_file():
                    os.replace(backup, output)
                    backup = None
                else:
                    output.unlink(missing_ok=True)
            except OSError as rollback_error:
                raise OSError("review snapshot changed during DOCX publication and rollback failed") from rollback_error
        if backup is not None:
            backup.unlink(missing_ok=True)
        raise

    if not overwrite:
        temp_docx.unlink(missing_ok=True)
    if backup is not None:
        backup.unlink(missing_ok=True)


def _cmd_check(args: argparse.Namespace) -> int:
    workspace, manifest, _text, fields, state = _load_cli_state(args)
    sensitive_map = fields.get("sensitive_map_path")
    selected_map: Path | None = None
    if args.sensitive_map and args.gate not in {"all", "research", "deliver"}:
        raise ValueError("--sensitive-map can only be used with research, deliver, or all checks")
    if args.sensitive_map:
        if not sensitive_map:
            raise ValueError("init or resume must record sensitive_map_path before it can be used")
        selected_map = _resolve_selected_input(args.sensitive_map, workspace)
        if _path_reference_key(str(selected_map), workspace) != _path_reference_key(sensitive_map, workspace):
            raise ValueError("--sensitive-map must match the path selected in the run manifest")
    state, precheck_snapshot = _refresh_state(state, fields, workspace)
    _write_state(manifest, state)
    command = [
        sys.executable,
        str(SCRIPTS_DIR / "run_phase_gates.py"),
        "--_workflow-cli-lock-held",
        "--gate", args.gate,
        "--workspace", str(workspace),
        "--manifest", str(manifest),
    ]
    run_id = str(uuid.uuid4())
    command.extend(["--run-id", run_id])
    output_dir = fields.get("output_dir")
    title = fields.get("final_title") or fields.get("working_title")
    final_markdown = fields.get("final_markdown_path")
    if args.gate in {"all", "deliver"}:
        if output_dir:
            command.extend(["--deliver-dir", str(_resolve_under_workspace(output_dir, workspace))])
        if title:
            command.extend(["--patent-title", title])
        if final_markdown:
            command.extend(["--final-markdown", str(_resolve_under_workspace(final_markdown, workspace))])
    if selected_map and args.gate in {"all", "research", "deliver"}:
        command.extend(["--sensitive-map", str(selected_map)])
    if args.report:
        report = _resolve_under_workspace(args.report, workspace)
        if not is_within(report, workspace):
            raise ValueError("check report must be inside the selected workspace")
        if report.exists() and not args.overwrite_report:
            raise FileExistsError("check report already exists; pass --overwrite-report to replace it")
    sensitive_map_before = (
        _hash_file(selected_map) if selected_map and selected_map.is_file() else None
    )
    env = {**os.environ, "PYTHONUTF8": "1"}
    proc = subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env)
    if proc.stderr:
        print(proc.stderr.rstrip(), file=sys.stderr)
    summary = _gate_summary(proc.stdout)
    report_valid = (
        proc.returncode in {0, 2}
        and summary.get("run_id") == run_id
        and isinstance(summary.get("checks_passed"), bool)
        and isinstance(summary.get("workflow_complete"), bool)
        and isinstance(summary.get("gateResults"), list)
        and all(
            isinstance(result, dict)
            and isinstance(result.get("gate"), str)
            and isinstance(result.get("status"), str)
            for result in summary["gateResults"]
        )
    )
    if not report_valid:
        summary = {
            "run_id": run_id,
            "checks_passed": False,
            "workflow_complete": False,
            "review_completed": False,
            "revision_validation": "not_run",
            "skipped": [],
            "not_run": [args.gate],
            "gateResults": [],
            "runner_error": "current subprocess did not return a matching structurally valid run report",
        }
    sensitive_map_audit: dict[str, Any] | None = None
    sensitive_map_audit_passed = True
    if selected_map:
        sensitive_map_after = (
            _hash_file(selected_map) if selected_map.is_file() else None
        )
        validation = _sensitive_map_validation(summary, selected_map, workspace)
        stable = bool(sensitive_map_before and sensitive_map_after == sensitive_map_before)
        validator_confirmation_valid = validation.get("confirmation_binding_valid") is True
        current_confirmation = _sensitive_map_declared_confirmation(selected_map)
        confirmation_matches = (
            isinstance(validation.get("confirmation_sha256"), str)
            and validation.get("confirmation_sha256") == current_confirmation
        )
        confirmation_valid = validator_confirmation_valid and confirmation_matches
        sensitive_map_audit_passed = stable and confirmation_valid
        sensitive_map_audit = {
            "audit_version": 1,
            "run_id": run_id,
            "checked_at": _now(),
            "selection_path_sha256": _sensitive_map_path_key(str(selected_map), workspace),
            "content_sha256": sensitive_map_after if stable else None,
            "confirmation_sha256": validation.get("confirmation_sha256") if confirmation_valid else None,
            "confirmation_binding_valid": confirmation_valid,
            "confirmation_matches_current_contents": confirmation_matches,
            "content_stable_during_check": stable,
            "checks_passed": sensitive_map_audit_passed,
        }
        summary["sensitive_map_audit"] = sensitive_map_audit
        if not sensitive_map_audit_passed:
            summary["checks_passed"] = False
            summary["passed"] = False
            summary["workflow_complete"] = False
            summary.setdefault("not_run", [])
            for result in summary.get("gateResults", []):
                if not isinstance(result, dict) or result.get("gate") not in {"research", "deliver"}:
                    continue
                if result.get("status") in {"passed", "failed"}:
                    result.update({
                        "status": "failed",
                        "passed": False,
                        "checks_passed": False,
                        "workflow_complete": False,
                        "sensitive_map_audit_valid": False,
                    })
                    result["sensitive_map_audit_error"] = (
                        "selected map confirmation could not be bound to stable current contents"
                    )
    if report_valid:
        _write_gate_summary(manifest, summary)
    if args.report and report_valid:
        report = _resolve_under_workspace(args.report, workspace)
        atomic_write_text(report, json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    gate_results = summary.get("gateResults", [])
    required_mode_gates = [gate for gate, _stage in MODE_GATES[state["workflow_mode"]]]
    active_mode_gates = set(required_mode_gates)
    completed = {
        str(value) for value in state.get("completed_gates", [])
        if isinstance(value, str) and value in active_mode_gates
    }
    invalidated = {
        str(value) for value in state.get("invalidated_gates", [])
        if isinstance(value, str) and value in active_mode_gates
    }
    attempted_gates = [args.gate] if args.gate != "all" else required_mode_gates
    seen_results: set[str] = set()
    for result in gate_results if isinstance(gate_results, list) else []:
        if not isinstance(result, dict):
            continue
        gate = result.get("gate")
        if not isinstance(gate, str) or gate not in attempted_gates:
            continue
        seen_results.add(gate)
        gate_complete = (
            result.get("status") == "passed"
            and result.get("checks_passed", result.get("passed")) is True
            and result.get("workflow_complete") is True
            and (gate != "review" or result.get("review_completed") is True)
            and not (selected_map and gate in {"research", "deliver"} and not sensitive_map_audit_passed)
        )
        if not gate_complete:
            for dependent in GATE_DOWNSTREAM.get(gate, {gate}):
                if dependent in active_mode_gates:
                    completed.discard(dependent)
                    invalidated.add(dependent)
            continue
        completed.add(gate)
        invalidated.discard(gate)
    if not report_valid:
        for gate in attempted_gates:
            if gate not in seen_results:
                for dependent in GATE_DOWNSTREAM.get(gate, {gate}):
                    if dependent in active_mode_gates:
                        completed.discard(dependent)
                        invalidated.add(dependent)
    _text2, fields2, latest = _read_manifest(manifest)
    latest.update({
        "completed_gates": sorted(completed),
        "invalidated_gates": sorted(invalidated),
        "last_check_run_id": run_id,
        "last_check_result": {
            "gate": args.gate,
            "run_id": run_id,
            "subprocess_returncode": proc.returncode,
            "report_valid": report_valid,
            "checks_passed": summary.get("checks_passed") is True,
            "workflow_complete": summary.get("workflow_complete") is True,
            "review_completed": summary.get("review_completed") is True,
            "revision_validation": summary.get("revision_validation", "not_run"),
            "skipped": summary.get("skipped", []),
            "not_run": summary.get("not_run", []),
            "gate_results": gate_results,
            "sensitive_map_audit": sensitive_map_audit,
        },
    })
    if sensitive_map_audit is not None:
        latest["sensitive_map_audit"] = sensitive_map_audit
    latest, snapshot = _refresh_state(latest, fields2, workspace)
    final_invalidated = set(latest.get("invalidated_gates", [])) & active_mode_gates
    final_completed = (set(latest.get("completed_gates", [])) & active_mode_gates) - final_invalidated
    latest["completed_gates"] = sorted(final_completed)
    latest["invalidated_gates"] = sorted(final_invalidated)
    _normalize_gate_state(latest, state["workflow_mode"])
    if not final_invalidated:
        latest["stale_materials"] = []
        snapshot["stale_materials"] = []
    snapshot["conclusions_need_review"] = latest["conclusions_need_review"]
    last_result = latest.get("last_check_result")
    if isinstance(last_result, dict):
        last_result["workflow_mode"] = state["workflow_mode"]
        last_result["material_snapshot_sha256"] = canonical_json_sha256(
            latest.get("material_hashes", {})
        )
    current_text = manifest.read_text(encoding="utf-8")
    atomic_write_text(manifest, _set_field(current_text, "current_step", snapshot["current_stage"]))
    update_manifest_state(
        manifest,
        event="cli_check",
        status="passed" if summary.get("checks_passed") is True else "not_passed",
        stage=snapshot["current_stage"],
        details={
            "gate": args.gate,
            "checks_passed": summary.get("checks_passed") is True,
            "workflow_complete": summary.get("workflow_complete") is True,
            "run_id": run_id,
            "report_valid": report_valid,
        },
        state_updates={
            "completed_gates": latest["completed_gates"],
            "invalidated_gates": latest["invalidated_gates"],
            "material_paths": latest.get("material_paths", {}),
            "material_registry": latest.get("material_registry", {}),
            "approved_inputs": latest.get("approved_inputs", {}),
            "material_hashes": latest.get("material_hashes", {}),
            "stale_materials": latest.get("stale_materials", []),
            "conclusions_need_review": bool(latest.get("conclusions_need_review")),
            "last_check_run_id": run_id,
            "last_check_result": latest["last_check_result"],
            "sensitive_map_audit": latest.get("sensitive_map_audit"),
            "current_stage": snapshot["current_stage"],
            "missing_materials": snapshot["missing_materials"],
            "next_step": snapshot["next_step"],
            "waiting_for_user": snapshot["waiting_for_user"],
        },
    )
    if not report_valid or (selected_map and not sensitive_map_audit_passed):
        return max(proc.returncode, 2)
    return proc.returncode


def _cmd_export(args: argparse.Namespace) -> int:
    workspace, manifest, _text, fields, state = _load_cli_state(args)
    migrated_sensitive_map = _strip_legacy_sensitive_map_tracking(state, fields, workspace)
    state, _snapshot = _refresh_state(state, fields, workspace)
    if migrated_sensitive_map:
        _write_state(manifest, state)
    mode = state["workflow_mode"]
    title = fields.get("final_title") or fields.get("working_title")
    if not title:
        raise ValueError("manifest final_title is required before export")
    problem = title_error(title)
    if problem:
        raise ValueError(problem)
    raw_markdown = fields.get("final_markdown_path")
    if not raw_markdown:
        raise ValueError("manifest final_markdown_path is required before export")
    markdown = _resolve_under_workspace(raw_markdown, workspace)
    if not markdown.is_file():
        raise FileNotFoundError("final Markdown file is missing")
    raw_output_dir = fields.get("output_dir")
    if not raw_output_dir:
        raise ValueError("manifest output_dir is required before export")
    output_dir = _resolve_under_workspace(raw_output_dir, workspace)
    if not is_within(markdown, output_dir):
        raise ValueError("final Markdown must be inside output_dir for a bound delivery export")

    declared_map = fields.get("sensitive_map_path")
    mine_origin = (fields.get("research_origin") or "").casefold() == "mine" or (
        fields.get("vault_direction_origin") or ""
    ).casefold() == "mine"
    if declared_map and not args.sensitive_map:
        raise ValueError("export requires --sensitive-map to explicitly reselect and validate the configured map")
    if mine_origin and not declared_map:
        raise ValueError("mine-origin runs require a manifest sensitive_map_path before export")
    if args.sensitive_map and not declared_map:
        raise ValueError("export --sensitive-map must match a sensitive_map_path selected in the manifest")
    selected_map: Path | None = None
    if args.sensitive_map:
        selected_map = _resolve_selected_input(args.sensitive_map, workspace)
        if _path_reference_key(str(selected_map), workspace) != _path_reference_key(declared_map or "", workspace):
            raise ValueError("export --sensitive-map must match the manifest path selection")
        if not selected_map.is_file():
            raise FileNotFoundError("explicitly selected sensitive map was not found")

    review_status_path = fields.get("review_status_path") or state.get("material_paths", {}).get("review_status")
    if not review_status_path:
        raise ValueError("export requires a current manifest review_status_path")
    review_status = _resolve_under_workspace(review_status_path, workspace)
    if not is_within(review_status, workspace) or not review_status.is_file():
        raise ValueError("current review status must be a JSON file inside the workspace")

    output = _resolve_under_workspace(args.output, workspace) if args.output else output_dir / f"{title}{DOCX_SUFFIX}"
    if not is_within(output, output_dir):
        raise ValueError("DOCX output must be inside the configured output_dir")
    if output.exists() and not args.overwrite:
        raise FileExistsError("DOCX output already exists; pass --overwrite to replace it")
    markdown_sha256 = _hash_file(markdown)
    selected_map_sha256 = _hash_file(selected_map) if selected_map else None

    # Re-run the real configured route validators. A prior state block or a
    # hand-edited completed_gates list is not sufficient export evidence.
    route_check = _run_export_gate_check(workspace, manifest, mode, selected_map)
    check_run_id = str(route_check["run_id"])
    route_map_audit = route_check.get("sensitive_map_audit")
    if selected_map and (
        not isinstance(route_map_audit, dict)
        or route_map_audit.get("content_sha256") != selected_map_sha256
    ):
        raise ValueError("sensitive map changed during current workflow checks; no DOCX was written")

    _current_text, current_fields, current_state = _read_manifest(manifest)
    current_state, _current_snapshot = _refresh_state(current_state, current_fields, workspace)
    current_mode = current_state["workflow_mode"]
    required_gates = [gate for gate, _stage in MODE_GATES[current_mode]]
    pre_export_gates = set(required_gates) - {"deliver"}
    completed = set(current_state.get("completed_gates", []))
    invalidated = set(current_state.get("invalidated_gates", []))
    check_state = current_state.get("last_check_result")
    if not (
        current_mode == mode
        and isinstance(check_state, dict)
        and check_state.get("gate") == "all"
        and check_state.get("report_valid") is True
        and check_state.get("run_id") == check_run_id
        and check_state.get("material_snapshot_sha256")
        == canonical_json_sha256(current_state.get("material_hashes", {}))
        and pre_export_gates.issubset(completed)
        and not pre_export_gates.intersection(invalidated)
        and current_state.get("conclusions_need_review") is not True
    ):
        raise ValueError("current route materials or review are stale; no DOCX was written")

    pre_export_health = _run_pre_export_health_check(
        workspace=workspace, manifest=manifest, output_dir=output_dir,
        title=title, markdown=markdown,
        facts_ledger=_resolve_under_workspace(
            fields.get("facts_ledger_path") or "artifacts/draft/facts_ledger.json", workspace,
        ),
        consistency_report=_resolve_under_workspace(
            fields.get("consistency_report_path") or "artifacts/audit/phase_08_consistency_audit_report.md",
            workspace,
        ),
        ipr_report=_resolve_under_workspace(
            fields.get("ipr_report_path") or "artifacts/audit/phase_09_ipr_review_report.md", workspace,
        ),
        review_status=review_status,
    )
    manifest_snapshot_sha256 = _hash_file(manifest)
    review_status_snapshot_sha256 = _hash_file(review_status)
    try:
        review_data = json.loads(review_status.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("current review status could not be revalidated; no DOCX was written") from exc
    revision_required = (
        (workspace / "artifacts" / "revision" / "phase_10_edit_plan.json").is_file()
        or (workspace / "artifacts" / "revision" / "phase_10_structured_diff.json").is_file()
    )
    review_errors, review_state = validate_review_status(
        review_data, workspace=workspace, output_dir=output_dir,
        require_revision=revision_required,
    )
    if (
        review_errors
        or review_state.get("review_fresh") is not True
        or review_state.get("workflow_complete") is not True
        or not isinstance(review_state.get("review_version_sha256"), str)
    ):
        raise ValueError("current review snapshot is incomplete or stale; no DOCX was written")
    review_version_sha256 = review_state["review_version_sha256"]

    with tempfile.TemporaryDirectory(prefix="patent-workflow-export-") as snapshot_temp:
        map_snapshot = _freeze_sensitive_map_snapshot(
            selected_map, Path(snapshot_temp), expected_sha256=selected_map_sha256,
        )
        markdown_map_audit = None
        if selected_map and map_snapshot:
            markdown_map_audit = _run_sensitive_map_scan(
                map_snapshot, markdown, workspace,
                expected_map_sha256=selected_map_sha256 or "", run_id=check_run_id,
                selection_path=selected_map,
            )

        temp_docx = output_dir / f".{output.stem}.{uuid.uuid4().hex}.tmp.docx"
        try:
            command = [sys.executable, str(SCRIPTS_DIR / "generate_docx.py"), str(markdown), str(temp_docx)]
            proc = subprocess.run(
                command, cwd=REPO_ROOT, capture_output=True, text=True,
                encoding="utf-8", errors="replace", env={**os.environ, "PYTHONUTF8": "1"},
            )
            generated = _gate_summary(proc.stdout)
            if proc.returncode != 0 or generated.get("status") != "generated" or not temp_docx.is_file():
                raise ValueError("DOCX generation failed; no final output was published")

            docx_map_audit = None
            if selected_map and map_snapshot:
                docx_map_audit = _run_sensitive_map_scan(
                    map_snapshot, temp_docx, workspace,
                    expected_map_sha256=selected_map_sha256 or "", run_id=check_run_id,
                    selection_path=selected_map,
                )
            review_snapshot = {
                "snapshot_version": 1,
                "workflow_mode": mode,
                "gate_check_run_id": check_run_id,
                "final_markdown_sha256": markdown_sha256,
                "review_status_sha256": review_status_snapshot_sha256,
                "review_version_sha256": review_version_sha256,
                "sensitive_map_sha256": selected_map_sha256,
                "sensitive_map_confirmation_sha256": (
                    markdown_map_audit.get("confirmation_sha256") if markdown_map_audit else None
                ),
            }
            review_snapshot["snapshot_sha256"] = canonical_json_sha256(review_snapshot)

            def validate_snapshot() -> None:
                _validate_current_export_snapshot(
                    manifest=manifest,
                    manifest_sha256=manifest_snapshot_sha256,
                    markdown=markdown,
                    markdown_sha256=markdown_sha256,
                    review_status=review_status,
                    review_status_sha256=review_status_snapshot_sha256,
                    review_version_sha256=review_version_sha256,
                    workspace=workspace,
                    output_dir=output_dir,
                    require_revision=revision_required,
                    selected_map=selected_map,
                    selected_map_sha256=selected_map_sha256,
                    map_snapshot=map_snapshot,
                )

            _publish_docx(
                temp_docx, output, overwrite=args.overwrite,
                validate_snapshot=validate_snapshot,
            )
        finally:
            temp_docx.unlink(missing_ok=True)

    sensitive_map_audit = None
    if selected_map and markdown_map_audit and docx_map_audit:
        sensitive_map_audit = {
            "audit_version": 3,
            "run_id": check_run_id,
            "selection_path_sha256": markdown_map_audit["selection_path_sha256"],
            "content_sha256": markdown_map_audit["content_sha256"],
            "snapshot_sha256": markdown_map_audit["content_sha256"],
            "confirmation_sha256": markdown_map_audit["confirmation_sha256"],
            "markdown_target_sha256": markdown_map_audit["target_sha256"],
            "docx_target_sha256": docx_map_audit["target_sha256"],
            "review_snapshot_sha256": review_snapshot["snapshot_sha256"],
            "review_version_sha256": review_version_sha256,
            "explicit_reselection": True,
            "checks_passed": True,
        }
    state_update = {
        "last_export": {
            "output_path": str(output.resolve()),
            "source_markdown_sha256": markdown_sha256,
            "docx_sha256": _hash_file(output),
            "pre_export_checks_passed": pre_export_health.get("export_allowed") is True,
            "post_export_delivery_check_required": True,
            "review_snapshot": review_snapshot,
            "sensitive_map_audit": sensitive_map_audit,
            "generated_at": _now(),
        }
    }
    update_manifest_state(
        manifest,
        event="export",
        status="exported_pending_delivery_check",
        stage="delivery",
        details={
            "output_path": str(output.resolve()),
            "source_preserved": markdown.is_file(),
            "workflow_complete": False,
            "post_export_delivery_check_required": True,
        },
        state_updates=state_update,
    )
    print(json.dumps({
        "status": "generated_pending_delivery_check",
        "output_path": str(output.resolve()),
        "workflow_complete": False,
        "post_export_delivery_check_required": True,
    }, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local manifest-backed patent collaboration workflow controls")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="Create a new run manifest without replacing existing files")
    init.add_argument("--workspace", default=".")
    init.add_argument("--manifest", default="artifacts/run_manifest.md")
    init.add_argument("--mode", choices=MODE_CHOICES, default="full_research")
    init.add_argument("--search-depth", choices=DEPTH_CHOICES, default="balanced")
    init.add_argument("--output-dir")
    init.add_argument("--title")
    init.add_argument("--search-brief", help="Requested research scope, stored locally in the manifest")
    init.add_argument("--run-id")
    _add_input_options(init)
    init.set_defaults(func=_cmd_init)

    for name in ("status", "resume"):
        command = subparsers.add_parser(name, help="Inspect or recover a local workflow checkpoint")
        command.add_argument("--workspace", default=".")
        command.add_argument("--manifest", default="artifacts/run_manifest.md")
        if name == "resume":
            command.add_argument("--mode", choices=MODE_CHOICES, help="Switch workflow route and invalidate route-dependent conclusions")
            command.add_argument("--title", help="Record a confirmed title, up to 24 characters")
            command.add_argument("--search-brief", help="Record the requested local search scope")
            command.add_argument("--output-dir", help="Record the local delivery directory")
            _add_input_options(command)
        command.set_defaults(func=_cmd_status if name == "status" else _cmd_resume)

    check = subparsers.add_parser("check", help="Run existing phase validators")
    check.add_argument("--workspace", default=".")
    check.add_argument("--manifest", default="artifacts/run_manifest.md")
    check.add_argument("--gate", choices=["research", "prior-art", "draft", "review", "deliver", "all"], default="all")
    check.add_argument("--sensitive-map", help="Explicitly reselect the manifest-referenced map for this check; reads it in place and never copies it")
    check.add_argument("--report", help="Optional summary report path inside the workspace")
    check.add_argument("--overwrite-report", action="store_true", help="Permit replacing an existing summary report")
    check.set_defaults(func=_cmd_check)

    export = subparsers.add_parser("export", help="Generate a local DOCX from the bound final Markdown")
    export.add_argument("--workspace", default=".")
    export.add_argument("--manifest", default="artifacts/run_manifest.md")
    export.add_argument("--output", help="DOCX output path inside output_dir")
    export.add_argument("--overwrite", action="store_true", help="Permit atomically replacing the DOCX output")
    export.add_argument("--sensitive-map", help="Explicitly reselect the manifest map; required when a map is configured")
    export.set_defaults(func=_cmd_export)
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    try:
        workspace = _resolve_workspace(getattr(args, "workspace", "."))
        with _workspace_operation_lock(workspace):
            return int(args.func(args))
    except (FileNotFoundError, FileExistsError, ValueError, OSError) as exc:
        print(f"workflow_cli: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
