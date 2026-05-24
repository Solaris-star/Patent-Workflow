#!/usr/bin/env python3
"""Phase 9 delivery regression tests."""

import json
import sys
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from executors.phase_9_executor import PhaseExecutor  # noqa: E402


def write_workspace(workspace: Path) -> None:
    drafts = {
        "part_01_技术领域.md": "# 一、技术领域\n\n本发明涉及 AI 仓储质检技术领域，尤其涉及一种多源证据融合的质检方法及系统。",
        "part_02_背景技术.md": "# 二、背景技术\n\n## 2.1 与本申请相关的现有技术背景知识\n\n现有仓储质检方案通常分别依赖图像识别、条码识别、称重或人工复核等信息来源。\n\n## 2.2 与本申请相关的最接近的现有技术\n\nCN110910151A 等 CN 专利线索显示，相关方案仍需要在证据组织、结论追溯和多来源结果统一表达方面进一步改进。\n\n## 2.3 现有技术的缺陷和不足\n\n多种质检来源并存时，现有方案缺少统一的融合判断和追溯记录。",
        "part_03_发明内容.md": "# 三、发明内容\n\n## 3.1 本申请所需要解决的技术问题\n\n本发明要解决的技术问题在于：针对 AI 仓储质检场景下多来源质检证据分散、不同检测结论缺少统一融合依据以及质检结果难以追溯的问题，提供一种可复核、可追溯的多源证据融合质检方案。\n\n## 3.2 本申请的技术方案\n\n本发明包括多源质检数据采集单元、证据标准化单元、证据融合单元、质检结论生成单元和追溯记录单元。\n\n## 3.3 本申请的技术效果\n\n本发明能够统一多源质检结果表达，并支持异常结论追溯到原始记录。",
        "part_04_附图说明.md": "# 四、附图说明\n\n图 1 为系统架构图。\n\n```mermaid\ngraph TD\nA[图像/标签/称重/人工复核数据] --> B[多源质检数据采集单元]\nB --> C[证据标准化单元]\nC --> D[证据融合单元]\n```",
        "part_05_具体实施方式.md": "# 五、具体实施方式\n\nS101，如图 1 所示，采集仓储作业对象的多源质检数据。\n\nS102，如图 1 所示，将多源质检数据转换为统一格式的质检证据记录。\n\nS103，如图 1 所示，按照货物标识和质检项目关联质检证据记录，并生成可追溯的质检结论。",
    }
    for name, content in drafts.items():
        (workspace / name).write_text(content, encoding="utf-8")

    figure_dir = workspace / "附图"
    figure_dir.mkdir()
    (figure_dir / "fig_01_系统架构.png").write_bytes(b"png")
    (figure_dir / "fig_01_系统架构.mmd").write_text("graph TD; A-->B", encoding="utf-8")
    (figure_dir / "fig_01_系统架构.drawio").write_text("<mxfile />", encoding="utf-8")
    (figure_dir / "fig_02_方法流程.png").write_bytes(b"png")
    (figure_dir / "fig_02_方法流程.mmd").write_text("graph TD; A-->B", encoding="utf-8")
    (figure_dir / "fig_02_方法流程.drawio").write_text("<mxfile />", encoding="utf-8")

    (workspace / "artifacts" / "draft").mkdir(parents=True)
    (workspace / "artifacts" / "draft" / "facts_ledger.json").write_text(
        json.dumps(
            {
                "figure_registry": [
                    {
                        "figure_id": "图 1",
                        "artifacts": {
                            "image": "附图/fig_01_系统架构.png",
                            "mmd": "附图/fig_01_系统架构.mmd",
                            "editable": ["附图/fig_01_系统架构.drawio"],
                        },
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (workspace / "artifacts" / "draft" / "shared_context.json").write_text("{}", encoding="utf-8")
    (workspace / "artifacts" / "draft" / "phase_05_writing_plan.json").write_text("{}", encoding="utf-8")
    (workspace / "artifacts" / "draft" / "step_registry.json").write_text("{}", encoding="utf-8")
    (workspace / "artifacts" / "draft" / "figure_registry.json").write_text("{}", encoding="utf-8")
    (workspace / "artifacts" / "draft" / "terminology_registry.json").write_text("{}", encoding="utf-8")
    (workspace / "artifacts" / "draft" / "block_contexts").mkdir(parents=True)
    (workspace / "artifacts" / "draft" / "block_contexts" / "part_01.json").write_text("{}", encoding="utf-8")
    (workspace / "artifacts" / "draft" / "block_reviews").mkdir(parents=True)
    (workspace / "artifacts" / "draft" / "block_reviews" / "part_01.json").write_text("{}", encoding="utf-8")
    audit_dir = workspace / "artifacts" / "audit"
    audit_dir.mkdir(parents=True)
    (audit_dir / "phase_06_consistency_audit_report.md").write_text("pass", encoding="utf-8")
    (audit_dir / "phase_07_ipr_review_report.md").write_text("pass", encoding="utf-8")
    revision_dir = workspace / "artifacts" / "revision"
    revision_dir.mkdir(parents=True)
    (revision_dir / "phase_08_edit_plan.json").write_text("{}", encoding="utf-8")
    (revision_dir / "phase_08_structured_diff.json").write_text("{}", encoding="utf-8")
    (revision_dir / "phase_08_post_fix_check.json").write_text("{}", encoding="utf-8")
    (revision_dir / "phase_08_post_fix_check_report.md").write_text("pass", encoding="utf-8")
    research_dir = workspace / "artifacts" / "research"
    research_dir.mkdir(parents=True)
    (research_dir / "phase_02_research_pack.json").write_text("{}", encoding="utf-8")
    prior_art_dir = workspace / "artifacts" / "prior_art"
    prior_art_dir.mkdir(parents=True)
    (prior_art_dir / "phase_02_evidence_pack.json").write_text("{}", encoding="utf-8")
    (prior_art_dir / "phase_02_patent_candidate_pool.json").write_text("{}", encoding="utf-8")
    (prior_art_dir / "phase_02_patent_search_queries.txt").write_text("query", encoding="utf-8")


def test_phase_9_dirty_tree_does_not_crash_and_uses_embedded_mmd_figures() -> None:
    workspace = Path(tempfile.mkdtemp())
    deliver_dir = workspace / "deliver"
    write_workspace(workspace)
    executor = PhaseExecutor(
        "phase_9",
        workspace,
        {"patent_title": "测试专利", "output_dir": str(deliver_dir), "deliver_dir_explicit": True},
    )

    def create_docx(_merged, docx_path):
        docx_path.write_bytes(b"docx")
        return True

    with patch.object(executor, "_generate_docx", side_effect=create_docx), \
         patch.object(executor, "_check_dirty_tree", return_value={"is_dirty": True, "changed_files": ["a"], "untracked_files": [], "summary": "dirty"}), \
         patch.object(executor, "_run_health_check", return_value=True):
        result = executor._execute()

    assert result.status == "success"
    assert result.manifest_updates["delivery_from_dirty_tree"] is True
    assert not (deliver_dir / "附图").exists()
    assert "```mermaid" in (deliver_dir / "测试专利技术交底书.md").read_text(encoding="utf-8")


def test_phase_9_docx_generation_failure_fails_delivery() -> None:
    workspace = Path(tempfile.mkdtemp())
    deliver_dir = workspace / "deliver"
    write_workspace(workspace)
    executor = PhaseExecutor(
        "phase_9",
        workspace,
        {"patent_title": "测试专利", "output_dir": str(deliver_dir), "deliver_dir_explicit": True},
    )

    with patch.object(executor, "_generate_docx", return_value=False), \
         patch.object(executor, "_check_dirty_tree", return_value={"is_dirty": False, "changed_files": [], "untracked_files": [], "summary": ""}):
        result = executor._execute()

    assert result.status == "failed"
    assert result.error == "docx 生成失败"
    assert result.manifest_updates["delivery_passed"] is False
    assert result.manifest_updates["docx_generated"] is False
    assert result.manifest_updates["final_docx_path"].endswith("测试专利技术交底书.docx")


def test_phase_9_attempts_pandoc_install_when_missing() -> None:
    workspace = Path(tempfile.mkdtemp())
    write_workspace(workspace)
    executor = PhaseExecutor(
        "phase_9",
        workspace,
        {"patent_title": "测试专利", "output_dir": str(workspace / "deliver"), "deliver_dir_explicit": True},
    )
    calls = []

    def fake_which(name):
        if name == "pandoc":
            return None if not calls else "/opt/homebrew/bin/pandoc"
        if name == "brew":
            return "/opt/homebrew/bin/brew"
        return None

    def fake_run(cmd, **_kwargs):
        calls.append(cmd)
        class Result:
            returncode = 0
            stdout = "installed"
            stderr = ""
        return Result()

    with patch("executors.phase_9_executor.shutil.which", side_effect=fake_which), \
         patch("executors.phase_9_executor.subprocess.run", side_effect=fake_run):
        assert executor._ensure_pandoc_available() is True

    assert calls == [["/opt/homebrew/bin/brew", "install", "pandoc"]]


def test_phase_9_requires_explicit_deliver_dir() -> None:
    workspace = Path(tempfile.mkdtemp())
    write_workspace(workspace)
    executor = PhaseExecutor(
        "phase_9",
        workspace,
        {"patent_title": "测试专利"},
    )

    def create_docx(_merged, docx_path):
        docx_path.write_bytes(b"docx")
        return True

    with patch.object(executor, "_generate_docx", side_effect=create_docx), \
         patch.object(executor, "_check_dirty_tree", return_value={"is_dirty": False, "changed_files": [], "untracked_files": [], "summary": ""}), \
         patch.object(executor, "_run_health_check", return_value=True):
        result = executor._execute()

    report = json.loads((workspace / "artifacts" / "delivery" / "phase_09_delivery_health_report.json").read_text(encoding="utf-8"))
    assert result.status == "failed"
    assert result.error == "最终交付目录未明确指定"
    assert result.manifest_updates["deliver_dir_explicit"] is False
    assert result.manifest_updates["delivery_passed"] is False
    assert report["pass_fail"] == "fail"
    assert "最终交付目录未明确指定" in report["missing_items"]


def test_phase_9_merged_markdown_contains_embedded_mmd_not_image_refs() -> None:
    workspace = Path(tempfile.mkdtemp())
    write_workspace(workspace)
    executor = PhaseExecutor(
        "phase_9",
        workspace,
        {"patent_title": "测试专利", "output_dir": str(workspace / "deliver"), "deliver_dir_explicit": True},
    )

    merged = executor._merge_draft_blocks()

    assert "# 四、附图说明" in merged
    assert "```mermaid" in merged
    assert "![图 1](附图/fig_01_系统架构.png)" not in merged


def test_phase_9_runs_cleanup_before_health_check() -> None:
    workspace = Path(tempfile.mkdtemp())
    deliver_dir = workspace / "deliver"
    write_workspace(workspace)
    stale_docx = deliver_dir / "旧版技术交底书.docx"
    executor = PhaseExecutor(
        "phase_9",
        workspace,
        {"patent_title": "测试专利", "output_dir": str(deliver_dir), "deliver_dir_explicit": True},
    )

    def create_docx(_merged, docx_path):
        docx_path.write_bytes(b"docx")
        stale_docx.write_bytes(b"old")
        return True

    def assert_cleaned_before_health(_deliver_dir, _patent_title, _docx_path):
        assert not stale_docx.exists()
        return True

    with patch.object(executor, "_generate_docx", side_effect=create_docx), \
         patch.object(executor, "_check_dirty_tree", return_value={"is_dirty": False, "changed_files": [], "untracked_files": [], "summary": ""}), \
         patch.object(executor, "_run_health_check", side_effect=assert_cleaned_before_health):
        result = executor._execute()

    assert result.status == "success"
    assert not stale_docx.exists()
    assert (workspace / "artifacts" / "delivery" / "archived_delivery_files" / stale_docx.name).exists()


def test_phase_9_rejects_contaminated_draft_before_delivery() -> None:
    workspace = Path(tempfile.mkdtemp())
    deliver_dir = workspace / "deliver"
    write_workspace(workspace)
    (workspace / "part_01_技术领域.md").write_text(
        "# 一、技术领域\n\n本发明适用于冷链物流中心，包括但不限于多个场景。\n\n<!-- ED-002: 需扩展内容以满足字数要求 -->",
        encoding="utf-8",
    )
    executor = PhaseExecutor(
        "phase_9",
        workspace,
        {"patent_title": "测试专利", "output_dir": str(deliver_dir), "deliver_dir_explicit": True},
    )

    with patch.object(executor, "_generate_docx") as generate_docx, \
         patch.object(executor, "_check_dirty_tree", return_value={"is_dirty": False, "changed_files": [], "untracked_files": [], "summary": ""}):
        result = executor._execute()

    assert result.status == "failed"
    assert result.error == "正文质量门禁未通过"
    generate_docx.assert_not_called()


def test_phase_9_creates_ascii_safe_delivery_zip() -> None:
    workspace = Path(tempfile.mkdtemp())
    deliver_dir = workspace / "deliver"
    write_workspace(workspace)
    executor = PhaseExecutor(
        "phase_9",
        workspace,
        {"patent_title": "测试专利", "output_dir": str(deliver_dir), "deliver_dir_explicit": True},
    )

    def create_docx(_merged, docx_path):
        docx_path.write_bytes(b"docx")
        docx_path.with_suffix(".md").write_text("markdown", encoding="utf-8")
        return True

    with patch.object(executor, "_generate_docx", side_effect=create_docx), \
         patch.object(executor, "_check_dirty_tree", return_value={"is_dirty": False, "changed_files": [], "untracked_files": [], "summary": ""}), \
         patch.object(executor, "_run_health_check", return_value=True):
        result = executor._execute()

    zip_path = Path(result.manifest_updates["delivery_zip_path"])
    assert zip_path.name == "patent_delivery_package.zip"
    with zipfile.ZipFile(zip_path, "r") as archive:
        names = archive.namelist()
    assert "final/patent_disclosure.docx" in names
    assert "README.md" in names
    assert not any(name.startswith("figures/") for name in names)
    assert "artifacts/DELIVERY_ARTIFACTS_INDEX.json" in names
    assert "artifacts/draft/facts_ledger.json" in names
    assert "artifacts/draft/block_contexts/part_01.json" in names
    assert (deliver_dir / "artifacts" / "DELIVERY_ARTIFACTS_INDEX.json").exists()
    assert all(name.isascii() for name in names)


def test_phase_9_health_check_rejects_extra_root_docx_after_cleanup_gate() -> None:
    workspace = Path(tempfile.mkdtemp())
    deliver_dir = workspace / "deliver"
    deliver_dir.mkdir()
    write_workspace(workspace)
    final_docx = deliver_dir / "测试专利技术交底书.docx"
    stale_docx = deliver_dir / "其他技术交底书.docx"
    for docx in [final_docx, stale_docx]:
        with zipfile.ZipFile(docx, "w") as z:
            z.writestr("word/document.xml", "<w:document />")
            z.writestr("word/media/image1.png", b"png")

    from health_check_delivery_package import main as health_main  # noqa: E402

    argv = [
        "health_check_delivery_package.py",
        "--deliver-dir", str(deliver_dir),
        "--patent-title", "测试专利",
        "--facts-ledger", str(workspace / "artifacts" / "draft" / "facts_ledger.json"),
        "--consistency-report", str(workspace / "artifacts" / "audit" / "phase_06_consistency_audit_report.md"),
        "--ipr-report", str(workspace / "artifacts" / "audit" / "phase_07_ipr_review_report.md"),
        "--out", str(workspace / "artifacts" / "delivery" / "phase_09_delivery_health_report.json"),
        "--base-dir", str(workspace),
    ]
    with patch.object(sys, "argv", argv):
        exit_code = health_main()

    report = json.loads((workspace / "artifacts" / "delivery" / "phase_09_delivery_health_report.json").read_text(encoding="utf-8"))
    assert exit_code == 2
    assert any(c["name"] == "delivery root contains only final docx" and c["result"] == "fail" for c in report["checks"])


if __name__ == "__main__":
    test_phase_9_dirty_tree_does_not_crash_and_uses_embedded_mmd_figures()
    test_phase_9_docx_generation_failure_fails_delivery()
    test_phase_9_attempts_pandoc_install_when_missing()
    test_phase_9_requires_explicit_deliver_dir()
    test_phase_9_merged_markdown_contains_embedded_mmd_not_image_refs()
    test_phase_9_runs_cleanup_before_health_check()
    test_phase_9_rejects_contaminated_draft_before_delivery()
    test_phase_9_creates_ascii_safe_delivery_zip()
    test_phase_9_health_check_rejects_extra_root_docx_after_cleanup_gate()
    print("phase_9_executor regression tests passed")
