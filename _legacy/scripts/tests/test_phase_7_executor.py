#!/usr/bin/env python3
"""Phase 7 IPR review regression tests."""

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from executors.phase_7_executor import PhaseExecutor  # noqa: E402


def write_workspace(workspace: Path, *, trusted_url: bool = True, figure_title: str = "四、附图说明") -> None:
    (workspace / "artifacts" / "audit").mkdir(parents=True)
    prior_dir = workspace / "artifacts" / "prior_art"
    prior_dir.mkdir(parents=True)
    evidence_url = "https://patents.google.com/patent/CN123456A/zh" if trusted_url else ""
    (prior_dir / "phase_02_evidence_pack.json").write_text(
        json.dumps(
            {
                "pack_type": "evidence_pack",
                "phase": "phase_02",
                "evidence": [
                    {
                        "evidence_id": "EV-001",
                        "source_type": "patent",
                        "url": evidence_url,
                        "excerpt": "中国发明专利 CN123456A 公开了常规检索方案。",
                        "is_auxiliary": False,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    files = {
        "part_01_技术领域.md": "一、技术领域\n本发明涉及智能检索技术领域。" + "字" * 80,
        "part_02_背景技术.md": "二、背景技术\n中国发明专利 CN123456A 公开了常规检索方案。现有技术存在证据链割裂、检索结果难以复核的问题。" + "字" * 400,
        "part_03_发明内容.md": "三、发明内容\n3.1 要解决的技术问题\n本发明解决证据链割裂和检索结果难以复核的技术问题。\n3.2 技术方案\n本发明提供一种智能检索审查方法，包括 S101 读取证据、S102 建立映射、S103 生成审计结果。该方案通过证据链映射与可信渠道联动，实现检索、写作和审查的协同。\n3.3 有益效果\n通过上述技术特征对应形成可追溯证据链，从而降低事实漂移并提高审查复核效率。" + "字" * 1200,
        "part_04_附图说明.md": f"{figure_title}\n图1为系统架构图。图2为方法流程图，其中包括步骤S101至步骤S103。" + "字" * 120,
        "part_05_具体实施方式.md": "五、具体实施方式\n下面对照附图，通过对较优实施例的描述，对本申请的具体实施方式作进一步详细说明。本实施例提供的一种智能检索审查方法，包括以下步骤：S101，读取证据资料；S102，建立证据与技术特征的映射；S103，生成审计结果。S101步骤具体如下：其核心逻辑是：获取证据来源和专利号。S102步骤具体如下：其核心逻辑是：将证据编号映射到技术特征。S103步骤具体如下：其核心逻辑是：输出审查结论。前者负责输入；后者负责输出；二者协同形成闭环。" + "字" * 1500,
    }
    for filename, content in files.items():
        (workspace / filename).write_text(content, encoding="utf-8")


def run_review(workspace: Path):
    return PhaseExecutor("phase_7", workspace, {"patent_title": "测试专利"})._execute()


def report_text(workspace: Path) -> str:
    return (workspace / "artifacts" / "audit" / "phase_07_ipr_review_report.md").read_text(encoding="utf-8")


def test_phase_7_accepts_figure_description_heading() -> None:
    workspace = Path(tempfile.mkdtemp())
    write_workspace(workspace, figure_title="四、附图说明")

    result = run_review(workspace)
    report = report_text(workspace)

    assert result.error is None
    assert "附图标题未更新" not in report


def test_phase_7_flags_untrusted_or_missing_evidence_url() -> None:
    workspace = Path(tempfile.mkdtemp())
    write_workspace(workspace, trusted_url=False)

    result = run_review(workspace)
    report = report_text(workspace)

    assert result.error is None
    assert "证据来源可追溯性不足" in report


def test_phase_7_report_contains_legal_rule_mapping() -> None:
    workspace = Path(tempfile.mkdtemp())
    write_workspace(workspace)

    result = run_review(workspace)
    report = report_text(workspace)

    assert result.error is None
    assert "## 法规依据与规则映射" in report
    assert "CN-PA-002-TECH-SOLUTION" in report
    assert "实现函数: `_check_tech_solution`" in report
    assert "本阶段不内置法规全文" in report


if __name__ == "__main__":
    test_phase_7_accepts_figure_description_heading()
    test_phase_7_flags_untrusted_or_missing_evidence_url()
    test_phase_7_report_contains_legal_rule_mapping()
    print("phase_7_executor regression tests passed")
