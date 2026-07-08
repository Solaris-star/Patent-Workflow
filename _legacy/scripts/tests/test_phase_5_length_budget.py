"""Phase 5 section length budget regression tests."""

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from executors.phase_5_executor import PhaseExecutor, DRAFT_BLOCKS  # noqa: E402


def _executor() -> PhaseExecutor:
    return PhaseExecutor("phase_5", Path(tempfile.mkdtemp()), {"patent_title": "测试专利"})


def test_writing_plan_contains_section_word_budget() -> None:
    executor = _executor()
    shared_context = {"context_hash": "abc"}

    plan = executor._build_writing_plan("测试专利", "仓储物流", "仓储质检", {}, shared_context)

    assert "section_word_budget" in plan
    assert plan["section_word_budget"]["part_01"]["target_min_chars"] == 50
    assert plan["section_word_budget"]["part_05"]["target_max_chars"] == 3500
    assert plan["section_word_budget"]["part_04"]["target_min_chars"] == 30
    assert plan["section_word_budget"]["part_04"]["target_max_chars"] == 120
    assert plan["section_word_budget"]["part_04"]["target_min_figures"] == 4
    assert plan["section_word_budget"]["part_04"]["requires_mmd_per_figure"] is True
    assert "不包含 Mermaid/mmd 代码块" in plan["section_word_budget"]["part_04"]["counting_rule"]
    assert "为什么" not in plan["section_word_budget"]["part_01"]["reason"]


def test_block_review_records_length_check() -> None:
    executor = _executor()
    block = next(item for item in DRAFT_BLOCKS if item["id"] == "part_01")
    content = "本发明涉及AI仓储质检技术领域，特别涉及一种仓储质检方法。" + "字" * 35
    context = {
        "project": {"title": "测试专利", "selected_direction": "仓储质检", "domain_scope": "仓储物流"},
        "evidence": [],
        "shared_context_path": "artifacts/draft/shared_context.json",
        "shared_context_hash": "hash",
    }
    shared_context = {
        "context_hash": "hash",
        "budget": {"within_budget": True},
        "canonical_terms": [{"term": "仓储质检"}],
        "steps": [{"step_id": "S101"}],
        "figures": [{"figure_id": "图 1"}],
    }

    review = executor._review_block(block, content, context, shared_context)

    assert review["char_count"] == len(content)
    assert review["target_min_chars"] == 50
    assert review["target_max_chars"] == 150
    assert review["length_check"]["length_status"] == "pass"
    assert review["checks"]["length_within_target_range"] is True


def test_part_04_counts_natural_language_and_checks_mmd_structure() -> None:
    executor = _executor()
    block = next(item for item in DRAFT_BLOCKS if item["id"] == "part_04")
    captions = "四、专利附图\n" + "\n".join([
        "图 1 为系统架构图。",
        "图 2 为方法流程图。",
        "图 3 为证据记录结构图。",
        "图 4 为追溯关系图。",
    ]) + "\n" + "图中仅示意模块、步骤和证据关系。"
    content = captions + "\n" + "\n".join([
        "```mermaid\ngraph TD\nA[采集]-->B[融合]\n```",
        "```mmd\nflowchart TD\nS101-->S102\n```",
        "```mermaid\nerDiagram\n证据记录 ||--|| 货物 : 关联\n```",
        "```mermaid\ngraph LR\nC[结论]-->D[原始证据]\n```",
    ])
    context = {
        "project": {"title": "测试专利", "selected_direction": "仓储质检", "domain_scope": "仓储物流"},
        "evidence": [],
        "shared_context_path": "artifacts/draft/shared_context.json",
        "shared_context_hash": "hash",
    }
    shared_context = {
        "context_hash": "hash",
        "budget": {"within_budget": True},
        "canonical_terms": [{"term": "仓储质检"}],
        "steps": [{"step_id": "S101"}],
        "figures": [{"figure_id": f"图 {idx}"} for idx in range(1, 5)],
    }

    review = executor._review_block(block, content, context, shared_context)

    assert review["char_count"] < review["total_char_count"]
    assert review["length_check"]["length_status"] == "pass"
    assert review["figure_structure_check"]["figure_count"] == 4
    assert review["figure_structure_check"]["mmd_block_count"] == 4
    assert review["checks"]["figure_structure_passed"] is True


