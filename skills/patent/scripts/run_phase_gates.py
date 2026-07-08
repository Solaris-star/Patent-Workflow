#!/usr/bin/env python3
"""Run patent gate validators for a given gate and emit a concise JSON summary.

Gates (semantic names):
  research   -> validate_research_pack
  prior-art  -> validate_patent_candidates (+ optional relevance_terms.json) + validate_evidence_pack
  draft      -> validate_facts_ledger
  review     -> validate_edit_plan + validate_structured_diff
  deliver    -> assert_output_dir_in_manifest + health_check_delivery_package
  all        -> research, prior-art, draft, review, deliver (deliver skipped unless args provided)

Design goals:
- stdlib only; works from ANY working directory (validators self-locate next to this file)
- fixed artifact paths under <workspace>/artifacts/
- audit-friendly JSON output; optionally patches run manifest JSON block

Usage examples:
  python run_phase_gates.py --gate research  --workspace . --manifest artifacts/run_manifest.md
  python run_phase_gates.py --gate prior-art --workspace . --manifest artifacts/run_manifest.md
  python run_phase_gates.py --gate deliver   --workspace . --deliver-dir <dir> --patent-title <title> --manifest artifacts/run_manifest.md
  python run_phase_gates.py --gate all       --workspace . --manifest artifacts/run_manifest.md

Exit codes:
  0 = all gates passed
  2 = any gate failed
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent

JSON_BEGIN = "<!-- GATE_RESULTS_JSON_BEGIN -->"
JSON_END = "<!-- GATE_RESULTS_JSON_END -->"

GATE_ORDER = ["research", "prior-art", "draft", "review", "deliver"]


def _run(cmd: list[str]) -> dict:
    started = datetime.now(timezone.utc)
    try:
        # Force UTF-8 to avoid mojibake on Windows hosts defaulting to cp936.
        if cmd and cmd[0] == "python":
            cmd = [sys.executable, *cmd[1:]]

        import os

        env = {**os.environ, "PYTHONUTF8": "1"}

        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        return {
            "cmd": cmd,
            "exitCode": p.returncode,
            "stdout": (p.stdout or "").strip(),
            "stderr": (p.stderr or "").strip(),
            "startedAt": started.isoformat(),
            "finishedAt": datetime.now(timezone.utc).isoformat(),
            "passed": p.returncode == 0,
        }
    except Exception as e:
        return {
            "cmd": cmd,
            "exitCode": 99,
            "stdout": "",
            "stderr": str(e),
            "startedAt": started.isoformat(),
            "finishedAt": datetime.now(timezone.utc).isoformat(),
            "passed": False,
        }


def _patch_manifest(manifest_path: Path, summary_json: str) -> None:
    """Replace the JSON code block between markers; append if markers missing."""
    text = manifest_path.read_text(encoding="utf-8") if manifest_path.exists() else ""

    block = f"{JSON_BEGIN}\n```json\n{summary_json}\n```\n{JSON_END}\n"

    if JSON_BEGIN in text and JSON_END in text:
        pre = text.split(JSON_BEGIN, 1)[0]
        post = text.split(JSON_END, 1)[1]
        new_text = pre + block + post.lstrip("\r\n")
    else:
        sep = "\n" if text and not text.endswith("\n") else ""
        new_text = text + sep + "\n" + block

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(new_text, encoding="utf-8")


def _artifact_paths(ws: Path) -> dict:
    return {
        "research_pack": ws / "artifacts" / "research" / "phase_02_research_pack.json",
        "candidate_pool": ws / "artifacts" / "prior_art" / "phase_04_patent_candidate_pool.json",
        "evidence_pack": ws / "artifacts" / "prior_art" / "phase_04_evidence_pack.json",
        "relevance_terms": ws / "artifacts" / "prior_art" / "relevance_terms.json",
        "facts_ledger": ws / "artifacts" / "draft" / "facts_ledger.json",
        "edit_plan": ws / "artifacts" / "revision" / "phase_10_edit_plan.json",
        "structured_diff": ws / "artifacts" / "revision" / "phase_10_structured_diff.json",
        "consistency_report": ws / "artifacts" / "audit" / "phase_08_consistency_audit_report.md",
        "ipr_report": ws / "artifacts" / "audit" / "phase_09_ipr_review_report.md",
        "health_report": ws / "artifacts" / "delivery" / "phase_11_delivery_health_report.json",
    }


def _run_gate(gate: str, ws: Path, deliver_dir: str | None, patent_title: str | None, manifest: str | None) -> list[dict]:
    ap = _artifact_paths(ws)
    runs: list[dict] = []

    if gate == "research":
        runs.append(_run(["python", str(SCRIPTS_DIR / "validate_research_pack.py"), str(ap["research_pack"])]))

    elif gate == "prior-art":
        cmd = ["python", str(SCRIPTS_DIR / "validate_patent_candidates.py"), str(ap["candidate_pool"])]
        # Domain-adaptive scoring terms written by patent-prior-art skill; falls back to built-in legacy profile.
        if ap["relevance_terms"].exists():
            cmd += ["--terms-file", str(ap["relevance_terms"])]
        runs.append(_run(cmd))
        runs.append(_run(["python", str(SCRIPTS_DIR / "validate_evidence_pack.py"), str(ap["evidence_pack"])]))

    elif gate == "draft":
        runs.append(
            _run(
                [
                    "python",
                    str(SCRIPTS_DIR / "validate_facts_ledger.py"),
                    str(ap["facts_ledger"]),
                    "--base-dir",
                    str(ws),
                    "--require-docx-visible-mermaid",
                ]
            )
        )

    elif gate == "review":
        runs.append(_run(["python", str(SCRIPTS_DIR / "validate_edit_plan.py"), str(ap["edit_plan"])]))
        runs.append(
            _run(
                [
                    "python",
                    str(SCRIPTS_DIR / "validate_structured_diff.py"),
                    str(ap["structured_diff"]),
                    "--edit-plan",
                    str(ap["edit_plan"]),
                ]
            )
        )

    elif gate == "deliver":
        if not deliver_dir or not patent_title:
            return []
        if manifest:
            runs.append(_run(["python", str(SCRIPTS_DIR / "assert_output_dir_in_manifest.py"), manifest]))
        runs.append(
            _run(
                [
                    "python",
                    str(SCRIPTS_DIR / "health_check_delivery_package.py"),
                    "--deliver-dir",
                    deliver_dir,
                    "--patent-title",
                    patent_title,
                    "--facts-ledger",
                    str(ap["facts_ledger"]),
                    "--consistency-report",
                    str(ap["consistency_report"]),
                    "--ipr-report",
                    str(ap["ipr_report"]),
                    "--out",
                    str(ap["health_report"]),
                    "--base-dir",
                    str(ws),
                ]
            )
        )

    return runs


def main() -> int:
    ap = argparse.ArgumentParser(description="Run patent gate validators")
    ap.add_argument("--gate", required=True, choices=[*GATE_ORDER, "all"], help="research|prior-art|draft|review|deliver|all")
    ap.add_argument("--workspace", default=".", help="Workspace root (base dir)")

    # deliver gate extras
    ap.add_argument("--deliver-dir", help="Delivery dir (deliver gate)")
    ap.add_argument("--patent-title", help="Final patent title (deliver gate)")

    ap.add_argument("--out", help="Optional output path for JSON summary")
    ap.add_argument("--manifest", help="Optional markdown run manifest path to patch JSON block")
    args = ap.parse_args()

    ws = Path(args.workspace)
    gates = GATE_ORDER if args.gate == "all" else [args.gate]

    all_runs: list[dict] = []
    gate_results: list[dict] = []

    for g in gates:
        runs = _run_gate(g, ws, args.deliver_dir, args.patent_title, args.manifest)

        if g == "deliver" and not runs and args.gate == "all":
            gate_results.append({"gate": g, "skipped": True, "reason": "missing --deliver-dir/--patent-title"})
            continue

        g_passed = all(r.get("passed") for r in runs) if runs else False
        gate_results.append({"gate": g, "skipped": False, "passed": g_passed, "runs": runs})
        all_runs.extend(runs)

        if not g_passed:
            break  # fail-fast

    passed = all(r.get("passed") for r in all_runs) if all_runs else False

    summary = {
        "runner": "run_phase_gates.py",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "workspace": str(ws.resolve()),
        "gate": args.gate,
        "passed": passed,
        "gateResults": gate_results,
    }

    summary_json = json.dumps(summary, ensure_ascii=False, indent=2)

    if args.manifest:
        _patch_manifest(Path(args.manifest), summary_json)

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(summary_json, encoding="utf-8")
    else:
        print(summary_json)

    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
