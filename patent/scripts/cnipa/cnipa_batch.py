"""Bounded, offline-testable batching primitives for CNIPA keyword searches."""

from __future__ import annotations

import time
from typing import Any, Callable, Iterable


class SecurityStopError(RuntimeError):
    """Search cannot continue until the site security challenge is resolved."""


class ForbiddenError(RuntimeError):
    """The service returned HTTP 403; the batch must stop without retries."""


def classify_error(error: BaseException) -> str:
    """Return a stable category without persisting exception text or page data."""
    if isinstance(error, ForbiddenError):
        return "forbidden_403"
    if isinstance(error, SecurityStopError):
        return "security_validation"
    message = str(error).casefold()
    if "403" in message or "forbidden" in message:
        return "forbidden_403"
    if any(token in message for token in (
        "captcha", "verification", "security validation", "human verification",
        "验证码", "安全验证", "人机验证", "访问过于频繁", "访问频繁",
    )):
        return "security_validation"
    if isinstance(error, (TimeoutError, ConnectionError, OSError)) or any(token in message for token in (
        "timed out", "timeout", "connection reset", "connection aborted",
        "temporarily unavailable", "temporary failure", "net::err_",
        "429", "502", "503", "504",
    )):
        return "retryable_transient"
    return "non_retryable"


def _safe_status(category: str) -> tuple[str, bool]:
    if category == "forbidden_403":
        return "blocked", True
    if category == "security_validation":
        return "blocked", True
    return "error", False


def run_keyword_batch(
    keywords: Iterable[str],
    search_one: Callable[[str], Any],
    *,
    max_retries: int = 2,
    base_delay_seconds: float = 1.0,
    max_delay_seconds: float = 4.0,
    sleep: Callable[[float], None] = time.sleep,
    serialize: Callable[[Any], Any] | None = None,
    on_update: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Search each keyword, preserving per-keyword outcomes after partial failure.

    ``max_retries`` means retries *after* the first attempt and is deliberately
    capped at three. Security validation and HTTP 403 stop immediately and are
    never retried. ``on_update`` receives snapshots after a keyword starts and
    whenever its state changes, so callers can persist partial progress.
    """
    if not isinstance(max_retries, int) or isinstance(max_retries, bool) or not 0 <= max_retries <= 3:
        raise ValueError("max_retries must be an integer from 0 to 3")
    if base_delay_seconds < 0 or max_delay_seconds < 0:
        raise ValueError("retry delays must be non-negative")
    items = [str(term).strip() for term in keywords if str(term).strip()]
    result: dict[str, Any] = {
        "schema_version": 1,
        "status": "running",
        "results": [],
        "security_stop": False,
        "stop_reason": None,
    }
    convert = serialize or (lambda value: value)

    def publish() -> None:
        if on_update:
            on_update({**result, "results": [dict(entry) for entry in result["results"]]})

    for keyword in items:
        entry: dict[str, Any] = {
            "keyword": keyword,
            "status": "running",
            "attempts": 0,
            "hits": [],
            "hit_count": 0,
            "error_code": None,
        }
        result["results"].append(entry)
        publish()
        for attempt in range(1, max_retries + 2):
            entry["attempts"] = attempt
            publish()
            try:
                raw = search_one(keyword)
                serialized = convert(raw)
                if serialized is None:
                    serialized = []
                if not isinstance(serialized, list):
                    serialized = [serialized]
                entry.update({
                    "status": "success",
                    "hits": serialized,
                    "hit_count": len(serialized),
                    "error_code": None,
                    "last_retryable_error": None,
                })
                publish()
                break
            except KeyboardInterrupt:
                entry.update({"status": "interrupted", "error_code": "interrupted"})
                result["status"] = "interrupted"
                result["stop_reason"] = "interrupted"
                publish()
                return result
            except Exception as error:
                category = classify_error(error)
                if category in {"forbidden_403", "security_validation"}:
                    entry.update({"status": "blocked", "error_code": category})
                    result["security_stop"] = True
                    result["status"] = "stopped"
                    result["stop_reason"] = category
                    publish()
                    return result
                if category == "retryable_transient" and attempt <= max_retries:
                    entry["last_retryable_error"] = category
                    delay = min(max_delay_seconds, base_delay_seconds * (2 ** (attempt - 1)))
                    publish()
                    if delay:
                        try:
                            sleep(delay)
                        except KeyboardInterrupt:
                            entry.update({"status": "interrupted", "error_code": "interrupted"})
                            result["status"] = "interrupted"
                            result["stop_reason"] = "interrupted"
                            publish()
                            return result
                    continue
                entry.update({
                    "status": "error",
                    "error_code": "retry_exhausted" if category == "retryable_transient" else category,
                })
                publish()
                break

    statuses = {entry["status"] for entry in result["results"]}
    if "error" in statuses or "interrupted" in statuses:
        result["status"] = "partial"
    else:
        result["status"] = "completed"
    return result
