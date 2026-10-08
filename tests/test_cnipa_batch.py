from __future__ import annotations

import sys
import json
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "patent" / "scripts" / "cnipa"))

from cnipa_batch import ForbiddenError, SecurityStopError, run_keyword_batch
import cnipa_epub_search


class CnipaBatchTests(unittest.TestCase):
    def test_retryable_failure_retries_once_and_keeps_partial_results(self) -> None:
        calls: dict[str, int] = {}
        snapshots: list[dict] = []

        def mocked_search(keyword: str):
            calls[keyword] = calls.get(keyword, 0) + 1
            if keyword == "transient" and calls[keyword] == 1:
                raise TimeoutError("synthetic transient error")
            if keyword == "permanent":
                raise ValueError("synthetic query error")
            return [{"id": "SYNTHETIC-HIT"}]

        report = run_keyword_batch(
            ["success", "transient", "permanent", "after-error"],
            mocked_search,
            max_retries=2,
            base_delay_seconds=0,
            on_update=snapshots.append,
        )
        self.assertEqual(calls["transient"], 2)
        self.assertEqual(calls["permanent"], 1)
        self.assertEqual(report["status"], "partial")
        self.assertEqual([item["status"] for item in report["results"]], ["success", "success", "error", "success"])
        self.assertEqual(report["results"][0]["hits"], [{"id": "SYNTHETIC-HIT"}])
        self.assertGreaterEqual(len(snapshots), len(report["results"]))

    def test_captcha_stops_remaining_keywords_without_retry(self) -> None:
        calls: list[str] = []

        def mocked_search(keyword: str):
            calls.append(keyword)
            if keyword == "blocked":
                raise SecurityStopError("synthetic security validation")
            return []

        report = run_keyword_batch(["done", "blocked", "must-not-run"], mocked_search, max_retries=3, base_delay_seconds=0)
        self.assertEqual(calls, ["done", "blocked"])
        self.assertEqual(report["status"], "stopped")
        self.assertTrue(report["security_stop"])
        self.assertEqual(report["stop_reason"], "security_validation")
        self.assertEqual(report["results"][1]["attempts"], 1)
        self.assertEqual(report["results"][1]["status"], "blocked")

    def test_http_403_stops_remaining_keywords_without_retry(self) -> None:
        calls: list[str] = []

        def mocked_search(keyword: str):
            calls.append(keyword)
            if keyword == "blocked":
                raise ForbiddenError("synthetic forbidden response")
            return [{"id": "SYNTHETIC-HIT"}]

        report = run_keyword_batch(["first", "blocked", "last"], mocked_search, max_retries=1, base_delay_seconds=0)
        self.assertEqual(calls, ["first", "blocked"])
        self.assertEqual(report["stop_reason"], "forbidden_403")
        self.assertEqual(report["results"][1]["attempts"], 1)
        self.assertEqual(report["results"][0]["status"], "success")

    def test_retry_limit_is_bounded(self) -> None:
        with self.assertRaises(ValueError):
            run_keyword_batch([], lambda _keyword: [], max_retries=4)

    def test_output_publish_is_no_clobber_until_this_run_owns_the_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "batch.json"
            target.write_text("old synthetic contents", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                cnipa_epub_search._atomic_json(target, {"status": "new"})
            self.assertEqual(target.read_text(encoding="utf-8"), "old synthetic contents")

            cnipa_epub_search._atomic_json(target, {"status": "replaced"}, overwrite=True)
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"status": "replaced"})
            target.unlink()
            cnipa_epub_search._atomic_json(target, {"status": "first snapshot"})
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"status": "first snapshot"})


if __name__ == "__main__":
    unittest.main()
