#!/usr/bin/env python3
"""Research cache MVP tests."""

import tempfile
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from research_cache import ResearchCache  # noqa: E402


def test_research_cache_imports_external_notes_and_searches_fts() -> None:
    root = Path(tempfile.mkdtemp()) / "cache"
    cache = ResearchCache(root)
    notes = [
        {
            "note_id": "RN-001",
            "source_type": "technical",
            "source_channel": "smart-search",
            "site": "example.com",
            "title": "智能驾驶链路异常预警实践",
            "url": "https://example.com/autodrive-link-warning",
            "page_summary": "文章讨论智能驾驶数据传输链路异常预警和故障恢复。",
            "key_technical_facts": ["需要端到端追踪链路状态。"],
            "do_not_overclaim": "不能证明专利新颖性。",
            "usable_in_writing": True,
        }
    ]

    report = cache.import_source_reading_notes(notes, phase="phase_2", query="智能驾驶 数据传输", domain_scope="智能驾驶")
    results = cache.search("智能驾驶 链路异常", phase="phase_2", limit=5)

    assert report["imported_count"] == 1
    assert results[0]["url"] == "https://example.com/autodrive-link-warning"
    assert "链路异常预警" in results[0]["page_summary"]
    assert (root / "cache.db").exists()
    assert list((root / "records").glob("**/*.jsonl"))


def test_research_cache_exposes_patent_hits_as_revalidation_candidates() -> None:
    root = Path(tempfile.mkdtemp()) / "cache"
    cache = ResearchCache(root)
    notes = [
        {
            "source_type": "patent",
            "source_channel": "google_patents",
            "site": "patents.google.com",
            "title": "一种智能驾驶数据传输异常预警方法",
            "url": "https://patents.google.com/patent/CN119636612A/zh",
            "page_summary": "摘要公开智能驾驶数据传输异常检测、链路健康评估和预警输出。",
            "key_technical_facts": ["根据链路健康指标生成预警。"],
            "do_not_overclaim": "法律状态和权利要求范围必须重新验证。",
        }
    ]

    report = cache.import_source_reading_notes(notes, phase="phase_2", query="智能驾驶 数据传输异常", domain_scope="智能驾驶")
    results = cache.search("智能驾驶 数据传输异常", phase="phase_2", source_types=["patent"], limit=5)

    assert report["imported_count"] == 1
    assert results[0]["source_type"] == "patent"
    assert "CN119636612A" in results[0]["url"]


def test_research_cache_skips_local_project_and_private_paths() -> None:
    root = Path(tempfile.mkdtemp()) / "cache"
    cache = ResearchCache(root)
    notes = [
        {"source_type": "local_project", "title": "本地项目", "url": "docs/design.md", "page_summary": "私有项目资料"},
        {"source_type": "technical", "title": "泄漏路径", "url": "/Users/solar/private.md", "page_summary": "本地路径"},
    ]

    report = cache.import_source_reading_notes(notes, phase="phase_2", query="私有项目", domain_scope="内部")
    results = cache.search("私有项目", phase="phase_2", limit=5)

    assert report["imported_count"] == 0
    assert report["skipped_private_count"] == 2
    assert results == []


if __name__ == "__main__":
    test_research_cache_imports_external_notes_and_searches_fts()
    test_research_cache_exposes_patent_hits_as_revalidation_candidates()
    test_research_cache_skips_local_project_and_private_paths()
    print("research_cache tests passed")
