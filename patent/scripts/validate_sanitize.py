#!/usr/bin/env python3
"""Sanitize gate: assert target texts contain NO sensitive-map terms.

Pass condition: (target text) INTERSECT (map terms incl. aliases/regex) == empty set.

Scans:
- text files (.md .mmd .txt .json .drawio .xml .html .csv) directly
- .docx via zipfile: concatenates <w:t> runs (word splits terms across runs)
  per paragraph, plus raw xml as a safety net

Usage:
  python validate_sanitize.py --map <sensitive_map.json> --files f1 [f2 ...]
  python validate_sanitize.py --map <sensitive_map.json> --scan-dir <dir>
  python validate_sanitize.py --heuristics --files f1        (advisory scan, no map needed)

Exit codes:
  0 = pass (no map-term hits; heuristic hits are advisory only)
  2 = fail (map-term hit, or input/map errors)
"""

import argparse
import html
import json
import re
import sys
import unicodedata
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from workflow_common import canonical_json_sha256

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass

TEXT_EXTS = {".md", ".mmd", ".txt", ".json", ".drawio", ".xml", ".html", ".csv"}

HEURISTIC_PATTERNS = {
    "ipv4": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
    "email": r"\b[\w.+-]+@[\w-]+\.[\w.]+\b",
    "url": r"https?://[^\s\"'<>)]+",
    "win_path": r"\b[A-Za-z]:\\[^\s\"'<>|]+",
    "unix_path": r"(?:^|[\s\"'(])(/(?:home|opt|var|etc|usr|srv|data)/[^\s\"'<>)]+)",
}

W_T = re.compile(r"<w:t(?:\s[^>]*)?>(.*?)</w:t>", re.DOTALL)
W_P_END = re.compile(r"</w:p>")


def _now():
    return datetime.now(timezone.utc).isoformat()


def _docx_texts(path: Path) -> list[tuple[str, str]]:
    """Return [(member_name, extracted_text)] for all word/*.xml members."""
    out = []
    with zipfile.ZipFile(path, "r") as z:
        for name in z.namelist():
            if not (name.startswith("word/") and name.endswith(".xml")):
                continue
            raw = z.read(name).decode("utf-8", errors="replace")
            # join runs so terms split across <w:t> nodes are still found;
            # paragraph ends become newlines to avoid cross-paragraph false joins
            joined = "\n".join(
                "".join(W_T.findall(para)) for para in W_P_END.split(raw)
            )
            # unescape XML entities ('AT&T' is stored as 'AT&amp;T' — matching the
            # escaped form would systematically miss such terms)
            out.append((name, html.unescape(joined)))
            out.append((f"{name}(raw)", html.unescape(raw)))
    return out


def _load_texts(path: Path) -> tuple[list[tuple[str, str]], list[str]]:
    """Return ([(label, text)], errors) for one file.

    A file this gate cannot read is a FAILURE, not a pass — an unverifiable
    input must never let the leak check go green (fail-closed).
    """
    if path.suffix.lower() == ".docx":
        try:
            return [(f"{path}::{m}", t) for m, t in _docx_texts(path)], []
        except Exception as e:
            return [], ["docx read error (unverifiable, treated as fail)"]
    if path.suffix.lower() in TEXT_EXTS:
        try:
            return [(str(path), path.read_text(encoding="utf-8", errors="replace"))], []
        except Exception as e:
            return [], ["read error (unverifiable, treated as fail)"]
    return [], []


def _fold(s: str, case_sensitive: bool) -> str:
    # NFKC: full-width/half-width and compatibility forms compare equal
    s = unicodedata.normalize("NFKC", s)
    return s if case_sensitive else s.casefold()


