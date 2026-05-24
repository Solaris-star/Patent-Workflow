#!/usr/bin/env python3
"""Phase 6 executor regression tests."""

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from executors.phase_6_executor import PhaseExecutor  # noqa: E402


def write_workspace(workspace: Path) -> None:
    draft_dir = workspace / "artifacts" / "draft"
    draft_dir.mkdir(parents=True)
    (workspace / "artifacts" / "audit").mkdir(parents=True)

    evidence_pack_path = workspace / "artifacts" / "prior_art" / "phase_02_evidence_pack.json"
    evidence_pack_path.parent.mkdir(parents=True)
    evidence_pack_path.write_text(
        json.dumps(
            {
                "pack_type": "evidence_pack",
                "phase": "phase_02",
                "evidence": [
                    {
                        "evidence_id": "EV-001",
                        "source_type": "patent",
                        "url": "https://patents.google.com/patent/CN123456A/zh",
                        "excerpt": "中国发明专利 CN123456A 公开了相关方案。",
                        "is_auxiliary": False,
                    }
                ],
                "evidence_alignment": [
                    {
                        "alignment_id": "AL-001",
                        "claim_aspect": "背景专利参考",
                        "evidence_ids": ["EV-001"],
                        "conclusion": "可信专利渠道命中",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    (draft_dir / "facts_ledger.json").write_text(
        json.dumps(
            {
                "terminology": [{"term": "智能检索"}],
                "figure_registry": [{"figure_id": f"图{idx}", "artifacts": {}} for idx in range(1, 5)],
                "block_statuses": [
                    {
                        "file": "part_04_附图说明.md",
                        "char_count": 180,
                        "target_min_chars": 120,
                        "target_max_chars": 400,
                        "length_reason": "附图说明以图注和 Mermaid/mmd 源码为主，自然语言应简洁。",
                    }
                ],
                "research_inputs": {
                    "evidence_pack_path": "artifacts/prior_art/phase_02_evidence_pack.json",
                    "patent_evidence_count": 1,
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (draft_dir / "step_registry.json").write_text(
        json.dumps([{"step_id": "S101"}, {"step_id": "S102"}], ensure_ascii=False),
        encoding="utf-8",
    )

    files = {
        "part_01_技术领域.md": "一、技术领域\n智能检索技术。" + "字" * 60,
        "part_02_背景技术.md": "二、背景技术\n## 2.1 与本申请相关的现有技术背景知识\n中国发明专利 CN123456A 公开了相关方案。证据编号 EV-001 支撑该背景专利引用。\n## 2.2 与本申请相关的最接近的现有技术\n该专利用于说明现有技术已经关注智能检测。\n## 2.3 现有技术的缺陷和不足\n现有技术仍存在证据融合不足。" + "字" * 520,
        "part_03_发明内容.md": "三、发明内容\n3.1 技术问题\n3.2 技术方案\nS101 执行检索。S102 生成结果。\n3.3 有益效果\n" + "字" * 1300,
        "part_04_附图说明.md": "四、专利附图\n图1为系统结构图。图2为方法流程图，包括步骤S101至步骤S102。图3为证据记录结构图。图4为追溯关系图。\n```mermaid\ngraph TD\nA[输入]-->B[处理]\n```\n```mermaid\nflowchart TD\nS101-->S102\n```\n```mermaid\nerDiagram\n证据 ||--|| 结果 : 关联\n```\n```mermaid\ngraph LR\n结论-->证据\n```\n" + "字" * 150,
        "part_05_具体实施方式.md": "五、具体实施方式\n下面对照附图，通过对较优实施例的描述，对本申请的具体实施方式作进一步详细说明。本实施例提供的一种智能检索方法，包括以下步骤：如图1所示，S101 执行检索。S102 生成结果。S101步骤具体如下：其核心逻辑是：完成数据获取。S102步骤具体如下：其核心逻辑是：完成答案生成。前者负责获取；后者负责输出；二者协同形成闭环。" + "字" * 1850, 
    }
    for filename, content in files.items():
        (workspace / filename).write_text(content, encoding="utf-8")


def test_phase_6_accepts_standalone_step_registry() -> None:
    workspace = Path(tempfile.mkdtemp())
    write_workspace(workspace)

    result = PhaseExecutor("phase_6", workspace, {"patent_title": "测试专利"})._execute()

    assert result.status in {"success", "partial"}
    assert result.error is None
    assert (workspace / "artifacts" / "audit" / "phase_06_consistency_audit_report.md").exists()
    assert "consistency_audit_score" in result.manifest_updates


def test_phase_6_does_not_conflict_on_figure_heading_or_jinyibu() -> None:
    workspace = Path(tempfile.mkdtemp())
    write_workspace(workspace)

    result = PhaseExecutor("phase_6", workspace, {"patent_title": "测试专利"})._execute()
    report = (workspace / "artifacts" / "audit" / "phase_06_consistency_audit_report.md").read_text(encoding="utf-8")

    assert "缺少章节标记 '四、附图说明'" not in report
    assert "附图章节标题仍为'附图说明'" not in report
    assert "发现禁用用语: '进一步'" not in report
    assert result.error is None


def test_phase_6_flags_unknown_evidence_id_reference() -> None:
    workspace = Path(tempfile.mkdtemp())
    write_workspace(workspace)
    part03 = workspace / "part_03_发明内容.md"
    part03.write_text(part03.read_text(encoding="utf-8") + "\n未登记证据 EV-999 支撑该效果。", encoding="utf-8")

    result = PhaseExecutor("phase_6", workspace, {"patent_title": "测试专利"})._execute()
    report = (workspace / "artifacts" / "audit" / "phase_06_consistency_audit_report.md").read_text(encoding="utf-8")

    assert result.error is None
    assert "正文引用了未登记证据编号 'EV-999'" in report


def test_phase_6_strips_mmd_when_counting_figure_description_without_ledger() -> None:
    workspace = Path(tempfile.mkdtemp())
    write_workspace(workspace)
    ledger_path = workspace / "artifacts" / "draft" / "facts_ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    ledger["block_statuses"] = []
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False), encoding="utf-8")

    long_mmd = "\n```mermaid\n" + ("A-->B\n" * 300) + "```"
    part04 = workspace / "part_04_附图说明.md"
    part04.write_text("四、专利附图\n图1为系统结构图。图2为方法流程图。图3为证据记录结构图。图4为追溯关系图。" + "说明" * 50 + long_mmd, encoding="utf-8")

    result = PhaseExecutor("phase_6", workspace, {"patent_title": "测试专利"})._execute()
    report = (workspace / "artifacts" / "audit" / "phase_06_consistency_audit_report.md").read_text(encoding="utf-8")

    assert result.error is None
    assert "part_04_附图说明.md | 字数偏多" not in report


def test_phase_6_word_count_uses_ledger_length_budget() -> None:
    workspace = Path(tempfile.mkdtemp())
    write_workspace(workspace)
    ledger_path = workspace / "artifacts" / "draft" / "facts_ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    ledger["block_statuses"] = [
        {
            "file": "part_03_发明内容.md",
            "target_min_chars": 2000,
            "target_max_chars": 2400,
            "length_reason": "发明内容需要覆盖技术问题、技术方案和有益效果。",
        }
    ]
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False), encoding="utf-8")

    result = PhaseExecutor("phase_6", workspace, {"patent_title": "测试专利"})._execute()
    report = (workspace / "artifacts" / "audit" / "phase_06_consistency_audit_report.md").read_text(encoding="utf-8")

    assert result.error is None
    assert "建议 2000-2400 字" in report


def test_phase_6_flags_redaction_residue_when_local_project_redaction_enabled() -> None:
    workspace = Path(tempfile.mkdtemp())
    write_workspace(workspace)
    redaction_path = workspace / "artifacts" / "draft" / "redaction_policy.json"
    redaction_path.write_text(
        json.dumps({"enabled": True, "sensitive_terms": ["AcmeVision", "客户A"]}, ensure_ascii=False),
        encoding="utf-8",
    )
    part03 = workspace / "part_03_发明内容.md"
    part03.write_text(part03.read_text(encoding="utf-8") + "\nAcmeVision 为客户A处理每日12000件数据。", encoding="utf-8")

    result = PhaseExecutor("phase_6", workspace, {"patent_title": "测试专利"})._execute()
    report = (workspace / "artifacts" / "audit" / "phase_06_consistency_audit_report.md").read_text(encoding="utf-8")

    assert result.error is None
    assert "本地项目敏感信息残留" in report


def test_phase_6_flags_incomplete_technical_closure() -> None:
    workspace = Path(tempfile.mkdtemp())
    write_workspace(workspace)
    part05 = workspace / "part_05_具体实施方式.md"
    part05.write_text("五、具体实施方式\n本实施例仅采集输入数据。" + "字" * 1900, encoding="utf-8")

    result = PhaseExecutor("phase_6", workspace, {"patent_title": "测试专利"})._execute()
    report = (workspace / "artifacts" / "audit" / "phase_06_consistency_audit_report.md").read_text(encoding="utf-8")

    assert result.error is None
    assert "技术方案闭环不完整" in report


def test_phase_6_flags_formula_parameter_inconsistency() -> None:
    workspace = Path(tempfile.mkdtemp())
    write_workspace(workspace)
    part03 = workspace / "part_03_发明内容.md"
    part05 = workspace / "part_05_具体实施方式.md"
    part03.write_text(part03.read_text(encoding="utf-8") + "\n阈值范围为0.5-1.5，置信度权重α用于融合判断。", encoding="utf-8")
    part05.write_text(part05.read_text(encoding="utf-8") + "\n阈值范围为0.8-1.2，置信度权重β用于融合判断。", encoding="utf-8")

    result = PhaseExecutor("phase_6", workspace, {"patent_title": "测试专利"})._execute()
    report = (workspace / "artifacts" / "audit" / "phase_06_consistency_audit_report.md").read_text(encoding="utf-8")

    assert result.error is None
    assert "公式或参数表述不一致" in report


def test_phase_6_flags_cnipa_abstract_alignment_mismatch() -> None:
    workspace = Path(tempfile.mkdtemp())
    write_workspace(workspace)
    evidence_pack_path = workspace / "artifacts" / "prior_art" / "phase_02_evidence_pack.json"
    pack = json.loads(evidence_pack_path.read_text(encoding="utf-8"))
    pack["evidence"][0]["abstract"] = "本摘要公开了基于图像采集和缺陷识别的仓储质检方法。"
    evidence_pack_path.write_text(json.dumps(pack, ensure_ascii=False), encoding="utf-8")
    part02 = workspace / "part_02_背景技术.md"
    part02.write_text("二、背景技术\n中国发明专利 CN123456A 公开了相关方案。该专利主要涉及网络通信路由。证据编号 EV-001。" + "字" * 700, encoding="utf-8")

    result = PhaseExecutor("phase_6", workspace, {"patent_title": "测试专利"})._execute()
    report = (workspace / "artifacts" / "audit" / "phase_06_consistency_audit_report.md").read_text(encoding="utf-8")

    assert result.error is None
    assert "CNIPA 摘要理解不一致" in report


def test_phase_6_requires_revision_log_when_revision_mode_enabled() -> None:
    workspace = Path(tempfile.mkdtemp())
    write_workspace(workspace)

    result = PhaseExecutor("phase_6", workspace, {"patent_title": "测试专利", "revision_mode": True})._execute()
    report = (workspace / "artifacts" / "audit" / "phase_06_consistency_audit_report.md").read_text(encoding="utf-8")

    assert result.error is None
    assert "缺少修订对话记录" in report


if __name__ == "__main__":
    test_phase_6_accepts_standalone_step_registry()
    test_phase_6_does_not_conflict_on_figure_heading_or_jinyibu()
    test_phase_6_flags_unknown_evidence_id_reference()
    test_phase_6_strips_mmd_when_counting_figure_description_without_ledger()
    test_phase_6_word_count_uses_ledger_length_budget()
    test_phase_6_flags_redaction_residue_when_local_project_redaction_enabled()
    test_phase_6_flags_incomplete_technical_closure()
    test_phase_6_flags_formula_parameter_inconsistency()
    test_phase_6_flags_cnipa_abstract_alignment_mismatch()
    test_phase_6_requires_revision_log_when_revision_mode_enabled()
    print("phase_6_executor regression tests passed")
