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
            return [], [f"docx read error (unverifiable, treated as fail): {path}: {e}"]
    if path.suffix.lower() in TEXT_EXTS:
        try:
            return [(str(path), path.read_text(encoding="utf-8", errors="replace"))], []
        except Exception as e:
            return [], [f"read error (unverifiable, treated as fail): {path}: {e}"]
    return [], []


def _context(text: str, start: int, end: int, span: int = 40) -> str:
    lo, hi = max(0, start - span), min(len(text), end + span)
    return text[lo:hi].replace("\n", " ")


def _fold(s: str, case_sensitive: bool) -> str:
    # NFKC: full-width/half-width and compatibility forms compare equal
    s = unicodedata.normalize("NFKC", s)
    return s if case_sensitive else s.casefold()


def _prepare_entries(entries: list[dict], errors: list[str]) -> list[dict]:
    """Precompile regex entries; an uncompilable or empty pattern is an ERROR —
    a map entry that can never match is false security, not a no-op."""
    prepared = []
    for e in entries:
        if (e.get("match") or "literal") == "regex":
            pat = e.get("pattern") or ""
            if not pat:
                errors.append(f"map entry {e.get('id')}: match=regex but pattern is empty")
                continue
            try:
                e = {**e, "_compiled": re.compile(pat)}
            except re.error as ex:
                errors.append(f"map entry {e.get('id')}: invalid regex: {ex}")
                continue
        prepared.append(e)
    return prepared


def _match_entry(entry: dict, label: str, text: str) -> list[dict]:
    hits = []
    compiled = entry.get("_compiled")
    if compiled is not None:
        for m in compiled.finditer(text):
            hits.append({"file": label, "entry_id": entry.get("id"), "term": m.group(0),
                         "context": _context(text, m.start(), m.end())})
        return hits
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
            hits.append({"file": label, "entry_id": entry.get("id"), "term": term,
                         "context": _context(haystack, pos, pos + len(needle))})
            idx = pos + len(needle)
    return hits


def main() -> int:
    ap = argparse.ArgumentParser(description="Assert texts contain no sensitive-map terms")
    ap.add_argument("--map", dest="map_path", help="Path to sensitive_map.json")
    ap.add_argument("--files", nargs="*", default=[], help="Explicit files to scan")
    ap.add_argument("--scan-dir", help="Directory to scan recursively")
    ap.add_argument("--heuristics", action="store_true",
                    help="Also run built-in ip/url/path/email patterns (advisory; never affects pass/fail)")
    ap.add_argument("--output", help="Optional path to write JSON summary")
    args = ap.parse_args()

    errors: list[str] = []
    entries: list[dict] = []

    if args.map_path:
        mp = Path(args.map_path)
        if not mp.exists():
            errors.append(f"sensitive map not found: {mp}")
        else:
            try:
                data = json.loads(mp.read_text(encoding="utf-8"))
                if data.get("map_type") != "sensitive_map":
                    errors.append("map_type must be 'sensitive_map'")
                entries = [e for e in (data.get("entries") or []) if isinstance(e, dict)]
                if not entries:
                    errors.append("sensitive_map has no entries")
            except Exception as e:
                errors.append(f"map JSON parse error: {e}")
    elif not args.heuristics:
        errors.append("either --map or --heuristics is required")

    targets: list[Path] = [Path(f) for f in args.files]
    if args.scan_dir:
        base = Path(args.scan_dir)
        if not base.exists():
            errors.append(f"scan dir not found: {base}")
        else:
            targets += [p for p in base.rglob("*")
                        if p.is_file() and (p.suffix.lower() in TEXT_EXTS or p.suffix.lower() == ".docx")]
    if not targets and not errors:
        errors.append("nothing to scan: provide --files or --scan-dir")

    entries = _prepare_entries(entries, errors)

    map_hits: list[dict] = []
    heuristic_hits: list[dict] = []
    scanned = 0
    explicit = {Path(f) for f in args.files}

    for path in targets:
        if not path.exists():
            errors.append(f"file not found: {path}")
            continue
        texts, load_errors = _load_texts(path)
        errors.extend(load_errors)
        if not texts and not load_errors and path in explicit:
            # explicitly named but of a type this gate cannot scan — refusing
            # silently would fake a pass on an unverified file
            errors.append(f"unsupported file type, cannot verify: {path}")
        for label, text in texts:
            scanned += 1
            for entry in entries:
                map_hits.extend(_match_entry(entry, label, text))
            if args.heuristics:
                for kind, pat in HEURISTIC_PATTERNS.items():
                    for m in re.finditer(pat, text):
                        heuristic_hits.append({"file": label, "kind": kind, "match": m.group(0)[:120],
                                               "context": _context(text, m.start(), m.end())})

    if scanned == 0 and not errors:
        errors.append("no scannable texts found — nothing was verified")

    passed = len(errors) == 0 and len(map_hits) == 0

    summary = {
        "validator": "validate_sanitize.py",
        "generatedAt": _now(),
        "mapPath": args.map_path,
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