def _prepare_entries(entries: list[dict], errors: list[str]) -> list[dict]:
    """Precompile regex entries; an uncompilable or empty pattern is an ERROR —
    a map entry that can never match is false security, not a no-op."""
    prepared = []
    seen_ids: set[str] = set()
    for entry_index, e in enumerate(entries):
        entry_id = e.get("id")
        if not isinstance(entry_id, str) or not entry_id.strip():
            errors.append("sensitive-map entry is missing a non-empty id")
            continue
        if entry_id in seen_ids:
            errors.append("sensitive-map entry ids must be unique")
            continue
        seen_ids.add(entry_id)
        mode = e.get("match") or "literal"
        if mode not in ("literal", "regex"):
            errors.append(f"sensitive-map entry[{entry_index}] has unsupported match mode")
            continue
        if mode == "literal":
            term = e.get("term")
            aliases = e.get("aliases", [])
            if not isinstance(term, str) or not term.strip():
                errors.append(f"sensitive-map entry[{entry_index}] is missing its literal term")
                continue
            if not isinstance(aliases, list) or any(not isinstance(a, str) or not a.strip() for a in aliases):
                errors.append(f"sensitive-map entry[{entry_index}] has invalid aliases")
                continue
        if (e.get("match") or "literal") == "regex":
            pat = e.get("pattern") or ""
            if not pat:
                errors.append("sensitive-map regex entry is missing a pattern")
                continue
            try:
                e = {**e, "_compiled": re.compile(pat)}
            except re.error as ex:
                errors.append("sensitive-map regex entry is invalid")
                continue
        prepared.append(e)
    return prepared


def _match_entry(entry: dict, text: str) -> int:
    count = 0
    compiled = entry.get("_compiled")
    if compiled is not None:
        return sum(1 for _ in compiled.finditer(text))
    cs = bool(entry.get("case_sensitive"))
    action_terms = [t for t in [entry.get("term"), *(entry.get("aliases") or [])] if t]
    haystack = _fold(text, cs)
    for term in action_terms:
        needle = _fold(term, cs)
        if not needle:
            continue
        idx = 0
        while True:
            pos = haystack.find(needle, idx)
            if pos < 0:
                break
            # context is taken from the folded text: NFKC/casefold can shift
            # offsets relative to the original, folded offsets are always valid
            count += 1
            idx = pos + len(needle)
    return count


def _confirmation_errors(data: object) -> list[str]:
    """Bind the confirmation record to the normalized map and scope.

    This digest detects accidental or post-confirmation edits. It is not a
    signature and does not authenticate who set the JSON confirmation fields;
    the host must obtain confirmation from the actual user.
    """
    errors: list[str] = []
    if not isinstance(data, dict) or data.get("map_type") != "sensitive_map":
        return ["map_type must be 'sensitive_map'"]
    if data.get("confirmed_by_user") is not True:
        errors.append("sensitive map is not confirmed_by_user; scan was not run")
    if not isinstance(data.get("confirmation_scope"), str) or not data["confirmation_scope"].strip():
        errors.append("sensitive map confirmation_scope is required")
    confirmed_at = data.get("confirmed_at")
    if not isinstance(confirmed_at, str) or not confirmed_at.strip():
        errors.append("sensitive map confirmed_at is required")
    else:
        try:
            datetime.fromisoformat(confirmed_at.replace("Z", "+00:00"))
        except ValueError:
            errors.append("sensitive map confirmed_at must be an ISO-8601 timestamp")
    expected = data.get("confirmation_sha256")
    actual = canonical_json_sha256({
        key: value for key, value in data.items()
        if key not in {"confirmed_by_user", "confirmed_at", "confirmation_sha256"}
    })
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", expected):
        errors.append("sensitive map confirmation_sha256 is required")
    elif expected.casefold() != actual.casefold():
        errors.append("sensitive map confirmation is stale; confirm the current map contents and scope")
    return errors


