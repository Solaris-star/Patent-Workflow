#!/usr/bin/env python3
"""
Base Executor — 阶段执行器基类。
提供：retry（指数退避）、fallback 链、degraded_run 自动标记、
部分成功处理、错误分类、trace 日志。
解决坑点：executor 调用外部 skill 失败。
"""

import os
import sys
import time
import json
import subprocess
import traceback
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable, Tuple
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ExecutorResult:
    """执行器结果。"""
    status: str  # "success" | "partial" | "failed" | "degraded"
    artifacts: List[str] = field(default_factory=list)
    manifest_updates: Dict[str, Any] = field(default_factory=dict)
    trace_log: List[Dict] = field(default_factory=list)
    error: Optional[str] = None
    degraded_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "artifacts": self.artifacts,
            "manifest_updates": self.manifest_updates,
            "trace_log": self.trace_log,
            "error": self.error,
            "degraded_reason": self.degraded_reason,
        }


class ExecutorError(Exception):
    """执行器错误基类。"""
    pass


class RecoverableError(ExecutorError):
    """可恢复错误（如网络超时、服务暂时不可用）。"""
    pass


class UnrecoverableError(ExecutorError):
    """不可恢复错误（如文件不存在、配置错误）。"""
    pass


class PartialSuccessError(ExecutorError):
    """部分成功错误（主链路失败但备用链路成功）。"""
    pass


