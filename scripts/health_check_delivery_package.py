#!/usr/bin/env python3
"""Phase 9 delivery health gate for patent-workflow.

This script checks deliverable completeness and writes a health report JSON.

Usage (simple):
  python health_check_delivery_package.py \
    --deliver-dir <dir> \
    --patent-title "<专利标题>" \
    --facts-ledger artifacts/draft/facts_ledger.json \
    --consistency-report artifacts/audit/phase_06_consistency_audit_report.md \
    --ipr-report artifacts/audit/phase_07_ipr_review_report.md \
    --out artifacts/delivery/phase_09_delivery_health_report.json

Exit codes:
  0 = pass
  2 = fail
"""

import argparse
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path


def _check(checks: list[dict], name: str, cond: bool, details_ok: str = "", details_fail: str = ""):
    checks.append({
        "name": name,
        "result": "pass" if cond else "fail",
        "details": details_ok if cond else details_fail,
    })


def _exists(p) -> bool:
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


def _resolve_artifact_path(rel_or_abs: str, base_dir: Path) -> Path:
    p = Path(rel_or_abs)
    return p if p.is_absolute() else (base_dir / p)


def _root_docx_files(deliver_dir: Path) -> list[Path]:
    if not deliver_dir.exists():
        return []
    return sorted(p for p in deliver_dir.glob("*.docx") if p.is_file())


def main() -> int:
    ap = argparse.ArgumentParser(description="Delivery health gate (phase 9)")
    ap.add_argument("--deliver-dir", required=True, help="Delivery directory (root containing final docx and figures dir)")
    ap.add_argument("--patent-title", required=True, help="Final patent title (used for filename check)")
    ap.add_argument("--facts-ledger", required=True, help="Path to facts_ledger.json")
    ap.add_argument("--consistency-report", required=True, help="Path to phase_06 consistency report")
    ap.add_argument("--ipr-report", required=True, help="Path to phase_07 ipr report")
    ap.add_argument("--out", default="artifacts/delivery/phase_09_delivery_health_report.json", help="Output report JSON path")
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

    root_docx_files = _root_docx_files(deliver_dir)
    extra_docx_files = [p for p in root_docx_files if p.name != expected_name]
    _check(
        checks,
        "delivery root contains only final docx",
        final_docx.exists() and len(root_docx_files) == 1 and not extra_docx_files,
        details_ok=expected_name,
        details_fail="extra or missing root docx: " + ", ".join(p.name for p in root_docx_files),
    )
    missing.extend(str(p) for p in extra_docx_files)

    # mmd-only figure delivery check: Mermaid source is embedded in document text, image media is optional.
    final_md = final_docx.with_suffix(".md")
    md_text = final_md.read_text(encoding="utf-8", errors="ignore") if final_md.exists() else ""
    _check(
        checks,
        "figure Mermaid source embedded in 附图说明",
        "```mermaid" in md_text and "附图说明" in md_text,
        details_ok="Mermaid source found in markdown copy",
        details_fail="Mermaid source not found in markdown copy",
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
                mmd = art.get("mmd") or ""
                mmd_p = _resolve_artifact_path(mmd, base_dir)
                if not mmd or not mmd_p.exists():
                    figure_ok = False
                    missing.append(str(mmd_p) if mmd else f"figure[{idx}].mmd_missing")
                if fig.get("mermaid_source_embedded_in_docx") is not True:
                    figure_ok = False
                    missing.append(f"figure[{idx}].embedded_mermaid_flag_missing")

            _check(checks, "figure artifacts complete (mmd embedded mode)", figure_ok, details_ok="ok", details_fail="missing mmd figure artifacts")
    else:
        figure_ok = False

    passed = all(c["result"] == "pass" for c in checks)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    report = {
        "doc_type": "delivery_health_report",
        "phase": "phase_9",
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