def test_part_04_flags_missing_mmd_per_figure() -> None:
    executor = _executor()
    block = next(item for item in DRAFT_BLOCKS if item["id"] == "part_04")
    content = "四、专利附图\n图 1 为系统架构图。图 2 为方法流程图。图 3 为证据记录结构图。图 4 为追溯关系图。" + "说明" * 60 + "\n```mermaid\ngraph TD\nA-->B\n```"
    context = {
        "project": {"title": "测试专利", "selected_direction": "仓储质检", "domain_scope": "仓储物流"},
        "evidence": [],
        "shared_context_path": "artifacts/draft/shared_context.json",
        "shared_context_hash": "hash",
    }
    shared_context = {
        "context_hash": "hash",
        "budget": {"within_budget": True},
        "canonical_terms": [{"term": "仓储质检"}],
        "steps": [{"step_id": "S101"}],
        "figures": [{"figure_id": f"图 {idx}"} for idx in range(1, 5)],
    }

    review = executor._review_block(block, content, context, shared_context)

    assert review["checks"]["figure_structure_passed"] is False
    assert any("每图对应 Mermaid/mmd" in finding["issue"] for finding in review["findings"])


def test_block_review_flags_too_short_length() -> None:
    executor = _executor()
    block = next(item for item in DRAFT_BLOCKS if item["id"] == "part_03")
    context = {
        "project": {"title": "测试专利", "selected_direction": "仓储质检", "domain_scope": "仓储物流"},
        "evidence": [],
        "shared_context_path": "artifacts/draft/shared_context.json",
        "shared_context_hash": "hash",
    }
    shared_context = {
        "context_hash": "hash",
        "budget": {"within_budget": True},
        "canonical_terms": [{"term": "仓储质检"}],
        "steps": [{"step_id": "S101"}],
        "figures": [{"figure_id": "图 1"}],
    }

    review = executor._review_block(block, "短内容", context, shared_context)

    assert review["length_check"]["length_status"] == "too_short"
    assert any("字数低于建议范围" in finding["issue"] for finding in review["findings"])


def test_local_project_redaction_filters_sensitive_terms_only_when_local_material_exists() -> None:
    executor = PhaseExecutor("phase_5", Path(tempfile.mkdtemp()), {"local_project_paths": ["docs/project"]})
    research_inputs = {
        "research_evidence": [
            {
                "source_type": "local_project",
                "title": "AcmeVision 客户A 每日 12000 件质检流程",
                "excerpt": "AcmeVision 在 /srv/acme/prod 中处理客户A订单，每日12000件，使用类别1和类别2。",
                "claim_supported": "AcmeVision 产品在客户A场景下形成质检闭环。",
            }
        ]
    }

    policy = executor._build_redaction_policy(research_inputs)
    filtered = executor._apply_redaction_filter("AcmeVision 为客户A处理每日12000件，路径 /srv/acme/prod，分类类别1。", policy)
    online_only_policy = PhaseExecutor("phase_5", Path(tempfile.mkdtemp()), {}). _build_redaction_policy({"research_evidence": []})

    assert policy["enabled"] is True
    assert "AcmeVision" not in filtered
    assert "客户A" not in filtered
    assert "/srv/acme/prod" not in filtered
    assert "每日一定规模" in filtered
    assert "某系统" in filtered
    assert online_only_policy["enabled"] is False


def test_block_context_prefers_source_reading_notes_for_writing() -> None:
    executor = _executor()
    block = next(item for item in DRAFT_BLOCKS if item["id"] == "part_02")
    research_inputs = {
        "research_evidence": [],
        "patent_evidence": [],
        "final_relevant_patents": [],
        "source_reading_notes": [
            {
                "note_id": "RN-001",
                "source_type": "hotspot",
                "url": "https://example.com/hotspot",
                "page_summary": "热点文章总结了智能驾驶链路异常预警需求。",
                "key_technical_facts": ["需要端到端追踪链路异常。"],
                "usable_in_writing": True,
            }
        ],
    }
    shared_context = {"context_hash": "hash", "canonical_terms": [], "steps": [], "figures": [], "locked_facts": []}

    context = executor._build_block_context(block, "测试专利", "智能驾驶", "链路异常预警", research_inputs, shared_context)

    assert context["source_reading_notes"][0]["note_id"] == "RN-001"
    assert "链路异常预警" in context["source_reading_notes"][0]["page_summary"]


