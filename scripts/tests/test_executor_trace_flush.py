"""Executor trace flush regression tests."""

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from executors.base_executor import BaseExecutor, ExecutorResult  # noqa: E402


class DummyExecutor(BaseExecutor):
    def _execute(self) -> ExecutorResult:
        self._log("dummy_step", {"ok": True})
        return ExecutorResult(status="success", trace_log=self.trace)


def test_executor_log_flushes_phase_trace_file() -> None:
    workspace = Path(tempfile.mkdtemp())
    executor = DummyExecutor("phase_x", workspace, {})

    result = executor.execute()

    trace_path = workspace / "artifacts" / "phase_x_trace.json"
    assert result.status == "success"
    assert trace_path.exists()
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    assert any(entry["action"] == "dummy_step" for entry in trace)


if __name__ == "__main__":
    test_executor_log_flushes_phase_trace_file()
    print("executor_trace_flush tests passed")
