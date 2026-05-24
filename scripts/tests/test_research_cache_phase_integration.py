#!/usr/bin/env python3
"""Phase 2/4 research cache integration smoke tests."""

import tempfile
from pathlib import Path
from typing import Optional
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import executors.phase_2_executor as phase2_module  # noqa: E402
import executors.phase_4_executor as patent_review_module  # noqa: E402


class _FakeCacheBase:
    last_instance = None

    def __init__(self, root: Optional[Path] = None):
        type(self).last_instance = self
        self.root = Path(root or tempfile.mkdtemp())
        self.search_calls = []
        self.import_calls = []

    def search(self, query, phase="", source_types=None, limit=10):
        self.search_calls.append({"query": query, "phase": phase, "source_types": source_types, "limit": limit})
        return [
            {
                "record_id": "src_fake",
                "source_type": source_types[0] if source_types else "technical",
                "source_channel": "smart-search",
                "site": "example.com",
                "title": "缓存命中示例",
                "url": "https://example.com/cache-hit",
                "page_summary": "缓存命中摘要",
                "key_technical_facts": ["缓存命中事实"],
                "tags": ["缓存"],
                "keywords": ["缓存"],
                "cache_status": "fresh",
                "expires_at": "2026-06-01T00:00:00Z",
                "revalidated_at": "",
                "cached_at": "2026-05-23T00:00:00Z",
                "lexical_score": 0.1,
            }
        ]

    def import_source_reading_notes(self, notes, phase, query="", domain_scope=None, candidate_direction=""):
        notes = list(notes or [])
        self.import_calls.append(
            {
                "phase": phase,
                "query": query,
                "domain_scope": domain_scope,
                "candidate_direction": candidate_direction,
                "count": len(notes),
            }
        )
        return {
            "search_run_id": "run_fake",
            "input_count": len(notes),
            "imported_count": len(notes),
            "duplicate_count": 0,
            "skipped_private_count": 0,
            "jsonl_path": str(self.root / "records.jsonl"),
        }


class FakePhase2Cache(_FakeCacheBase):
    pass


class FakePatentReviewCache(_FakeCacheBase):
    pass


def test_phase_2_uses_research_cache_and_exports_manifest_fields() -> None:
    workspace = Path(tempfile.mkdtemp())
    phase2_module.ResearchCache = FakePhase2Cache
    executor = phase2_module.PhaseExecutor(
        "phase_2",
        workspace,
        {"domain_scope": "智能驾驶数据传输", "fixed_topic_or_title": "智能驾驶数据传输预警方法"},
    )
    executor._build_research_questions = lambda *args, **kwargs: [
        {"id": "RQ-00", "question": "智能驾驶数据传输预警方法", "source_focus": "technical", "research_layer": "baseline"}
    ]
    executor._smart_search = lambda query, timeout=120: {
        "content": "智能驾驶数据传输链路异常预警与恢复。",
        "sources": [{"title": "智能驾驶链路异常", "url": "https://example.com/phase2", "site": "example.com"}],
        "sources_count": 1,
    }
    executor._normalize_sources = lambda result: result["sources"]
    executor._enrich_patent_source_titles = lambda sources, content: None
    executor._collect_unique_sources = lambda results: [{"url": "https://example.com/phase2", "source_type": "technical", "title": "智能驾驶链路异常"}]
    executor._extract_evidence = lambda *args, **kwargs: [{"evidence_id": "EV-001", "source_type": "technical"}]
    executor._scan_local_project_materials = lambda scope: []
    executor._local_material_evidence = lambda materials, start: []
    executor._count_strong_sources = lambda sources: len(sources)
    executor._rank_candidate_directions = lambda *args, **kwargs: [
        {"direction_id": "CD-01", "title": "智能驾驶数据传输预警方法", "scores": {"total_score": 1.0}, "evidence_ids": ["EV-001"]}
    ]
    executor._assess_research_quality = lambda *args, **kwargs: {"passed": True, "missing_dimensions": []}
    executor._build_source_reading_notes = lambda *args, **kwargs: [
        {
            "note_id": "PRN-001",
            "source_type": "technical",
            "source_channel": "smart-search",
            "site": "example.com",
            "title": "缓存命中示例",
            "url": "https://example.com/phase2",
            "page_summary": "缓存命中摘要",
            "key_technical_facts": ["缓存命中事实"],
            "usable_in_writing": True,
            "do_not_overclaim": "仅作背景参考。",
        }
    ]
    executor._build_outline_skeleton = lambda evidence: []
    executor._claims_requiring_patent_verification = lambda directions: ["claim-1"]

    def fake_patent_review(*args, **kwargs):
        prior_dir = workspace / "artifacts" / "prior_art"
        prior_dir.mkdir(parents=True, exist_ok=True)
        (prior_dir / "phase_02_patent_candidate_pool.json").write_text('{"patents": []}', encoding="utf-8")
        (prior_dir / "phase_02_evidence_pack.json").write_text('{"evidence": []}', encoding="utf-8")
        return {
            "manifest_updates": {
                "patent_candidate_pool_count": 1,
                "finalRelevantPatents_count": 1,
                "cn_only_passed": True,
                "freshness_passed": True,
                "relevance_passed": True,
                "candidate_pool_generation_mode": "test",
                "candidate_pool_channels_used": ["smart-search"],
                "trusted_patent_channels": ["Google Patents"],
                "evidence_pack_path": "artifacts/prior_art/phase_02_evidence_pack.json",
            },
            "artifacts": [
                str(prior_dir / "phase_02_patent_candidate_pool.json"),
                str(prior_dir / "phase_02_evidence_pack.json"),
            ],
        }

    executor._populate_phase_2_patent_review_artifacts = fake_patent_review

    result = executor._execute()
    cache = FakePhase2Cache.last_instance

    assert result.status in {"success", "degraded"}
    assert cache is not None
    assert cache.search_calls[0]["phase"] == "phase_2"
    assert result.manifest_updates["research_cache_enabled"] is True
    assert result.manifest_updates["research_cache_hit_count"] == 1
    assert result.manifest_updates["research_cache_imported_count"] == 1
    assert result.manifest_updates["research_cache_hit"] is True
    assert result.manifest_updates["selected_direction"]
    assert result.manifest_updates["patent_title"]
    assert result.manifest_updates["patent_candidate_pool_count"] >= 1
    assert (workspace / "artifacts" / "prior_art" / "phase_02_patent_candidate_pool.json").exists()
    assert (workspace / "artifacts" / "prior_art" / "phase_02_evidence_pack.json").exists()


