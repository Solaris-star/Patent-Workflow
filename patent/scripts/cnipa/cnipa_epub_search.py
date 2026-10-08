# -*- coding: utf-8 -*-
"""Run a bounded CNIPA keyword batch and preserve partial outcomes."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from cnipa_batch import run_keyword_batch


def _ensure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, TypeError, ValueError):
            pass


def _terms_from_args(arguments: list[str]) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for argument in arguments:
        for part in (argument or "").split():
            keyword = part.strip()
            if keyword and keyword not in seen:
                terms.append(keyword)
                seen.add(keyword)
    return terms


def _atomic_json(path: Path, data: dict[str, Any], *, overwrite: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        if overwrite:
            os.replace(temp_path, path)
        else:
            # Publish the first snapshot without clobbering a file created after
            # the initial CLI existence check. Later updates may replace only
            # the file this run successfully created.
            os.link(temp_path, path)
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Search CNIPA by keyword with bounded retries")
    parser.add_argument("--output", "-o", help="Optional local JSON file updated after each keyword state change")
    parser.add_argument("--max-retries", type=int, default=2,
                        help="Retries after the first attempt for transient errors; range 0..3")
    parser.add_argument("--overwrite", action="store_true",
                        help="Permit atomically replacing an existing output file")
    parser.add_argument("terms", nargs="*", help="Search terms; whitespace also separates terms")
    return parser


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_stdio()
    args = _build_parser().parse_args(sys.argv[1:] if argv is None else argv)
    terms = _terms_from_args(args.terms)
    if not terms:
        print("usage: python cnipa_epub_search.py [--output result.json] <term> [more terms...]", file=sys.stderr)
        return 2
    if not 0 <= args.max_retries <= 3:
        print("ERROR: --max-retries must be from 0 to 3", file=sys.stderr)
        return 2
    output_path = Path(args.output).expanduser().resolve() if args.output else None
    if output_path and output_path.exists() and not args.overwrite:
        print("ERROR: output already exists; use --overwrite to replace it", file=sys.stderr)
        return 2

    os.environ.setdefault("EPUB_WAF_MAX_WAIT_SEC", "180")
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            browser.close()
    except ImportError:
        print("ERROR: Playwright is not installed; see requirements-cnipa.txt", file=sys.stderr)
        return 1
    except Exception as error:
        message = str(error).casefold()
        if "executable" in message or "browser" in message or "chromium" in message:
            print("ERROR: the local Playwright Chromium runtime is not installed", file=sys.stderr)
        else:
            print("ERROR: local Playwright preflight failed", file=sys.stderr)
        return 1

    from cnipa_epub_crawler import search_epub_keyword
    from cnipa_epub_parse import hits_to_jsonable

    def search(keyword: str) -> list:
        _html, hits = search_epub_keyword(keyword)
        return hits

    latest: dict[str, Any] = {}
    output_created_by_run = False

    def persist(snapshot: dict[str, Any]) -> None:
        nonlocal latest, output_created_by_run
        latest = {
            **snapshot,
            "keywords": terms,
            "max_retries": args.max_retries,
        }
        if output_path:
            _atomic_json(output_path, latest, overwrite=output_created_by_run or args.overwrite)
            output_created_by_run = True

    result = run_keyword_batch(
        terms,
        search,
        max_retries=args.max_retries,
        serialize=hits_to_jsonable,
        on_update=persist if output_path else None,
    )
    latest = {**result, "keywords": terms, "max_retries": args.max_retries}
    if output_path:
        _atomic_json(output_path, latest, overwrite=output_created_by_run or args.overwrite)
    all_hits = [hit for item in result["results"] for hit in item.get("hits", [])]
    print("EPUB_HITS_JSON:", json.dumps(all_hits, ensure_ascii=False), flush=True)
    print("CNIPA_BATCH_JSON:", json.dumps(latest, ensure_ascii=False), flush=True)
    if output_path:
        print("CNIPA_BATCH_SAVED:", str(output_path), file=sys.stderr, flush=True)
    if result.get("security_stop"):
        return 4
    if result.get("status") == "partial":
        return 3
    if result.get("status") == "interrupted":
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
