#!/usr/bin/env python3
"""Check text credentials and the integrity/review state of listed examples.

This tool is a narrow publication checklist. It does not infer whether content
is confidential, verify human semantic review, inspect Git history/binaries,
or certify that publication is safe.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path, PurePosixPath

TEXT_SUFFIXES = {
    ".md", ".mmd", ".txt", ".py", ".json", ".toml", ".yaml", ".yml", ".ini",
    ".cfg", ".csv", ".html", ".xml", ".sh", ".ps1", ".bat", ".rst",
}
EXCLUDED_DIRS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache",
}
DEFAULT_MANIFEST = Path("patent/references/public_examples_manifest.json")
DEFAULT_SAMPLE_ROOTS = ("examples", "samples", "patent/examples", "patent/references/examples")
SAMPLE_DIR_NAMES = {"example", "examples", "sample", "samples", "demo", "demos"}
SAMPLE_NAME_RE = re.compile(r"(?i)(?:^|[._-])(?:example|sample|demo|synthetic)(?:[._-]|$)")
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
RULES = (
    ("private_key_marker", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("credential_assignment", re.compile(
        r"(?i)\b(?:api[_-]?key|access[_-]?token|client[_-]?secret|password|secret[_-]?key)\b"
        r"\s*[:=]\s*[\"']?[A-Za-z0-9_./+=-]{16,}"
    )),
    ("bearer_token", re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{16,}")),
    ("github_token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b")),
    ("cloud_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("email_address", re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")),
)
PLACEHOLDER_EMAIL_SUFFIXES = (".example", ".invalid", ".test")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _excluded(relative: Path) -> bool:
    return any(part in EXCLUDED_DIRS or part.startswith(".patent-private") for part in relative.parts)


def _candidate_sample(relative: Path, roots: tuple[str, ...]) -> bool:
    posix = relative.as_posix()
    if any(posix == root or posix.startswith(root.rstrip("/") + "/") for root in roots):
        return relative.suffix.lower() in TEXT_SUFFIXES
    if _excluded(relative):
        return False
    return (
        any(part.casefold() in SAMPLE_DIR_NAMES for part in relative.parts[:-1])
        or bool(SAMPLE_NAME_RE.search(relative.name))
    ) and relative.suffix.lower() in TEXT_SUFFIXES


def _load_manifest(root: Path, manifest_path: Path) -> tuple[dict, list[str]]:
    path = manifest_path if manifest_path.is_absolute() else root / manifest_path
    if path.is_symlink():
        return {}, ["public example manifest must not be a symbolic link"]
    path = path.resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError:
        return {}, ["public example manifest must be inside the scan root"]
    if not path.is_file():
        return {}, ["public example manifest is missing"]
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}, ["public example manifest is missing or unreadable"]
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        return {}, ["public example manifest must be a schema_version 1 object"]
    return value, []


def _sample_inventory(root: Path, manifest_path: Path) -> dict:
    manifest, errors = _load_manifest(root, manifest_path)
    roots_value = manifest.get("sample_roots", list(DEFAULT_SAMPLE_ROOTS))
    if (
        not isinstance(roots_value, list)
        or any(not isinstance(item, str) or not item.strip() for item in roots_value)
    ):
        errors.append("sample_roots must be a list of relative directories")
        roots_value = list(DEFAULT_SAMPLE_ROOTS)
    roots: list[str] = []
    for raw in roots_value:
        parsed = PurePosixPath(raw.replace("\\", "/"))
        if parsed.is_absolute() or ".." in parsed.parts:
            errors.append("sample_roots may only name directories inside the scan root")
            continue
        roots.append(parsed.as_posix().rstrip("/"))
    root_tuple = tuple(roots)
    entries = manifest.get("samples")
    if not isinstance(entries, list):
        errors.append("samples must be a list")
        entries = []
    listed: dict[str, dict] = {}
    changed: list[str] = []
    missing: list[str] = []
    unregistered: list[str] = []
    pending_review: list[str] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"samples[{index}] must be an object")
            continue
        raw_path = entry.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            errors.append(f"samples[{index}].path is required")
            continue
        rel = PurePosixPath(raw_path.replace("\\", "/"))
        if rel.is_absolute() or ".." in rel.parts:
            errors.append(f"samples[{index}].path must stay inside the scan root")
            continue
        key = rel.as_posix()
        if key in listed:
            errors.append(f"duplicate sample path: {key}")
            continue
        listed[key] = entry
        raw_target = root / Path(*rel.parts)
        if raw_target.is_symlink():
            errors.append(f"sample {key} must not be a symbolic link")
            missing.append(key)
            continue
        target = raw_target.resolve()
        try:
            target.relative_to(root.resolve())
        except ValueError:
            errors.append(f"sample path escapes the scan root: {key}")
            continue
        if target.is_symlink() or not target.is_file():
            missing.append(key)
            continue
        expected = entry.get("sha256")
        if not isinstance(expected, str) or not SHA256_RE.fullmatch(expected):
            errors.append(f"sample {key} requires a SHA-256 digest")
        elif _sha256(target).casefold() != expected.casefold():
            changed.append(key)
        source_status = entry.get("source_status")
        if not isinstance(source_status, str) or source_status not in {
            "synthetic", "public_source", "case_material", "unknown",
        }:
            errors.append(f"sample {key} requires source_status")
        elif source_status == "case_material":
            errors.append(f"sample {key} is classified as case_material and cannot be a public example")
        review = entry.get("human_review_status")
        if not isinstance(review, str) or review not in {"reviewed", "pending", "not_recorded"}:
            errors.append(f"sample {key} requires human_review_status")
        elif review != "reviewed" or (
            isinstance(source_status, str) and source_status in {"case_material", "unknown"}
        ):
            pending_review.append(key)
        else:
            try:
                datetime.fromisoformat(str(entry.get("human_reviewed_at", "")).replace("Z", "+00:00"))
            except ValueError:
                errors.append(f"sample {key} marked reviewed requires human_reviewed_at")
            if not isinstance(entry.get("human_review_reference"), str) or not entry["human_review_reference"].strip():
                errors.append(f"sample {key} marked reviewed requires human_review_reference")
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            try:
                relative = path.relative_to(root)
            except ValueError:
                continue
            if _candidate_sample(relative, root_tuple):
                errors.append("symbolic links are not allowed as public sample files")
            continue
        if not path.is_file():
            continue
        try:
            relative = path.resolve().relative_to(root.resolve())
        except ValueError:
            continue
        if _excluded(relative) or not _candidate_sample(relative, root_tuple):
            continue
        key = relative.as_posix()
        if key not in listed:
            unregistered.append(key)
    integrity_ok = not errors and not changed and not missing and not unregistered
    if not integrity_ok or pending_review:
        status = "needs_review"
    else:
        status = "passed"
    return {
        "status": status,
        "integrity_passed": integrity_ok,
        "entries_checked": len(listed),
        "changed_samples": changed,
        "missing_samples": missing,
        "unregistered_samples": unregistered,
        "pending_human_review": pending_review,
        "errors": errors,
    }


def scan(root: Path, manifest_path: Path | None = None) -> dict:
    findings: list[dict] = []
    scanned = 0
    root = root.resolve()
    manifest_path = manifest_path or DEFAULT_MANIFEST
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            relative = path.resolve().relative_to(root)
        except ValueError:
            continue
        if _excluded(relative):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            findings.append({"path": relative.as_posix(), "line": 0, "rule": "unreadable_text"})
            continue
        scanned += 1
        for line_number, line in enumerate(text.splitlines(), start=1):
            for rule, pattern in RULES:
                matches = list(pattern.finditer(line))
                if rule == "email_address":
                    matches = [
                        match for match in matches
                        if not match.group(0).casefold().endswith(PLACEHOLDER_EMAIL_SUFFIXES)
                    ]
                for _ in matches:
                    findings.append({"path": relative.as_posix(), "line": line_number, "rule": rule})
    inventory = _sample_inventory(root, manifest_path)
    credential_ok = not findings
    checks_passed = credential_ok and inventory["integrity_passed"] and inventory["status"] == "passed"
    return {
        "scanner": "check_public_release.py",
        "files_scanned": scanned,
        "checks_passed": checks_passed,
        "passed": checks_passed,
        "credential_scan": {
            "status": "passed" if credential_ok else "failed",
            "files_scanned": scanned,
            "findings_count": len(findings),
            "findings": findings,
            "matched_values_included": False,
        },
        "sample_manifest": inventory,
        "human_semantic_review": {
            "status": "pending" if inventory["pending_human_review"] else "recorded",
            "pending_paths": inventory["pending_human_review"],
            "assessed_by_scanner": False,
        },
        "publication_readiness": {
            "status": "not_certified",
            "reason": "credential and hash checks do not assess semantic confidentiality or replace human publication review",
        },
        "scope_note": "Current text files including .mmd only; Git history, binary content, and semantic/legal publication review are not covered.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check current text credentials and the registered public-example inventory")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--manifest", help="Example inventory JSON path, relative to --root unless absolute")
    parser.add_argument("--out")
    args = parser.parse_args()
    report = scan(
        Path(args.root),
        Path(args.manifest) if args.manifest else DEFAULT_MANIFEST,
    )
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        target = Path(args.out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(output, encoding="utf-8")
    else:
        print(output)
    return 0 if report["checks_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