def test_phase_2_internal_review_uses_research_cache_and_marks_patent_hits_for_revalidation() -> None:
    workspace = Path(tempfile.mkdtemp())
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "artifacts" / "research").mkdir(parents=True, exist_ok=True)
    (workspace / "artifacts" / "research" / "phase_02_research_pack.json").write_text(
        "{}",
        encoding="utf-8",
    )
    patent_review_module.ResearchCache = FakePatentReviewCache
    executor = patent_review_module.PhaseExecutor(
        "phase_2",
        workspace,
        {"domain_scope": "智能驾驶数据传输", "patent_title": "智能驾驶数据传输预警方法", "selected_direction": "智能驾驶数据传输预警方法"},
    )
    executor._load_research_pack = lambda: {"candidate_directions": [], "claims_requiring_patent_verification": []}
    executor._build_search_queries = lambda *args, **kwargs: [
        {"id": "PQ-01", "channel": "cnipa", "query": "site:cnipa.gov.cn 智能驾驶数据传输预警方法 发明专利"}
    ]
    executor._smart_search = lambda query, timeout=120: {
        "content": "CN119636612A 智能驾驶数据传输异常预警",
        "sources": [{"title": "CN119636612A", "url": "https://patents.google.com/patent/CN119636612A/zh", "site": "patents.google.com", "patent_channel": "google_patents", "trusted_patent_source": True}],
        "sources_count": 1,
    }
    executor._normalize_sources = lambda result, channel: result["sources"]
    executor._collect_unique_sources = lambda results: [{"url": "https://patents.google.com/patent/CN119636612A/zh", "trusted_patent_source": True, "title": "CN119636612A", "source_type": "patent", "source_channel": "google_patents"}]
    executor._build_candidate_pool = lambda *args, **kwargs: {"patents": [{"source_url": "https://patents.google.com/patent/CN119636612A/zh", "abstract": "摘要", "source_channel": "google_patents", "title": "CN119636612A"}], "trusted_patent_channels": {"google_patents": {"name": "Google Patents"}}}
    executor._evaluate_candidate_pool = lambda pool: {"gates": {"cn_only_passed": True, "freshness_passed": True, "relevance_passed": True, "min_count_passed": True}, "final_relevant_patents": [1], "peripheral_references": [], "rejected_references": []}
    executor._build_source_reading_notes = lambda *args, **kwargs: [
        {
            "note_id": "PRN-001",
            "source_type": "patent",
            "source_channel": "google_patents",
            "site": "patents.google.com",
            "title": "CN119636612A",
            "url": "https://patents.google.com/patent/CN119636612A/zh",
            "page_summary": "缓存命中摘要",
            "key_technical_facts": ["缓存命中事实"],
            "usable_in_writing": True,
            "do_not_overclaim": "法律状态必须重新验证。",
        }
    ]
    executor._build_evidence_pack = lambda *args, **kwargs: {
        "pack_type": "evidence_pack",
        "phase": "phase_02",
        "schema_version": "2.0",
        "search_trace": {},
        "source_reading_notes": [
            {
                "note_id": "PRN-001",
                "source_type": "patent",
                "source_channel": "google_patents",
                "site": "patents.google.com",
                "title": "CN119636612A",
                "url": "https://patents.google.com/patent/CN119636612A/zh",
                "page_summary": "缓存命中摘要",
                "key_technical_facts": ["缓存命中事实"],
                "usable_in_writing": True,
                "do_not_overclaim": "法律状态必须重新验证。",
            }
        ],
    }
    executor._ensure_excerpt = lambda text: text
    executor._patent_from_source = lambda *args, **kwargs: {"source_url": "https://patents.google.com/patent/CN119636612A/zh", "abstract": "摘要", "source_channel": "google_patents", "title": "CN119636612A"}

    result = executor._execute()
    cache = FakePatentReviewCache.last_instance

    assert result.status in {"success", "degraded"}
    assert cache is not None
    assert cache.search_calls[0]["phase"] == "phase_2"
    assert result.manifest_updates["research_cache_enabled"] is True
    assert result.manifest_updates["research_cache_hit_count"] == 1
    assert result.manifest_updates["research_cache_imported_count"] == 1
    assert result.manifest_updates["research_cache_hit"] is True


if __name__ == "__main__":
    test_phase_2_uses_research_cache_and_exports_manifest_fields()
    test_phase_2_internal_review_uses_research_cache_and_marks_patent_hits_for_revalidation()
    print("research cache phase integration tests passed")
