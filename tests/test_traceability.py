from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "patent" / "scripts"))

import validate_background_pack
import validate_edit_plan
import validate_evidence_pack
import validate_facts_ledger
import validate_ipr_pack
import validate_research_pack
import validate_structured_diff


def evidence_pack() -> dict:
    return {
        "pack_type": "evidence_pack",
        "phase": "phase_04",
        "patent_candidate_pool_path": "artifacts/prior_art/candidates.json",
        "search_trace": {
            "patent_search_queries": ["synthetic scoped query"],
            "final_relevant_patent_count": 1,
        },
        "final_relevant_patents": [{"evidence_id": "E-SYN-1"}],
        "scheme_features": [{
            "feature_id": "F-SYN-1",
            "statement": "Synthetic feature",
            "evidence_kind": "source_claim",
            "status": "source_stated",
            "evidence_ids": ["E-SYN-1"],
        }],
        "evidence": [{
            "evidence_id": "E-SYN-1",
            "url": "https://example.invalid/synthetic-source",
            "excerpt": "Synthetic excerpt for validator tests.",
            "publication_date": "2026-07-15",
            "freshness": "fresh",
            "verification_status": "verified",
            "verified_at": "2026-10-08T00:00:00Z",
            "verification_method": "synthetic fixture",
            "conclusion_use": "usable",
            "feature_ids": ["F-SYN-1"],
            "is_auxiliary": False,
        }],
        "evidence_alignment": [{"feature_id": "F-SYN-1", "evidence_ids": ["E-SYN-1"]}],
    }


