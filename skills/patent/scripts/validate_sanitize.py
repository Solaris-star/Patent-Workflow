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
import json
import re
import sys
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
            out.append((name, joined))
            out.append((f"{name}(raw)", raw))
    return out


def _load_texts(path: Path) -> list[tuple[str, str]]:
    """Return [(label, text)] for one file; empty list if unsupported/binary."""
    if path.suffix.lower() == ".docx":
        try:
            return [(f"{path}::{m}", t) for m, t in _docx_texts(path)]
        except Exception as e:
            return [(str(path), f"__DOCX_READ_ERROR__: {e}")]
    if path.suffix.lower() in TEXT_EXTS:
        try:
            return [(str(path), path.read_text(encoding="utf-8", errors="replace"))]
        except Exception as e:
            return [(str(path), f"__READ_ERROR__: {e}")]
    return []


def _context(text: str, start: int, end: int, span: int = 40) -> str:
    lo, hi = max(0, start - span), min(len(text), end + span)
    return text[lo:hi].replace("\n", " ")


def _match_entry(entry: dict, label: str, text: str) -> list[dict]:
    hits = []
    action_terms = [t for t in [entry.get("term"), *(entry.get("aliases") or [])] if t]
    if (entry.get("match") or "literal") == "regex":
        pat = entry.get("pattern") or ""
        if pat:
            for m in re.finditer(pat, text):
                hits.append({"file": label, "entry_id": entry.get("id"), "term": m.group(0),
                             "context": _context(text, m.start(), m.end())})
        return hits
    haystack = text if entry.get("case_sensitive") else text.casefold()
    for term in action_terms:
        needle = term if entry.get("case_sensitive") else term.casefold()
        idx = 0
        while True:
            pos = haystack.find(needle, idx)
            if pos < 0:
                break
            hits.append({"file": label, "entry_id": entry.get("id"), "term": term,
                         "context": _context(text, pos, pos + len(term))})
            idx = pos + len(term)
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

    map_hits: list[dict] = []
    heuristic_hits: list[dict] = []
    scanned = 0

    for path in targets:
        if not path.exists():
            errors.append(f"file not found: {path}")
            continue
        for label, text in _load_texts(path):
            scanned += 1
            for entry in entries:
                map_hits.extend(_match_entry(entry, label, text))
            if args.heuristics:
                for kind, pat in HEURISTIC_PATTERNS.items():
                    for m in re.finditer(pat, text):
                        heuristic_hits.append({"file": label, "kind": kind, "match": m.group(0)[:120],
                                               "context": _context(text, m.start(), m.end())})

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
