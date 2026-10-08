#!/usr/bin/env python3
"""Run patent workflow validators and report checks separately from completion."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from workflow_common import (
    MODE_GATES,
    atomic_write_text,
    is_within,
    manifest_field_text,
    read_workflow_state,
    update_manifest_state,
)
from workflow_cli import _workspace_operation_lock

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass

SCRIPTS_DIR = Path(__file__).resolve().parent
JSON_BEGIN = "<!-- GATE_RESULTS_JSON_BEGIN -->"
JSON_END = "<!-- GATE_RESULTS_JSON_END -->"
GATE_ORDER = ["research", "prior-art", "draft", "review", "deliver"]


def _run(cmd: list[str]) -> dict:
    started = datetime.now(timezone.utc)
    if cmd and cmd[0] == "python":
        cmd = [sys.executable, *cmd[1:]]
    env = {**os.environ, "PYTHONUTF8": "1"}
    try:
        process = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        return {
            "cmd": cmd,
            "exitCode": process.returncode,
            "stdout": (process.stdout or "").strip(),
            "stderr": (process.stderr or "").strip(),
            "startedAt": started.isoformat(),
            "finishedAt": datetime.now(timezone.utc).isoformat(),
            "passed": process.returncode == 0,
            "checks_passed": process.returncode == 0,
            "workflow_complete": _load_result({"stdout": (process.stdout or "").strip()}).get(
                "workflow_complete", process.returncode == 0
            ),
            "not_run": _load_result({"stdout": (process.stdout or "").strip()}).get("not_run", []),
            "skipped": _load_result({"stdout": (process.stdout or "").strip()}).get("skipped", []),
        }
    except Exception:
        return {
            "cmd": cmd,
            "exitCode": 99,
            "stdout": "",
            "stderr": "validator could not be started",
            "startedAt": started.isoformat(),
            "finishedAt": datetime.now(timezone.utc).isoformat(),
            "passed": False,
            "checks_passed": False,
        }


def _policy_fail(name: str, message: str) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "cmd": ["<policy>", name],
        "exitCode": 2,
        "stdout": "",
        "stderr": message,
        "startedAt": now,
        "finishedAt": now,
        "passed": False,
        "checks_passed": False,
    }


def _load_result(run: dict) -> dict:
    try:
        value = json.loads(run.get("stdout", ""))
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _field(manifest: str | None, key: str) -> str | None:
    if not manifest:
        return None
    path = Path(manifest)
    if not path.is_file():
        return None
    return manifest_field_text(path.read_text(encoding="utf-8"), key)


def _same_selected_path(selected: str, declared: str, workspace: Path) -> bool:
    def key(value: str) -> str:
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = workspace / path
        return os.path.normcase(os.path.abspath(os.fspath(path)))

    return key(selected) == key(declared)


def _artifact_paths(workspace: Path) -> dict[str, Path]:
    artifacts = workspace / "artifacts"
    return {
        "research_pack": artifacts / "research" / "phase_02_research_pack.json",
        "candidate_pool": artifacts / "prior_art" / "phase_04_patent_candidate_pool.json",
        "evidence_pack": artifacts / "prior_art" / "phase_04_evidence_pack.json",
        "background_pack": artifacts / "prior_art" / "phase_05_background_pack.json",
        "ipr_pack": artifacts / "prior_art" / "phase_05_ipr_pack.json",
        "relevance_terms": artifacts / "prior_art" / "relevance_terms.json",
        "facts_ledger": artifacts / "draft" / "facts_ledger.json",
        "edit_plan": artifacts / "revision" / "phase_10_edit_plan.json",
        "structured_diff": artifacts / "revision" / "phase_10_structured_diff.json",
        "review_status": artifacts / "audit" / "review_status.json",
        "consistency_report": artifacts / "audit" / "phase_08_consistency_audit_report.md",
        "ipr_report": artifacts / "audit" / "phase_09_ipr_review_report.md",
        "health_report": artifacts / "delivery" / "phase_11_delivery_health_report.json",
    }


def _run_gate(
    gate: str,
    workspace: Path,
    deliver_dir: str | None,
    patent_title: str | None,
    final_markdown: str | None,
    manifest: str | None,
    sensitive_map: str | None,
) -> tuple[list[dict], str | None, dict]:
    paths = _artifact_paths(workspace)
    runs: list[dict] = []
    details: dict = {}
    if gate == "research":
        if manifest:
            origin = _field(manifest, "research_origin")
            lineage = _field(manifest, "vault_direction_origin")
            declared = _field(manifest, "sensitive_map_path")
            if origin == "mine" or lineage == "mine":
                if not declared:
                    runs.append(_policy_fail(
                        "mine-run-missing-sensitive-map-declaration",
                        "mine lineage requires a confirmed sensitive-map declaration",
                    ))
                elif not sensitive_map:
                    runs.append(_policy_fail(
                        "mine-run-sensitive-map-not-selected-for-check",
                        "reselect the manifest-referenced sensitive map for this research check",
                    ))
                elif not _same_selected_path(sensitive_map, declared, workspace):
                    runs.append(_policy_fail(
                        "mine-run-sensitive-map-selection-mismatch",
                        "the selected sensitive map does not match the run manifest reference",
                    ))
                else:
                    declared_path = Path(sensitive_map).expanduser()
                    if not declared_path.is_absolute():
                        declared_path = workspace / declared_path
                    declared_path = declared_path.resolve()
                    if not declared_path.is_file():
                        runs.append(_policy_fail(
                            "mine-run-sensitive-map-not-found",
                            "selected sensitive map was not found",
                        ))
                    else:
                        runs.append(_run([
                            "python", str(SCRIPTS_DIR / "validate_sanitize.py"),
                            "--map", str(declared_path), "--validate-only",
                        ]))
            elif sensitive_map:
                if declared and not _same_selected_path(sensitive_map, declared, workspace):
                    runs.append(_policy_fail(
                        "sensitive-map-selection-mismatch",
                        "the selected sensitive map does not match the run manifest reference",
                    ))
                else:
                    runs.append(_run([
                        "python", str(SCRIPTS_DIR / "validate_sanitize.py"),
                        "--map", sensitive_map, "--validate-only",
                    ]))
        runs.append(_run([
            "python", str(SCRIPTS_DIR / "validate_research_pack.py"),
            str(paths["research_pack"]),
        ]))

    elif gate == "prior-art":
        candidate_cmd = [
            "python", str(SCRIPTS_DIR / "validate_patent_candidates.py"),
            str(paths["candidate_pool"]), "--min-count", "0",
        ]
        if paths["relevance_terms"].is_file():
            candidate_cmd += ["--terms-file", str(paths["relevance_terms"])]
        runs.append(_run(candidate_cmd))
        runs.append(_run([
            "python", str(SCRIPTS_DIR / "validate_evidence_pack.py"),
            str(paths["evidence_pack"]),
        ]))
        runs.append(_run([
            "python", str(SCRIPTS_DIR / "validate_background_pack.py"),
            str(paths["background_pack"]), "--evidence-pack", str(paths["evidence_pack"]),
        ]))
        ipr_requested = (_field(manifest, "ipr_requested") or "false").casefold() == "true"
        details["ipr_requested"] = ipr_requested
        if ipr_requested:
            runs.append(_run([
                "python", str(SCRIPTS_DIR / "validate_ipr_pack.py"),
                str(paths["ipr_pack"]), "--evidence-pack", str(paths["evidence_pack"]),
                "--ipr-requested",
            ]))
        else:
            details["ipr_pack"] = {"status": "not_requested"}

    elif gate == "draft":
        runs.append(_run([
            "python", str(SCRIPTS_DIR / "validate_facts_ledger.py"),
            str(paths["facts_ledger"]),
            "--base-dir", str(workspace),
            "--evidence-pack", str(paths["evidence_pack"]),
            "--require-main-parts",
            "--require-docx-visible-mermaid",
            "--check-draft-format",
        ]))

    elif gate == "review":
        revision_requested = paths["edit_plan"].exists() or paths["structured_diff"].exists()
        details["revision_validation"] = "requested" if revision_requested else "not_required"
        details["revision_skip_reason"] = (
            None if revision_requested else "no authorized modification was commissioned"
        )
        runs.append(_run([
            "python", str(SCRIPTS_DIR / "validate_review_status.py"),
            str(paths["review_status"]), "--workspace", str(workspace),
            *(["--output-dir", _field(manifest, "output_dir")] if manifest and _field(manifest, "output_dir") else []),
            *(["--require-revision"] if revision_requested else []),
        ]))
        if revision_requested:
            if not paths["edit_plan"].exists() or not paths["structured_diff"].exists():
                runs.append(_policy_fail(
                    "incomplete-revision-artifacts",
                    "authorized revision requires both edit_plan and structured_diff",
                ))
            else:
                runs.append(_run([
                    "python", str(SCRIPTS_DIR / "validate_edit_plan.py"),
                    str(paths["edit_plan"]), "--review-status", str(paths["review_status"]),
                ]))
                runs.append(_run([
                    "python", str(SCRIPTS_DIR / "validate_structured_diff.py"),
                    str(paths["structured_diff"]), "--edit-plan", str(paths["edit_plan"]),
                ]))

    elif gate == "deliver":
        if not final_markdown and manifest and deliver_dir:
            declared_markdown = _field(manifest, "final_markdown_path")
            if declared_markdown:
                raw_path = Path(declared_markdown).expanduser()
                if not raw_path.is_absolute():
                    raw_path = workspace / raw_path
                candidate = raw_path.resolve()
                raw_delivery = Path(deliver_dir).expanduser() if deliver_dir else None
                delivery_root = raw_delivery if raw_delivery and raw_delivery.is_absolute() else (
                    workspace / raw_delivery if raw_delivery else None
                )
                delivery_root = delivery_root.resolve() if delivery_root else None
                if not delivery_root or not is_within(candidate, delivery_root):
                    return [_policy_fail(
                        "final-markdown-outside-delivery-directory",
                        "manifest final_markdown_path must resolve inside the configured delivery directory",
                    )], None, details
                final_markdown = str(candidate)
        if not deliver_dir or not patent_title or not final_markdown:
            return [], "deliver requires --deliver-dir, --patent-title, and --final-markdown", details
        if manifest:
            runs.append(_run([
                "python", str(SCRIPTS_DIR / "assert_output_dir_in_manifest.py"),
                manifest, "--expected-dir", deliver_dir,
            ]))
        declared = _field(manifest, "sensitive_map_path")
        if sensitive_map:
            if declared and not _same_selected_path(sensitive_map, declared, workspace):
                runs.append(_policy_fail(
                    "sensitive-map-selection-mismatch",
                    "the selected sensitive map does not match the run manifest reference",
                ))
            else:
                runs.append(_run([
                    "python", str(SCRIPTS_DIR / "validate_sanitize.py"),
                    "--map", sensitive_map, "--scan-dir", deliver_dir,
                ]))
        elif declared:
            runs.append(_policy_fail(
                "sensitive-map-declared-but-not-checked",
                "reselect the manifest-referenced sensitive map for this delivery check",
            ))
        mode = _field(manifest, "figure_delivery_mode") or "mermaid_only"
        runs.append(_run([
            "python", str(SCRIPTS_DIR / "health_check_delivery_package.py"),
            "--deliver-dir", deliver_dir,
            "--patent-title", patent_title,
            "--final-markdown", final_markdown,
            "--facts-ledger", str(paths["facts_ledger"]),
            "--consistency-report", str(paths["consistency_report"]),
            "--ipr-report", str(paths["ipr_report"]),
            "--review-status", str(paths["review_status"]),
            "--manifest", manifest or "",
            "--figure-delivery-mode", mode,
            "--out", str(paths["health_report"]),
            "--base-dir", str(workspace),
        ]))
    return runs, None, details


def build_summary(
    selected_gate: str,
    gate_results: list[dict],
    review_completed: bool,
    revision_validation: str,
    workspace: Path,
    *,
    required_gates: list[str] | None = None,
    workflow_mode: str | None = None,
    run_id: str | None = None,
) -> dict:
    all_runs = [run for result in gate_results for run in result.get("runs", [])]
    checks_passed = bool(all_runs) and all(run.get("passed") is True for run in all_runs)
    skipped = [
        result["gate"] for result in gate_results
        if result.get("status") == "skipped"
    ]
    not_run = sorted({
        item
        for result in gate_results
        for item in (
            ([result["gate"]] if result.get("status") == "not_run" else [])
            + [str(value) for run in result.get("runs", []) for value in run.get("not_run", [])]
        )
    })
    if any(
        result.get("gate") == "review"
        and isinstance(result.get("revision_validation"), str)
        and result.get("revision_validation") in {"pending", "not_run"}
        for result in gate_results
    ):
        not_run.append("review:revision_validation")
    skipped.extend(
        f"{result['gate']}:{value}"
        for result in gate_results
        for run in result.get("runs", [])
        for value in run.get("skipped", [])
    )
    if any(result.get("revision_validation") == "not_required" for result in gate_results):
        skipped.append("review:revision_validation")
    required_skips = [item for item in skipped if item != "review:revision_validation"]
    seen_gates = [str(result.get("gate", "")) for result in gate_results]
    expected_gate_sequence = required_gates or seen_gates
    workflow_complete = (
        selected_gate == "all"
        and bool(gate_results)
        and seen_gates == expected_gate_sequence
        and all(result.get("status") == "passed" for result in gate_results)
        and all(all(run.get("workflow_complete", True) is True for run in result.get("runs", [])) for result in gate_results)
        and review_completed
        and not not_run
        and not required_skips
    )
    return {
        "runner": "run_phase_gates.py",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "workspace": str(workspace.resolve()),
        "workflow_mode": workflow_mode,
        "run_id": run_id,
        "required_gates": expected_gate_sequence if selected_gate == "all" else [],
        "gate": selected_gate,
        "passed": checks_passed,
        "checks_passed": checks_passed,
        "workflow_complete": workflow_complete,
        "review_completed": review_completed,
        "revision_validation": revision_validation,
        "skipped": skipped,
        "not_run": sorted(set(not_run)),
        "gateResults": gate_results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run patent workflow validators")
    parser.add_argument("--gate", required=True, choices=[*GATE_ORDER, "all"])
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--deliver-dir")
    parser.add_argument("--patent-title")
    parser.add_argument("--final-markdown")
    parser.add_argument("--sensitive-map", help="Explicitly reselected sensitive-map path; read in place without copying")
    parser.add_argument("--out")
    parser.add_argument("--manifest")
    parser.add_argument("--run-id")
    parser.add_argument("--_workflow-cli-lock-held", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    if args._workflow_cli_lock_held:
        return _run_with_args(args, parser)
    with _workspace_operation_lock(Path(args.workspace).expanduser().resolve()):
        return _run_with_args(args, parser)


def _run_with_args(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:

    workspace = Path(args.workspace)
    manifest_path = Path(args.manifest).resolve() if args.manifest else None
    manifest_text = manifest_path.read_text(encoding="utf-8") if manifest_path and manifest_path.is_file() else ""
    field_mode = _field(str(manifest_path), "workflow_mode") if manifest_path else None
    manifest_state = read_workflow_state(manifest_text)
    state_mode = manifest_state.get("workflow_mode")
    if field_mode and isinstance(state_mode, str) and state_mode != field_mode:
        parser.error("manifest workflow_mode differs from checkpoint; reconcile with workflow_cli.py resume --mode")
    workflow_mode = field_mode or (state_mode if isinstance(state_mode, str) else None) or "full_research"
    if workflow_mode not in MODE_GATES:
        parser.error("manifest workflow_mode must be full_research, titled_evidence, or draft_review")
    required_gates = [gate for gate, _stage in MODE_GATES[workflow_mode]]
    if args.gate != "all" and args.gate not in required_gates:
        parser.error(f"gate {args.gate!r} is not part of workflow mode {workflow_mode!r}")
    gates = required_gates if args.gate == "all" else [args.gate]
    results: list[dict] = []
    halted = False
    review_completed = False
    revision_validation = "not_run"
    for gate in gates:
        if halted:
            results.append({
                "gate": gate, "status": "not_run", "passed": False,
                "checks_passed": False, "not_run": True, "runs": [],
                "reason": "a previous required gate failed",
            })
            continue
        runs, skip_reason, details = _run_gate(
            gate, workspace, args.deliver_dir, args.patent_title,
            args.final_markdown, args.manifest, args.sensitive_map,
        )
        if skip_reason:
            if gate == "deliver" and args.gate != "all":
                runs = [_policy_fail("deliver-gate-missing-args", skip_reason)]
            else:
                results.append({
                    "gate": gate, "status": "skipped", "passed": False,
                    "checks_passed": False, "skipped": True, "runs": [],
                    "reason": skip_reason, **details,
                })
                continue
        gate_passed = bool(runs) and all(run.get("checks_passed", run.get("passed") is True) is True for run in runs)
        entry = {
            "gate": gate,
            "status": "passed" if gate_passed else "failed",
            "passed": gate_passed,
            "checks_passed": gate_passed,
            "workflow_complete": gate_passed and all(run.get("workflow_complete", True) is True for run in runs),
            "skipped": False,
            "not_run": False,
            "runs": runs,
            **details,
        }
        results.append(entry)
        if gate == "review":
            status = _load_result(runs[0]) if runs else {}
            review_completed = status.get("review_completed") is True and gate_passed
            revision_validation = status.get(
                "revision_validation", details.get("revision_validation", "not_run")
            )
            if revision_validation == "requested":
                revision_validation = "passed" if gate_passed else "failed"
            if details.get("revision_validation") == "not_required" and revision_validation == "passed":
                runs.append(_policy_fail(
                    "revision-validation-without-authorized-artifacts",
                    "review status reports a passed revision but edit_plan and structured_diff are missing",
                ))
                gate_passed = False
                revision_validation = "failed"
                entry["status"] = "failed"
                entry["passed"] = False
                entry["checks_passed"] = False
                entry["workflow_complete"] = False
                entry["runs"] = runs
            entry["review_completed"] = review_completed
            entry["revision_validation"] = revision_validation
        if not gate_passed or not entry["workflow_complete"]:
            halted = True

    summary = build_summary(
        args.gate, results, review_completed, revision_validation, workspace,
        required_gates=required_gates if args.gate == "all" else None,
        workflow_mode=workflow_mode,
        run_id=args.run_id,
    )
    summary_json = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.manifest and Path(args.manifest).is_file():
        manifest_path = Path(args.manifest)
        current = manifest_path.read_text(encoding="utf-8")
        fence = chr(96) * 3
        block = f"{JSON_BEGIN}\n{fence}json\n{summary_json}\n{fence}\n{JSON_END}\n"
        if JSON_BEGIN in current and JSON_END in current:
            current = current.split(JSON_BEGIN, 1)[0] + block + current.split(JSON_END, 1)[1].lstrip("\r\n")
        else:
            current = current.rstrip() + "\n\n" + block
        atomic_write_text(manifest_path, current)
        update_manifest_state(
            manifest_path,
            event="gate_check",
            status="passed" if summary["checks_passed"] else "not_passed",
            stage=args.gate,
            details={
                "checks_passed": summary["checks_passed"],
                "workflow_complete": summary["workflow_complete"],
                "run_id": args.run_id,
            },
        )
    if args.out:
        atomic_write_text(Path(args.out), summary_json)
    else:
        print(summary_json)
    return 0 if summary["checks_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