class TraceabilityTests(unittest.TestCase):
    def test_facts_ledger_rejects_evidence_refs_missing_from_an_empty_pack(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pack_path = root / "evidence.json"
            pack_path.write_text(json.dumps({
                "pack_type": "evidence_pack", "scheme_features": [], "evidence": [],
            }), encoding="utf-8")
            ledger = {
                "ledger_type": "facts_ledger",
                "terminology": [{"term": "Synthetic", "definition": "Synthetic definition"}],
                "constraints_and_effects": [{"constraint": "Synthetic", "effect": "Synthetic"}],
                "figure_registry": [],
                "source_registry": [{
                    "source_id": "SRC-SYN-1", "source_type": "external_evidence",
                    "evidence_id": "E-UNKNOWN",
                }],
                "feature_registry": [{
                    "feature_id": "F-SYN-1", "statement": "Synthetic feature",
                    "evidence_kind": "source_claim", "status": "source_stated",
                    "source_ids": ["SRC-SYN-1"], "evidence_ids": ["E-UNKNOWN"],
                }],
            }
            errors = validate_facts_ledger.validate_ledger(
                ledger, base_dir=root, evidence_pack_path=pack_path,
            )
            self.assertTrue(any("external evidence_id does not resolve" in error for error in errors))
            self.assertTrue(any("unknown evidence_id" in error for error in errors))

    def test_facts_ledger_does_not_read_an_unregistered_external_evidence_pack(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "case-workspace"
            workspace.mkdir()
            outside_pack = root / "selected-but-not-imported.json"
            outside_pack.write_text(json.dumps(evidence_pack()), encoding="utf-8")
            errors = validate_facts_ledger.validate_ledger(
                {"ledger_type": "facts_ledger"},
                base_dir=workspace,
                evidence_pack_path=outside_pack,
            )
            self.assertTrue(any("evidence pack path must remain inside" in error for error in errors))

    def test_facts_ledger_rejects_external_source_before_filesystem_access(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "case-workspace"
            workspace.mkdir()
            outside = root / "private-source.txt"
            outside.write_text("synthetic external source", encoding="utf-8")
            outside_abs = Path(os.path.abspath(outside))
            calls: list[str] = []

            def guard(name, original):
                def wrapped(path, *args, **kwargs):
                    if Path(os.path.abspath(os.fspath(path))) == outside_abs:
                        calls.append(name)
                        raise AssertionError(f"rejected source reached {name}")
                    return original(path, *args, **kwargs)
                return wrapped

            ledger = {
                "ledger_type": "facts_ledger",
                "terminology": [{"term": "Synthetic", "definition": "Synthetic"}],
                "constraints_and_effects": [{"constraint": "Synthetic", "effect": "Synthetic"}],
                "figure_registry": [],
                "source_registry": [{
                    "source_id": "SRC-SYN-OUTSIDE", "source_type": "code",
                    "path": str(outside_abs), "sha256": "a" * 64,
                }],
                "feature_registry": [],
            }
            with (
                mock.patch.object(Path, "resolve", new=guard("resolve", Path.resolve)),
                mock.patch.object(Path, "stat", new=guard("stat", Path.stat)),
                mock.patch.object(Path, "is_file", new=guard("is_file", Path.is_file)),
                mock.patch.object(Path, "open", new=guard("open", Path.open)),
                mock.patch.object(Path, "read_text", new=guard("read_text", Path.read_text)),
                mock.patch.object(validate_facts_ledger, "sha256_file") as hash_file,
            ):
                errors = validate_facts_ledger.validate_ledger(ledger, base_dir=workspace)

            self.assertTrue(any("source path must remain inside" in error for error in errors))
            self.assertEqual(calls, [])
            hash_file.assert_not_called()

    def test_one_evidence_record_is_enough_and_duplicate_ids_fail(self) -> None:
        pack = evidence_pack()
        errors, counts = validate_evidence_pack.validate(pack)
        self.assertEqual(errors, [])
        self.assertEqual(counts["evidence"], 1)

        pack["evidence"].append(dict(pack["evidence"][0]))
        errors, _ = validate_evidence_pack.validate(pack)
        self.assertTrue(any("duplicate evidence_id" in error for error in errors))

    def test_bad_date_verification_and_feature_mapping_fail_closed(self) -> None:
        pack = evidence_pack()
        pack["evidence"][0]["publication_date"] = "not-a-date"
        pack["evidence"][0]["verification_status"] = "verified-ish"
        pack["evidence"][0]["feature_ids"] = ["F-UNKNOWN"]
        errors, _ = validate_evidence_pack.validate(pack)
        self.assertTrue(any("publication_date" in error for error in errors))
        self.assertTrue(any("verification_status" in error for error in errors))
        self.assertTrue(any("unknown feature_id" in error for error in errors))

    def test_unhashable_evidence_fields_return_validation_errors(self) -> None:
        pack = evidence_pack()
        pack["evidence"][0]["freshness"] = ["fresh"]
        pack["evidence"][0]["verification_status"] = {"verified": True}
        pack["evidence"][0]["conclusion_use"] = ["usable"]
        errors, counts = validate_evidence_pack.validate(pack)
        self.assertTrue(any("freshness" in error for error in errors))
        self.assertTrue(any("verification_status" in error for error in errors))
        self.assertTrue(any("conclusion_use" in error for error in errors))
        self.assertEqual(counts["usable_for_current_conclusions"], 0)

        research = {
            "pack_type": "research_pack", "phase": "phase_02",
            "research_questions": [{"id": "RQ-SYN-1", "question": "Synthetic question"}],
            "outline_skeleton": [{"section_id": "S-SYN-1", "title": "Synthetic", "intent": "Explain",
                                  "covers_questions": ["RQ-SYN-1"], "evidence_ids": ["E-SYN-1"]}],
            "evidence": [{"evidence_id": "E-SYN-1", "url": "https://example.invalid/source",
                          "excerpt": "Synthetic", "publication_date": "2026-07-15",
                          "freshness": [], "verification_status": {}, "conclusion_use": {}}],
        }
        errors, _ = validate_research_pack.validate(research)
        self.assertTrue(any("freshness" in error for error in errors))
        self.assertTrue(any("verification_status" in error for error in errors))
        self.assertTrue(any("conclusion_use" in error for error in errors))

    def test_single_research_question_and_source_pass_without_quota(self) -> None:
        pack = {
            "pack_type": "research_pack",
            "phase": "phase_02",
            "research_questions": [{"id": "RQ-SYN-1", "question": "Synthetic question"}],
            "outline_skeleton": [{
                "section_id": "S-SYN-1", "title": "Synthetic section", "intent": "Explain evidence",
                "covers_questions": ["RQ-SYN-1"], "evidence_ids": ["E-SYN-1"],
            }],
            "evidence": [{
                "evidence_id": "E-SYN-1", "url": "https://example.invalid/source",
                "excerpt": "Synthetic excerpt", "publication_date": "2026-07-15",
                "freshness": "fresh", "verification_status": "verified",
                "verified_at": "2026-10-08T00:00:00Z", "verification_method": "synthetic fixture",
                "conclusion_use": "usable",
            }],
        }
        errors, _ = validate_research_pack.validate(pack)
        self.assertEqual(errors, [])
        pack["evidence"][0]["publication_date"] = "unknown"
        errors, _ = validate_research_pack.validate(pack)
        self.assertTrue(any("unknown publication date" in error for error in errors))

    def test_background_and_ipr_packs_require_verified_mapped_evidence_and_opt_in(self) -> None:
        canonical = evidence_pack()
        background = {
            "pack_type": "background_pack", "phase": "phase_05",
            "closest_source_evidence_id": "E-SYN-1", "evidence_ids": ["E-SYN-1"],
            "feature_comparisons": [{
                "feature_id": "F-SYN-1", "evidence_ids": ["E-SYN-1"],
                "difference": "Synthetic observed difference",
            }],
        }
        self.assertEqual(validate_background_pack.validate(background, canonical)[0], [])
        canonical["evidence"][0]["verification_status"] = "unverified"
        errors, _ = validate_background_pack.validate(background, canonical)
        self.assertTrue(any("verified" in error for error in errors))

        canonical = evidence_pack()
        ipr = {
            "pack_type": "ipr_pack", "phase": "phase_05",
            "assessments": [{
                "assessment_id": "IPR-SYN-1", "scope": "Synthetic scope",
                "feature_ids": ["F-SYN-1"], "evidence_ids": ["E-SYN-1"],
                "status": "reviewed", "summary": "Synthetic result",
                "limitations": "Structure only; no legal conclusion.",
            }],
        }
        self.assertEqual(validate_ipr_pack.validate(ipr, canonical, requested=True)[0], [])
        errors, _ = validate_ipr_pack.validate(ipr, canonical, requested=False)
        self.assertTrue(any("ipr_requested=true" in error for error in errors))

    def test_issue_ids_flow_from_review_scope_through_edit_plan_and_diff(self) -> None:
        issue_id = "ISSUE-SYN-1"
        review = {"issues": [{"issue_id": issue_id, "severity": "medium", "disposition": "open"}]}
        plan = {
            "doc_type": "edit_plan", "phase": "phase_10",
            "approved_issue_scope": {
                "approval_id": "APPROVAL-SYN-1", "confirmed_by_user": True,
                "confirmed_at": "2026-10-08T00:00:00Z", "scope": "Only this synthetic correction.",
                "issue_ids": [issue_id],
            },
            "edits": [{
                "edit_id": "EDIT-SYN-1", "issue_ids": [issue_id],
                "type": "clarify", "problem": "Synthetic issue", "change_instruction": "Clarify without new facts.",
                "risk_if_not_fixed": "medium", "target": {"section": "Synthetic section"},
            }],
            "acceptance_checks": ["Resolve ISSUE-SYN-1 without expanding scope."],
        }
        errors, _ = validate_edit_plan.validate(plan, review)
        self.assertEqual(errors, [])

        diff = {
            "doc_type": "structured_diff", "phase": "phase_10",
            "diff_items": [{
                "linked_edit_id": "EDIT-SYN-1", "issue_ids": [issue_id],
                "change_kind": "replace", "location": {"section": "Synthetic section"},
                "before_excerpt": "Synthetic prior wording.", "after_excerpt": "Synthetic revised wording.",
            }],
        }
        self.assertEqual(validate_structured_diff.validate(diff, plan)[0], [])
        diff["diff_items"][0]["issue_ids"] = ["ISSUE-SYN-OUTSIDE"]
        errors, _ = validate_structured_diff.validate(diff, plan)
        self.assertTrue(any("approved scope" in error for error in errors))

    def test_edit_plan_unhashable_risk_has_a_stable_validation_error(self) -> None:
        issue_id = "ISSUE-SYN-RISK"
        review = {"issues": [{"issue_id": issue_id, "severity": "medium", "disposition": "open"}]}
        plan = {
            "doc_type": "edit_plan", "phase": "phase_10",
            "approved_issue_scope": {
                "approval_id": "APPROVAL-SYN-RISK", "confirmed_by_user": True,
                "confirmed_at": "2026-10-08T00:00:00Z", "scope": "Only this synthetic correction.",
                "issue_ids": [issue_id],
            },
            "edits": [{
                "edit_id": "EDIT-SYN-RISK", "issue_ids": [issue_id],
                "type": "clarify", "problem": "Synthetic issue", "change_instruction": "Clarify safely.",
                "risk_if_not_fixed": ["high"], "target": {"section": "Synthetic section"},
            }],
            "acceptance_checks": ["Resolve the synthetic issue without scope expansion."],
        }
        errors, _ = validate_edit_plan.validate(plan, review)
        self.assertEqual(
            [error for error in errors if "risk_if_not_fixed" in error],
            ["edits[0].risk_if_not_fixed must be high, medium, or low"],
        )

    def test_ipr_unhashable_status_is_reported_without_crashing(self) -> None:
        ipr = {
            "pack_type": "ipr_pack", "phase": "phase_05",
            "assessments": [{
                "assessment_id": "IPR-SYN-UNHASHABLE", "scope": "Synthetic scope",
                "feature_ids": ["F-SYN-1"], "evidence_ids": ["E-SYN-1"],
                "status": ["reviewed"], "summary": "Synthetic result",
                "limitations": "Structure only; no legal conclusion.",
            }],
        }
        errors, _ = validate_ipr_pack.validate(ipr, evidence_pack(), requested=True)
        self.assertTrue(any("status must be reviewed, no_evidence, or pending" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