class BaseExecutor(ABC):
    """
    阶段执行器基类。
    子类实现 execute() 方法，基类负责 retry、fallback、日志。
    """

    def __init__(self, phase_id: str, workspace: Path, manifest: Dict[str, Any]):
        self.phase_id = phase_id
        self.workspace = Path(workspace)
        self.manifest = manifest
        self.trace: List[Dict] = []
        self.max_retries = 3
        self.retry_base_delay = 2.0  # 秒
        self.retry_max_delay = 30.0  # 秒
        self.fallback_executors: List[Callable] = []  # 备用执行器链
        self.trace_path = self.run_dir / f"{self.phase_id}_trace.json"

    @property
    def run_dir(self) -> Path:
        """本轮过程产物根目录。从 manifest 读取，无值时回退到 workspace。"""
        rd = self.manifest.get("run_dir", "")
        if rd:
            p = Path(rd)
            if not p.is_absolute():
                p = self.workspace / p
            return p
        return self.workspace

    # ── Trace 日志 ─────────────────────────────
    def _log(self, action: str, detail: Dict[str, Any]):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "phase": self.phase_id,
            "action": action,
            "detail": detail,
        }
        self.trace.append(entry)
        self._flush_trace()

    def _flush_trace(self):
        """实时落盘阶段 trace，避免长耗时外部命令期间只有内存日志。"""
        try:
            self.trace_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.trace_path, "w", encoding="utf-8") as f:
                json.dump(self.trace, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ── Retry 机制（指数退避）───────────────────
    def _with_retry(self, fn: Callable, *args, **kwargs) -> Any:
        """执行函数，失败时按指数退避重试。"""
        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                self._log("retry_attempt", {"attempt": attempt, "max": self.max_retries})
                return fn(*args, **kwargs)
            except RecoverableError as e:
                last_error = e
                if attempt < self.max_retries:
                    delay = min(
                        self.retry_base_delay * (2 ** (attempt - 1)),
                        self.retry_max_delay,
                    )
                    self._log("retry_delay", {"attempt": attempt, "delay": delay, "error": str(e)})
                    print(f"   ⏳ 可恢复错误，{delay:.1f}s 后重试 ({attempt}/{self.max_retries}): {e}")
                    time.sleep(delay)
                else:
                    self._log("retry_exhausted", {"attempt": attempt, "error": str(e)})
                    raise
            except UnrecoverableError as e:
                self._log("unrecoverable", {"error": str(e), "traceback": traceback.format_exc()})
                raise  # 不可恢复错误不重试
            except Exception as e:
                # 未知错误，尝试重试一次后放弃
                last_error = e
                if attempt == 1:
                    self._log("unknown_error_retry", {"error": str(e)})
                    time.sleep(self.retry_base_delay)
                else:
                    self._log("unknown_error_fatal", {"error": str(e)})
                    raise RecoverableError(f"未知错误（已重试）: {e}") from e

        raise last_error

    # ── Fallback 链 ───────────────────────────
    def _try_fallback(self, primary_result: Optional[ExecutorResult] = None) -> ExecutorResult:
        """主执行器失败后，依次尝试备用执行器。"""
        for idx, fallback_fn in enumerate(self.fallback_executors):
            try:
                print(f"   🔄 尝试备用方案 {idx + 1}/{len(self.fallback_executors)}")
                result = fallback_fn()
                self._log("fallback_success", {"fallback_index": idx})
                # 标记为降级运行
                result.status = "degraded"
                result.degraded_reason = f"主执行器失败，备用方案 {idx + 1} 成功"
                return result
            except Exception as e:
                self._log("fallback_failed", {"fallback_index": idx, "error": str(e)})
                print(f"   ❌ 备用方案 {idx + 1} 失败: {e}")
                continue

        # 所有备用方案都失败
        return ExecutorResult(
            status="failed",
            error="主执行器和所有备用方案均失败",
            trace_log=self.trace,
        )

    # ── 运行外部命令（封装 subprocess）────────
    def run_command(
        self,
        cmd: List[str],
        timeout: int = 300,
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[Path] = None,
    ) -> Tuple[int, str, str]:
        """运行外部命令，带错误分类。"""
        self._log("command_start", {"cmd": cmd, "timeout": timeout})
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                env={**os.environ, **(env or {})},
                cwd=cwd,
            )
            self._log("command_end", {
                "exit_code": result.returncode,
                "stdout_len": len(result.stdout),
                "stderr_len": len(result.stderr),
            })
            if result.returncode != 0:
                # 分类错误
                stderr_lower = result.stderr.lower()
                if any(k in stderr_lower for k in ["timeout", "timed out", "connection"]):
                    raise RecoverableError(f"命令超时或连接失败: {result.stderr[:200]}")
                elif any(k in stderr_lower for k in ["not found", "no such", "does not exist"]):
                    raise UnrecoverableError(f"资源不存在: {result.stderr[:200]}")
                else:
                    raise RecoverableError(f"命令失败 (exit={result.returncode}): {result.stderr[:200]}")
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            self._log("command_timeout", {"timeout": timeout})
            raise RecoverableError(f"命令超时 (> {timeout}s)")
        except FileNotFoundError as e:
            self._log("command_not_found", {"error": str(e)})
            raise UnrecoverableError(f"命令未找到: {e}")
        except Exception as e:
            self._log("command_exception", {"error": str(e), "traceback": traceback.format_exc()})
            raise RecoverableError(f"命令执行异常: {e}")

    # ── 核心执行接口 ──────────────────────────
    @abstractmethod
    def _execute(self) -> ExecutorResult:
        """子类实现的核心逻辑。"""
        pass

    def execute(self) -> ExecutorResult:
        """
        公开的执行入口。自动处理 retry 和 fallback。
        orchestrate.py 调用此方法，不直接调用 _execute。
        """
        print(f"\n🚀 执行阶段: {self.phase_id}")
        try:
            # 尝试主执行逻辑（带 retry）
            result = self._with_retry(self._execute)
            self._log("execute_success", {"artifacts": result.artifacts})
            return result
        except RecoverableError as e:
            print(f"   ⚠️ 主执行器失败（可恢复错误耗尽重试）: {e}")
            return self._try_fallback()
        except UnrecoverableError as e:
            print(f"   ❌ 主执行器失败（不可恢复错误）: {e}")
            return self._try_fallback()
        except Exception as e:
            print(f"   ❌ 主执行器失败（未知错误）: {e}")
            return self._try_fallback()

    # ── 工具方法 ─────────────────────────────
    def save_artifact(self, data: Any, path: str) -> Path:
        """保存工件到本轮产物目录 (run_dir)。"""
        full_path = self.run_dir / path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, (dict, list)):
            with open(full_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        elif isinstance(data, str):
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(data)
        else:
            raise ValueError(f"不支持的数据类型: {type(data)}")
        self._log("artifact_saved", {"path": str(full_path)})
        return full_path

    def save_workspace_artifact(self, data: Any, path: str) -> Path:
        """保存工件到 workspace 级目录（模板、风格画像等跨轮复用数据）。"""
        full_path = self.workspace / path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, (dict, list)):
            with open(full_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        elif isinstance(data, str):
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(data)
        else:
            raise ValueError(f"不支持的数据类型: {type(data)}")
        self._log("workspace_artifact_saved", {"path": str(full_path)})
        return full_path

    def load_artifact(self, path: str) -> Any:
        """读取本轮产物目录中的工件。"""
        full_path = self.run_dir / path
        if not full_path.exists():
            raise UnrecoverableError(f"工件不存在: {full_path}")
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return content

    def load_workspace_artifact(self, path: str) -> Any:
        """读取 workspace 级工件。"""
        full_path = self.workspace / path
        if not full_path.exists():
            raise UnrecoverableError(f"工件不存在: {full_path}")
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return content

    def update_manifest(self, updates: Dict[str, Any]):
        """更新 manifest 字典（由 orchestrate.py 负责持久化）。"""
        self.manifest.update(updates)
        self._log("manifest_updated", {"keys": list(updates.keys())})
