#!/usr/bin/env python3
"""Phase 11 delivery health gate for patent-workflow.

This script checks deliverable completeness and writes a health report JSON.

Usage (simple):
  python health_check_delivery_package.py \
    --deliver-dir <dir> \
    --patent-title "<专利标题>" \
    --facts-ledger artifacts/draft/facts_ledger.json \
    --consistency-report artifacts/audit/phase_08_consistency_audit_report.md \
    --ipr-report artifacts/audit/phase_09_ipr_review_report.md \
    --out artifacts/delivery/phase_11_delivery_health_report.json

Exit codes:
  0 = pass
  2 = fail
"""

import argparse
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass


def _check(checks: list[dict], name: str, cond: bool, details_ok: str = "", details_fail: str = ""):
    checks.append({
        "name": name,
        "result": "pass" if cond else "fail",
        "details": details_ok if cond else details_fail,
    })


def _exists(p: str | Path) -> bool:
    return Path(p).exists()


def _docx_has_media(docx_path: Path) -> bool:
    if not docx_path.exists():
        return False
    try:
        with zipfile.ZipFile(docx_path, "r") as z:
            names = z.namelist()
            return any(n.startswith("word/media/") and not n.endswith("/") for n in names)
    except Exception:
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description="Delivery health gate (phase 11)")
    ap.add_argument("--deliver-dir", required=True, help="Delivery directory (root containing final docx and figures dir)")
    ap.add_argument("--patent-title", required=True, help="Final patent title (used for filename check)")
    ap.add_argument("--facts-ledger", required=True, help="Path to facts_ledger.json")
    ap.add_argument("--consistency-report", required=True, help="Path to phase_08 consistency report")
    ap.add_argument("--ipr-report", required=True, help="Path to phase_09 ipr report")
    ap.add_argument("--out", default="artifacts/delivery/phase_11_delivery_health_report.json", help="Output report JSON path")
    ap.add_argument("--base-dir", default=".", help="Base dir for resolving relative paths in facts ledger")
    args = ap.parse_args()

    now = datetime.now(timezone.utc)
    deliver_dir = Path(args.deliver_dir)
    base_dir = Path(args.base_dir)

    checks: list[dict] = []
    missing: list[str] = []

    expected_name = f"{args.patent_title}技术交底书.docx"
    final_docx = deliver_dir / expected_name

    _check(checks, "delivery directory exists", deliver_dir.exists(), details_ok=str(deliver_dir), details_fail=str(deliver_dir))

    _check(
        checks,
        "final docx filename matches <title>技术交底书.docx",
        final_docx.exists(),
        details_ok=str(final_docx),
        details_fail=f"expected: {final_docx}",
    )
    if not final_docx.exists():
        missing.append(str(final_docx))

    # docx media embed check
    has_media = _docx_has_media(final_docx)
    _check(
        checks,
        "docx has embedded images (word/media non-empty)",
        has_media,
        details_ok="embedded media found",
        details_fail="no embedded media found (word/media empty or docx unreadable)",
    )

    # reports exist
    _check(checks, "consistency report exists", _exists(args.consistency_report), details_ok=args.consistency_report, details_fail=args.consistency_report)
    if not _exists(args.consistency_report):
        missing.append(args.consistency_report)

    _check(checks, "ipr report exists", _exists(args.ipr_report), details_ok=args.ipr_report, details_fail=args.ipr_report)
    if not _exists(args.ipr_report):
        missing.append(args.ipr_report)

    # facts ledger + figure artifact completeness
    ledger_path = Path(args.facts_ledger)
    _check(checks, "facts_ledger exists", ledger_path.exists(), details_ok=str(ledger_path), details_fail=str(ledger_path))
    if not ledger_path.exists():
        missing.append(str(ledger_path))
        ledger = None
    else:
        try:
            ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        except Exception as e:
            ledger = None
            _check(checks, "facts_ledger JSON parses", False, details_fail=str(e))

    # Figure artifacts are checked in the DELIVER dir — the delivery contract puts
    # 附图/ in the delivery root; a figure that exists only in the workspace means
    # the export step forgot to copy it (previously a silent pass).
    def _figure_missing(rel_or_abs: str) -> str | None:
        p = Path(rel_or_abs)
        if p.is_absolute():
            return None if p.exists() else str(p)
        if (deliver_dir / p).exists():
            return None
        hint = " (exists in workspace but not copied to deliver dir)" if (base_dir / p).exists() else ""
        return f"{deliver_dir / p}{hint}"

    figure_ok = True
    if isinstance(ledger, dict):
        figs = ledger.get("figure_registry") or []
        if not isinstance(figs, list) or len(figs) == 0:
            figure_ok = False
            _check(checks, "facts_ledger figure_registry non-empty", False, details_fail="figure_registry missing/empty")
        else:
            for idx, fig in enumerate(figs):
                if not isinstance(fig, dict):
                    figure_ok = False
                    continue
                art = fig.get("artifacts") or {}
                # mmd is required (editable source). image is required for docx embed.
                for key in ("mmd", "image"):
                    rel = art.get(key) or ""
                    miss = _figure_missing(rel) if rel else f"figure[{idx}].{key}_missing"
                    if miss:
                        figure_ok = False
                        missing.append(miss)
                # editable/drawio is optional; mmd is the editable source

            _check(checks, "figure artifacts complete in deliver dir (mmd+image)", figure_ok,
                   details_ok="ok", details_fail="missing figure artifacts in deliver dir")
    else:
        figure_ok = False

    passed = all(c["result"] == "pass" for c in checks)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    report = {
        "doc_type": "delivery_health_report",
        "phase": "phase_11",
        "generatedAt": now.isoformat(),
        "deliver_dir": str(deliver_dir.resolve()),
        "final_docx_path": str(final_docx.resolve()),
        "checks": checks,
        "pass_fail": "pass" if passed else "fail",
        "missing_items": sorted(set(missing)),
    }

    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
