#!/usr/bin/env python3
"""Validate Phase 2 research pack artifact for patent-workflow.

Boundary note:
- This validator checks *structure* and basic auditability (URLs/excerpts/ID references).
- It does NOT enforce patent-specific constraints; those remain in patent-workflow phase rules.

Usage:
  python validate_research_pack.py artifacts/research/phase_02_research_pack.json

Exit codes:
  0 = pass
  2 = fail
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


def _is_http_url(u: str) -> bool:
    try:
        p = urlparse(u)
        return p.scheme in ("http", "https") and bool(p.netloc)
    except Exception:
        return False


def _require(cond: bool, msg: str, errors: list[str]):
    if not cond:
        errors.append(msg)


def _as_list(x):
    return x if isinstance(x, list) else []


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate phase_02 research_pack.json structure")
    ap.add_argument("input", help="Path to phase_02_research_pack.json")
    ap.add_argument("--output", help="Optional path to write validation summary JSON")
    ap.add_argument("--min-questions", type=int, default=8)
    ap.add_argument("--min-outline", type=int, default=5)
    ap.add_argument("--min-evidence", type=int, default=8)
    ap.add_argument("--min-excerpt-len", type=int, default=50)
    args = ap.parse_args()

    now = datetime.now(timezone.utc)
    inp = Path(args.input)

    errors: list[str] = []
    _require(inp.exists(), f"Input file not found: {inp}", errors)
    if errors:
        summary = {
            "validator": "validate_research_pack.py",
            "generatedAt": now.isoformat(),
            "inputPath": str(inp),
            "passed": False,
            "errors": errors,
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 2

    try:
        data = json.loads(inp.read_text(encoding="utf-8"))
    except Exception as e:
        summary = {
            "validator": "validate_research_pack.py",
            "generatedAt": now.isoformat(),
            "inputPath": str(inp.resolve()),
            "passed": False,
            "errors": [f"JSON parse error: {e}"],
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 2

    pack_type = data.get("pack_type")
    phase = data.get("phase")

    questions = _as_list(data.get("research_questions"))
    outline = _as_list(data.get("outline_skeleton"))
    evidence = _as_list(data.get("evidence"))

    _require(pack_type == "research_pack", "pack_type must be 'research_pack'", errors)
    _require(phase == "phase_02", "phase must be 'phase_02'", errors)

    _require(len(questions) >= args.min_questions, f"research_questions length < {args.min_questions}", errors)
    _require(len(outline) >= args.min_outline, f"outline_skeleton length < {args.min_outline}", errors)
    _require(len(evidence) >= args.min_evidence, f"evidence length < {args.min_evidence}", errors)

    rq_ids = set()
    for i, rq in enumerate(questions):
        if not isinstance(rq, dict):
            errors.append(f"research_questions[{i}] must be object")
            continue
        rid = (rq.get("id") or "").strip()
        q = (rq.get("question") or "").strip()
        _require(bool(rid), f"research_questions[{i}].id missing", errors)
        _require(bool(q), f"research_questions[{i}].question missing", errors)
        if rid:
            rq_ids.add(rid)

    ev_ids = set()
    for i, ev in enumerate(evidence):
        if not isinstance(ev, dict):
            errors.append(f"evidence[{i}] must be object")
            continue
        eid = (ev.get("evidence_id") or "").strip()
        url = (ev.get("url") or "").strip()
        excerpt = (ev.get("excerpt") or "").strip()
        _require(bool(eid), f"evidence[{i}].evidence_id missing", errors)
        _require(_is_http_url(url), f"evidence[{i}].url not http(s): {url}", errors)
        _require(len(excerpt) >= args.min_excerpt_len, f"evidence[{i}].excerpt too short (<{args.min_excerpt_len})", errors)
        if eid:
            ev_ids.add(eid)

    for i, sec in enumerate(outline):
        if not isinstance(sec, dict):
            errors.append(f"outline_skeleton[{i}] must be object")
            continue
        sid = (sec.get("section_id") or "").strip()
        title = (sec.get("title") or "").strip()
        intent = (sec.get("intent") or "").strip()
        _require(bool(sid), f"outline_skeleton[{i}].section_id missing", errors)
        _require(bool(title), f"outline_skeleton[{i}].title missing", errors)
        _require(bool(intent), f"outline_skeleton[{i}].intent missing", errors)

        for rid in _as_list(sec.get("covers_questions")):
            if isinstance(rid, str) and rid.strip() and rid.strip() not in rq_ids:
                errors.append(f"outline_skeleton[{i}].covers_questions references unknown id: {rid}")

        for eid in _as_list(sec.get("evidence_ids")):
            if isinstance(eid, str) and eid.strip() and eid.strip() not in ev_ids:
                errors.append(f"outline_skeleton[{i}].evidence_ids references unknown id: {eid}")

    summary = {
        "validator": "validate_research_pack.py",
        "generatedAt": now.isoformat(),
        "inputPath": str(inp.resolve()),
        "thresholds": {
            "minQuestions": args.min_questions,
            "minOutline": args.min_outline,
            "minEvidence": args.min_evidence,
            "minExcerptLen": args.min_excerpt_len,
        },
        "counts": {
            "research_questions": len(questions),
            "outline_skeleton": len(outline),
            "evidence": len(evidence),
        },
        "passed": len(errors) == 0,
        "errors": errors,
    }

    out = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(out, encoding="utf-8")
    else:
        print(out)

    return 0 if summary["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
