#!/usr/bin/env python3
"""Content quality guardrail tests for patent workflow drafts."""

import sys
import tempfile
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from executors.phase_5_executor import PhaseExecutor as Phase5Executor  # noqa: E402
from executors.phase_8_executor import PhaseExecutor as Phase8Executor  # noqa: E402


def test_phase_8_expand_edits_do_not_insert_placeholder_comments() -> None:
    workspace = Path(tempfile.mkdtemp())
    (workspace / "part_01_技术领域.md").write_text("# 一、技术领域\n\n本发明涉及 AI 仓储质检技术领域。", encoding="utf-8")
    executor = Phase8Executor("phase_8", workspace, {})
    edit_plan = {
        "edits": [
            {
                "edit_id": "ED-001",
                "type": "expand",
                "target": {"section": "part_01_技术领域.md"},
            }
        ]
    }

    applied, structured_diff = executor._apply_edits(edit_plan, workspace)
    content = (workspace / "part_01_技术领域.md").read_text(encoding="utf-8")

    assert applied == []
    assert structured_diff["diff_items"] == []
    assert "<!--" not in content
    assert "需扩展内容" not in content


def test_phase_5_skeletons_follow_patent_content_guardrails() -> None:
    workspace = Path(tempfile.mkdtemp())
    executor = Phase5Executor("phase_5", workspace, {})
    context = {
        "project": {
            "title": "基于多源证据融合的AI仓储质检方法及系统",
            "domain_scope": "AI仓储质检",
            "selected_direction": "基于多源证据融合的AI仓储质检方法及系统",
        },
        "evidence": [
            {"evidence_id": "EV-001", "publicationNumber": "CN110910151A", "excerpt": "CN 专利证据"},
            {"evidence_id": "EV-002", "publicationNumber": "WO2024000000A1", "excerpt": "WO 外围证据"},
        ],
    }

    part01 = executor._make_skeleton({"id": "part_01", "name": "技术领域", "file": "part_01_技术领域.md"}, context)
    part02 = executor._make_skeleton({"id": "part_02", "name": "背景技术", "file": "part_02_背景技术.md"}, context)
    part03 = executor._make_skeleton({"id": "part_03", "name": "发明内容", "file": "part_03_发明内容.md"}, context)
    part04 = executor._make_skeleton({"id": "part_04", "name": "附图说明", "file": "part_04_附图说明.md"}, context)
    part05 = executor._make_skeleton({"id": "part_05", "name": "具体实施方式", "file": "part_05_具体实施方式.md"}, context)

    combined = "\n".join([part01, part02, part03, part04, part05])
    assert "包括但不限于" not in part01
    assert "冷链" not in part01
    assert "医药仓储" not in part01
    assert "WO2024000000A1" not in part02
    assert "本发明要解决的技术问题在于，克服" not in part03
    assert "本发明要解决的技术问题在于" in part03
    assert "```mermaid" in part04
    assert "图 1" in part05 and "图 2" in part05
    assert "98." not in combined
    assert "毫秒" not in combined
    assert "公式" not in combined


def test_phase_5_regenerates_contaminated_existing_blocks() -> None:
    workspace = Path(tempfile.mkdtemp())
    (workspace / "artifacts" / "research").mkdir(parents=True)
    (workspace / "artifacts" / "prior_art").mkdir(parents=True)
    (workspace / "artifacts" / "research" / "phase_02_research_pack.json").write_text(
        json.dumps(
            {
                "recommended_direction_detail": {"title": "基于多源证据融合的AI仓储质检方法"},
                "evidence_table": [
                    {"evidence_id": "EV-001", "excerpt": "多源质检证据需要统一追溯。"}
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (workspace / "artifacts" / "prior_art" / "phase_02_evidence_pack.json").write_text(
        json.dumps(
            {
                "final_relevant_patents": [
                    {"publicationNumber": "CN110910151A", "title": "仓储质检相关专利"},
                    {"publicationNumber": "WO2024000000A1", "title": "非 CN 外围专利"},
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    contaminated = """# 一、技术领域

本发明适用于仓储物流环境中对入库、出库、在库存储环节的商品实施自动化质量检验，包括但不限于外观缺陷检测、包装完整性评估、标签正确性验证和数量一致性核查等质检任务。本发明的技术方案可以部署于冷链物流中心以及医药仓储等各类智能仓储场景，具备广泛的工业适用性。

<!-- ED-002: 需扩展内容以满足字数要求 -->
"""
    (workspace / "part_01_技术领域.md").write_text(contaminated, encoding="utf-8")

    result = Phase5Executor("phase_5", workspace, {"domain_scope": "AI仓储质检"})._execute()
    rewritten = (workspace / "part_01_技术领域.md").read_text(encoding="utf-8")

    assert result.status in {"success", "partial"}
    assert "<!--" not in rewritten
    assert "包括但不限于" not in rewritten
    assert "冷链" not in rewritten
    review = json.loads((workspace / "artifacts" / "draft" / "block_reviews" / "part_01_review.json").read_text(encoding="utf-8"))
    assert not [item for item in review["findings"] if item["severity"] in {"high", "medium"}]
    backups = list((workspace / "artifacts" / "draft" / "superseded_blocks").glob("part_01_技术领域.md.*.bak"))
    assert backups


if __name__ == "__main__":
    test_phase_8_expand_edits_do_not_insert_placeholder_comments()
    test_phase_5_skeletons_follow_patent_content_guardrails()
    test_phase_5_regenerates_contaminated_existing_blocks()
    print("phase_content_quality tests passed")