def test_part_02_prefers_phase_2_patent_metadata_when_available() -> None:
    executor = _executor()
    shared_context = {"context_hash": "hash", "canonical_terms": [], "steps": [], "figures": [], "locked_facts": [], "preprocess_context": {"patent_references": [{"publicationNumber": "CN121526509A", "title": "参考专利用于风格"}]}}
    block = next(item for item in DRAFT_BLOCKS if item["id"] == "part_02")
    research_inputs = {
        "research_evidence": [],
        "patent_evidence": [],
        "final_relevant_patents": [
            {
                "publicationNumber": "CN202410000001A",
                "title": "一种智能仓储异常检测方法",
                "abstract": "该专利公开了通过图像识别与状态采集协同执行仓储异常检测的技术方案。",
                "source_url": "https://example.com/patent/CN202410000001A",
            }
        ],
        "source_reading_notes": [],
    }

    block_context = executor._build_block_context(block, "测试专利", "智能仓储", "异常检测交底书", research_inputs, shared_context)
    skeleton = executor._make_skeleton(block, block_context)

    assert "CN202410000001A" in skeleton
    assert "一种智能仓储异常检测方法" in skeleton
    assert "图像识别与状态采集协同执行仓储异常检测" in skeleton
    assert "CN121526509A" not in skeleton


def test_check_template_and_style_uses_preprocess_index_paths() -> None:
    workspace = Path(tempfile.mkdtemp())
    preprocess_dir = workspace / "artifacts" / "preprocess"
    preprocess_dir.mkdir(parents=True, exist_ok=True)
    (preprocess_dir / "preprocess_index.json").write_text(
        '{"artifacts": {"template_structure_rules": "artifacts/preprocess/template_structure_rules.json", "reference_style_profile": "artifacts/preprocess/reference_style_profile.json", "compliance_rules": "artifacts/preprocess/compliance_rules.json"}}',
        encoding="utf-8",
    )
    (preprocess_dir / "template_structure_rules.json").write_text('{"sections": [{"id": "part_01", "name": "技术领域"}]}', encoding="utf-8")
    (preprocess_dir / "reference_style_profile.json").write_text('{"writing_principles": ["解释型说明书笔法"], "extracted_examples": ["下面对照附图作进一步详细说明"], "patent_references": [{"publicationNumber": "CN121526509A", "title": "一种智能项目规划方法"}]}', encoding="utf-8")
    (preprocess_dir / "compliance_rules.json").write_text('{"rules": [{"rule_id": "CR-001", "text": "说明书应当清楚完整"}]}', encoding="utf-8")

    executor = PhaseExecutor("phase_5", workspace, {"preprocess_index_path": "artifacts/preprocess/preprocess_index.json"})

    template_ready, style_ready = executor._check_template_and_style()
    shared_context = executor._build_shared_context("测试专利", "智能制造", "智能制造交底书", {"research_evidence": [], "patent_evidence": [], "final_relevant_patents": []})
    block = next(item for item in DRAFT_BLOCKS if item["id"] == "part_02")
    block_context = executor._build_block_context(block, "测试专利", "智能制造", "智能制造交底书", {"research_evidence": [], "patent_evidence": [], "final_relevant_patents": []}, shared_context)
    skeleton = executor._make_skeleton(block, block_context)

    assert template_ready is True
    assert style_ready is True
    assert shared_context["preprocess_context"]["template_sections"][0] == "技术领域"
    assert shared_context["preprocess_context"]["style_examples"][0] == "下面对照附图作进一步详细说明"
    assert shared_context["preprocess_context"]["compliance_rules"][0] == "说明书应当清楚完整"
    assert "CN121526509A" in skeleton
    assert "如中国专利 CN121526509A" in skeleton


if __name__ == "__main__":
    test_writing_plan_contains_section_word_budget()
    test_block_review_records_length_check()
    test_part_04_counts_natural_language_and_checks_mmd_structure()
    test_part_04_flags_missing_mmd_per_figure()
    test_block_review_flags_too_short_length()
    test_local_project_redaction_filters_sensitive_terms_only_when_local_material_exists()
    test_block_context_prefers_source_reading_notes_for_writing()
    test_part_02_prefers_phase_2_patent_metadata_when_available()
    test_check_template_and_style_uses_preprocess_index_paths()
    print("phase_5_length_budget tests passed")
