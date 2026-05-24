#!/usr/bin/env python3
"""
Handoff Validator — 阶段交接验证器。
验证上一阶段产出是否满足 HANDOFF_CONTRACT.md 定义的交接条件。
失败时返回明确的缺失字段列表，用于 orchestrate.py 硬阻断。
"""

import os
import re
import json
from pathlib import Path
from typing import Dict, List, Tuple, Any, Callable, Optional

# HANDOFF_CONTRACT.md 中定义的规则（内联到代码中，不依赖外部文件解析）
HANDOFF_RULES = {
    "phase_0": {
        "required_manifest_fields": [
            "run_id",
            "output_dir",
            "preprocess_notes",
            "preprocess_cache_status",
            "source_fingerprints_path",
            "template_rules_ready",
            "style_profile_ready",
            "run_manifest_json_path",
        ],
        "required_artifacts": [
            "artifacts/preprocess/phase_00_preprocess_notes.md",
            "artifacts/preprocess/source_fingerprints.json",
            "template_rules.json",
            "style_profile.json",
            "style_profile.md",
            "artifacts/run_manifest.json",
        ],
        "field_validators": {
            "template_rules_ready": lambda v: v is True,
            "style_profile_ready": lambda v: v is True,
            "source_fingerprints_path": lambda v: isinstance(v, str) and v.endswith("source_fingerprints.json"),
            "run_manifest_json_path": lambda v: isinstance(v, str) and v.endswith("run_manifest.json"),
        },
    },
    "phase_1": {
        "required_manifest_fields": [
            "domain_scope",
        ],
        "required_artifacts": [],
        "field_validators": {},
    },

    "phase_2": {
        "required_manifest_fields": [
            "research_scope_key",
            "research_cache_enabled",
            "research_cache_hit",
            "research_cache_hit_count",
            "research_cache_imported_count",
            "research_cache_path",
            "channels_used",
            "channels_skipped",
            "why_skipped",
            "degraded_run",
            "brain_chain_status",
            "channel_failures",
            "fallback_actions",
            "strong_source_count",
            "evidence_table_count",
            "candidate_directions",
            "recommended_direction",
            "claims_requiring_patent_verification",
            "patent_search_queries",
            "patent_candidate_pool_count",
            "finalRelevantPatents_count",
            "cn_only_passed",
            "freshness_passed",
            "relevance_passed",
            "candidate_pool_generation_mode",
            "candidate_pool_channels_used",
            "trusted_patent_channels",
            "research_pack_path",
            "evidence_pack_path",
        ],
        "required_artifacts": [
            "artifacts/research/phase_02_research_pack.json",
            "artifacts/prior_art/phase_02_patent_candidate_pool.json",
            "artifacts/prior_art/phase_02_evidence_pack.json",
        ],
        "field_validators": {
            "research_cache_enabled": lambda v: v is True,
            "research_cache_hit_count": lambda v: isinstance(v, int) and v >= 0,
            "research_cache_imported_count": lambda v: isinstance(v, int) and v >= 0,
            "strong_source_count": lambda v: isinstance(v, int) and v >= 3,
            "evidence_table_count": lambda v: isinstance(v, int) and v >= 3,
        },
    },
    "phase_3": {
        "required_manifest_fields": [
            "selected_direction",
            "patent_title",
            "phase_03_confirmation",
        ],
        "required_artifacts": [],
        "field_validators": {},
    },
    "phase_5": {
        "required_manifest_fields": [
            "template_rules_ready",
            "style_profile_ready",
            "draft_status",
            "facts_ledger_ready",
            "step_registry_ready",
            "figure_registry_ready",
            "terminology_registry_ready",
            "research_inputs_ready",
            "shared_context_ready",
            "shared_context_within_budget",
            "block_contexts_ready",
            "block_reviews_ready",
        ],
        "required_artifacts": [
            "artifacts/draft/shared_context.json",
            "artifacts/draft/phase_05_writing_plan.json",
            "template_rules.json",
            "style_profile.md",
            "artifacts/draft/facts_ledger.json",
            "artifacts/draft/step_registry.json",
            "artifacts/draft/figure_registry.json",
            "artifacts/draft/terminology_registry.json",
            "artifacts/draft/block_contexts/part_01_context.json",
            "artifacts/draft/block_reviews/part_01_review.json",
        ],
        "field_validators": {
            "template_rules_ready": lambda v: v is True,
            "style_profile_ready": lambda v: v is True,
            "shared_context_ready": lambda v: v is True,
            "shared_context_within_budget": lambda v: v is True,
            "block_contexts_ready": lambda v: v is True,
            "block_reviews_ready": lambda v: v is True,
        },
    },
    "phase_6": {
        "required_manifest_fields": [
            "consistency_audit_score",
            "consistency_audit_passed",
            "top_issues",
        ],
        "required_artifacts": [],
        "field_validators": {
            "consistency_audit_passed": lambda v: v is True,
        },
    },
    "phase_7": {
        "required_manifest_fields": [
            "ipr_review_score",
            "ipr_review_passed",
            "top_risks",
        ],
        "required_artifacts": [],
        "field_validators": {
            "ipr_review_passed": lambda v: v is True,
        },
    },
    "phase_8": {
        "required_manifest_fields": [
            "edit_plan_validated",
            "structured_diff_validated",
            "post_fix_check_passed",
            "review_loop_passed",
        ],
        "required_artifacts": [
            "artifacts/revision/phase_08_edit_plan.json",
            "artifacts/revision/phase_08_structured_diff.json",
            "artifacts/revision/phase_08_post_fix_check_report.md",
            "artifacts/revision/phase_08_post_fix_check.json",
        ],
        "field_validators": {
            "edit_plan_validated": lambda v: v is True,
            "structured_diff_validated": lambda v: v is True,
            "post_fix_check_passed": lambda v: v is True,
            "review_loop_passed": lambda v: v is True,
        },
    },
    "phase_9": {
        "required_manifest_fields": [
            "delivery_health_report_path",
            "delivery_passed",
            "final_docx_path",
            "deliver_dir",
            "deliver_dir_explicit",
            "docx_generated",
            "delivery_structure_passed",
            "delivery_from_dirty_tree",
        ],
        "required_artifacts": [
            "artifacts/delivery/phase_09_delivery_health_report.json",
        ],
        "field_validators": {
            "delivery_passed": lambda v: v is True,
            "deliver_dir_explicit": lambda v: v is True,
            "docx_generated": lambda v: v is True,
            "delivery_structure_passed": lambda v: v is True,
            "final_docx_path": lambda v: isinstance(v, str) and v.endswith("技术交底书.docx"),
        },
    },
}


