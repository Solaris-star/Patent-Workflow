#!/usr/bin/env python3
"""Validate Phase 4 evidence pack artifact for patent-workflow.

Boundary note:
- This validator checks evidence_pack structure + basic auditability.
- Patent-specific search constraints (CN-only, <=1.5y, relevance thresholding) are enforced by
  patent-workflow phase rules and validate_patent_candidates.py. This script focuses on:
  - evidence pack completeness
  - evidence alignment coverage
  - separation between patent evidence vs auxiliary web evidence

Usage:
  python validate_evidence_pack.py artifacts/prior_art/phase_04_evidence_pack.json

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


def _as_dict(x):
    return x if isinstance(x, dict) else {}


def _is_aux(ev: dict) -> bool:
    return bool(ev.get("is_auxiliary", False))


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate phase_04 evidence_pack.json structure")
    ap.add_argument("input", help="Path to phase_04_evidence_pack.json")
    ap.add_argument("--output", help="Optional path to write validation summary JSON")
    ap.add_argument("--min-final", type=int, default=5)
    ap.add_argument("--min-alignments", type=int, default=3)
    ap.add_argument("--min-excerpt-len", type=int, default=50)
    args = ap.parse_args()

    now = datetime.now(timezone.utc)
    inp = Path(args.input)

    errors: list[str] = []
    _require(inp.exists(), f"Input file not found: {inp}", errors)
    if errors:
        summary = {
            "validator": "validate_evidence_pack.py",
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
            "validator": "validate_evidence_pack.py",
            "generatedAt": now.isoformat(),
            "inputPath": str(inp.resolve()),
            "passed": False,
            "errors": [f"JSON parse error: {e}"],
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 2

    pack_type = data.get("pack_type")
    phase = data.get("phase")

    _require(pack_type == "evidence_pack", "pack_type must be 'evidence_pack'", errors)
    _require(phase == "phase_04", "phase must be 'phase_04'", errors)

    pool_path = (data.get("patent_candidate_pool_path") or "").strip()
    _require(bool(pool_path), "patent_candidate_pool_path is required", errors)

    final_patents = _as_list(data.get("final_relevant_patents"))
    final_count = data.get("search_trace", {}).get("final_relevant_patent_count")

    # Prefer explicit count in search_trace if present, else derive from array.
    if isinstance(final_count, int):
        _require(final_count >= args.min_final, f"final_relevant_patent_count < {args.min_final}", errors)
    else:
        _require(len(final_patents) >= args.min_final, f"final_relevant_patents length < {args.min_final}", errors)

    search_trace = _as_dict(data.get("search_trace"))
    queries = _as_list(search_trace.get("patent_search_queries"))
    _require(len(queries) >= 1, "search_trace.patent_search_queries must be non-empty", errors)

    evidence = _as_list(data.get("evidence"))
    alignments = _as_list(data.get("evidence_alignment"))

    _require(len(evidence) >= 1, "evidence must be non-empty", errors)
    _require(len(alignments) >= args.min_alignments, f"evidence_alignment length < {args.min_alignments}", errors)

    ev_by_id: dict[str, dict] = {}
    aux_count = 0
    patent_evidence_count = 0

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
            ev_by_id[eid] = ev

        if _is_aux(ev):
            aux_count += 1
        else:
            # treat as "patent evidence" for gating purposes
            patent_evidence_count += 1

    _require(patent_evidence_count >= 1, "at least 1 non-auxiliary (patent) evidence item is required", errors)

    for i, a in enumerate(alignments):
        if not isinstance(a, dict):
            errors.append(f"evidence_alignment[{i}] must be object")
            continue
        eids = _as_list(a.get("evidence_ids"))
        _require(len(eids) >= 1, f"evidence_alignment[{i}].evidence_ids must be non-empty", errors)

        # must include at least 1 non-aux evidence
        non_aux_ok = False
        for eid in eids:
            if not isinstance(eid, str) or not eid.strip():
                continue
            if eid.strip() not in ev_by_id:
                errors.append(f"evidence_alignment[{i}] references unknown evidence_id: {eid}")
                continue
            if not _is_aux(ev_by_id[eid.strip()]):
                non_aux_ok = True

        _require(non_aux_ok, f"evidence_alignment[{i}] must reference >=1 non-auxiliary patent evidence", errors)

    summary = {
        "validator": "validate_evidence_pack.py",
        "generatedAt": now.isoformat(),
        "inputPath": str(inp.resolve()),
        "thresholds": {
            "minFinal": args.min_final,
            "minAlignments": args.min_alignments,
            "minExcerptLen": args.min_excerpt_len,
        },
        "counts": {
            "finalRelevantPatents": len(final_patents),
            "evidence": len(evidence),
            "evidenceAlignment": len(alignments),
            "evidenceAuxiliary": aux_count,
            "evidenceNonAuxiliary": patent_evidence_count,
            "patentSearchQueries": len(queries),
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
