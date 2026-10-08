from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "patent" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from check_public_release import scan


class PublicReleaseTests(unittest.TestCase):
    def test_release_check_detects_credentials_without_echoing_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            private_value = "Q" * 28
            (root / "sample.md").write_text("access_token=" + private_value, encoding="utf-8")
            report = scan(root)
            rendered = str(report)
            self.assertFalse(report["checks_passed"])
            self.assertEqual(report["credential_scan"]["findings"][0]["rule"], "credential_assignment")
            self.assertNotIn(private_value, rendered)
            self.assertEqual(report["publication_readiness"]["status"], "not_certified")

    def test_placeholder_email_is_allowed_but_real_contact_shape_is_flagged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "readme.md").write_text("demo@example.invalid", encoding="utf-8")
            placeholder = scan(root)
            self.assertEqual(placeholder["credential_scan"]["status"], "passed")
            self.assertFalse(placeholder["checks_passed"])
            self.assertIn("public example manifest is missing", placeholder["sample_manifest"]["errors"])
            test_address = "person@" + "samplemail.com"
            (root / "readme.md").write_text("synthetic " + test_address, encoding="utf-8")
            report = scan(root)
            self.assertFalse(report["checks_passed"])
            self.assertEqual(report["credential_scan"]["findings"][0]["rule"], "email_address")
            self.assertNotIn(test_address, str(report))

    def test_mermaid_text_and_synthetic_sample_manifest_are_checked_independently(self) -> None:
        import hashlib
        import json

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sample = root / "samples" / "synthetic-flow.mmd"
            sample.parent.mkdir()
            sample.write_text("flowchart TD\n  A-->B\n", encoding="utf-8")
            manifest = root / "examples.json"
            write_manifest = lambda review: manifest.write_text(json.dumps({
                "schema_version": 1,
                "sample_roots": ["samples"],
                "samples": [{
                    "path": "samples/synthetic-flow.mmd",
                    "sha256": hashlib.sha256(sample.read_bytes()).hexdigest(),
                    "source_status": "synthetic",
                    "human_review_status": review,
                }],
            }), encoding="utf-8")
            write_manifest("pending")
            pending = scan(root, manifest)
            self.assertEqual(pending["sample_manifest"]["status"], "needs_review")
            self.assertEqual(pending["human_semantic_review"]["status"], "pending")
            self.assertEqual(pending["publication_readiness"]["status"], "not_certified")

            private_value = "synthetic-" + "secret-" + "value"
            sample.write_text("flowchart TD\n  A-->B\n  %% access_token=" + private_value + "\n", encoding="utf-8")
            drifted = scan(root, manifest)
            self.assertFalse(drifted["sample_manifest"]["integrity_passed"])
            self.assertEqual(drifted["credential_scan"]["status"], "failed")
            self.assertNotIn(private_value, str(drifted))

    def test_complete_synthetic_inventory_still_does_not_certify_publication(self) -> None:
        import hashlib
        import json

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sample = root / "samples" / "synthetic-flow.mmd"
            sample.parent.mkdir()
            sample.write_text("flowchart TD\n  A-->B\n", encoding="utf-8")
            manifest = root / "examples.json"
            manifest.write_text(json.dumps({
                "schema_version": 1,
                "sample_roots": ["samples"],
                "samples": [{
                    "path": "samples/synthetic-flow.mmd",
                    "sha256": hashlib.sha256(sample.read_bytes()).hexdigest(),
                    "source_status": "synthetic",
                    "human_review_status": "reviewed",
                    "human_reviewed_at": "2026-10-08T00:00:00Z",
                    "human_review_reference": "synthetic test fixture",
                }],
            }), encoding="utf-8")
            report = scan(root, manifest)
            self.assertTrue(report["sample_manifest"]["integrity_passed"])
            self.assertEqual(report["sample_manifest"]["status"], "passed")
            self.assertEqual(report["publication_readiness"]["status"], "not_certified")

    def test_unhashable_source_status_is_reported_without_crashing(self) -> None:
        import hashlib
        import json

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sample = root / "samples" / "synthetic-flow.mmd"
            sample.parent.mkdir()
            sample.write_text("flowchart TD\n  A-->B\n", encoding="utf-8")
            manifest = root / "examples.json"
            manifest.write_text(json.dumps({
                "schema_version": 1,
                "sample_roots": ["samples"],
                "samples": [{
                    "path": "samples/synthetic-flow.mmd",
                    "sha256": hashlib.sha256(sample.read_bytes()).hexdigest(),
                    "source_status": [],
                    "human_review_status": "reviewed",
                    "human_reviewed_at": "2026-10-08T00:00:00Z",
                    "human_review_reference": "synthetic test fixture",
                }],
            }), encoding="utf-8")
            report = scan(root, manifest)
            self.assertFalse(report["checks_passed"])
            self.assertTrue(any("source_status" in error for error in report["sample_manifest"]["errors"]))


if __name__ == "__main__":
    unittest.main()