def main() -> int:
    ap = argparse.ArgumentParser(description="Assert texts contain no sensitive-map terms")
    ap.add_argument("--map", dest="map_path", help="Path to sensitive_map.json")
    ap.add_argument("--validate-only", action="store_true",
                    help="Validate confirmation and entry fields without scanning files")
    ap.add_argument("--files", nargs="*", default=[], help="Explicit files to scan")
    ap.add_argument("--scan-dir", help="Directory to scan recursively")
    ap.add_argument("--heuristics", action="store_true",
                    help="Also run built-in ip/url/path/email patterns (advisory; never affects pass/fail)")
    ap.add_argument("--output", help="Optional path to write JSON summary")
    args = ap.parse_args()

    errors: list[str] = []
    entries: list[dict] = []
    map_confirmed = False
    confirmation_sha256: str | None = None

    if args.map_path:
        mp = Path(args.map_path)
        if not mp.exists():
            errors.append("sensitive map was not found")
        else:
            try:
                data = json.loads(mp.read_text(encoding="utf-8"))
                confirmation_errors = _confirmation_errors(data)
                errors.extend(confirmation_errors)
                map_confirmed = not confirmation_errors
                if map_confirmed:
                    confirmation_sha256 = str(data.get("confirmation_sha256"))
                raw_entries = data.get("entries") if isinstance(data, dict) else None
                if not isinstance(raw_entries, list):
                    errors.append("sensitive-map entries must be a list")
                else:
                    entries = [e for e in raw_entries if isinstance(e, dict)]
                    if len(entries) != len(raw_entries):
                        errors.append("every sensitive-map entry must be an object")
                    if not entries:
                        errors.append("sensitive_map has no entries")
            except Exception as e:
                errors.append("sensitive map could not be parsed as JSON")
    elif not args.heuristics:
        errors.append("either --map or --heuristics is required")

    entries = _prepare_entries(entries, errors)

    if args.validate_only:
        passed = bool(args.map_path) and not errors and map_confirmed
        summary = {
            "validator": "validate_sanitize.py",
            "generatedAt": _now(),
            "map_confirmed": map_confirmed,
            "confirmation_binding_valid": map_confirmed,
            "confirmation_sha256": confirmation_sha256,
            "confirmation_authentication": "host_user_confirmation_required",
            "validation_only": True,
            "checks_passed": passed,
            "passed": passed,
            "errors": errors,
        }
        out = json.dumps(summary, ensure_ascii=False, indent=2)
        if args.output:
            Path(args.output).parent.mkdir(parents=True, exist_ok=True)
            Path(args.output).write_text(out, encoding="utf-8")
        else:
            print(out)
        return 0 if passed else 2

    pre_scan_blocked = bool(args.map_path) and bool(errors)
    targets: list[Path] = [Path(f) for f in args.files]
    if args.scan_dir:
        base = Path(args.scan_dir)
        if not base.exists():
            errors.append("scan dir was not found")
        else:
            targets += [p for p in base.rglob("*")
                        if p.is_file() and (p.suffix.lower() in TEXT_EXTS or p.suffix.lower() == ".docx")]
    if not targets and not errors:
        errors.append("nothing to scan: provide --files or --scan-dir")

    map_hits: list[dict] = []
    heuristic_hits: list[dict] = []
    scanned = 0
    explicit = {Path(f) for f in args.files}

    for target_index, path in enumerate([] if pre_scan_blocked else targets):
        if not path.exists():
            errors.append(f"target[{target_index}] was not found")
            continue
        texts, load_errors = _load_texts(path)
        errors.extend(f"target[{target_index}] is unreadable" for _ in load_errors)
        if not texts and not load_errors and path in explicit:
            # explicitly named but of a type this gate cannot scan — refusing
            # silently would fake a pass on an unverified file
            errors.append(f"target[{target_index}] has an unsupported file type")
        for label, text in texts:
            scanned += 1
            if map_confirmed:
                for entry_index, entry in enumerate(entries):
                    count = _match_entry(entry, text)
                    if count:
                        map_hits.append({
                            "target_index": target_index,
                            "entry_index": entry_index,
                            "match_count": count,
                        })
            if args.heuristics:
                for kind, pat in HEURISTIC_PATTERNS.items():
                    count = sum(1 for _ in re.finditer(pat, text))
                    if count:
                        heuristic_hits.append({
                            "target_index": target_index,
                            "kind": kind,
                            "match_count": count,
                        })

    if scanned == 0 and not errors:
        errors.append("no scannable texts found — nothing was verified")

    passed = len(errors) == 0 and len(map_hits) == 0

    summary = {
        "validator": "validate_sanitize.py",
        "generatedAt": _now(),
        "map_confirmed": map_confirmed,
        "confirmation_binding_valid": map_confirmed,
        "confirmation_sha256": confirmation_sha256,
        "confirmation_authentication": "host_user_confirmation_required",
        "counts": {"targets": len(targets), "textsScanned": scanned,
                   "mapHits": len(map_hits), "heuristicHits": len(heuristic_hits)},
        "mapHits": map_hits[:200],
        "heuristicHits": heuristic_hits[:200],
        "passed": passed,
        "errors": errors,
    }

    out = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(out, encoding="utf-8")
    print(out)
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
