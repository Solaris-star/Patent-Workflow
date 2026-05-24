"""Orchestrator manifest bootstrap regression tests."""

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from orchestrate import Orchestrator  # noqa: E402
from validators.preflight_validator import PreflightValidator  # noqa: E402


def test_preflight_accepts_phase_0_cache_without_markdown_manifest() -> None:
    workspace = Path(tempfile.mkdtemp())
    (workspace / "artifacts" / "preprocess").mkdir(parents=True, exist_ok=True)
    (workspace / "artifacts" / "run_manifest.json").write_text(
        json.dumps({"run_id": "test-run", "current_phase": "phase_0", "output_dir": str(workspace)}),
        encoding="utf-8",
    )
    (workspace / "artifacts" / "preprocess" / "source_fingerprints.json").write_text(
        json.dumps({"sources": []}),
        encoding="utf-8",
    )
    (workspace / "artifacts" / "preprocess" / "phase_00_preprocess_notes.md").write_text(
        "ok",
        encoding="utf-8",
    )

    validator = PreflightValidator(workspace, workspace / "artifacts" / "run_manifest.md")
    passed, issues = validator.run()

    assert passed is True
    assert any(issue.category == "manifest" and issue.level == "warning" for issue in issues)


def test_orchestrator_bootstraps_markdown_manifest_from_json_cache() -> None:
    workspace = Path(tempfile.mkdtemp())
    (workspace / "artifacts" / "preprocess").mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": "test-run",
        "current_phase": "phase_0",
        "output_dir": str(workspace),
        "domain_scope": "智能仓储",
        "source_fingerprints": [],
    }
    (workspace / "artifacts" / "run_manifest.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    (workspace / "artifacts" / "preprocess" / "source_fingerprints.json").write_text(
        json.dumps({"sources": []}, ensure_ascii=False),
        encoding="utf-8",
    )
    (workspace / "artifacts" / "preprocess" / "phase_00_preprocess_notes.md").write_text("ok", encoding="utf-8")

    orchestrator = Orchestrator(
        workspace=workspace,
        manifest_path=workspace / "artifacts" / "run_manifest.md",
        from_phase="phase_0",
    )

    manifest_md = workspace / "artifacts" / "run_manifest.md"
    assert manifest_md.exists()
    content = manifest_md.read_text(encoding="utf-8")
    assert "test-run" in content
    assert "智能仓储" in content
    assert orchestrator.manifest.get("run_id") == "test-run"


if __name__ == "__main__":
    test_preflight_accepts_phase_0_cache_without_markdown_manifest()
    test_orchestrator_bootstraps_markdown_manifest_from_json_cache()
    print("orchestrator_manifest_bootstrap tests passed")
