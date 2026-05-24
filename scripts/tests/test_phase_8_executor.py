#!/usr/bin/env python3
"""Phase 8 revision loop regression tests."""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from executors.phase_8_executor import PhaseExecutor  # noqa: E402
from executors.base_executor import ExecutorResult  # noqa: E402
from validate_structured_diff import main as validate_structured_diff_main  # noqa: E402


def write_reports(workspace: Path) -> None:
    audit_dir = workspace / "artifacts" / "audit"
    audit_dir.mkdir(parents=True)
    (audit_dir / "phase_06_consistency_audit_report.md").write_text(
        """# 一致性审计报告

### Top 问题

1. **MEDIUM** | part_05_具体实施方式.md
   - 症状: 发现禁用用语: '客户'
   - 建议: 将 '客户' 替换为专利规范用语

## 结论
- `pass_fail`: fail
""",
        encoding="utf-8",
    )
    (audit_dir / "phase_07_ipr_review_report.md").write_text(
        """# IPR 模拟审查报告

## Top 风险点

1. **MEDIUM** | 证据来源可追溯性不足
   - 原因: 专利证据缺少可信 URL
   - 建议: 补充可信专利 URL

## 结论
- `pass_fail_suggested`: fail
""",
        encoding="utf-8",
    )
    (workspace / "part_05_具体实施方式.md").write_text("五、具体实施方式\n客户可以执行该步骤。进一步说明保留。", encoding="utf-8")


def fake_phase_result(phase_id, workspace, manifest):
    def execute():
        report_name = "phase_06_consistency_audit_report.md" if phase_id == "phase_6" else "phase_07_ipr_review_report.md"
        (workspace / "artifacts" / "audit").mkdir(parents=True, exist_ok=True)
        (workspace / "artifacts" / "audit" / report_name).write_text(
            f"# regenerated {phase_id}\n\n- `pass_fail`: pass\n",
            encoding="utf-8",
        )
        return ExecutorResult(status="success", manifest_updates={f"{phase_id}_rerun": True})
    return execute


def test_phase_8_replace_edits_use_validator_change_kind() -> None:
    workspace = Path(tempfile.mkdtemp())
    write_reports(workspace)
    executor = PhaseExecutor("phase_8", workspace, {})
    edit_plan = {
        "edits": [
            {
                "edit_id": "ED-001",
                "type": "replace",
                "target": {"section": "part_05_具体实施方式.md"},
            }
        ]
    }

    _, structured_diff = executor._apply_edits(edit_plan, workspace)
    diff_path = workspace / "artifacts" / "revision" / "phase_08_structured_diff.json"
    plan_path = workspace / "artifacts" / "revision" / "phase_08_edit_plan.json"
    diff_path.parent.mkdir(parents=True, exist_ok=True)
    diff_path.write_text(json.dumps(structured_diff, ensure_ascii=False), encoding="utf-8")
    plan_path.write_text(json.dumps({"doc_type": "edit_plan", "phase": "phase_8", "edits": edit_plan["edits"]}, ensure_ascii=False), encoding="utf-8")

    argv = ["validate_structured_diff.py", str(diff_path), "--edit-plan", str(plan_path)]
    with patch.object(sys, "argv", argv):
        exit_code = validate_structured_diff_main()

    assert structured_diff["diff_items"][0]["change_kind"] in {"add", "delete", "replace", "move"}
    assert exit_code == 0


def test_phase_8_allows_empty_structured_diff_when_post_fix_passes() -> None:
    workspace = Path(tempfile.mkdtemp())
    revision_dir = workspace / "artifacts" / "revision"
    revision_dir.mkdir(parents=True)
    diff_path = revision_dir / "phase_08_structured_diff.json"
    plan_path = revision_dir / "phase_08_edit_plan.json"
    post_path = revision_dir / "phase_08_post_fix_check.json"
    diff_path.write_text(json.dumps({"doc_type": "structured_diff", "phase": "phase_8", "diff_items": [], "total_edits_planned": 3}, ensure_ascii=False), encoding="utf-8")
    plan_path.write_text(json.dumps({"doc_type": "edit_plan", "phase": "phase_8", "edits": [{"edit_id": "ED-001"}]}, ensure_ascii=False), encoding="utf-8")
    post_path.write_text(json.dumps({"content_fix_passed": True, "review_loop_passed": True, "post_fix_passed": True}, ensure_ascii=False), encoding="utf-8")

    argv = [
        "validate_structured_diff.py",
        str(diff_path),
        "--edit-plan",
        str(plan_path),
        "--post-fix-check",
        str(post_path),
    ]
    with patch.object(sys, "argv", argv):
        exit_code = validate_structured_diff_main()

    assert exit_code == 0


def test_phase_8_reruns_executors_and_writes_markdown_report() -> None:
    workspace = Path(tempfile.mkdtemp())
    write_reports(workspace)
    calls = []

    def factory(phase_id, workspace_arg, manifest_arg):
        calls.append(phase_id)
        return fake_phase_result(phase_id, workspace_arg, manifest_arg)

    executor = PhaseExecutor("phase_8", workspace, {})
    with patch.object(executor, "_make_review_executor", side_effect=factory):
        result = executor._execute()

    report_path = workspace / "artifacts" / "revision" / "phase_08_post_fix_check_report.md"
    report_text = report_path.read_text(encoding="utf-8")
    part05_text = (workspace / "part_05_具体实施方式.md").read_text(encoding="utf-8")

    assert calls == ["phase_6", "phase_7"]
    assert report_text.startswith("# 审后修订与复审闭环报告")
    assert result.manifest_updates["review_loop_results"]["phase_results"][0]["rerun_mode"] == "executor"
    assert "客户" not in part05_text
    assert "进一步" in part05_text


if __name__ == "__main__":
    test_phase_8_replace_edits_use_validator_change_kind()
    test_phase_8_allows_empty_structured_diff_when_post_fix_passes()
    test_phase_8_reruns_executors_and_writes_markdown_report()
    print("phase_8_executor regression tests passed")
