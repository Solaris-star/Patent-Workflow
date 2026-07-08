"""Phase 1 scope classification and Phase 2 discovery-mode tests."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from orchestrate import Orchestrator, STAGES  # noqa: E402
from executors.phase_2_executor import PhaseExecutor  # noqa: E402
from executors.phase_4_executor import PhaseExecutor as PatentReviewExecutor  # noqa: E402


def _orchestrator() -> Orchestrator:
    workspace = Path(tempfile.mkdtemp())
    manifest_path = workspace / "artifacts" / "run_manifest.md"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text("", encoding="utf-8")
    return Orchestrator(workspace, manifest_path, batch_mode=True)


def _disable_cnipa_network(executor: PhaseExecutor) -> None:
    executor._run_cnipa_epub_search = lambda terms: []


def test_phase_1_classifies_vague_domain_without_fixed_topic() -> None:
    updates = _orchestrator()._classify_phase_1_scope("仓储物流方向，没具体想法")

    assert updates["domain_scope"] == "仓储物流方向"
    assert updates["fixed_topic_or_title"] == ""
    assert updates["idea_maturity"] == "vague_domain"
    assert updates["phase_02_mode"] == "broad_domain_discovery"


def test_phase_1_classifies_empty_input_as_domain_recommendation() -> None:
    updates = _orchestrator()._classify_phase_1_scope("")

    assert updates["domain_scope"] == "待系统推荐"
    assert updates["idea_maturity"] == "no_idea"
    assert updates["phase_02_mode"] == "domain_recommendation"


def test_phase_1_reuses_existing_scope_without_prompt() -> None:
    orchestrator = _orchestrator()
    orchestrator.manifest.update(
        {
            "domain_scope": "自动驾驶、AI、项目管理、智能座舱",
            "idea_maturity": "vague_domain",
            "phase_02_mode": "broad_domain_discovery",
        }
    )

    assert orchestrator._phase_1_scope_ready() is True


def test_phase_1_collects_optional_local_project_path_after_scope() -> None:
    orchestrator = _orchestrator()
    prompts = []
    responses = iter(["仓储物流", "docs/project-a, /tmp/project-b"])
    orchestrator._prompt_user = lambda prompt, default="": (prompts.append(prompt) or next(responses))

    assert orchestrator._run_phase(STAGES[1]) is True

    assert any("本地项目" in prompt for prompt in prompts)
    assert orchestrator.manifest["domain_scope"] == "仓储物流"
    assert orchestrator.manifest["local_project_paths"] == ["docs/project-a", "/tmp/project-b"]
    assert orchestrator.manifest["phase_02_discovery_inputs"] == ["online_search", "local_project"]


def test_phase_1_keeps_online_only_when_local_project_path_is_empty() -> None:
    orchestrator = _orchestrator()
    responses = iter(["智能驾驶数据传输", ""])
    orchestrator._prompt_user = lambda prompt, default="": next(responses)

    assert orchestrator._run_phase(STAGES[1]) is True

    assert "local_project_paths" not in orchestrator.manifest
    assert orchestrator.manifest["phase_02_discovery_inputs"] == ["online_search"]
    assert orchestrator.manifest["phase_02_local_project_mode"] == "disabled"



def test_orchestrator_marks_phase_running_before_long_executor() -> None:
    orchestrator = _orchestrator()
    stage = {"id": "phase_2", "name": "长耗时搜索", "executor": "fake_long", "needs_user_input": False}

    def fake_executor(_executor_name, _phase_id):
        persisted = orchestrator.manifest_path.read_text(encoding="utf-8")
        assert "`current_phase`: phase_2" in persisted
        assert '"phase_2": "running"' in persisted
        from executors.base_executor import ExecutorResult
        return ExecutorResult(status="success")

    orchestrator._run_executor = fake_executor

    assert orchestrator._run_phase(stage) is True
    assert orchestrator.manifest["current_phase"] == "phase_2"
    assert orchestrator.manifest["phase_status"]["phase_2"] == "success"

def test_phase_2_cleans_vague_user_sentence_to_domain_terms() -> None:
    executor = PhaseExecutor("phase_2", Path(tempfile.mkdtemp()), {})

    effective_domain = executor._effective_domain_scope(
        "没什么想法，在自动驾驶、AI、项目管理、智能座舱等相关领域开始探索，找到可行的交叉方案",
        "broad_domain_discovery",
    )

    assert effective_domain == "自动驾驶、AI、项目管理、智能座舱"


def test_phase_2_broad_domain_adds_cross_domain_questions() -> None:
    executor = PhaseExecutor(
        "phase_2",
        Path(tempfile.mkdtemp()),
        {"domain_scope": "仓储物流", "phase_02_mode": "broad_domain_discovery"},
    )

    questions = executor._build_research_questions("仓储物流", "", "", "broad_domain_discovery")

    assert len(questions) == 9
    assert any(question["research_layer"] == "recent_patent_scan" and "最近18个月" in question["question"] for question in questions)
    assert any(question["research_layer"] == "hotspot_scan" and "X Twitter" in question["question"] for question in questions)
    assert any(question["research_layer"] == "frontier_research" and "Google Scholar" in question["question"] for question in questions)
    assert any(question["id"] == "RQ-07" and "cross-domain" in question["question"] for question in questions)
    assert all("待系统推荐" not in question["question"] for question in questions)


class FakeProcess:
    def __init__(self, model: str, returncode: int, stdout: str, delay_polls: int = 0):
        self.args = ["smart-search", "search", "--model", model]
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = ""
        self.delay_polls = delay_polls
        self.terminated = False

    def poll(self):
        if self.terminated:
            return -15
        if self.delay_polls > 0:
            self.delay_polls -= 1
            return None
        return self.returncode

    def communicate(self, timeout=None):
        return self.stdout, self.stderr

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        return self.poll()

    def kill(self):
        self.terminated = True


def test_phase_2_accepts_smart_search_error_json(monkeypatch=None) -> None:
    executor = PhaseExecutor("phase_2", Path(tempfile.mkdtemp()), {"phase_2_smart_search_parallel": False})
    failures = {
        "grok-4.3-beta": FakeProcess(
            "grok-4.3-beta",
            4,
            json.dumps({"ok": False, "error_type": "network_error", "content": "", "sources": [], "sources_count": 0}),
        ),
        "grok-4.20-fast": FakeProcess(
            "grok-4.20-fast",
            4,
            json.dumps({"ok": False, "error_type": "network_error", "content": "", "sources": [], "sources_count": 0}),
        ),
    }

    original_start = executor._start_smart_search_process
    executor._start_smart_search_process = lambda query, timeout, model: failures[model]
    try:
        result = executor._smart_search("测试查询", timeout=1)
    finally:
        executor._start_smart_search_process = original_start

    assert result["ok"] is False
    assert result["error_type"] == "all_models_failed"
    assert any(entry["action"] == "smart_search_degraded_json" for entry in executor.trace)


def test_phase_2_parallel_search_returns_fast_model_and_terminates_slow_model() -> None:
    executor = PhaseExecutor("phase_2", Path(tempfile.mkdtemp()), {"phase_2_smart_search_parallel": False})
    slow = FakeProcess(
        "grok-4.3-beta",
        0,
        json.dumps({"ok": True, "content": "slow", "sources": [], "sources_count": 0}),
        delay_polls=20,
    )
    fast = FakeProcess(
        "grok-4.20-fast",
        0,
        json.dumps({"ok": True, "content": "fast", "sources": [{"url": "https://example.com"}], "sources_count": 1}),
    )
    processes = {"grok-4.3-beta": slow, "grok-4.20-fast": fast}

    original_start = executor._start_smart_search_process
    executor._start_smart_search_process = lambda query, timeout, model: processes[model]
    try:
        result = executor._smart_search("测试查询", timeout=1)
    finally:
        executor._start_smart_search_process = original_start

    assert result["selected_model"] == "grok-4.20-fast"
    assert result["content"] == "fast"
    assert slow.terminated is True


def test_phase_2_research_quality_requires_hotspot_frontier_and_cross_source() -> None:
    executor = PhaseExecutor("phase_2", Path(tempfile.mkdtemp()), {})
    _disable_cnipa_network(executor)
    questions = executor._build_research_questions("自动驾驶", "", "", "broad_domain_discovery")
    search_results = [
        {"question_id": "RQ-02", "status": "ok", "sources_count": 1},
        {"question_id": "RQ-03", "status": "ok", "sources_count": 1},
        {"question_id": "RQ-04", "status": "ok", "sources_count": 1},
        {"question_id": "RQ-06", "status": "ok", "sources_count": 1},
    ]
    sources = [
        {"url": "https://x.com/a/status/1", "source_type": "hotspot"},
        {"url": "https://arxiv.org/abs/2501.1", "source_type": "academic"},
        {"url": "https://github.com/example/project", "source_type": "technical"},
        {"url": "https://www.mckinsey.com/industries/automotive-and-assembly/our-insights", "source_type": "industry"},
    ]
    evidence = [
        {
            "evidence_id": f"EV-{idx:03d}",
            "source_type": source["source_type"],
            "title": "2025 recent cross-domain fusion",
            "excerpt": "多模态 fusion 交叉迁移",
        }
        for idx, source in enumerate(sources, start=1)
    ] + [
        {"evidence_id": "EV-005", "source_type": "industry", "title": "2026 industry report", "excerpt": "工程落地 bottleneck"},
        {"evidence_id": "EV-006", "source_type": "web", "title": "latest challenge", "excerpt": "近期痛点"},
    ]

    quality = executor._assess_research_quality(questions, search_results, sources, evidence)
    directions = executor._rank_candidate_directions("自动驾驶", evidence, sources)

    assert quality["passed"] is True
    assert quality["required_dimensions"]["hotspot_signal"] is True
    assert quality["required_dimensions"]["academic_frontier"] is True
    assert "freshness_score" in directions[0]["scores"]
    assert "cross_source_consistency_score" in directions[0]["scores"]
    assert "transferability_score" in directions[0]["scores"]




def test_phase_2_multi_domain_generates_actual_cross_domain_directions() -> None:
    executor = PhaseExecutor("phase_2", Path(tempfile.mkdtemp()), {})
    _disable_cnipa_network(executor)
    evidence = [
        {
            "evidence_id": "EV-001",
            "source_type": "academic",
            "title": "AI planning for autonomous driving cockpit collaboration 2026",
            "excerpt": "AI 规划、自动驾驶、智能座舱与项目协同存在 cross-domain transfer opportunity 和工程 bottleneck。",
            "claim_supported": "跨领域迁移可支撑方向判断",
        },
        {
            "evidence_id": "EV-002",
            "source_type": "technical",
            "title": "GitHub autonomous driving project management agent",
            "excerpt": "自动驾驶研发项目需要 issue 风险预测、座舱体验反馈和工程任务联动。",
            "claim_supported": "工程实现存在可落地方向",
        },
        {
            "evidence_id": "EV-003",
            "source_type": "industry",
            "title": "Software-defined vehicle program management gap",
            "excerpt": "智能座舱和自动驾驶项目管理之间存在数据断层和产品 gap。",
            "claim_supported": "产业资料可支撑应用场景判断",
        },
    ]
    sources = [
        {"url": "https://arxiv.org/abs/2601.1", "source_type": "academic"},
        {"url": "https://github.com/example/sdv-agent", "source_type": "technical"},
        {"url": "https://www.mckinsey.com/report", "source_type": "industry"},
    ]

    directions = executor._rank_candidate_directions("AI,自动驾驶,项目管理,智能座舱-交叉组合探索", evidence, sources)
    titles = [direction["title"] for direction in directions]

    assert len(directions) >= 3
    assert len(titles) == len(set(titles))
    assert any("自动驾驶" in title and "项目管理" in title for title in titles)
    assert any("智能座舱" in title and "AI" in title for title in titles)
    assert not titles[0].startswith("基于多源证据融合的AI,自动驾驶,项目管理,智能座舱")
    assert not all(all(domain in title for domain in ["AI", "自动驾驶", "项目管理", "智能座舱"]) for title in titles)
    assert all(direction.get("generation_mode") in {"evidence_supported_domain_combination", "domain_pair_requires_followup_validation"} for direction in directions)
    assert all(direction.get("cross_domains") for direction in directions)
    assert all(direction.get("recommendation_reason") for direction in directions)
    assert all(direction.get("evidence_summary") for direction in directions)


def test_phase_2_multi_domain_generation_is_not_vehicle_specific() -> None:
    executor = PhaseExecutor("phase_2", Path(tempfile.mkdtemp()), {})
    _disable_cnipa_network(executor)
    evidence = [
        {
            "evidence_id": "EV-101",
            "source_type": "technical",
            "title": "warehouse robot scheduling anomaly detection",
            "excerpt": "仓储机器人、视觉质检与调度系统存在异常归因和任务排期 challenge。",
            "claim_supported": "开源实现可支撑工程可落地性判断",
        },
        {
            "evidence_id": "EV-102",
            "source_type": "industry",
            "title": "warehouse quality inspection automation report",
            "excerpt": "智能仓储和质检系统需要把设备反馈转化为调度策略。",
            "claim_supported": "产业资料可支撑应用场景判断",
        },
        {
            "evidence_id": "EV-103",
            "source_type": "academic",
            "title": "robotics scheduling open problem 2026",
            "excerpt": "robot scheduling and quality inspection has open problem in cross-domain transfer。",
            "claim_supported": "跨领域迁移可支撑方向判断",
        },
    ]
    sources = [
        {"url": "https://github.com/example/warehouse-robot", "source_type": "technical"},
        {"url": "https://www.idc.com/report", "source_type": "industry"},
        {"url": "https://arxiv.org/abs/2602.1", "source_type": "academic"},
    ]

    directions = executor._rank_candidate_directions("AI,智能仓储,视觉质检,机器人调度-交叉组合探索", evidence, sources)
    titles = [direction["title"] for direction in directions]

    assert len(directions) >= 3
    assert len(titles) == len(set(titles))
    assert any("智能仓储" in title and "视觉质检" in title for title in titles)
    assert any("机器人调度" in title for title in titles)
    assert all("自动驾驶" not in title and "智能座舱" not in title for title in titles)
    assert all(direction.get("generation_mode") in {"evidence_supported_domain_combination", "domain_pair_requires_followup_validation"} for direction in directions)


def test_phase_2_candidates_are_patent_title_improvements() -> None:
    executor = PhaseExecutor("phase_2", Path(tempfile.mkdtemp()), {})
    _disable_cnipa_network(executor)
    evidence = [
        {
            "evidence_id": "EV-P01",
            "source_type": "patent",
            "title": "一种自动驾驶任务调度方法",
            "url": "https://patents.google.com/patent/CN123456789A/zh",
            "excerpt": "法律状态：实质审查中。该专利解决自动驾驶研发任务调度依赖人工拆解的问题。",
            "claim_supported": "参考专利解决自动驾驶任务调度问题",
        },
        {
            "evidence_id": "EV-P02",
            "source_type": "patent",
            "title": "智能座舱用户反馈处理系统",
            "url": "https://patents.google.com/patent/CN119456789A/zh",
            "excerpt": "法律状态：授权。2025 年公开，该专利解决座舱用户反馈处理和体验评估问题。",
            "claim_supported": "参考专利解决座舱反馈处理问题",
        },
        {
            "evidence_id": "EV-P03",
            "source_type": "patent",
            "title": "一种车载风险预警方法",
            "url": "https://patents.google.com/patent/CN323456789A/zh",
            "excerpt": "法律状态：撤回。该专利涉及风险预警。",
            "claim_supported": "撤回专利不得作为核心参考",
        },
        {
            "evidence_id": "EV-H01",
            "source_type": "hotspot",
            "title": "X discussion about AI cockpit feedback loop",
            "url": "https://x.com/example/status/1",
            "excerpt": "热点讨论显示智能座舱反馈需要联动项目管理和自动驾驶测试闭环。",
            "claim_supported": "非专利热点支撑现实需求",
        },
    ]
    sources = [
        {"url": "https://patents.google.com/patent/CN123456789A/zh", "source_type": "patent"},
        {"url": "https://patents.google.com/patent/CN119456789A/zh", "source_type": "patent"},
        {"url": "https://x.com/example/status/1", "source_type": "hotspot"},
    ]

    directions = executor._rank_candidate_directions("AI,自动驾驶,项目管理,智能座舱-交叉组合探索", evidence, sources)

    assert directions
    assert len(directions) == 7
    assert all(direction["generation_mode"] == "patent_based_improvement" for direction in directions)
    assert all(len(direction["title"]) <= 25 for direction in directions)
    assert any("自动驾驶任务调度" in direction["title"] for direction in directions)
    assert any("座舱用户反馈" in direction["title"] or "智能座舱用户反馈" in direction["title"] for direction in directions)
    assert all(direction["reference_patent_problem"] for direction in directions)
    assert all(direction["improvement_point"] for direction in directions)
    assert all(direction["evidence_url"] for direction in directions)
    assert all(direction["non_patent_hotspot"] for direction in directions)
    assert all("撤回" not in direction["reference_patent_problem"] for direction in directions)


def test_phase_2_realistic_patent_output_keeps_titles_urls_and_problems() -> None:
    executor = PhaseExecutor("phase_2", Path(tempfile.mkdtemp()), {})
    _disable_cnipa_network(executor)
    evidence = [
        {
            "evidence_id": "EV-001",
            "question_id": "RQ-00",
            "source_type": "patent",
            "title": "**Baidu(百度)**:\"基于无人驾驶的乘客状态确定方法、装置、设备及介质\"",
            "url": "https://patents.google.com/patent/CN120308129A/zh",
            "excerpt": "法律状态：授权或实质审查中。标题：**Baidu(百度)**:\"基于无人驾驶的乘客状态确定方法、装置、设备及介质\"。",
            "claim_supported": "参考专利解决的问题：已有同类专利主要解决舱驾融合、跨域控制、数据交互或智能座舱响应中的工程协同问题。",
        },
        {
            "evidence_id": "EV-002",
            "question_id": "RQ-00",
            "source_type": "patent",
            "title": "**Changan(长安汽车)**:\"智能驾驶数据传输方法、装置、智能座舱系统和车辆\"",
            "url": "https://patents.google.com/patent/CN119636612A/zh",
            "excerpt": "法律状态：授权或实质审查中。标题：**Changan(长安汽车)**:\"智能驾驶数据传输方法、装置、智能座舱系统和车辆\"。",
            "claim_supported": "参考专利解决的问题：已有同类专利主要解决舱驾融合、跨域控制、数据交互或智能座舱响应中的工程协同问题。",
        },
        {
            "evidence_id": "EV-H01",
            "source_type": "hotspot",
            "title": "Google Scholar recent AI cockpit research",
            "url": "https://scholar.google.com/example",
            "claim_supported": "该证据支撑 热点 判断：学术进展可支撑技术路线的新颖性判断",
        },
    ]
    sources = [
        {"url": "https://patents.google.com/patent/CN120308129A/zh", "source_type": "patent"},
        {"url": "https://patents.google.com/patent/CN119636612A/zh", "source_type": "patent"},
        {"url": "https://scholar.google.com/example", "source_type": "academic"},
    ]

    directions = executor._rank_candidate_directions("AI,自动驾驶,项目管理,智能座舱-交叉组合探索", evidence, sources)

    assert len(directions) == 7
    assert all(direction["generation_mode"] == "patent_based_improvement" for direction in directions)
    assert all(direction["evidence_url"].startswith("https://patents.google.com/patent/") for direction in directions)
    assert all(direction["reference_patent_url"].startswith("https://patents.google.com/patent/") for direction in directions)
    assert all(direction["reference_patent_date"] for direction in directions)
    assert all("近18个月内" not in direction["reference_patent_date"] for direction in directions)
    assert all("reference_patent_date_is_explicit" in direction for direction in directions)
    assert all(direction["reference_patent_status"] for direction in directions)
    assert all("授权或实质审查中" not in direction["reference_patent_status"] for direction in directions)
    assert all("reference_patent_status_is_explicit" in direction for direction in directions)
    assert all("reference_patent_status_source" in direction for direction in directions)
    assert all("**" not in direction["reference_patent_title"] for direction in directions)
    assert all("已有同类专利主要解决" not in direction["reference_patent_problem"] for direction in directions)
    assert all(direction["reference_patent_selection_reason"] for direction in directions)
    assert all(direction["improvement_point"] for direction in directions)
    assert all("依据：" in direction["improvement_point"] for direction in directions)
    assert all(direction["collision_risk"] in {"low", "medium", "high"} for direction in directions)
    assert all("collision_reason" in direction for direction in directions)
    assert all("safe_to_select" in direction for direction in directions)
    assert all("avoidance_suggestion" in direction for direction in directions)
    assert all("collision_check_scope" in direction for direction in directions)
    assert all(direction["non_patent_hotspot_source"] for direction in directions)
    assert all(direction["non_patent_evidence"] for direction in directions)
    assert all("url" in direction["non_patent_evidence"][0] for direction in directions)
    assert all("该证据支撑" not in direction["non_patent_hotspot"] for direction in directions)
    assert all("参考专利解决的问题" not in direction["reference_patent_problem"] for direction in directions)
    assert all("[[" not in item["supports"] for direction in directions for item in direction["non_patent_evidence"])
    assert any("无人驾驶乘客状态确定" in direction["title"] for direction in directions)
    assert any("智能驾驶数据传输" in direction["title"] or "智能驾驶座舱数据传输" in direction["title"] for direction in directions)


def test_phase_2_cnipa_publication_kind_infers_status() -> None:
    executor = PhaseExecutor("phase_2", Path(tempfile.mkdtemp()), {})

    grant = {
        "title": "一种车载智能座舱交互系统",
        "url": "https://epub.cnipa.gov.cn/patent/CN120000001B",
        "excerpt": "授权公告号：CN120000001B。公告日：2025年7月。",
        "claim_supported": "参考专利解决的问题：座舱交互响应问题",
    }
    publication = {
        "title": "一种无人驾驶状态检测方法",
        "url": "https://epub.cnipa.gov.cn/patent/CN119000001A",
        "excerpt": "申请公布号：CN119000001A。公布日：2025年3月。",
        "claim_supported": "参考专利解决的问题：无人驾驶状态检测问题",
    }

    grant_meta = executor._cnipa_publication_metadata(grant)
    pub_meta = executor._cnipa_publication_metadata(publication)

    assert grant_meta["cnipa_publication_kind"] == "授权公告号"
    assert "授权公告" in grant_meta["cnipa_status_inference"]
    assert pub_meta["cnipa_publication_kind"] == "申请公布号"
    assert "未确认授权" in pub_meta["cnipa_status_inference"]

    page_hit = executor._cnipa_hit_to_similar_patent(
        {
            "title": "测试方法",
            "pub_number": "CN119636612A",
            "link": "http://epub.cnipa.gov.cn/patent/CN119636612A",
            "abstract": "智能驾驶数据传输",
            "publication_kind": "申请公布号",
            "publication_date": "2025-03-18",
            "application_date": "2025-01-17",
        },
        "智能驾驶数据传输方法",
    )
    utility_hit = executor._cnipa_hit_to_similar_patent(
        {
            "title": "测试系统",
            "pub_number": "CN223398557U",
            "link": "http://epub.cnipa.gov.cn/patent/CN223398557U",
            "abstract": "智能座舱数据传输",
        },
        "智能座舱数据传输系统",
    )
    executor._run_cnipa_epub_search = lambda terms: [
        {
            "title": "测试方法授权公告",
            "pub_number": "CN119636612B",
            "link": "http://epub.cnipa.gov.cn/patent/CN119636612B",
            "abstract": "智能驾驶数据传输",
            "publication_kind": "授权公告号",
            "publication_date": "2026-01-02",
            "application_number": "2025100768442",
        }
    ]
    verified_hit = executor._cnipa_hit_to_similar_patent(
        {
            "title": "测试方法",
            "pub_number": "CN119636612A",
            "link": "http://epub.cnipa.gov.cn/patent/CN119636612A",
            "abstract": "智能驾驶数据传输",
            "publication_kind": "申请公布号",
            "publication_date": "2025-03-18",
            "application_number": "2025100768442",
        },
        "智能驾驶数据传输方法",
    )

    assert page_hit["publication_kind"] == "申请公布号"
    assert page_hit["date"] == "2025-03-18"
    assert page_hit["application_date"] == "2025-01-17"
    assert "来源：CNIPA 页面字段" in page_hit["status"]
    assert utility_hit["publication_kind"] == "实用新型授权公告号"
    assert "实用新型授权公告" in utility_hit["status"]
    assert "已找到对应授权公告" in verified_hit["status"]
    assert verified_hit["legal_status_check"]["grant_hits"][0]["pub_number"] == "CN119636612B"


def test_phase_2_cnipa_search_hit_raises_collision_risk() -> None:
    executor = PhaseExecutor("phase_2", Path(tempfile.mkdtemp()), {})
    base = {
        "collision_risk": "low",
        "collision_reason": "本地未发现明显相似专利。",
        "similar_patents": [],
        "safe_to_select": True,
        "avoidance_suggestion": "后续复核。",
    }
    executor._run_cnipa_epub_search = lambda terms: [
        {
            "title": "智能驾驶数据传输方法、装置、智能座舱系统和车辆",
            "pub_number": "CN119636612A",
            "link": "https://epub.cnipa.gov.cn/patent/CN119636612A",
            "abstract": "涉及智能驾驶数据传输、智能座舱和异常检测。",
        }
    ]
    cnipa = executor._cnipa_candidate_novelty_search(
        "智能驾驶数据传输增强方法",
        "解决智能驾驶数据传输问题",
        "增加座舱反馈闭环和数据传输异常检测",
    )
    merged = executor._merge_cnipa_collision_check(base, cnipa)

    assert cnipa["status"] == "ok"
    assert cnipa["hits"]
    assert merged["collision_risk"] in {"medium", "high"}
    assert "CNIPA" in merged["collision_check_scope"]
    assert merged["similar_patents"][0]["pub_number"] == "CN119636612A"
    assert "申请公布" in merged["similar_patents"][0]["status"]


def test_phase_2_cnipa_degraded_does_not_claim_low_risk() -> None:
    executor = PhaseExecutor("phase_2", Path(tempfile.mkdtemp()), {})
    base = {
        "collision_risk": "low",
        "collision_reason": "本地未发现明显相似专利。",
        "similar_patents": [],
        "safe_to_select": True,
        "avoidance_suggestion": "后续复核。",
    }

    merged = executor._merge_cnipa_collision_check(base, {"status": "degraded", "query": "智能驾驶 数据传输", "hits": []})

    assert merged["collision_risk"] == "medium"
    assert merged["safe_to_select"] is False
    assert "降级" in merged["collision_check_scope"]


def test_phase_2_filters_irrelevant_domain_from_patent_improvement() -> None:
    executor = PhaseExecutor("phase_2", Path(tempfile.mkdtemp()), {})
    patent = {
        "title": "智能驾驶数据传输方法",
        "excerpt": "该专利涉及智能驾驶数据向智能座舱系统传输与协同响应。",
        "claim_supported": "参考专利解决的问题：智能驾驶数据传输问题",
    }

    combo = executor._relevant_technical_combo_for_patent(["AI", "项目管理", "智能座舱"], patent)
    improvement = executor._patent_improvement_point(combo, patent, [])

    assert "项目管理" not in combo
    assert "项目管理" not in improvement
    assert "智能座舱" in combo
    assert "智能驾驶" in combo
    assert "数据传输" in combo
    assert "传输异常识别" in improvement or "链路状态反馈" in improvement


def test_phase_2_keeps_ai_project_management_when_patent_is_related() -> None:
    executor = PhaseExecutor("phase_2", Path(tempfile.mkdtemp()), {})
    patent = {
        "title": "基于大模型的项目任务调度方法",
        "excerpt": "该专利涉及项目管理、任务调度、工作流状态预测和大模型辅助决策。",
        "claim_supported": "参考专利解决的问题：项目任务调度依赖人工拆解和进度风险预测不足。",
    }

    combo = executor._relevant_technical_combo_for_patent(["AI", "项目管理", "智能座舱"], patent)
    improvement = executor._patent_improvement_point(combo, patent, [])

    assert "项目管理" in combo
    assert "AI" in combo or "大模型" in combo
    assert "智能座舱" not in combo
    assert "项目管理" in improvement or "AI" in improvement or "大模型" in improvement


def test_phase_2_cnipa_similarity_uses_abstract_not_title_only() -> None:
    executor = PhaseExecutor("phase_2", Path(tempfile.mkdtemp()), {})
    candidate_text = "智能驾驶数据传输预警方法 解决智能驾驶数据向智能座舱系统传输与协同响应的问题"
    weak = executor._cnipa_hit_to_similar_patent(
        {
            "title": "数据传输方法、通信节点、介质及程序产品",
            "pub_number": "CN122073514A",
            "link": "http://epub.cnipa.gov.cn/patent/CN122073514A",
            "abstract": "涉及通信节点的比特序列划分、自编码器映射和复数符号流发送。",
        },
        candidate_text,
    )
    strong = executor._cnipa_hit_to_similar_patent(
        {
            "title": "智能驾驶数据传输方法及智能座舱系统",
            "pub_number": "CN122000001A",
            "link": "http://epub.cnipa.gov.cn/patent/CN122000001A",
            "abstract": "涉及智能驾驶数据传输、智能座舱协同响应和车辆端链路状态反馈。",
        },
        candidate_text,
    )

    assert weak["similarity_score"] < strong["similarity_score"]
    assert "仅题名重叠" in weak["similarity_basis"] or weak["similarity_score"] < 3
    assert "摘要级重叠特征" in strong["similarity_basis"]


def test_phase_2_cnipa_query_prefers_precise_compound_terms() -> None:
    executor = PhaseExecutor("phase_2", Path(tempfile.mkdtemp()), {})
    terms = executor._cnipa_search_terms_for_candidate(
        "智能驾驶数据传输预警方法",
        "解决智能驾驶数据向智能座舱系统传输与协同响应的问题",
        "增加传输异常识别、座舱侧响应校验和端到端链路状态反馈",
    )

    assert terms[0] == "智能驾驶数据传输"
    assert any(term.startswith("智能驾驶") and ("异常" in term or "数据传输" in term) for term in terms)
    assert any(term.startswith("智能座舱") and "校验" in term for term in terms)
    assert "数据传输预警" not in terms
    assert terms != ["数据传输"]
    assert len(terms) <= 5


def test_phase_2_cnipa_terms_are_short_and_run_one_by_one() -> None:
    executor = PhaseExecutor("phase_2", Path(tempfile.mkdtemp()), {})
    terms = executor._cnipa_search_terms_for_candidate(
        "智能驾驶数据传输预警方法",
        "解决智能驾驶数据向智能座舱系统传输与协同响应的问题",
        "引入项目管理和智能座舱反馈闭环",
    )

    calls = []
    executor._run_cnipa_epub_search_single = lambda term: calls.append(term) or [
        {"title": f"{term}相关专利", "pub_number": f"CN{len(calls)}A", "link": f"https://epub.cnipa.gov.cn/patent/CN{len(calls)}A"}
    ]
    hits = executor._run_cnipa_epub_search(terms[:3])

    assert "智能驾驶数据传输" in terms
    assert "智能座舱反馈闭环" in terms
    assert "项目管理" not in terms
    assert all(len(term) <= 12 for term in terms if any("\u4e00" <= ch <= "\u9fff" for ch in term))
    assert calls == terms[:3]
    assert len(hits) == 3


def test_phase_2_cnipa_search_merges_successful_terms_when_one_term_fails() -> None:
    executor = PhaseExecutor("phase_2", Path(tempfile.mkdtemp()), {})
    calls = []

    def fake_single(term):
        calls.append(term)
        if term == "智能驾驶数据传输":
            raise TimeoutError("slow term")
        return [{"title": f"{term}相关专利", "pub_number": f"CN{len(calls)}A", "link": f"https://epub.cnipa.gov.cn/patent/CN{len(calls)}A"}]

    executor._run_cnipa_epub_search_single = fake_single
    hits = executor._run_cnipa_epub_search(["智能驾驶数据传输", "智能驾驶传输异常", "智能座舱传输异常"])

    assert len(calls) == 3
    assert len(hits) == 2
    assert any("智能驾驶传输异常" in hit["title"] for hit in hits)
    assert any(entry["action"] == "cnipa_epub_term_degraded" for entry in executor.trace)


def test_phase_2_novelty_refinement_loop_rechecks_refined_improvement() -> None:
    executor = PhaseExecutor("phase_2", Path(tempfile.mkdtemp()), {})
    calls = []

    def fake_search(title, reference_problem, improvement_point):
        query_terms = executor._cnipa_search_terms_for_candidate(title, reference_problem, improvement_point)
        calls.append({"improvement": improvement_point, "query": " ".join(query_terms)})
        if len(calls) == 1:
            return {
                "status": "ok",
                "query": " ".join(query_terms),
                "hits": [
                    {
                        "title": "智能驾驶数据传输方法、装置、智能座舱系统和车辆",
                        "abstract": "按照各个功能应用的需求信息，对智能驾驶数据进行分类，得到多组数据流并传输至对应功能应用。",
                        "pub_number": "CN119636612A",
                        "url": "http://epub.cnipa.gov.cn/patent/CN119636612A",
                        "status": "申请公布（未确认授权；需继续查授权公告或法律状态）",
                        "similarity_score": 17,
                        "similarity_basis": "摘要级重叠特征：智能驾驶、智能座舱、数据传输",
                    }
                ],
            }
        return {"status": "ok", "query": " ".join(query_terms), "hits": []}

    executor._cnipa_candidate_novelty_search = fake_search
    result = executor._novelty_refinement_loop(
        "智能驾驶数据传输预警方法",
        "解决智能驾驶数据向智能座舱系统传输与协同响应的问题",
        "围绕智能驾驶、智能座舱、数据传输，增加传输异常识别和链路状态反馈",
        {"title": "智能驾驶数据传输方法", "url": "https://patents.google.com/patent/CN119636612A/zh"},
        [],
        max_iterations=2,
    )

    assert len(calls) == 2
    assert "智能驾驶" in calls[1]["query"] or "智能座舱" in calls[1]["query"]
    assert "链路健康度" in calls[1]["query"] or "完整性校验" in calls[1]["query"] or "传输异常" in calls[1]["query"]
    assert " 传输异常 " not in f" {calls[1]['query']} "
    assert " 链路健康度 " not in f" {calls[1]['query']} "
    assert result["status"] == "accepted"
    assert "二次改良" in result["final_improvement_point"]
    assert result["iterations"][0]["collision_risk"] == "high"
    assert result["iterations"][0]["refined_next_improvement_point"]
    assert result["iterations"][1]["collision_risk"] == "low"


def test_phase_2_cnipa_direct_env_does_not_leak_proxy(monkeypatch=None) -> None:
    executor = PhaseExecutor("phase_2", Path(tempfile.mkdtemp()), {})
    old_env = {key: __import__("os").environ.get(key) for key in ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"]}
    try:
        __import__("os").environ["HTTP_PROXY"] = "http://127.0.0.1:8888"
        __import__("os").environ["HTTPS_PROXY"] = "http://127.0.0.1:8888"
        __import__("os").environ["ALL_PROXY"] = "http://127.0.0.1:8888"
        __import__("os").environ["NO_PROXY"] = "localhost"
        direct_env = executor._cnipa_direct_env()
    finally:
        for key, value in old_env.items():
            if value is None:
                __import__("os").environ.pop(key, None)
            else:
                __import__("os").environ[key] = value

    assert "HTTP_PROXY" not in direct_env
    assert "HTTPS_PROXY" not in direct_env
    assert "ALL_PROXY" not in direct_env
    assert direct_env["CNIPA_EPUB_DIRECT"] == "1"
    assert "epub.cnipa.gov.cn" in direct_env["NO_PROXY"]


def test_phase_2_local_project_materials_generate_patent_points_and_related_fusion_only() -> None:
    workspace = Path(tempfile.mkdtemp())
    docs = workspace / "docs"
    docs.mkdir()
    (docs / "scheduler.md").write_text(
        "# 批量任务调度\n问题：资源不足时任务失败。方案：基于资源状态进行任务调度，记录执行状态并异常告警。模块：调度器、资源预测、反馈闭环。",
        encoding="utf-8",
    )
    (docs / "monitor.md").write_text(
        "# 执行监控\n问题：异常任务无法及时恢复。方案：检测异常状态，生成告警并反馈到调度器形成闭环。",
        encoding="utf-8",
    )
    default_executor = PhaseExecutor("phase_2", workspace, {"domain_scope": "批量任务调度"})
    assert default_executor._scan_local_project_materials("批量任务调度") == []

    executor = PhaseExecutor("phase_2", workspace, {"domain_scope": "批量任务调度", "local_project_path": "docs"})
    _disable_cnipa_network(executor)

    materials = executor._scan_local_project_materials("批量任务调度")
    evidence = executor._local_material_evidence(materials, 0)
    evidence.append(
        {
            "evidence_id": "EV-999",
            "source_type": "technical",
            "site": "技术博客",
            "title": "批量任务调度异常恢复与资源预测工程实践",
            "url": "https://example.com/scheduler-recovery",
            "excerpt": "近期工程实践关注批量任务调度中的资源预测、异常恢复和反馈闭环。",
            "claim_supported": "非专利信源显示批量任务调度异常恢复和资源预测存在工程改良空间。",
        }
    )
    directions = executor._rank_candidate_directions("批量任务调度", evidence, [{"source_type": "technical"}])

    assert len(materials) == 2
    assert directions[0]["generation_mode"] == "local_project_patent_point"
    assert directions[0]["technical_background"]
    assert directions[0]["innovation_point"]
    assert directions[0]["difference_from_prior_art"]
    assert directions[0]["implementation_feasibility"]
    assert any(item.get("url") == "https://example.com/scheduler-recovery" for item in directions[0].get("non_patent_evidence", []))
    assert any(direction.get("fusion_suggestion") for direction in directions)


def test_phase_2_no_idea_placeholder_uses_seed_domains() -> None:
    executor = PhaseExecutor(
        "phase_2",
        Path(tempfile.mkdtemp()),
        {"domain_scope": "待系统推荐", "phase_02_mode": "domain_recommendation"},
    )

    effective_domain = executor._effective_domain_scope("待系统推荐", "domain_recommendation")
    questions = executor._build_research_questions(effective_domain, "", "", "domain_recommendation")
    assert "智能仓储与物流质检" in effective_domain
    assert all("待系统推荐" not in question["question"] for question in questions)
    assert any(question["id"] == "RQ-08" for question in questions)


def test_phase_2_builds_source_reading_notes_from_smart_search_content() -> None:
    executor = PhaseExecutor("phase_2", Path(tempfile.mkdtemp()), {})
    questions = [{"id": "RQ-02", "purpose": "热点", "research_layer": "hotspot_scan"}]
    search_results = [
        {
            "question_id": "RQ-02",
            "query": "智能驾驶 数据传输 热点",
            "status": "ok",
            "content": "智能驾驶数据传输近期热点集中在链路异常预警。工程讨论指出需要端到端追踪和故障恢复。该方向适合形成可实施改良点。",
            "sources": [
                {"title": "智能驾驶链路异常讨论", "url": "https://example.com/hotspot", "source_type": "hotspot", "site": "Example"}
            ],
        }
    ]

    notes = executor._build_source_reading_notes(questions, search_results)

    assert notes[0]["url"] == "https://example.com/hotspot"
    assert notes[0]["source_type"] == "hotspot"
    assert "链路异常预警" in notes[0]["page_summary"]
    assert notes[0]["usable_in_writing"] is True


def test_phase_2_search_timeout_defaults_and_manifest_override() -> None:
    topic_executor = PhaseExecutor("phase_2", Path(tempfile.mkdtemp()), {"phase_2_search_timeout": 333})
    broad_executor = PhaseExecutor("phase_2", Path(tempfile.mkdtemp()), {})

    assert broad_executor._search_timeout("topic_research") == 60
    assert broad_executor._search_timeout("broad_domain_discovery") == 90
    assert broad_executor._search_timeout("domain_recommendation") == 90
    assert topic_executor._search_timeout("topic_research") == 333


def test_phase_2_internal_patent_review_timeout_defaults_and_manifest_override() -> None:
    default_executor = PatentReviewExecutor("phase_2", Path(tempfile.mkdtemp()), {})
    override_executor = PatentReviewExecutor("phase_2", Path(tempfile.mkdtemp()), {"phase_2_patent_review_timeout": 444})

    assert default_executor._search_timeout() == 180
    assert override_executor._search_timeout() == 444


def test_phase_2_marks_old_academic_sources_as_historical_background() -> None:
    executor = PhaseExecutor("phase_2", Path(tempfile.mkdtemp()), {})
    questions = [{"id": "RQ-03", "purpose": "学术"}]
    search_results = [
        {
            "question_id": "RQ-03",
            "status": "ok",
            "content": "A 2024 paper proposed an older agent debate workflow for engineering management.",
            "sources": [
                {
                    "title": "2024 agent debate workflow paper",
                    "url": "https://example.com/2024-paper",
                    "source_type": "academic",
                    "site": "Example",
                }
            ],
        }
    ]

    evidence = executor._extract_evidence(questions, search_results, "工程管理")
    quality = executor._assess_research_quality(questions, search_results, search_results[0]["sources"], evidence)

    assert evidence[0]["freshness_class"] == "historical_background"
    assert evidence[0]["usable_for_frontier"] is False
    assert "academic_frontier" in quality["missing_dimensions"]


def test_phase_2_ignores_numeric_patent_titles_from_search_source_indices() -> None:
    executor = PhaseExecutor("phase_2", Path(tempfile.mkdtemp()), {})
    evidence = [
        {
            "evidence_id": "EV-004",
            "source_type": "patent",
            "site": "Google Patents",
            "title": "4",
            "url": "https://patents.google.com/patent/CN117687384A/en",
            "excerpt": "**Provider: OpenAI-compatible** (model: grok-4.20-fast, 28140ms)",
            "claim_supported": "近期专利信源支撑 **Provider: OpenAI-compatible**",
        },
        {
            "evidence_id": "EV-010",
            "source_type": "technical",
            "title": "2026 cockpit feedback repo",
            "url": "https://github.com/example/cockpit-feedback",
            "excerpt": "智能座舱需要反馈闭环和异常恢复。",
            "claim_supported": "工程实现支撑反馈闭环需求。",
        },
    ]

    directions = executor._rank_candidate_directions("AI,自动驾驶,项目管理,智能座舱-交叉组合探索", evidence, [{"source_type": "patent"}, {"source_type": "technical"}])

    assert directions
    assert all("4改良方法" != direction["title"] for direction in directions)
    assert all("2改良方法" != direction["title"] for direction in directions)
    assert all(not direction["title"].startswith("4") for direction in directions)

def test_phase_2_candidate_novelty_guard_removes_direct_evidence_copy() -> None:
    executor = PhaseExecutor("phase_2", Path(tempfile.mkdtemp()), {})
    evidence = [
        {
            "evidence_id": "EV-001",
            "source_type": "academic",
            "title": "基于智能体辩论的跨阶段工程管理决策方法",
            "url": "https://www.sciexplor.com/jbde/articles/jbde.2025.0018",
            "excerpt": "该论文提出 agent debate workflow for cross-stage engineering management decisions。",
            "claim_supported": "论文提出智能体辩论工作流用于跨阶段工程管理决策。",
            "freshness_class": "current",
            "usable_for_frontier": True,
        },
        {
            "evidence_id": "EV-002",
            "source_type": "technical",
            "title": "engineering project risk issue tracker",
            "url": "https://github.com/example/risk-tracker",
            "excerpt": "工程项目需要把风险 issue 与成本、施工阶段状态联动。",
            "claim_supported": "工程实现支撑风险联动需求。",
            "freshness_class": "current",
            "usable_for_frontier": True,
        },
    ]

    directions = executor._rank_candidate_directions("智能体辩论,工程管理,项目风险", evidence, [{"source_type": "academic"}, {"source_type": "technical"}])

    assert all(direction["title"] != "基于智能体辩论的跨阶段工程管理决策方法" for direction in directions)
    assert all(direction.get("novelty_guard_status") != "rejected_direct_source_copy" for direction in directions)



def test_phase_2_broad_domain_outputs_contract_fields_and_evidence_supported_pairs() -> None:
    executor = PhaseExecutor("phase_2", Path(tempfile.mkdtemp()), {})
    evidence = [
        {
            "evidence_id": "EV-AD-IC",
            "source_type": "technical",
            "title": "2026 autonomous driving cockpit handoff",
            "url": "https://example.com/ad-cockpit",
            "excerpt": "自动驾驶与智能座舱在接管提醒、人机交互和安全告警方面存在明确协同需求。",
            "claim_supported": "自动驾驶和智能座舱之间存在证据支撑的技术组合。",
            "freshness_class": "current",
            "usable_for_frontier": True,
        },
        {
            "evidence_id": "EV-AI-AD",
            "source_type": "academic",
            "title": "2026 AI planning for autonomous driving",
            "url": "https://example.com/ai-ad",
            "excerpt": "AI 规划模型用于自动驾驶场景预测和异常风险识别。",
            "claim_supported": "AI 与自动驾驶之间存在证据支撑的技术组合。",
            "freshness_class": "current",
            "usable_for_frontier": True,
        },
        {
            "evidence_id": "EV-PM",
            "source_type": "industry",
            "title": "2026 project management report",
            "url": "https://example.com/pm",
            "excerpt": "项目管理资料仅讨论研发排期和任务追踪，没有与自动驾驶或智能座舱形成具体技术组合。",
            "claim_supported": "项目管理只作为工程管理背景。",
            "freshness_class": "current",
            "usable_for_frontier": True,
        },
    ]

    directions = executor._rank_candidate_directions(
        "自动驾驶,项目管理,AI,智能座舱-交叉组合探索",
        evidence,
        [{"source_type": "technical"}, {"source_type": "academic"}, {"source_type": "industry"}],
    )

    assert directions
    titles = [direction["title"] for direction in directions]
    assert len(titles) == len(set(titles))
    assert all("交叉组合探索" not in domain for direction in directions for domain in direction.get("cross_domains", []))
    assert all(not ("项目管理" in direction.get("cross_domains", []) and "智能座舱" in direction.get("cross_domains", [])) for direction in directions)
    assert all(direction.get("evidence_url") for direction in directions)
    assert all(direction.get("problem") for direction in directions)
    assert all(direction.get("improvement") for direction in directions)
    assert set(executor._candidate_display_item(directions[0])) == {"候选专利名称", "解决的问题", "本候选改良点", "证据 URL", "非专利热点信源"}

def test_phase_2_candidate_display_fields_match_contract() -> None:
    executor = PhaseExecutor("phase_2", Path(tempfile.mkdtemp()), {})
    candidate = {
        "title": "智能驾驶数据传输预警方法",
        "reference_patent_problem": "座舱与智驾域数据传输异常难以及时处理",
        "improvement_point": "依据：热点资料显示链路异常仍是痛点；改良为异常预警与反馈闭环。",
        "evidence_url": "https://patents.google.com/patent/CN119636612A/zh",
        "non_patent_hotspot_source": "https://example.com/hotspot",
        "reference_patent_title": "不应展示",
        "reference_patent_date": "2025-03-18",
        "collision_risk": "medium",
        "safe_to_select": True,
    }

    display = executor._candidate_display_item(candidate)

    assert set(display) == {"候选专利名称", "解决的问题", "本候选改良点", "证据 URL", "非专利热点信源"}
    assert display["候选专利名称"] == "智能驾驶数据传输预警方法"
    assert "reference_patent_title" not in display
    assert "collision_risk" not in display


def test_phase_2_research_pack_contains_contract_display_items() -> None:
    workspace = Path(tempfile.mkdtemp())
    executor = PhaseExecutor(
        "phase_2",
        workspace,
        {"domain_scope": "智能座舱", "phase_02_mode": "topic_research", "idea_maturity": "fixed_topic"},
    )
    _disable_cnipa_network(executor)

    def fake_search(query, timeout=120):
        return {
            "ok": True,
            "content": "2026 智能座舱链路异常预警成为工程热点，产业报告和开源项目均关注可追溯反馈闭环。",
            "sources": [
                {"title": "2026 cockpit feedback hotspot", "url": "https://example.com/2026-hotspot", "source_type": "hotspot", "site": "Example"},
                {"title": "2026 cockpit engineering repo", "url": "https://github.com/example/cockpit", "source_type": "technical", "site": "GitHub"},
                {"title": "2026 cockpit industry report", "url": "https://example.com/report", "source_type": "industry", "site": "Example"},
            ],
            "sources_count": 3,
        }

    executor._smart_search = fake_search
    executor._populate_phase_2_patent_review_artifacts = lambda *args, **kwargs: {"manifest_updates": {}, "artifacts": []}
    result = executor._execute()
    pack = json.loads((workspace / "artifacts" / "research" / "phase_02_research_pack.json").read_text(encoding="utf-8"))

    assert result.status == "success"
    assert pack["candidate_display_items"]
    assert set(pack["candidate_display_items"][0]) == {"候选专利名称", "解决的问题", "本候选改良点", "证据 URL", "非专利热点信源"}



def test_phase_2_internal_patent_review_sanitizes_polluted_query_subject() -> None:
    executor = PatentReviewExecutor("phase_2", Path(tempfile.mkdtemp()), {})

    queries = executor._build_search_queries(
        "AI,自动驾驶,项目管理,智能座舱-交叉组合探索",
        "PATENTSCOPEArtificialInte",
        "自动驾驶项目管理协同优化方法",
        [],
    )

    query_text = "\n".join(query["query"] for query in queries)
    assert "PATENTSCOPEArtificialInte" not in query_text
    assert "自动驾驶项目管理协同优化方法" in query_text

def test_phase_2_default_smart_search_uses_cli_parallel_extra_sources() -> None:
    executor = PhaseExecutor("phase_2", Path(tempfile.mkdtemp()), {"phase_2_extra_sources": 9})
    process = FakeProcess(
        "smart-search-parallel",
        0,
        json.dumps({"ok": True, "content": "merged", "sources": [{"url": "https://example.com/a"}], "sources_count": 1}),
    )
    started = []

    original_start = executor._start_smart_search_process
    executor._start_smart_search_process = lambda query, timeout, model="": (started.append(model) or process)
    try:
        result = executor._smart_search("测试查询", timeout=1)
    finally:
        executor._start_smart_search_process = original_start

    assert started == [""]
    assert result["selected_model"] == "smart-search-parallel"
    assert executor._smart_search_extra_sources() == 9
    assert PhaseExecutor("phase_2", Path(tempfile.mkdtemp()), {})._smart_search_extra_sources() == 4
    assert PhaseExecutor("phase_2", Path(tempfile.mkdtemp()), {})._smart_search_parallel_enabled() is False
    assert PhaseExecutor("phase_2", Path(tempfile.mkdtemp()), {})._phase_2_max_workers(8) == 1


def test_phase_2_smart_search_command_is_non_interactive_for_webchat() -> None:
    executor = PhaseExecutor("phase_2", Path(tempfile.mkdtemp()), {"phase_2_extra_sources": 15})
    captured = {}

    class DummyProcess:
        pass

    def fake_popen(cmd, stdout=None, stderr=None, text=None, env=None, start_new_session=False):
        captured["cmd"] = cmd
        captured["env"] = env
        captured["start_new_session"] = start_new_session
        return DummyProcess()

    original_popen = subprocess.Popen
    subprocess.Popen = fake_popen
    try:
        process = executor._start_smart_search_process("智能座舱 热点", 30, "grok-4.20-fast")
    finally:
        subprocess.Popen = original_popen

    assert isinstance(process, DummyProcess)
    assert "search" in captured["cmd"]
    assert "--format" in captured["cmd"]
    assert "--parallel" in captured["cmd"]
    assert "--model" not in captured["cmd"]
    assert captured["cmd"][captured["cmd"].index("--extra-sources") + 1] == "15"
    assert captured["env"]["SMART_SEARCH_INTERACTIVE"] == "0"
    assert captured["env"]["NO_COLOR"] == "1"
    assert captured["start_new_session"] is True
if __name__ == "__main__":
    test_phase_1_classifies_vague_domain_without_fixed_topic()
    test_phase_1_classifies_empty_input_as_domain_recommendation()
    test_phase_1_reuses_existing_scope_without_prompt()
    test_phase_1_collects_optional_local_project_path_after_scope()
    test_phase_1_keeps_online_only_when_local_project_path_is_empty()
    test_orchestrator_marks_phase_running_before_long_executor()
    test_phase_2_cleans_vague_user_sentence_to_domain_terms()
    test_phase_2_broad_domain_adds_cross_domain_questions()
    test_phase_2_accepts_smart_search_error_json()
    test_phase_2_parallel_search_returns_fast_model_and_terminates_slow_model()
    test_phase_2_research_quality_requires_hotspot_frontier_and_cross_source()
    test_phase_2_multi_domain_generates_actual_cross_domain_directions()
    test_phase_2_multi_domain_generation_is_not_vehicle_specific()
    test_phase_2_candidates_are_patent_title_improvements()
    test_phase_2_realistic_patent_output_keeps_titles_urls_and_problems()
    test_phase_2_cnipa_publication_kind_infers_status()
    test_phase_2_cnipa_search_hit_raises_collision_risk()
    test_phase_2_cnipa_degraded_does_not_claim_low_risk()
    test_phase_2_filters_irrelevant_domain_from_patent_improvement()
    test_phase_2_keeps_ai_project_management_when_patent_is_related()
    test_phase_2_cnipa_similarity_uses_abstract_not_title_only()
    test_phase_2_cnipa_query_prefers_precise_compound_terms()
    test_phase_2_cnipa_terms_are_short_and_run_one_by_one()
    test_phase_2_cnipa_search_merges_successful_terms_when_one_term_fails()
    test_phase_2_novelty_refinement_loop_rechecks_refined_improvement()
    test_phase_2_cnipa_direct_env_does_not_leak_proxy()
    test_phase_2_local_project_materials_generate_patent_points_and_related_fusion_only()
    test_phase_2_no_idea_placeholder_uses_seed_domains()
    test_phase_2_builds_source_reading_notes_from_smart_search_content()
    test_phase_2_search_timeout_defaults_and_manifest_override()
    test_phase_2_internal_patent_review_timeout_defaults_and_manifest_override()
    test_phase_2_marks_old_academic_sources_as_historical_background()
    test_phase_2_ignores_numeric_patent_titles_from_search_source_indices()
    test_phase_2_candidate_novelty_guard_removes_direct_evidence_copy()
    test_phase_2_broad_domain_outputs_contract_fields_and_evidence_supported_pairs()
    test_phase_2_candidate_display_fields_match_contract()
    test_phase_2_research_pack_contains_contract_display_items()
    test_phase_2_internal_patent_review_sanitizes_polluted_query_subject()
    test_phase_2_default_smart_search_uses_cli_parallel_extra_sources()
    test_phase_2_smart_search_command_is_non_interactive_for_webchat()
    print("phase_1_2_discovery_modes tests passed")
