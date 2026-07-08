#!/usr/bin/env python3
"""
Gate Runner — 门禁运行器。
封装 run_phase_gates.py 的调用，捕获输出，解析结果，返回结构化状态。
解决坑点：orchestrate.py 需要可靠的门禁执行和结果解析。
"""

import os
import sys
import json
import subprocess
from pathlib import Path
from typing import Dict, Any, Tuple, Optional
from dataclasses import dataclass


@dataclass
class GateResult:
    passed: bool
    phase: str
    stdout: str
    stderr: str
    exit_code: int
    summary: Optional[str] = None
    details: Optional[Dict] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "phase": self.phase,
            "exit_code": self.exit_code,
            "summary": self.summary,
            "details": self.details,
        }


class GateRunner:
    """运行指定阶段的门禁脚本。"""

    def __init__(self, workspace: Path, manifest_path: Path):
        self.workspace = Path(workspace)
        self.manifest_path = Path(manifest_path)
        self.script_dir = Path(__file__).parent.parent

    def run(self, phase: str, extra_args: Optional[Dict[str, str]] = None) -> GateResult:
        """运行门禁脚本。"""
        # phase 参数去掉 "phase_" 前缀以适配 run_phase_gates.py
        phase_num = phase.replace("phase_", "")
        cmd = [
            sys.executable,
            str(self.script_dir / "run_phase_gates.py"),
            "--phase", phase_num,
            "--workspace", str(self.workspace),
            "--manifest", str(self.manifest_path),
        ]

        # 阶段 9 需要额外参数
        if extra_args:
            for key, value in extra_args.items():
                cmd.extend([f"--{key}", value])

        print(f"🔒 运行门禁: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 门禁脚本最多运行5分钟
            )

            exit_code = result.returncode
            stdout = result.stdout
            stderr = result.stderr

            # 解析结果
            passed = exit_code == 0
            summary = self._extract_summary(stdout)
            details = self._extract_json(stdout)

            if not passed:
                print(f"❌ 门禁未通过 (exit_code={exit_code})")
                if stderr:
                    print(f"   stderr: {stderr[:500]}")
            else:
                print(f"✅ 门禁通过")

            return GateResult(
                passed=passed,
                phase=phase,
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
                summary=summary,
                details=details,
            )

        except subprocess.TimeoutExpired:
            print(f"❌ 门禁超时 (>300s)")
            return GateResult(
                passed=False,
                phase=phase,
                stdout="",
                stderr="timeout",
                exit_code=-1,
                summary="门禁脚本超时",
            )
        except Exception as e:
            print(f"❌ 门禁执行异常: {e}")
            return GateResult(
                passed=False,
                phase=phase,
                stdout="",
                stderr=str(e),
                exit_code=-2,
                summary=f"门禁执行异常: {e}",
            )

    def _extract_summary(self, stdout: str) -> Optional[str]:
        """从 stdout 中提取 summary 行。"""
        for line in stdout.split("\n"):
            if "summary" in line.lower() or "result" in line.lower():
                return line.strip()
        return None

    def _extract_json(self, stdout: str) -> Optional[Dict]:
        """尝试从 stdout 中提取 JSON 块。"""
        try:
            # 查找可能的 JSON 块
            start = stdout.find("{")
            if start >= 0:
                # 尝试解析最后一个 { 开头的块
                for candidate in reversed(stdout[start:].split("{")):
                    if not candidate:
                        continue
                    try:
                        return json.loads("{" + candidate)
                    except json.JSONDecodeError:
                        continue
        except Exception:
            pass
        return None


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Gate Runner")
    parser.add_argument("--phase", required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    runner = GateRunner(Path(args.workspace), Path(args.manifest))
    result = runner.run(args.phase)

    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2) if args.json else result.summary)

    sys.exit(0 if result.passed else 1)


if __name__ == "__main__":
    main()
