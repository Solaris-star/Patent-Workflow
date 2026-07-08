#!/usr/bin/env python3
"""Run patent-workflow gate validators for a given phase and emit a concise JSON summary.

Design goals:
- Very small dependency surface (stdlib only)
- Works with fixed artifact paths (A-mode)
- Produces audit-friendly output
- Optionally patches a markdown run manifest by replacing the JSON block between markers

Usage examples:
  python run_phase_gates.py --phase 2 --workspace .
  python run_phase_gates.py --phase 4 --workspace .
  python run_phase_gates.py --phase 7 --workspace .
  python run_phase_gates.py --phase 10 --workspace .
  python run_phase_gates.py --phase 11 --workspace . --deliver-dir <dir> --patent-title <title>

Patch run manifest (A-mode):
  python run_phase_gates.py --phase 4 --workspace . --manifest artifacts/run_manifest.md

Run all phases (skips phase 11 unless deliver args provided):
  python run_phase_gates.py --phase all --workspace . --manifest artifacts/run_manifest.md

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


JSON_BEGIN = "<!-- GATE_RESULTS_JSON_BEGIN -->"
JSON_END = "<!-- GATE_RESULTS_JSON_END -->"


def _run(cmd: list[str]) -> dict:
    started = datetime.now(timezone.utc)
    try:
        # Force UTF-8 to avoid mojibake in captured logs on Windows.
        # Also ensure we run a UTF-8 mode Python even if host default is cp936.
        if cmd and cmd[0] == "python":
            cmd = [sys.executable, *cmd[1:]]

        try:
            import os

            env = {**os.environ, **{"PYTHONUTF8": "1"}}
        except Exception:
            env = {"PYTHONUTF8": "1"}

        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        out = (p.stdout or "").strip()
        err = (p.stderr or "").strip()
        return {
            "cmd": cmd,
            "exitCode": p.returncode,
            "stdout": out,
            "stderr": err,
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
    """Replace the JSON code block between markers.

    If markers are missing, append a new block at the end.
    """
    text = manifest_path.read_text(encoding="utf-8") if manifest_path.exists() else ""

    block = (
        f"{JSON_BEGIN}\n"
        "```json\n"
        f"{summary_json}\n"
        "```\n"
        f"{JSON_END}\n"
    )

    if JSON_BEGIN in text and JSON_END in text:
        pre = text.split(JSON_BEGIN, 1)[0]
        post = text.split(JSON_END, 1)[1]
        new_text = pre + block + post.lstrip("\r\n")
    else:
        sep = "\n" if text and not text.endswith("\n") else ""
        new_text = text + sep + "\n" + block

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(new_text, encoding="utf-8")


def _scripts_dir(ws: Path) -> Path:
    return ws / "skills" / "patent-workflow" / "scripts"


def _artifact_paths(ws: Path) -> dict:
    return {
        "research_pack": ws / "artifacts" / "research" / "phase_02_research_pack.json",
        "candidate_pool": ws / "artifacts" / "prior_art" / "phase_04_patent_candidate_pool.json",
        "evidence_pack": ws / "artifacts" / "prior_art" / "phase_04_evidence_pack.json",
        "facts_ledger": ws / "artifacts" / "draft" / "facts_ledger.json",
        "edit_plan": ws / "artifacts" / "revision" / "phase_10_edit_plan.json",
        "structured_diff": ws / "artifacts" / "revision" / "phase_10_structured_diff.json",
        "consistency_report": ws / "artifacts" / "audit" / "phase_08_consistency_audit_report.md",
        "ipr_report": ws / "artifacts" / "audit" / "phase_09_ipr_review_report.md",
        "health_report": ws / "artifacts" / "delivery" / "phase_11_delivery_health_report.json",
    }


def _run_phase(phase: int, ws: Path, deliver_dir: str | None, patent_title: str | None) -> list[dict]:
    scripts = _scripts_dir(ws)
    ap = _artifact_paths(ws)
    runs: list[dict] = []

    if phase == 2:
        runs.append(_run(["python", str(scripts / "validate_research_pack.py"), str(ap["research_pack"])]))

    elif phase == 4:
        # Optional domain-aware scoring profile for relevance gating.
        # Default behavior remains legacy unless manifest clearly indicates plan/constraint/conflict.
        profile = None
        if (ws / "artifacts" / "run_manifest.md").exists():
            try:
                txt = (ws / "artifacts" / "run_manifest.md").read_text(encoding="utf-8", errors="replace")
                if "项目计划" in txt and ("约束" in txt or "冲突" in txt or "修复" in txt):
                    profile = "ai_project_plan_constraints"
            except Exception:
                profile = None

        cmd = ["python", str(scripts / "validate_patent_candidates.py"), str(ap["candidate_pool"])]
        if profile:
            cmd += ["--profile", profile]
        runs.append(_run(cmd))
        runs.append(_run(["python", str(scripts / "validate_evidence_pack.py"), str(ap["evidence_pack"])]))

    elif phase == 7:
        runs.append(
            _run(
                [
                    "python",
                    str(scripts / "validate_facts_ledger.py"),
                    str(ap["facts_ledger"]),
                    "--base-dir",
                    str(ws),
                    "--require-docx-visible-mermaid",
                ]
            )
        )

    elif phase == 10:
        runs.append(_run(["python", str(scripts / "validate_edit_plan.py"), str(ap["edit_plan"])]))
        runs.append(
            _run(
                [
                    "python",
                    str(scripts / "validate_structured_diff.py"),
                    str(ap["structured_diff"]),
                    "--edit-plan",
                    str(ap["edit_plan"]),
                ]
            )
        )

    elif phase == 11:
        if not deliver_dir or not patent_title:
            # skip phase 11 when running "all" unless args provided
            return []
        runs.append(
            _run(
                [
                    "python",
                    str(scripts / "health_check_delivery_package.py"),
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
    ap = argparse.ArgumentParser(description="Run patent-workflow phase gate validators")
    ap.add_argument("--phase", required=True, help="2|4|7|10|11|all")
    ap.add_argument("--workspace", default=".", help="Workspace root (base dir)")

    # phase 11 extras
    ap.add_argument("--deliver-dir", help="Delivery dir (phase 11)")
    ap.add_argument("--patent-title", help="Final patent title (phase 11)")

    ap.add_argument("--out", help="Optional output path for JSON summary")
    ap.add_argument("--manifest", help="Optional markdown run manifest path to patch JSON block")
    args = ap.parse_args()

    ws = Path(args.workspace)

    phases: list[int]
    if args.phase == "all":
        phases = [2, 4, 7, 10, 11]
    else:
        try:
            phases = [int(args.phase)]
        except ValueError:
            raise SystemExit("--phase must be one of: 2,4,7,10,11,all")

    all_runs: list[dict] = []
    phase_results: list[dict] = []

    for p in phases:
        # Cold-start hard gate: output_dir must be explicitly set by user in run manifest.
        # Apply this before phase 11 (delivery) and also when running all phases.
        if args.manifest and p == 11:
            check = _run(["python", str(_scripts_dir(ws) / "assert_output_dir_in_manifest.py"), args.manifest])
            phase_results.append({"phase": "manifest_output_dir_check", "skipped": False, "passed": check.get("passed"), "runs": [check]})
            all_runs.append(check)
            if not check.get("passed"):
                break

        runs = _run_phase(p, ws, args.deliver_dir, args.patent_title)
        # if skipped (phase 11 without args), record as skipped
        if p == 11 and not runs and args.phase == "all":
            phase_results.append({"phase": 11, "skipped": True, "reason": "missing --deliver-dir/--patent-title"})
            continue

        p_passed = all(r.get("passed") for r in runs) if runs else False
        phase_results.append({"phase": p, "skipped": False, "passed": p_passed, "runs": runs})
        all_runs.extend(runs)

        # fail-fast
        if not p_passed:
            break

    passed = all(r.get("passed") for r in all_runs) if all_runs else False

    summary = {
        "runner": "run_phase_gates.py",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "workspace": str(ws.resolve()),
        "phase": args.phase,
        "passed": passed,
        "phaseResults": phase_results,
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
