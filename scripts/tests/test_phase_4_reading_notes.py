#!/usr/bin/env python3
"""Phase 2 internal patent-review source reading notes tests."""

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from executors.phase_4_executor import PhaseExecutor  # noqa: E402


def test_phase_2_internal_review_builds_source_reading_notes_from_patent_search_content() -> None:
    executor = PhaseExecutor("phase_2", Path(tempfile.mkdtemp()), {})
    queries = [{"id": "PQ-BASE-01", "channel": "google_patents", "query": "site:patents.google.com 智能驾驶数据传输"}]
    search_results = [
        {
            "query_id": "PQ-BASE-01",
            "channel": "google_patents",
            "query": "site:patents.google.com 智能驾驶数据传输",
            "status": "ok",
            "content": "CN119636612A 公开了一种智能驾驶数据传输异常预警方法。摘要显示该方案采集链路状态并进行故障恢复。",
            "sources": [
                {"title": "CN119636612A", "url": "https://patents.google.com/patent/CN119636612A/zh", "site": "Google Patents", "patent_channel": "google_patents"}
            ],
        }
    ]

    notes = executor._build_source_reading_notes(queries, search_results)

    assert notes[0]["url"] == "https://patents.google.com/patent/CN119636612A/zh"
    assert notes[0]["source_type"] == "patent"
    assert "智能驾驶数据传输异常预警" in notes[0]["page_summary"]
    assert notes[0]["usable_in_writing"] is True


if __name__ == "__main__":
    test_phase_2_internal_review_builds_source_reading_notes_from_patent_search_content()
    print("phase_2_internal_patent_review_reading_notes tests passed")
