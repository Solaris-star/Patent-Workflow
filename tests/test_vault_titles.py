from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "patent-vault" / "scripts"))

import vault


class VaultTitleTests(unittest.TestCase):
    def test_title_check_and_new_case_registration_use_the_24_character_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(vault.cmd_check_title(root, "x" * 24), 0)
            self.assertTrue(json.loads(output.getvalue())["ok"])

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(vault.cmd_check_title(root, "x" * 25), 2)
            self.assertIn("at most 24", json.loads(output.getvalue())["error"])

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(vault.cmd_register_case(root, json.dumps({"title": "x" * 25})), 2)
            self.assertFalse((root / "cases.json").exists())

            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(vault.cmd_register_case(root, json.dumps({"title": "x" * 24})), 0)
            self.assertEqual(len(json.loads((root / "cases.json").read_text(encoding="utf-8"))["cases"]), 1)


if __name__ == "__main__":
    unittest.main()
