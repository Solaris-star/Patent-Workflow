"""Offline regression tests for the local workflow checkpoint CLI."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "patent" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import workflow_cli
import run_phase_gates
from workflow_common import DOCX_SUFFIX, canonical_json_sha256, read_workflow_state, update_manifest_state
from validate_review_status import material_version_sha256


class WorkflowCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="patent-workflow-test-")
        self.workspace = Path(self.temp.name) / "case"
        self.workspace.mkdir()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_cli(self, *arguments: str) -> tuple[int, str, str]:
        return self.run_cli_at(self.workspace, *arguments)

    def run_cli_at(self, workspace: Path, *arguments: str) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = workflow_cli.main([arguments[0], "--workspace", str(workspace), *arguments[1:]])
        return code, stdout.getvalue(), stderr.getvalue()

    @property
    def manifest(self) -> Path:
        return self.workspace / "artifacts" / "run_manifest.md"

    def create_export_review(
        self,
        final_markdown: Path,
        draft: Path,
        facts_ledger: Path,
        review_status: Path,
        *,
        workspace: Path | None = None,
    ) -> None:
        case_workspace = workspace or self.workspace
        files = (final_markdown, draft, facts_ledger)
        hashes = {str(path.resolve()): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}
        normalized_hashes = {str(Path(path).resolve()).casefold(): digest for path, digest in hashes.items()}
        reviewed = {
            "final_markdown_path": str(final_markdown.resolve()),
            "files": hashes,
            "version_sha256": material_version_sha256(normalized_hashes),
        }

        reports: dict[str, dict] = {}
        for kind, name in (
            ("consistency_review", "phase_08_consistency_audit_report.md"),
            ("ipr_review", "phase_09_ipr_review_report.md"),
        ):
            report_path = case_workspace / "artifacts" / "audit" / name
            report = {
                "doc_type": f"{kind}_report",
                "report_type": kind,
                "review_id": f"REVIEW-SYN-{kind.upper()}",
                "completed_at": "2026-10-08T00:00:00Z",
                "scope": "Synthetic review fixture only.",
                "reviewed_materials": reviewed,
                "issues": [],
            }
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            reports[kind] = {
                "status": "completed",
                "report_type": kind,
                "report_path": str(report_path.resolve()),
                "report_sha256": hashlib.sha256(report_path.read_bytes()).hexdigest(),
            }
        data = {
            "doc_type": "review_status",
            "review_completed": True,
            "consistency_review": reports["consistency_review"],
            "ipr_review": reports["ipr_review"],
            "reviewed_materials": reviewed,
            "issues": [],
            "revision_validation": "not_required",
        }
        review_status.parent.mkdir(parents=True, exist_ok=True)
        review_status.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def prepare_export_case(
        self,
        workspace: Path,
        mode: str,
        *,
        sensitive_map: Path | None = None,
        final_body: str = "Synthetic body [[E-SYN-1]].",
    ) -> dict[str, Path]:
        def write_json(path: Path, value: object) -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")

        input_dir = workspace / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        draft = input_dir / "draft.md"
        draft.write_text("Synthetic software patent draft.", encoding="utf-8")
        disclosure = input_dir / "disclosure.md"
        disclosure.write_text("Synthetic disclosed implementation facts.", encoding="utf-8")

        output_dir = workspace / "delivery"
        output_dir.mkdir(parents=True, exist_ok=True)
        final_markdown = output_dir / "final.md"
        mmd = output_dir / "figure_01.mmd"
        mmd.write_text("flowchart TD\n  A-->B\n", encoding="utf-8")
        fence = chr(96) * 3
        final_markdown.write_text(
            f"# Synthetic title\n\n{final_body}\n\n"
            f"{fence}mermaid\n{mmd.read_text(encoding='utf-8')}{fence}\n\n"
            "FIG-SYN-1: Synthetic figure\n",
            encoding="utf-8",
        )

        artifacts = workspace / "artifacts"
        facts = artifacts / "draft" / "facts_ledger.json"
        research = artifacts / "research" / "phase_02_research_pack.json"
        candidates = artifacts / "prior_art" / "phase_04_patent_candidate_pool.json"
        evidence_pack = artifacts / "prior_art" / "phase_04_evidence_pack.json"
        background = artifacts / "prior_art" / "phase_05_background_pack.json"
        relevance_terms = artifacts / "prior_art" / "relevance_terms.json"
        review_status = artifacts / "audit" / "review_status.json"

        evidence = {
            "evidence_id": "E-SYN-1",
            "url": "https://example.invalid/synthetic-evidence",
            "excerpt": "Synthetic, local test evidence only.",
            "publication_date": "2026-10-01",
            "freshness": "fresh",
            "verification_status": "verified",
            "verified_at": "2026-10-08T00:00:00Z",
            "verification_method": "synthetic fixture",
            "conclusion_use": "usable",
            "feature_ids": ["F-SYN-1"],
            "is_auxiliary": False,
        }
        feature = {
            "feature_id": "F-SYN-1",
            "statement": "Synthetic software workflow feature",
            "evidence_kind": "source_claim",
            "status": "source_stated",
            "evidence_ids": ["E-SYN-1"],
        }
        write_json(research, {
            "pack_type": "research_pack", "phase": "phase_02",
            "research_questions": [{"id": "RQ-SYN-1", "question": "What supports the synthetic feature?"}],
            "outline_skeleton": [{
                "section_id": "S-SYN-1", "title": "Synthetic evidence",
                "intent": "Trace the synthetic feature.",
                "covers_questions": ["RQ-SYN-1"], "evidence_ids": ["E-SYN-1"],
            }],
            "evidence": [evidence], "scheme_features": [feature],
        })
        write_json(candidates, [{
            "title": "Synthetic software workflow",
            "publicationNumber": "CN-SYN-1",
            "filingDate": "2001-01-01",
            "abstract": "Synthetic software workflow example.",
        }])
        write_json(relevance_terms, {
            "project_terms": ["synthetic"], "ai_terms": [],
            "constraint_terms": [], "negative_terms": [],
            "weights": {"project": 100, "ai": 0, "constraint": 0, "negative": 0, "cn_bonus": 0},
        })
        write_json(evidence_pack, {
            "pack_type": "evidence_pack", "phase": "phase_04",
            "patent_candidate_pool_path": str(candidates),
            "search_trace": {
                "patent_search_queries": ["synthetic software workflow"],
                "final_relevant_patent_count": 1,
            },
            "final_relevant_patents": [{"evidence_id": "E-SYN-1"}],
            "scheme_features": [feature], "evidence": [evidence],
            "evidence_alignment": [{"feature_id": "F-SYN-1", "evidence_ids": ["E-SYN-1"]}],
        })
        write_json(background, {
            "pack_type": "background_pack", "phase": "phase_05",
            "closest_source_evidence_id": "E-SYN-1", "evidence_ids": ["E-SYN-1"],
            "feature_comparisons": [{
                "feature_id": "F-SYN-1", "difference": "Synthetic structural difference.",
                "evidence_ids": ["E-SYN-1"],
            }],
        })

        parts_dir = artifacts / "draft"
        parts_dir.mkdir(parents=True, exist_ok=True)
        for index in range(1, 6):
            figure_note = " FIG-SYN-1 Synthetic figure." if index == 4 else ""
            (parts_dir / f"part_{index:02d}_synthetic.md").write_text(
                f"# Part {index}\nSynthetic section {index}.{figure_note}\n",
                encoding="utf-8",
            )
        mmd_sha = hashlib.sha256(mmd.read_bytes()).hexdigest()
        write_json(facts, {
            "ledger_type": "facts_ledger",
            "terminology": [{"term": "Synthetic term", "definition": "Synthetic test definition."}],
            "constraints_and_effects": [{"constraint": "Synthetic constraint", "effect": "Synthetic effect."}],
            "source_registry": [
                {"source_id": "SRC-DRAFT-SYN-1", "source_type": "material",
                 "path": str(draft.resolve()), "sha256": hashlib.sha256(draft.read_bytes()).hexdigest()},
                {"source_id": "SRC-E-SYN-1", "source_type": "external_evidence", "evidence_id": "E-SYN-1"},
                {"source_id": "SRC-FIG-SYN-1", "source_type": "figure", "figure_id": "FIG-SYN-1",
                 "path": str(mmd.resolve()), "sha256": mmd_sha},
            ],
            "feature_registry": [{
                **feature, "source_ids": ["SRC-DRAFT-SYN-1", "SRC-E-SYN-1", "SRC-FIG-SYN-1"],
                "paragraph_ids": [], "figure_ids": ["FIG-SYN-1"],
            }],
            "figure_registry": [{
                "figure_id": "FIG-SYN-1", "caption": "Synthetic figure",
                "artifacts": {"mmd": str(mmd.resolve())},
                "mermaid_source_embedded_in_docx": True,
            }],
        })
        self.create_export_review(final_markdown, draft, facts, review_status, workspace=workspace)

        manifest = artifacts / "run_manifest.md"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        init_args = [
            "init", "--mode", mode, "--title", "Synthetic title",
            "--output-dir", "delivery", "--final-markdown", "delivery/final.md",
            "--research-pack", "artifacts/research/phase_02_research_pack.json",
            "--candidate-pool", "artifacts/prior_art/phase_04_patent_candidate_pool.json",
            "--evidence-pack", "artifacts/prior_art/phase_04_evidence_pack.json",
            "--background-pack", "artifacts/prior_art/phase_05_background_pack.json",
            "--facts-ledger", "artifacts/draft/facts_ledger.json",
            "--review-status", "artifacts/audit/review_status.json",
        ]
        if mode == "draft_review":
            init_args.extend(["--draft", "input/draft.md"])
        else:
            init_args.extend([
                "--disclosure", "input/disclosure.md",
                "--search-brief", "Synthetic software patent evidence scope.",
            ])
        if sensitive_map:
            init_args.extend(["--sensitive-map", str(sensitive_map)])
        code, _out, err = self.run_cli_at(workspace, *init_args)
        self.assertEqual(code, 0, err)
        return {
            "manifest": manifest, "output_dir": output_dir, "markdown": final_markdown,
            "draft": draft, "facts": facts, "mmd": mmd, "review_status": review_status,
            "sensitive_map": sensitive_map,
        }

    @staticmethod
    def write_sensitive_map(path: Path, term: str, *, confirmed: bool = True) -> None:
        payload = {
            "map_type": "sensitive_map",
            "confirmation_scope": "Synthetic test only.",
            "confirmed_at": "2026-10-08T00:00:00Z",
            "confirmed_by_user": confirmed,
            "entries": [{"id": "SYN-1", "term": term, "match": "literal"}],
        }
        payload["confirmation_sha256"] = canonical_json_sha256({
            key: value for key, value in payload.items()
            if key not in {"confirmed_by_user", "confirmed_at", "confirmation_sha256"}
        })
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def test_init_status_resume_preserve_existing_materials(self) -> None:
        source = self.workspace / "input" / "disclosure.md"
        source.parent.mkdir(parents=True)
        source.write_bytes(b"synthetic disclosure text")
        unrelated = self.workspace / "existing-output.txt"
        unrelated.write_bytes(b"do not replace")

        code, _out, err = self.run_cli(
            "init", "--mode", "full_research", "--disclosure", "input/disclosure.md",
            "--search-brief", "synthetic software patent scope", "--search-depth", "light",
        )
        self.assertEqual(code, 0, err)
        first_manifest = self.manifest.read_bytes()

        code, out, err = self.run_cli("status")
        self.assertEqual(code, 0, err)
        status = json.loads(out)
        self.assertEqual(status["current_stage"], "research")
        self.assertEqual(status["missing_materials"], [])
        self.assertFalse(status["waiting_for_user"])
        self.assertEqual(status["search_depth"], "light")

        code, out, err = self.run_cli("resume")
        self.assertEqual(code, 0, err)
        resumed = json.loads(out)
        self.assertFalse(resumed["artifacts_modified"])
        self.assertEqual(source.read_bytes(), b"synthetic disclosure text")
        self.assertEqual(unrelated.read_bytes(), b"do not replace")
        state = read_workflow_state(self.manifest.read_text(encoding="utf-8"))
        self.assertTrue(any(event.get("event") == "resume" for event in state.get("stage_history", [])))

        after_resume = self.manifest.read_bytes()
        code, _out, err = self.run_cli("init", "--mode", "draft_review")
        self.assertEqual(code, 2)
        self.assertIn("already exists", err)
        self.assertEqual(self.manifest.read_bytes(), after_resume)
        self.assertNotEqual(first_manifest, after_resume)

    def test_workflow_cli_operations_wait_for_the_workspace_lock(self) -> None:
        code, _out, err = self.run_cli("init", "--mode", "draft_review")
        self.assertEqual(code, 0, err)
        marker = Path(self.temp.name) / "child-started.txt"
        script = (
            "import sys; from pathlib import Path; "
            f"sys.path.insert(0, {str(SCRIPTS)!r}); import workflow_cli; "
            f"Path({str(marker)!r}).write_text('started', encoding='utf-8'); "
            f"raise SystemExit(workflow_cli.main(['status', '--workspace', {str(self.workspace)!r}]))"
        )
        with workflow_cli._workspace_operation_lock(self.workspace):
            child = subprocess.Popen(
                [sys.executable, "-c", script],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            deadline = time.monotonic() + 5
            while not marker.is_file() and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(marker.is_file(), "child did not reach the lock attempt")
            with self.assertRaises(subprocess.TimeoutExpired):
                child.communicate(timeout=0.2)
        _out, err = child.communicate(timeout=5)
        self.assertEqual(child.returncode, 0, err)

    def test_direct_phase_gate_runner_waits_for_the_workspace_lock(self) -> None:
        code, _out, err = self.run_cli("init", "--mode", "draft_review")
        self.assertEqual(code, 0, err)
        marker = Path(self.temp.name) / "gate-child-started.txt"
        script = (
            "import sys; from pathlib import Path; "
            f"sys.path.insert(0, {str(SCRIPTS)!r}); import run_phase_gates; "
            f"sys.argv = ['run_phase_gates.py', '--gate', 'review', '--workspace', {str(self.workspace)!r}, "
            f"'--manifest', {str(self.manifest)!r}]; "
            f"Path({str(marker)!r}).write_text('started', encoding='utf-8'); "
            "raise SystemExit(run_phase_gates.main())"
        )
        with workflow_cli._workspace_operation_lock(self.workspace):
            child = subprocess.Popen(
                [sys.executable, "-c", script],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            deadline = time.monotonic() + 5
            while not marker.is_file() and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(marker.is_file(), "gate child did not reach the lock attempt")
            with self.assertRaises(subprocess.TimeoutExpired):
                child.communicate(timeout=0.2)
        _out, err = child.communicate(timeout=10)
        self.assertIn(child.returncode, {0, 2}, err)

    def test_missing_materials_are_explicit_and_wait_for_user(self) -> None:
        code, _out, err = self.run_cli("init", "--mode", "full_research")
        self.assertEqual(code, 0, err)
        code, out, err = self.run_cli("status")
        self.assertEqual(code, 0, err)
        status = json.loads(out)
        self.assertTrue(status["waiting_for_user"])
        self.assertEqual(
            {item["name"] for item in status["missing_materials"]},
            {"disclosure", "search_request"},
        )
        self.assertIn("Supply the missing inputs", status["next_step"])

    def test_resume_hash_change_invalidates_conclusions_without_editing_source(self) -> None:
        source = self.workspace / "input" / "disclosure.md"
        scope = self.workspace / "input" / "scope.md"
        source.parent.mkdir(parents=True)
        source.write_text("synthetic version one", encoding="utf-8")
        scope.write_text("synthetic scope version one", encoding="utf-8")
        code, _out, err = self.run_cli(
            "init", "--mode", "full_research", "--disclosure", "input/disclosure.md",
            "--search-request", "input/scope.md",
        )
        self.assertEqual(code, 0, err)
        code, _out, err = self.run_cli("resume")
        self.assertEqual(code, 0, err)

        scope.write_text("synthetic scope version two", encoding="utf-8")
        code, out, err = self.run_cli("resume")
        self.assertEqual(code, 0, err)
        resumed = json.loads(out)
        self.assertEqual(resumed["stale_materials"], ["search_request"])
        self.assertTrue(resumed["conclusions_need_review"])
        state = read_workflow_state(self.manifest.read_text(encoding="utf-8"))
        self.assertTrue({"research", "prior-art", "draft", "review", "deliver"}.issubset(
            set(state["invalidated_gates"])
        ))
        self.assertEqual(source.read_text(encoding="utf-8"), "synthetic version one")
        self.assertEqual(scope.read_text(encoding="utf-8"), "synthetic scope version two")

    def test_removed_then_recreated_material_stays_invalidated(self) -> None:
        disclosure = self.workspace / "input" / "disclosure.md"
        search = self.workspace / "input" / "search.md"
        disclosure.parent.mkdir(parents=True)
        disclosure.write_text("synthetic disclosure", encoding="utf-8")
        search.write_text("synthetic search", encoding="utf-8")
        code, _out, err = self.run_cli(
            "init", "--mode", "full_research", "--disclosure", "input/disclosure.md",
            "--search-request", "input/search.md",
        )
        self.assertEqual(code, 0, err)
        code, _out, err = self.run_cli("resume")
        self.assertEqual(code, 0, err)
        original_hash = read_workflow_state(self.manifest.read_text(encoding="utf-8"))["material_hashes"]["disclosure"]
        disclosure.unlink()
        code, _out, err = self.run_cli("resume")
        self.assertEqual(code, 0, err)
        state = read_workflow_state(self.manifest.read_text(encoding="utf-8"))
        self.assertEqual(state["material_registry"]["disclosure"]["status"], "missing")
        self.assertEqual(state["material_hashes"]["disclosure"], original_hash)
        disclosure.write_text("synthetic disclosure", encoding="utf-8")
        code, out, err = self.run_cli("resume")
        self.assertEqual(code, 0, err)
        self.assertTrue(json.loads(out)["conclusions_need_review"])
        state = read_workflow_state(self.manifest.read_text(encoding="utf-8"))
        self.assertEqual(state["material_registry"]["disclosure"]["status"], "present")
        self.assertIn("recreated", [item["status"] for item in state["material_registry"]["disclosure"]["history"]])
        self.assertIn("disclosure", state["stale_materials"])

    def test_resume_mode_switch_is_explicit_and_invalidates_route_dependent_gates(self) -> None:
        disclosure = self.workspace / "input" / "disclosure.md"
        search = self.workspace / "input" / "search.md"
        draft = self.workspace / "input" / "draft.md"
        disclosure.parent.mkdir(parents=True)
        disclosure.write_text("synthetic disclosure", encoding="utf-8")
        search.write_text("synthetic scope", encoding="utf-8")
        draft.write_text("synthetic draft", encoding="utf-8")
        code, _out, err = self.run_cli(
            "init", "--mode", "full_research", "--disclosure", "input/disclosure.md",
            "--search-request", "input/search.md",
        )
        self.assertEqual(code, 0, err)
        code, _out, err = self.run_cli("resume")
        self.assertEqual(code, 0, err)
        update_manifest_state(
            self.manifest, event="synthetic_completed", status="passed",
            state_updates={"completed_gates": ["research", "prior-art", "draft", "review", "deliver"]},
        )
        code, out, err = self.run_cli("resume", "--mode", "draft_review", "--draft", "input/draft.md")
        self.assertEqual(code, 0, err)
        resumed = json.loads(out)
        self.assertEqual(resumed["workflow_mode"], "draft_review")
        self.assertEqual(resumed["current_stage"], "independent_review")
        self.assertEqual(set(resumed["invalidated_gates"]), {"review", "deliver"})
        self.assertTrue(resumed["conclusions_need_review"])
        self.assertFalse(set(resumed["completed_gates"]) & {"research", "prior-art", "draft"})
        state = read_workflow_state(self.manifest.read_text(encoding="utf-8"))
        switches = [event for event in state["stage_history"] if event.get("event") == "resume"]
        self.assertEqual(switches[-1]["details"]["mode_switch"], {
            "from": "full_research", "to": "draft_review",
        })

    def test_status_detects_manifest_mode_drift_until_explicit_resume_reconciles(self) -> None:
        draft = self.workspace / "input" / "draft.md"
        draft.parent.mkdir(parents=True)
        draft.write_text("synthetic draft", encoding="utf-8")
        code, _out, err = self.run_cli("init", "--mode", "draft_review", "--draft", "input/draft.md")
        self.assertEqual(code, 0, err)
        text = self.manifest.read_text(encoding="utf-8")
        self.manifest.write_text(workflow_cli._set_field(text, "workflow_mode", "titled_evidence"), encoding="utf-8")
        code, _out, err = self.run_cli("status")
        self.assertEqual(code, 2)
        self.assertIn("differs from checkpoint", err)
        code, out, err = self.run_cli("resume", "--mode", "draft_review")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["workflow_mode"], "draft_review")

    def test_explicit_external_input_is_imported_and_external_output_is_allowed(self) -> None:
        external_input = Path(self.temp.name) / "selected disclosure.md"
        external_input.write_text("synthetic external input version one", encoding="utf-8")
        scope = self.workspace / "input" / "scope.md"
        scope.parent.mkdir(parents=True)
        scope.write_text("synthetic search scope", encoding="utf-8")
        code, _out, err = self.run_cli(
            "init", "--mode", "full_research", "--disclosure", str(external_input),
            "--search-request", "input/scope.md",
        )
        self.assertEqual(code, 0, err)
        manifest_text = self.manifest.read_text(encoding="utf-8")
        self.assertNotIn(str(external_input), manifest_text)
        state = read_workflow_state(manifest_text)
        imported = Path(state["material_paths"]["disclosure"])
        self.assertTrue(imported.is_file())
        self.assertEqual(imported.read_text(encoding="utf-8"), "synthetic external input version one")
        external_input.write_text("synthetic external input changed", encoding="utf-8")
        code, out, err = self.run_cli("status")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out)["stale_materials"], [])
        self.assertEqual(imported.read_text(encoding="utf-8"), "synthetic external input version one")

        outside_delivery = Path(self.temp.name) / "outside-delivery"
        outside_delivery.mkdir()
        final = outside_delivery / "final.md"
        final.write_text("# Synthetic title\nSynthetic body.", encoding="utf-8")
        draft = self.workspace / "input" / "draft.md"
        draft.write_text("Synthetic draft", encoding="utf-8")
        other_workspace = Path(self.temp.name) / "second-case"
        other_workspace.mkdir()
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = workflow_cli.main([
                "init", "--workspace", str(other_workspace), "--mode", "draft_review",
                "--title", "Synthetic title", "--draft", str(draft),
                "--output-dir", str(outside_delivery), "--final-markdown", str(final),
            ])
        self.assertEqual(code, 0, stderr.getvalue())
        out_manifest = other_workspace / "artifacts" / "run_manifest.md"
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = workflow_cli.main(["status", "--workspace", str(other_workspace)])
        self.assertEqual(code, 0, stderr.getvalue())
        self.assertIn(str(outside_delivery.resolve()), out_manifest.read_text(encoding="utf-8"))
        self.assertTrue(final.is_file())

    def test_explicit_external_directory_and_registered_material_are_imported_as_snapshots(self) -> None:
        source_dir = Path(self.temp.name) / "external-reference-bundle"
        nested = source_dir / "nested"
        nested.mkdir(parents=True)
        (source_dir / "overview.md").write_text("synthetic overview", encoding="utf-8")
        (nested / "details.txt").write_text("synthetic details", encoding="utf-8")
        scope = self.workspace / "input" / "scope.md"
        scope.parent.mkdir(parents=True)
        scope.write_text("synthetic scope", encoding="utf-8")

        code, _out, err = self.run_cli(
            "init", "--mode", "full_research", "--disclosure", str(source_dir),
            "--search-request", "input/scope.md", "--material", f"reference_bundle={source_dir}",
        )
        self.assertEqual(code, 0, err)
        state = read_workflow_state(self.manifest.read_text(encoding="utf-8"))
        imported_disclosure = Path(state["material_paths"]["disclosure"])
        imported_bundle = Path(state["material_paths"]["reference_bundle"])
        self.assertTrue(imported_disclosure.is_dir())
        self.assertTrue(imported_bundle.is_dir())
        for imported in (imported_disclosure, imported_bundle):
            self.assertEqual((imported / "overview.md").read_text(encoding="utf-8"), "synthetic overview")
            self.assertEqual((imported / "nested" / "details.txt").read_text(encoding="utf-8"), "synthetic details")
            self.assertTrue(workflow_cli.is_within(imported, self.workspace))
        self.assertNotIn(str(source_dir), self.manifest.read_text(encoding="utf-8"))

    def test_relative_parent_input_is_rejected(self) -> None:
        outside = Path(self.temp.name) / "outside.md"
        outside.write_text("synthetic", encoding="utf-8")
        code, _out, err = self.run_cli("init", "--mode", "full_research", "--disclosure", "../outside.md")
        self.assertEqual(code, 2)
        self.assertIn("relative input paths must stay inside", err)
        self.assertFalse(self.manifest.exists())
        outside_map = Path(self.temp.name) / "outside-map.json"
        outside_map.write_text('{"synthetic":true}', encoding="utf-8")
        code, _out, err = self.run_cli(
            "init", "--mode", "full_research", "--sensitive-map", "../outside-map.json",
        )
        self.assertEqual(code, 2)
        self.assertIn("relative input paths must stay inside", err)
        self.assertFalse(self.manifest.exists())

    def test_sensitive_map_is_a_path_reference_and_requires_explicit_reselection(self) -> None:
        external_map = Path(self.temp.name) / "private" / "sensitive_map.json"
        external_map.parent.mkdir()
        secret_marker = "synthetic-sensitive-map-marker-do-not-import"
        external_map.write_text(json.dumps({"term": secret_marker}), encoding="utf-8")
        disclosure = self.workspace / "input" / "disclosure.md"
        disclosure.parent.mkdir()
        disclosure.write_text("Synthetic disclosure.", encoding="utf-8")

        original_fingerprint = workflow_cli._fingerprint
        fingerprinted: list[Path] = []

        def fingerprint(path: Path) -> str | None:
            selected = Path(path)
            self.assertNotEqual(selected, external_map)
            fingerprinted.append(selected)
            return original_fingerprint(selected)

        with patch.object(workflow_cli, "_fingerprint", side_effect=fingerprint):
            code, _out, err = self.run_cli(
                "init", "--mode", "full_research", "--disclosure", "input/disclosure.md",
                "--search-brief", "Synthetic software patent scope.",
                "--sensitive-map", str(external_map),
            )
        self.assertEqual(code, 0, err)
        state = read_workflow_state(self.manifest.read_text(encoding="utf-8"))
        self.assertEqual(state["material_paths"].get("sensitive_map"), None)
        self.assertNotIn("sensitive_map", state["material_hashes"])
        selection = state["approved_inputs"]["sensitive_map"]
        self.assertEqual(selection["source_kind"], "explicit_path_reference")
        self.assertNotIn("sha256", selection)
        self.assertIn(str(external_map.resolve()), self.manifest.read_text(encoding="utf-8"))
        self.assertFalse((self.workspace / "inputs" / "registered" / "sensitive_map").exists())
        for path in self.workspace.rglob("*"):
            if path.is_file():
                self.assertNotIn(secret_marker.encode("utf-8"), path.read_bytes(), str(path))

        with patch.object(workflow_cli, "_fingerprint", side_effect=fingerprint):
            code, _out, err = self.run_cli("status")
        self.assertEqual(code, 0, err)
        update_manifest_state(
            self.manifest,
            event="synthetic_completed_gates",
            status="passed",
            state_updates={
                "completed_gates": ["research", "prior-art", "draft", "review", "deliver"],
                "invalidated_gates": [],
                "sensitive_map_audit": {"content_sha256": "old-map-audit-content-hash"},
            },
        )

        resumed_map = Path(self.temp.name) / "private" / "resumed-sensitive-map.json"
        resumed_marker = "synthetic-resumed-map-marker-do-not-import"
        resumed_map.write_text(json.dumps({"term": resumed_marker}), encoding="utf-8")
        with patch.object(workflow_cli, "_fingerprint", side_effect=fingerprint):
            code, _out, err = self.run_cli("resume", "--sensitive-map", str(resumed_map))
        self.assertEqual(code, 0, err)
        external_map = resumed_map
        state = read_workflow_state(self.manifest.read_text(encoding="utf-8"))
        self.assertNotIn("sensitive_map", state["material_paths"])
        self.assertNotIn("sensitive_map", state["material_hashes"])
        self.assertTrue({"research", "prior-art", "draft", "review", "deliver"}.issubset(
            set(state["invalidated_gates"])
        ))
        self.assertFalse(set(state["completed_gates"]).intersection(
            {"research", "prior-art", "draft", "review", "deliver"}
        ))
        self.assertIsNone(state.get("sensitive_map_audit"))
        self.assertIn(str(resumed_map.resolve()), self.manifest.read_text(encoding="utf-8"))
        self.assertFalse((self.workspace / "inputs" / "registered" / "sensitive_map").exists())
        for path in self.workspace.rglob("*"):
            if path.is_file():
                contents = path.read_bytes()
                self.assertNotIn(secret_marker.encode("utf-8"), contents, str(path))
                self.assertNotIn(resumed_marker.encode("utf-8"), contents, str(path))

        invocations: list[list[str]] = []

        def fake_runner(command, **_kwargs):
            invocations.append(command)
            run_id = command[command.index("--run-id") + 1]
            report = {
                "runner": "run_phase_gates.py", "run_id": run_id,
                "checks_passed": False, "workflow_complete": False,
                "gateResults": [{"gate": "deliver", "status": "failed"}],
                "skipped": [], "not_run": [],
            }
            return SimpleNamespace(returncode=2, stdout=json.dumps(report), stderr="")

        with patch.object(workflow_cli.subprocess, "run", side_effect=fake_runner):
            code, _out, err = self.run_cli("check", "--gate", "deliver")
        self.assertEqual(code, 2, err)
        self.assertNotIn("--sensitive-map", invocations[-1])

        with patch.object(workflow_cli.subprocess, "run", side_effect=fake_runner):
            code, _out, err = self.run_cli(
                "check", "--gate", "deliver", "--sensitive-map", str(external_map),
            )
        self.assertEqual(code, 2, err)
        map_option = invocations[-1].index("--sensitive-map")
        self.assertEqual(invocations[-1][map_option + 1], str(external_map.resolve()))
        self.assertFalse((self.workspace / "inputs" / "registered" / "sensitive_map").exists())

        mismatch = Path(self.temp.name) / "private" / "other-map.json"
        mismatch.write_text("{}", encoding="utf-8")
        before_mismatch = self.manifest.read_bytes()
        with patch.object(workflow_cli.subprocess, "run", side_effect=fake_runner) as runner:
            code, _out, err = self.run_cli(
                "check", "--gate", "deliver", "--sensitive-map", str(mismatch),
            )
        self.assertEqual(code, 2)
        self.assertIn("must match the path selected", err)
        runner.assert_not_called()
        self.assertEqual(self.manifest.read_bytes(), before_mismatch)

    def test_status_migrates_legacy_sensitive_map_without_reading_it(self) -> None:
        disclosure = self.workspace / "input" / "disclosure.md"
        search = self.workspace / "input" / "search.md"
        disclosure.parent.mkdir(parents=True)
        disclosure.write_text("Synthetic disclosure.", encoding="utf-8")
        search.write_text("Synthetic scope.", encoding="utf-8")
        private_map = Path(self.temp.name) / "private" / "legacy-map.json"
        private_map.parent.mkdir()
        secret_marker = "synthetic-legacy-sensitive-map-marker"
        private_map.write_text(json.dumps({"term": secret_marker}), encoding="utf-8")
        code, _out, err = self.run_cli(
            "init", "--mode", "full_research", "--disclosure", "input/disclosure.md",
            "--search-request", "input/search.md",
        )
        self.assertEqual(code, 0, err)
        update_manifest_state(
            self.manifest,
            event="synthetic_legacy_state",
            status="passed",
            state_updates={
                "material_paths": {
                    "disclosure": str(disclosure),
                    "search_request": str(search),
                    "sensitive_map": str(private_map),
                },
                "material_hashes": {"sensitive_map": "legacy-content-hash-marker"},
                "material_registry": {
                    "sensitive_map": {
                        "path": str(private_map),
                        "status": "present",
                        "last_present_sha256": "legacy-registry-content-hash-marker",
                    },
                },
                "approved_inputs": {
                    "sensitive_map": {
                        "source_kind": "explicit_external",
                        "source_path": str(private_map),
                        "sha256": "legacy-approved-content-hash-marker",
                    },
                },
                "completed_gates": ["research", "prior-art", "draft", "review", "deliver"],
                "invalidated_gates": [],
                "sensitive_map_audit": {"content_sha256": "legacy-audit-content-hash-marker"},
            },
        )
        original_fingerprint = workflow_cli._fingerprint

        def fingerprint(path: Path) -> str | None:
            self.assertNotEqual(Path(path).resolve(), private_map.resolve())
            return original_fingerprint(path)

        with patch.object(workflow_cli, "_fingerprint", side_effect=fingerprint):
            code, _out, err = self.run_cli("status")
        self.assertEqual(code, 0, err)
        state = read_workflow_state(self.manifest.read_text(encoding="utf-8"))
        self.assertNotIn("sensitive_map", state["material_paths"])
        self.assertNotIn("sensitive_map", state["material_hashes"])
        self.assertNotIn("sensitive_map", state["material_registry"])
        self.assertNotIn("sha256", state["approved_inputs"].get("sensitive_map", {}))
        self.assertTrue({"research", "prior-art", "draft", "review", "deliver"}.issubset(
            set(state["invalidated_gates"])
        ))
        self.assertFalse(set(state["completed_gates"]).intersection(
            {"research", "prior-art", "draft", "review", "deliver"}
        ))
        manifest_text = self.manifest.read_text(encoding="utf-8")
        self.assertNotIn(secret_marker, manifest_text)
        self.assertNotIn("legacy-content-hash-marker", manifest_text)
        self.assertNotIn("legacy-registry-content-hash-marker", manifest_text)
        self.assertNotIn("legacy-approved-content-hash-marker", manifest_text)
        self.assertNotIn("legacy-audit-content-hash-marker", manifest_text)
        self.assertTrue(private_map.is_file())
        self.assertEqual(private_map.read_text(encoding="utf-8"), json.dumps({"term": secret_marker}))

    def test_explicit_sensitive_map_check_records_current_confirmation_and_rejects_mid_check_change(self) -> None:
        sensitive_map = Path(self.temp.name) / "private" / "confirmed-map.json"
        sensitive_map.parent.mkdir()

        def write_map(scope: str) -> str:
            data = {
                "map_type": "sensitive_map",
                "confirmed_by_user": True,
                "confirmation_scope": scope,
                "confirmed_at": "2026-10-08T00:00:00Z",
                "entries": [{"id": "SYN-MAP-1", "term": "SYNTHETIC-PRIVATE-MARKER"}],
            }
            data["confirmation_sha256"] = canonical_json_sha256({
                key: value for key, value in data.items()
                if key not in {"confirmed_by_user", "confirmed_at", "confirmation_sha256"}
            })
            sensitive_map.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            return data["confirmation_sha256"]

        confirmation = write_map("Synthetic check scope.")
        draft = self.workspace / "input" / "draft.md"
        draft.parent.mkdir(parents=True)
        draft.write_text("Synthetic draft.", encoding="utf-8")
        delivery = self.workspace / "delivery"
        delivery.mkdir()
        final_markdown = delivery / "final.md"
        final_markdown.write_text("# Synthetic title\n", encoding="utf-8")
        code, _out, err = self.run_cli(
            "init", "--mode", "draft_review", "--title", "Synthetic title",
            "--draft", "input/draft.md", "--output-dir", "delivery",
            "--final-markdown", "delivery/final.md", "--sensitive-map", str(sensitive_map),
        )
        self.assertEqual(code, 0, err)

        mutate_during_check = False

        def fake_runner(command, **_kwargs):
            run_id = command[command.index("--run-id") + 1]
            validator = {
                "validator": "validate_sanitize.py",
                "map_confirmed": True,
                "confirmation_binding_valid": True,
                "confirmation_sha256": confirmation,
                "checks_passed": True,
                "passed": True,
            }
            run = {
                "cmd": [
                    sys.executable, str(SCRIPTS / "validate_sanitize.py"),
                    "--map", str(sensitive_map.resolve()), "--scan-dir", str(delivery.resolve()),
                ],
                "stdout": json.dumps(validator), "passed": True, "checks_passed": True,
            }
            report = {
                "run_id": run_id,
                "checks_passed": True,
                "workflow_complete": False,
                "review_completed": False,
                "gateResults": [{
                    "gate": "deliver", "status": "passed", "checks_passed": True,
                    "workflow_complete": True, "runs": [run],
                }],
            }
            if mutate_during_check:
                write_map("Synthetic changed scope during check.")
            return SimpleNamespace(returncode=0, stdout=json.dumps(report), stderr="")

        with patch.object(workflow_cli.subprocess, "run", side_effect=fake_runner):
            code, out, err = self.run_cli(
                "check", "--gate", "deliver", "--sensitive-map", str(sensitive_map),
            )
        self.assertEqual(code, 0, err)
        result = json.loads(out)
        state = read_workflow_state(self.manifest.read_text(encoding="utf-8"))
        audit = state["sensitive_map_audit"]
        self.assertTrue(audit["checks_passed"])
        self.assertTrue(audit["confirmation_binding_valid"])
        self.assertEqual(audit["confirmation_sha256"], confirmation)
        self.assertEqual(audit["content_sha256"], hashlib.sha256(sensitive_map.read_bytes()).hexdigest())
        self.assertEqual(audit["run_id"], state["last_check_run_id"])
        self.assertEqual(result["sensitive_map_audit"]["audit_version"], 1)

        mutate_during_check = True
        with patch.object(workflow_cli.subprocess, "run", side_effect=fake_runner):
            code, out, err = self.run_cli(
                "check", "--gate", "deliver", "--sensitive-map", str(sensitive_map),
            )
        self.assertEqual(code, 2, err)
        result = json.loads(out)
        state = read_workflow_state(self.manifest.read_text(encoding="utf-8"))
        self.assertFalse(result["sensitive_map_audit"]["content_stable_during_check"])
        self.assertFalse(state["sensitive_map_audit"]["checks_passed"])
        self.assertIn("deliver", state["invalidated_gates"])
        gate_report_text = self.manifest.read_text(encoding="utf-8")
        gate_report = gate_report_text.split(run_phase_gates.JSON_BEGIN, 1)[1].split(
            run_phase_gates.JSON_END, 1,
        )[0]
        gate_report = gate_report.split("json", 1)[1].split("```", 1)[0]
        saved_summary = json.loads(gate_report)
        self.assertFalse(saved_summary["checks_passed"])
        self.assertFalse(saved_summary["sensitive_map_audit"]["checks_passed"])

    def test_research_gate_never_reads_manifest_sensitive_map_without_reselection(self) -> None:
        external_map = Path(self.temp.name) / "private" / "sensitive_map.json"
        external_map.parent.mkdir()
        external_map.write_text("synthetic map data", encoding="utf-8")
        manifest = self.workspace / "artifacts" / "run_manifest.md"
        manifest.parent.mkdir(parents=True)
        manifest.write_text(
            f"- `research_origin`: mine\n- `sensitive_map_path`: {external_map.resolve()}\n",
            encoding="utf-8",
        )
        commands: list[list[str]] = []

        def fake_run(command):
            commands.append(command)
            return {"passed": False, "checks_passed": False, "exitCode": 2}

        with patch.object(run_phase_gates, "_run", side_effect=fake_run):
            runs, skip_reason, _details = run_phase_gates._run_gate(
                "research", self.workspace, None, None, None, str(manifest), None,
            )
        self.assertIsNone(skip_reason)
        self.assertEqual(runs[0]["cmd"][1], "mine-run-sensitive-map-not-selected-for-check")
        self.assertFalse(any(
            any("validate_sanitize.py" in part for part in command)
            for command in commands
        ))

        commands.clear()
        with patch.object(run_phase_gates, "_run", side_effect=fake_run):
            run_phase_gates._run_gate(
                "research", self.workspace, None, None, None, str(manifest), str(external_map.resolve()),
            )
        self.assertTrue(any(
            any("validate_sanitize.py" in part for part in command)
            and str(external_map.resolve()) in command
            for command in commands
        ))

        commands.clear()
        with patch.object(run_phase_gates, "_run", side_effect=fake_run):
            delivery_runs, _skip, _details = run_phase_gates._run_gate(
                "deliver", self.workspace, str(self.workspace / "delivery"), "Synthetic title",
                str(self.workspace / "delivery" / "final.md"), str(manifest), None,
            )
        self.assertFalse(any(
            any("validate_sanitize.py" in part for part in command)
            for command in commands
        ))
        self.assertTrue(any(
            run.get("cmd", [None, None])[1] == "sensitive-map-declared-but-not-checked"
            for run in delivery_runs
        ))

        commands.clear()
        with patch.object(run_phase_gates, "_run", side_effect=fake_run):
            run_phase_gates._run_gate(
                "deliver", self.workspace, str(self.workspace / "delivery"), "Synthetic title",
                str(self.workspace / "delivery" / "final.md"), str(manifest), str(external_map.resolve()),
            )
        self.assertTrue(any(
            any("validate_sanitize.py" in part for part in command)
            and str(external_map.resolve()) in command
            for command in commands
        ))

    def test_delivery_gate_uses_safe_manifest_final_markdown_fallback(self) -> None:
        delivery = self.workspace / "delivery"
        delivery.mkdir()
        final_markdown = delivery / "final.md"
        final_markdown.write_text("Synthetic delivery draft.", encoding="utf-8")
        manifest = self.workspace / "artifacts" / "run_manifest.md"
        manifest.parent.mkdir(parents=True)
        manifest.write_text(
            "\n".join([
                "- `workflow_mode`: draft_review",
                f"- `output_dir`: {delivery.resolve()}",
                "- `final_title`: Synthetic title",
                f"- `final_markdown_path`: {final_markdown.resolve()}",
            ]) + "\n",
            encoding="utf-8",
        )
        commands: list[list[str]] = []

        def fake_run(command):
            commands.append(command)
            return {"passed": True, "checks_passed": True, "exitCode": 0}

        with patch.object(run_phase_gates, "_run", side_effect=fake_run):
            runs, skip_reason, _details = run_phase_gates._run_gate(
                "deliver", self.workspace, str(delivery.resolve()), "Synthetic title",
                None, str(manifest), None,
            )
        self.assertIsNone(skip_reason)
        self.assertTrue(runs)
        health_command = next(
            command for command in commands
            if any("health_check_delivery_package.py" in part for part in command)
        )
        markdown_arg = health_command[health_command.index("--final-markdown") + 1]
        self.assertEqual(Path(markdown_arg).resolve(), final_markdown.resolve())

        manifest.write_text(
            "\n".join([
                "- `workflow_mode`: draft_review",
                f"- `output_dir`: {delivery.resolve()}",
                "- `final_title`: Synthetic title",
                f"- `final_markdown_path`: {(self.workspace / 'outside.md').resolve()}",
            ]) + "\n",
            encoding="utf-8",
        )
        commands.clear()
        with patch.object(run_phase_gates, "_run", side_effect=fake_run):
            runs, skip_reason, _details = run_phase_gates._run_gate(
                "deliver", self.workspace, str(delivery.resolve()), "Synthetic title",
                None, str(manifest), None,
            )
        self.assertIsNone(skip_reason)
        self.assertFalse(any(
            any("health_check_delivery_package.py" in part for part in command)
            for command in commands
        ))
        self.assertEqual(runs[0]["cmd"][1], "final-markdown-outside-delivery-directory")

        runs, skip_reason, _details = run_phase_gates._run_gate(
            "deliver", self.workspace, None, None, None, str(manifest), None,
        )
        self.assertEqual(runs, [])
        self.assertIn("requires --deliver-dir", skip_reason or "")

    def test_status_at_delivery_stage_reports_missing_delivery_directory(self) -> None:
        draft = self.workspace / "input" / "draft.md"
        draft.parent.mkdir(parents=True)
        draft.write_text("synthetic draft", encoding="utf-8")
        code, _out, err = self.run_cli("init", "--mode", "draft_review", "--draft", "input/draft.md")
        self.assertEqual(code, 0, err)
        update_manifest_state(
            self.manifest,
            event="test_review_complete",
            status="passed",
            state_updates={"completed_gates": ["review"]},
        )
        code, out, err = self.run_cli("status")
        self.assertEqual(code, 0, err)
        status = json.loads(out)
        self.assertEqual(status["current_stage"], "delivery")
        self.assertTrue(status["waiting_for_user"])
        self.assertIn("output_dir", {item["name"] for item in status["missing_materials"]})

    def test_check_does_not_complete_gate_when_workflow_is_incomplete(self) -> None:
        draft = self.workspace / "input" / "draft.md"
        draft.parent.mkdir(parents=True)
        draft.write_text("synthetic draft", encoding="utf-8")
        code, _out, err = self.run_cli("init", "--mode", "draft_review", "--draft", "input/draft.md")
        self.assertEqual(code, 0, err)
        update_manifest_state(
            self.manifest,
            event="test_review_complete",
            status="passed",
            state_updates={"completed_gates": ["review"]},
        )
        runner_result = {
            "checks_passed": True,
            "workflow_complete": False,
            "review_completed": True,
            "skipped": [],
            "not_run": ["render"],
            "gateResults": [{"gate": "deliver", "status": "passed", "workflow_complete": False}],
        }
        def fake_run(command, **_kwargs):
            runner_result["run_id"] = command[command.index("--run-id") + 1]
            return SimpleNamespace(returncode=0, stdout=json.dumps(runner_result), stderr="")

        with patch.object(workflow_cli.subprocess, "run", side_effect=fake_run):
            code, _out, err = self.run_cli("check", "--gate", "deliver")
        self.assertEqual(code, 0, err)
        state = read_workflow_state(self.manifest.read_text(encoding="utf-8"))
        self.assertNotIn("deliver", state.get("completed_gates", []))

    def test_failed_child_does_not_reuse_or_replace_an_old_report(self) -> None:
        draft = self.workspace / "input" / "draft.md"
        draft.parent.mkdir(parents=True)
        draft.write_text("synthetic draft", encoding="utf-8")
        code, _out, err = self.run_cli("init", "--mode", "draft_review", "--draft", "input/draft.md")
        self.assertEqual(code, 0, err)
        report = self.workspace / "artifacts" / "previous-check.json"
        report.parent.mkdir(parents=True, exist_ok=True)
        old_report = b'{"checks_passed":true,"workflow_complete":true,"gateResults":[]}\n'
        report.write_bytes(old_report)
        update_manifest_state(
            self.manifest, event="synthetic_completed", status="passed",
            state_updates={"completed_gates": ["review", "deliver"]},
        )
        fake_process = SimpleNamespace(returncode=1, stdout="", stderr="synthetic child failure")
        with patch.object(workflow_cli.subprocess, "run", return_value=fake_process):
            code, _out, err = self.run_cli(
                "check", "--gate", "deliver", "--report", "artifacts/previous-check.json", "--overwrite-report",
            )
        self.assertEqual(code, 2)
        self.assertIn("synthetic child failure", err)
        self.assertEqual(report.read_bytes(), old_report)
        state = read_workflow_state(self.manifest.read_text(encoding="utf-8"))
        self.assertNotIn("deliver", state.get("completed_gates", []))
        self.assertIn("deliver", state.get("invalidated_gates", []))
        self.assertFalse(state["last_check_result"]["report_valid"])

    def test_current_failed_gate_reports_are_preserved_across_all_workflow_modes(self) -> None:
        routes = {
            "full_research": ["research", "prior-art", "draft", "review", "deliver"],
            "titled_evidence": ["prior-art", "draft", "review", "deliver"],
            "draft_review": ["review", "deliver"],
        }

        def initialize(workspace: Path, mode: str) -> None:
            self.workspace = workspace
            self.workspace.mkdir(parents=True)
            inputs = workspace / "input"
            inputs.mkdir()
            if mode == "full_research":
                (inputs / "disclosure.md").write_text("Synthetic disclosure.", encoding="utf-8")
                code, _out, err = self.run_cli(
                    "init", "--mode", mode, "--disclosure", "input/disclosure.md",
                    "--search-brief", "Synthetic software patent scope.",
                )
            elif mode == "titled_evidence":
                (inputs / "disclosure.md").write_text("Synthetic disclosure.", encoding="utf-8")
                code, _out, err = self.run_cli(
                    "init", "--mode", mode, "--disclosure", "input/disclosure.md",
                    "--title", "Synthetic title", "--search-brief", "Synthetic evidence gaps.",
                )
            else:
                (inputs / "draft.md").write_text("Synthetic draft.", encoding="utf-8")
                code, _out, err = self.run_cli("init", "--mode", mode, "--draft", "input/draft.md")
            self.assertEqual(code, 0, err)

        for mode, mode_gates in routes.items():
            failed_gate = mode_gates[0]
            expected_not_run = mode_gates[1:]
            for outcome in ("valid_failure", "crash", "stale"):
                with self.subTest(mode=mode, outcome=outcome):
                    workspace = Path(self.temp.name) / f"{mode}-{outcome}"
                    initialize(workspace, mode)
                    report = workspace / "artifacts" / "check-report.json"
                    report.parent.mkdir(parents=True, exist_ok=True)
                    prior_report = b'{"previous":"synthetic report"}\n'
                    if outcome != "valid_failure":
                        report.write_bytes(prior_report)

                    def fake_run(command, **_kwargs):
                        current_run_id = command[command.index("--run-id") + 1]
                        report_run_id = "STALE-SYNTHETIC-RUN" if outcome == "stale" else current_run_id
                        summary = {
                            "runner": "run_phase_gates.py",
                            "run_id": report_run_id,
                            "checks_passed": False,
                            "workflow_complete": False,
                            "review_completed": False,
                            "revision_validation": "not_run",
                            "skipped": [],
                            "not_run": expected_not_run,
                            "gateResults": [
                                {
                                    "gate": failed_gate, "status": "failed", "passed": False,
                                    "checks_passed": False, "workflow_complete": False,
                                    "skipped": False, "not_run": False, "runs": [],
                                },
                                *[{
                                    "gate": gate, "status": "not_run", "passed": False,
                                    "checks_passed": False, "workflow_complete": False,
                                    "skipped": False, "not_run": True, "runs": [],
                                } for gate in expected_not_run],
                            ],
                        }
                        code = 1 if outcome == "crash" else 2
                        return SimpleNamespace(returncode=code, stdout=json.dumps(summary), stderr="synthetic runner result")

                    with patch.object(workflow_cli.subprocess, "run", side_effect=fake_run):
                        code, _out, _err = self.run_cli(
                            "check", "--gate", "all", "--report", "artifacts/check-report.json",
                            "--overwrite-report",
                        )
                    state = read_workflow_state(self.manifest.read_text(encoding="utf-8"))
                    result = state["last_check_result"]
                    if outcome == "valid_failure":
                        self.assertEqual(code, 2)
                        self.assertTrue(result["report_valid"])
                        self.assertFalse(result["checks_passed"])
                        self.assertEqual(result["not_run"], expected_not_run)
                        self.assertEqual(result["gate_results"][0]["gate"], failed_gate)
                        self.assertEqual(result["gate_results"][0]["status"], "failed")
                        self.assertEqual(json.loads(report.read_text(encoding="utf-8"))["gateResults"][0]["gate"], failed_gate)
                    else:
                        self.assertEqual(code, 2)
                        self.assertFalse(result["report_valid"])
                        self.assertEqual(result["not_run"], ["all"])
                        self.assertEqual(result["gate_results"], [])
                        self.assertEqual(report.read_bytes(), prior_report)

    def test_single_gate_success_keeps_downstream_material_invalidation(self) -> None:
        disclosure = self.workspace / "input" / "disclosure.md"
        search = self.workspace / "input" / "search.md"
        disclosure.parent.mkdir(parents=True)
        disclosure.write_text("synthetic disclosure version one", encoding="utf-8")
        search.write_text("synthetic scope", encoding="utf-8")
        code, _out, err = self.run_cli(
            "init", "--mode", "full_research", "--disclosure", "input/disclosure.md",
            "--search-request", "input/search.md",
        )
        self.assertEqual(code, 0, err)
        code, _out, err = self.run_cli("resume")
        self.assertEqual(code, 0, err)
        update_manifest_state(
            self.manifest, event="synthetic_completed", status="passed",
            state_updates={"completed_gates": ["research", "prior-art", "draft", "review", "deliver"]},
        )
        disclosure.write_text("synthetic disclosure version two", encoding="utf-8")

        def fake_run(command, **_kwargs):
            run_id = command[command.index("--run-id") + 1]
            return SimpleNamespace(returncode=0, stderr="", stdout=json.dumps({
                "run_id": run_id,
                "checks_passed": True,
                "workflow_complete": False,
                "review_completed": False,
                "gateResults": [{
                    "gate": "research", "status": "passed", "checks_passed": True,
                    "workflow_complete": True,
                }],
            }))

        with patch.object(workflow_cli.subprocess, "run", side_effect=fake_run):
            code, _out, err = self.run_cli("check", "--gate", "research")
        self.assertEqual(code, 0, err)
        state = read_workflow_state(self.manifest.read_text(encoding="utf-8"))
        self.assertIn("research", state["completed_gates"])
        self.assertTrue({"prior-art", "draft", "review", "deliver"}.issubset(state["invalidated_gates"]))
        self.assertIn("disclosure", state["stale_materials"])
        self.assertTrue(state["conclusions_need_review"])

    def test_export_refuses_to_replace_existing_docx_by_default(self) -> None:
        draft = self.workspace / "input" / "draft.md"
        draft.parent.mkdir(parents=True)
        draft.write_text("# Synthetic review draft\n", encoding="utf-8")
        delivery = self.workspace / "delivery"
        delivery.mkdir()
        final_markdown = delivery / "final.md"
        final_markdown.write_text("# Synthetic title\n", encoding="utf-8")
        facts_ledger = self.workspace / "artifacts" / "draft" / "facts_ledger.json"
        facts_ledger.parent.mkdir(parents=True)
        facts_ledger.write_text('{"ledger_type":"facts_ledger"}', encoding="utf-8")
        review_status = self.workspace / "artifacts" / "audit" / "review_status.json"
        self.create_export_review(final_markdown, draft, facts_ledger, review_status)
        output = delivery / f"Synthetic title{DOCX_SUFFIX}"
        output.write_bytes(b"existing synthetic file")

        code, _out, err = self.run_cli(
            "init", "--mode", "draft_review", "--title", "Synthetic title",
            "--draft", "input/draft.md", "--output-dir", "delivery",
            "--final-markdown", "delivery/final.md",
            "--facts-ledger", "artifacts/draft/facts_ledger.json",
            "--review-status", "artifacts/audit/review_status.json",
        )
        self.assertEqual(code, 0, err)
        code, _out, err = self.run_cli("export")
        self.assertEqual(code, 2)
        self.assertIn("already exists", err)
        self.assertEqual(output.read_bytes(), b"existing synthetic file")

    @unittest.skipIf(__import__("importlib").util.find_spec("docx") is None, "python-docx not installed")
    def test_export_creates_canonical_docx_and_records_actual_path(self) -> None:
        case = self.prepare_export_case(self.workspace, "draft_review")
        source = case["markdown"]
        before = source.read_bytes()
        code, out, err = self.run_cli("export")
        self.assertEqual(code, 0, err)
        output = case["output_dir"] / f"Synthetic title{DOCX_SUFFIX}"
        self.assertTrue(output.is_file())
        self.assertEqual(source.read_bytes(), before)
        export_result = json.loads(out)
        self.assertEqual(export_result["status"], "generated_pending_delivery_check")
        self.assertFalse(export_result["workflow_complete"])
        self.assertTrue(export_result["post_export_delivery_check_required"])
        self.assertEqual(export_result["output_path"], str(output.resolve()))
        state = read_workflow_state(self.manifest.read_text(encoding="utf-8"))
        self.assertEqual(state["last_export"]["output_path"], str(output.resolve()))
        self.assertTrue(state["last_export"]["post_export_delivery_check_required"])
        self.assertNotIn("deliver", state["completed_gates"])
        self.assertIn("deliver", state["invalidated_gates"])
        first_delivery = next(
            item for item in state["last_check_result"]["gate_results"]
            if item["gate"] == "deliver"
        )
        self.assertEqual(first_delivery["status"], "failed")
        first_health_run = next(
            run for run in first_delivery["runs"]
            if any("health_check_delivery_package.py" in str(part) for part in run.get("cmd", []))
        )
        first_health = json.loads(first_health_run["stdout"])
        self.assertIn(
            {"name": "final DOCX exists at canonical path", "result": "fail", "details": ""},
            first_health["checks"],
        )

        # Exercise the real post-export route and delivery checker. The initial
        # export must not claim completion; only this independent check can do so.
        code, check_out, err = self.run_cli("check", "--gate", "all")
        self.assertEqual(code, 0, err)
        checked = json.loads(check_out)
        delivery = next(item for item in checked["gateResults"] if item["gate"] == "deliver")
        self.assertEqual(delivery["status"], "passed")
        self.assertTrue(delivery["checks_passed"])
        self.assertEqual(checked["workflow_mode"], "draft_review")
        health_run = next(
            run for run in delivery["runs"]
            if any("health_check_delivery_package.py" in str(part) for part in run.get("cmd", []))
        )
        health = json.loads(health_run["stdout"])
        self.assertTrue(health["checks_passed"])
        if "docx_render" in health["not_run"]:
            self.assertFalse(health["workflow_complete"])
            self.assertEqual(health["render"]["status"], "not_run")
            self.assertFalse(checked["workflow_complete"])
        else:
            self.assertTrue(health["workflow_complete"])

    @unittest.skipIf(__import__("importlib").util.find_spec("docx") is None, "python-docx not installed")
    def test_export_requires_reselected_map_and_checks_same_path_current_contents(self) -> None:
        case_workspace = self.workspace / "map-case"
        selected_map = case_workspace / "private" / "sensitive-map.json"
        self.write_sensitive_map(selected_map, "OLD-SYNTHETIC-MAP-TERM")
        case = self.prepare_export_case(
            case_workspace, "draft_review", sensitive_map=selected_map,
        )

        original_hash = workflow_cli._hash_file
        unauthorized_reads: list[Path] = []

        def refuse_unselected_map_read(path: Path) -> str:
            if Path(path).resolve() == selected_map.resolve():
                unauthorized_reads.append(Path(path))
                raise AssertionError("export read a map without explicit reselection")
            return original_hash(path)

        with patch.object(workflow_cli, "_hash_file", side_effect=refuse_unselected_map_read):
            code, _out, err = self.run_cli_at(case_workspace, "export")
        self.assertEqual(code, 2)
        self.assertIn("--sensitive-map", err)
        self.assertEqual(unauthorized_reads, [])
        self.assertFalse(list(case["output_dir"].glob("*.docx")))
        self.assertFalse(list(case["output_dir"].glob(".*.tmp.docx")))

        changed_term = "CURRENT-SYNTHETIC-SECRET-TERM"
        self.write_sensitive_map(selected_map, changed_term)
        code, _out, err = self.run_cli_at(
            case_workspace, "resume", "--sensitive-map", str(selected_map),
        )
        self.assertEqual(code, 0, err)
        resumed = json.loads(_out)
        self.assertEqual(set(resumed["invalidated_gates"]), {"review", "deliver"})
        self.assertTrue(resumed["conclusions_need_review"])
        case["markdown"].write_text(
            case["markdown"].read_text(encoding="utf-8").replace(
                "Synthetic body", changed_term,
            ),
            encoding="utf-8",
        )
        # Make the review current for this synthetic test version; map auditing
        # must still use the new bytes selected at the same path.
        self.create_export_review(
            case["markdown"], case["draft"], case["facts"], case["review_status"],
            workspace=case_workspace,
        )
        code, out, err = self.run_cli_at(
            case_workspace, "export", "--sensitive-map", str(selected_map),
        )
        self.assertEqual(code, 2)
        self.assertNotIn(changed_term, out + err)
        self.assertTrue(any(word in err.casefold() for word in ("sensitive-map", "sensitive map", "current")))
        self.assertFalse(list(case["output_dir"].glob("*.docx")))
        self.assertFalse(list(case["output_dir"].glob(".*.tmp.docx")))

    @unittest.skipIf(__import__("importlib").util.find_spec("docx") is None, "python-docx not installed")
    def test_export_records_the_frozen_map_and_review_snapshot_binding(self) -> None:
        selected_map = self.workspace / "snapshot" / "sensitive-map.json"
        self.write_sensitive_map(selected_map, "MAP-TERM-NOT-IN-SYNTHETIC-MATERIAL")
        case = self.prepare_export_case(
            self.workspace, "draft_review", sensitive_map=selected_map,
        )
        output = case["output_dir"] / f"Synthetic title{DOCX_SUFFIX}"
        code, _out, err = self.run_cli("export", "--sensitive-map", str(selected_map))
        self.assertEqual(code, 0, err)

        state = read_workflow_state(self.manifest.read_text(encoding="utf-8"))
        record = state["last_export"]
        snapshot = record["review_snapshot"]
        snapshot_payload = {key: value for key, value in snapshot.items() if key != "snapshot_sha256"}
        self.assertEqual(snapshot["snapshot_sha256"], canonical_json_sha256(snapshot_payload))
        self.assertEqual(snapshot["sensitive_map_sha256"], hashlib.sha256(selected_map.read_bytes()).hexdigest())
        audit = record["sensitive_map_audit"]
        self.assertEqual(audit["snapshot_sha256"], snapshot["sensitive_map_sha256"])
        self.assertEqual(audit["content_sha256"], snapshot["sensitive_map_sha256"])
        self.assertEqual(audit["review_snapshot_sha256"], snapshot["snapshot_sha256"])
        self.assertEqual(audit["review_version_sha256"], snapshot["review_version_sha256"])
        self.assertEqual(audit["docx_target_sha256"], hashlib.sha256(output.read_bytes()).hexdigest())

    @unittest.skipIf(__import__("importlib").util.find_spec("docx") is None, "python-docx not installed")
    def test_map_change_during_publication_removes_new_docx_or_restores_old_output(self) -> None:
        for preserve_existing in (False, True):
            with self.subTest(preserve_existing=preserve_existing):
                workspace = self.workspace / ("with-old-output" if preserve_existing else "new-output")
                selected_map = workspace / "private" / "sensitive-map.json"
                self.write_sensitive_map(selected_map, "ORIGINAL-SYNTHETIC-MAP-TERM")
                case = self.prepare_export_case(
                    workspace, "draft_review", sensitive_map=selected_map,
                )
                output = case["output_dir"] / f"Synthetic title{DOCX_SUFFIX}"
                old_bytes = b"old synthetic output to preserve" if preserve_existing else None
                if old_bytes is not None:
                    output.write_bytes(old_bytes)

                changed = "SYNTHETIC-MAP-CHANGED-DURING-PUBLISH"
                if preserve_existing:
                    original_replace = workflow_cli.os.replace

                    def replace_then_change_map(source, destination) -> None:
                        original_replace(source, destination)
                        if ".tmp.docx" in Path(source).name:
                            self.write_sensitive_map(selected_map, changed)

                    mutator = patch.object(workflow_cli.os, "replace", side_effect=replace_then_change_map)
                    arguments = ("export", "--overwrite", "--sensitive-map", str(selected_map))
                else:
                    original_link = workflow_cli.os.link

                    def link_then_change_map(source, destination) -> None:
                        original_link(source, destination)
                        self.write_sensitive_map(selected_map, changed)

                    mutator = patch.object(workflow_cli.os, "link", side_effect=link_then_change_map)
                    arguments = ("export", "--sensitive-map", str(selected_map))

                with mutator:
                    code, out, err = self.run_cli_at(workspace, *arguments)
                self.assertEqual(code, 2)
                self.assertNotIn(changed, out + err)
                self.assertIn("sensitive map changed during DOCX publication", err)
                if old_bytes is None:
                    self.assertFalse(output.exists())
                else:
                    self.assertEqual(output.read_bytes(), old_bytes)
                self.assertFalse(list(case["output_dir"].glob(".*.tmp.docx")))
                self.assertFalse(list(case["output_dir"].glob(".*.rollback")))

    @unittest.skipIf(__import__("importlib").util.find_spec("docx") is None, "python-docx not installed")
    def test_export_rejects_unconfirmed_sensitive_map_without_output(self) -> None:
        selected_map = self.workspace / "unconfirmed" / "sensitive-map.json"
        self.write_sensitive_map(selected_map, "UNCONFIRMED-SYNTHETIC-TERM", confirmed=False)
        case = self.prepare_export_case(
            self.workspace, "draft_review", sensitive_map=selected_map,
        )
        code, out, err = self.run_cli("export", "--sensitive-map", str(selected_map))
        self.assertEqual(code, 2)
        self.assertNotIn("UNCONFIRMED-SYNTHETIC-TERM", out + err)
        self.assertFalse(list(case["output_dir"].glob("*.docx")))
        self.assertFalse(list(case["output_dir"].glob(".*.tmp.docx")))

    @unittest.skipIf(__import__("importlib").util.find_spec("docx") is None, "python-docx not installed")
    def test_export_then_real_delivery_check_works_for_all_three_modes(self) -> None:
        for mode in ("full_research", "titled_evidence", "draft_review"):
            with self.subTest(mode=mode):
                workspace = self.workspace / mode
                case = self.prepare_export_case(workspace, mode)
                code, out, err = self.run_cli_at(workspace, "export")
                self.assertEqual(code, 0, f"{mode}: {err}")
                result = json.loads(out)
                self.assertEqual(result["status"], "generated_pending_delivery_check")
                self.assertFalse(result["workflow_complete"])
                self.assertTrue((case["output_dir"] / f"Synthetic title{DOCX_SUFFIX}").is_file())

                code, out, err = self.run_cli_at(workspace, "check", "--gate", "all")
                self.assertEqual(code, 0, f"{mode}: {err}")
                checked = json.loads(out)
                self.assertEqual(checked["workflow_mode"], mode)
                self.assertEqual(checked["required_gates"], [gate for gate, _ in workflow_cli.MODE_GATES[mode]])
                delivery = next(item for item in checked["gateResults"] if item["gate"] == "deliver")
                self.assertEqual(delivery["status"], "passed")
                self.assertTrue(delivery["checks_passed"])
                health_run = next(
                    run for run in delivery["runs"]
                    if any("health_check_delivery_package.py" in str(part) for part in run.get("cmd", []))
                )
                health = json.loads(health_run["stdout"])
                self.assertTrue(health["checks_passed"])
                self.assertFalse(health["errors"])

    @unittest.skipIf(__import__("importlib").util.find_spec("docx") is None, "python-docx not installed")
    def test_mode_switch_keeps_only_active_route_gate_state_and_invalidates_review(self) -> None:
        case = self.prepare_export_case(self.workspace, "full_research")
        code, _out, err = self.run_cli("export")
        self.assertEqual(code, 0, err)
        code, _out, err = self.run_cli("check", "--gate", "all")
        self.assertEqual(code, 0, err)

        code, out, err = self.run_cli(
            "resume", "--mode", "draft_review", "--draft", "input/draft.md",
        )
        self.assertEqual(code, 0, err)
        state = json.loads(out)
        self.assertEqual(state["workflow_mode"], "draft_review")
        self.assertEqual(set(state["invalidated_gates"]), {"review", "deliver"})
        self.assertFalse(set(state["completed_gates"]) & {"research", "prior-art", "draft"})
        self.assertTrue(state["conclusions_need_review"])
        self.assertTrue(case["manifest"].is_file())

    def test_export_refuses_after_resume_invalidates_reviewed_draft(self) -> None:
        case = self.prepare_export_case(self.workspace, "draft_review")
        case["draft"].write_text("Synthetic draft version two.", encoding="utf-8")
        code, _out, err = self.run_cli("resume")
        self.assertEqual(code, 0, err)
        state = read_workflow_state(self.manifest.read_text(encoding="utf-8"))
        self.assertTrue({"review", "deliver"}.issubset(set(state["invalidated_gates"])))

        code, _out, err = self.run_cli("export")
        self.assertEqual(code, 2)
        self.assertIn("current review", err)
        self.assertFalse(list(case["output_dir"].glob("*.docx")))
        self.assertFalse(list(case["output_dir"].glob(".*.tmp.docx")))

    def test_title_limit_is_strictly_under_twenty_five(self) -> None:
        too_long = "X" * 25
        code, _out, err = self.run_cli("init", "--mode", "draft_review", "--title", too_long)
        self.assertEqual(code, 2)
        self.assertIn("at most 24", err)
        self.assertFalse(self.manifest.exists())


if __name__ == "__main__":
    unittest.main()
