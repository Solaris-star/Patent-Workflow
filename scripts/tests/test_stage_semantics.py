#!/usr/bin/env python3
"""Stage list and merged Phase 2/4 semantics tests."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import orchestrate  # noqa: E402
from validators.handoff_validator import HANDOFF_RULES  # noqa: E402


def test_stage_list_uses_current_merged_phase_semantics() -> None:
    stages = {stage["id"]: stage for stage in orchestrate.STAGES}

    assert list(stages) == ["phase_0", "phase_1", "phase_2", "phase_3", "phase_5", "phase_6", "phase_7", "phase_8", "phase_9"]
    assert stages["phase_2"]["name"] == "候选专利挖掘、查新与内部专利复核"
    assert stages["phase_2"]["executor"] == "smart_search"
    assert "phase_4" not in stages
    assert "phase_10" not in stages
    assert "phase_11" not in stages


def test_handoff_requires_research_cache_fields_for_phase_2() -> None:
    phase_2_fields = set(HANDOFF_RULES["phase_2"]["required_manifest_fields"])

    for field in [
        "research_cache_enabled",
        "research_cache_hit",
        "research_cache_hit_count",
        "research_cache_imported_count",
        "research_cache_path",
        "patent_search_queries",
        "patent_candidate_pool_count",
        "finalRelevantPatents_count",
        "cn_only_passed",
        "freshness_passed",
        "relevance_passed",
    ]:
        assert field in phase_2_fields
    assert "claims_requiring_patent_verification" in phase_2_fields


if __name__ == "__main__":
    test_stage_list_uses_current_merged_phase_semantics()
    test_handoff_requires_research_cache_fields_for_phase_2()
    print("stage semantics tests passed")