class HandoffViolation:
    def __init__(self, phase: str, kind: str, field: str, expected: Any, actual: Any):
        self.phase = phase
        self.kind = kind  # "missing_field" | "missing_artifact" | "field_validation"
        self.field = field
        self.expected = expected
        self.actual = actual

    def __str__(self):
        if self.kind == "missing_field":
            return f"[phase_{self.phase}] 缺失必需字段: {self.field}"
        elif self.kind == "missing_artifact":
            return f"[phase_{self.phase}] 缺失必需工件: {self.field}"
        elif self.kind == "field_validation":
            return (
                f"[phase_{self.phase}] 字段验证失败: {self.field}"
                f" (期望: {self.expected}, 实际: {self.actual})"
            )
        return f"[phase_{self.phase}] 未知违规: {self.field}"


class HandoffValidator:
    """
    验证上一阶段产出是否满足交接契约。
    orchestrate.py 在阶段推进前调用，失败时硬阻断。
    """

    def __init__(self, workspace: Path, manifest: Dict[str, Any]):
        self.workspace = Path(workspace)
        self.manifest = manifest
        self.violations: List[HandoffViolation] = []
        self.passed = True

    def _parse_manifest_field(self, field: str) -> Any:
        """从 manifest 字典中解析嵌套字段，如 'research.scope.key'。"""
        keys = field.split(".")
        current = self.manifest
        for k in keys:
            if isinstance(current, dict) and k in current:
                current = current[k]
            else:
                return None
        return current

    def validate_phase(self, phase_id: str) -> Tuple[bool, List[HandoffViolation]]:
        """验证指定阶段是否满足交接条件。"""
        self.violations = []
        self.passed = True

        if phase_id not in HANDOFF_RULES:
            self.violations.append(
                HandoffViolation(phase_id, "missing_field", f"未知阶段: {phase_id}", "已知阶段", phase_id)
            )
            self.passed = False
            return self.passed, self.violations

        rules = HANDOFF_RULES[phase_id]

        # 1. 检查必需字段
        for field in rules.get("required_manifest_fields", []):
            value = self._parse_manifest_field(field)
            if value is None:
                self.violations.append(
                    HandoffViolation(phase_id, "missing_field", field, "存在", None)
                )
                self.passed = False

        # 2. 检查字段验证器
        for field, validator in rules.get("field_validators", {}).items():
            value = self._parse_manifest_field(field)
            if value is None:
                continue  # 已在上面报 missing_field
            try:
                if not validator(value):
                    self.violations.append(
                        HandoffViolation(phase_id, "field_validation", field, "满足验证器", value)
                    )
                    self.passed = False
            except Exception as e:
                self.violations.append(
                    HandoffViolation(phase_id, "field_validation", field, f"验证器可执行 ({e})", value)
                )
                self.passed = False

        # 3. 检查必需工件
        for artifact in rules.get("required_artifacts", []):
            artifact_path = self.workspace / artifact
            if not artifact_path.exists():
                self.violations.append(
                    HandoffViolation(phase_id, "missing_artifact", artifact, "存在", None)
                )
                self.passed = False

        return self.passed, self.violations

    def get_summary(self) -> str:
        lines = []
        if self.passed:
            lines.append("✅ HANDOFF_CONTRACT 验证通过")
        else:
            lines.append(f"❌ HANDOFF_CONTRACT 验证失败: {len(self.violations)} 个违规")
            for v in self.violations:
                lines.append(f"   - {v}")
        return "\n".join(lines)

    def to_dict(self) -> Dict:
        return {
            "passed": self.passed,
            "violations": [
                {
                    "phase": v.phase,
                    "kind": v.kind,
                    "field": v.field,
                    "expected": str(v.expected),
                    "actual": str(v.actual),
                }
                for v in self.violations
            ],
        }


