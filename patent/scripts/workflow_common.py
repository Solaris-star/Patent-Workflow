#!/usr/bin/env python3
"""Small shared helpers for manifest-backed patent collaboration workflows."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

WORKFLOW_BEGIN = "<!-- WORKFLOW_STATE_JSON_BEGIN -->"
WORKFLOW_END = "<!-- WORKFLOW_STATE_JSON_END -->"
TITLE_MAX_CHARS = 24
DOCX_SUFFIX = "\u4e13\u5229\u6280\u672f\u4ea4\u5e95\u4e66.docx"
MODE_GATES: dict[str, list[tuple[str, str]]] = {
    "full_research": [
        ("research", "research"),
        ("prior-art", "evidence_synthesis"),
        ("draft", "draft"),
        ("review", "independent_review"),
        ("deliver", "delivery"),
    ],
    "titled_evidence": [
        ("prior-art", "evidence_gap_research"),
        ("draft", "draft"),
        ("review", "independent_review"),
        ("deliver", "delivery"),
    ],
    "draft_review": [
        ("review", "independent_review"),
        ("deliver", "delivery"),
    ],
}
MODE_CHOICES = tuple(MODE_GATES)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def manifest_field_text(text: str, key: str) -> str | None:
    tick = "\x60"
    match = re.search(
        rf"^[ \t]*-[ \t]*{tick}?{re.escape(key)}{tick}?[ \t]*:[ \t]*(.*)$",
        text,
        flags=re.MULTILINE,
    )
    if not match:
        return None
    value = re.sub(r"(?:^|\s+)#.*$", "", match.group(1)).strip().strip(tick).strip()
    if value.casefold() in {"", "tbd", "todo", "none", "null", "n/a", "na", "-"}:
        return None
    if value.startswith("<") and value.endswith(">"):
        return None
    return value


def read_manifest_fields(path: Path) -> dict[str, str | None]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    tick = "\x60"
    keys = re.findall(
        rf"^[ \t]*-[ \t]*(?:{tick}([^\r\n{tick}]+){tick}|([^:\r\n]+))[ \t]*:",
        text,
        flags=re.MULTILINE,
    )
    keys = [quoted or plain.strip() for quoted, plain in keys]
    return {key: manifest_field_text(text, key) for key in keys}


def read_workflow_state(text: str) -> dict[str, Any]:
    if WORKFLOW_BEGIN not in text or WORKFLOW_END not in text:
        return {}
    block = text.split(WORKFLOW_BEGIN, 1)[1].split(WORKFLOW_END, 1)[0]
    fence = chr(96) * 3
    match = re.search(
        r"(?:" + re.escape(fence) + r"|~~~)json\s*(.*?)\s*(?:" + re.escape(fence) + r"|~~~)",
        block,
        flags=re.DOTALL,
    )
    if not match:
        return {}
    try:
        parsed = json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def patch_workflow_state(text: str, state: dict[str, Any]) -> str:
    fence = chr(96) * 3
    block = (
        f"{WORKFLOW_BEGIN}\n{fence}json\n"
        f"{json.dumps(state, ensure_ascii=False, indent=2)}\n"
        f"{fence}\n{WORKFLOW_END}"
    )
    if WORKFLOW_BEGIN in text and WORKFLOW_END in text:
        prefix = text.split(WORKFLOW_BEGIN, 1)[0]
        suffix = text.split(WORKFLOW_END, 1)[1]
        return prefix + block + suffix
    separator = "\n" if not text or text.endswith("\n") else "\n\n"
    return text + separator + block + "\n"


def update_manifest_state(
    manifest_path: Path,
    *,
    event: str,
    status: str,
    stage: str | None = None,
    details: dict[str, Any] | None = None,
    state_updates: dict[str, Any] | None = None,
) -> dict[str, Any]:
    text = manifest_path.read_text(encoding="utf-8")
    state = read_workflow_state(text)
    history = state.get("stage_history")
    if not isinstance(history, list):
        history = []
    history.append({
        "at": utc_now(),
        "event": event,
        "status": status,
        "stage": stage,
        "details": details or {},
    })
    state["stage_history"] = history
    state["last_event_at"] = utc_now()
    if state_updates:
        state.update(state_updates)
    atomic_write_text(manifest_path, patch_workflow_state(text, state))
    return state


def atomic_write_text(path: Path, text: str, *, overwrite: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not overwrite and path.exists():
        raise FileExistsError(path)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        if not overwrite and path.exists():
            raise FileExistsError(path)
        os.replace(temp_path, path)
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_sha256(value: Any) -> str:
    """Hash a stable JSON representation for confirmation/version bindings."""
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def title_error(title: str, *, field: str = "title") -> str | None:
    if not title.strip():
        return f"{field} is empty"
    length = len(title.strip())
    if length > TITLE_MAX_CHARS:
        return f"{field} must be at most {TITLE_MAX_CHARS} characters (got {length})"
    return None