def load_manifest(path: Path) -> Dict[str, Any]:
    """从 Markdown 文件中解析 YAML-like 键值对。"""
    manifest = {}
    if not path.exists():
        return manifest
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # 简单解析：行格式为 "- `key`: value" 或 "- key: value"
    for line in content.split("\n"):
        line = line.strip()
        if not line.startswith("-"):
            continue
        # 去掉开头的 -
        line = line[1:].strip()
        # 尝试匹配 `- `key`: value`
        match = re.match(r"`?([^`:]+)`?\s*:\s*(.*)", line)
        if match:
            key = match.group(1).strip()
            value = match.group(2).strip()
            # 尝试解析 JSON / 布尔值 / 整数
            if value.lower() == "true":
                value = True
            elif value.lower() == "false":
                value = False
            else:
                parsed = None
                if value and value[0] in "[{\"":
                    try:
                        parsed = json.loads(value)
                    except Exception:
                        parsed = None
                if parsed is not None:
                    value = parsed
                else:
                    try:
                        value = int(value)
                    except ValueError:
                        pass
            manifest[key] = value
    state = manifest.get("state")
    if isinstance(state, dict):
        for key, value in state.items():
            manifest.setdefault(key, value)
    return manifest


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Handoff Validator")
    parser.add_argument("--phase", required=True, help="目标阶段 (如 phase_2)")
    parser.add_argument("--workspace", required=True, help="工作目录")
    parser.add_argument("--manifest", required=True, help="Run manifest 路径")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = parser.parse_args()

    manifest = load_manifest(Path(args.manifest))
    validator = HandoffValidator(Path(args.workspace), manifest)
    passed, violations = validator.validate_phase(args.phase)

    print(validator.get_summary())

    if args.json:
        print(json.dumps(validator.to_dict(), ensure_ascii=False, indent=2))

    import sys
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
