#!/usr/bin/env python3
"""Run patent-workflow gate validators for a given phase and emit a concise JSON summary.

Design goals:
- Very small dependency surface (stdlib only)
- Works with fixed artifact paths (A-mode)
- Produces audit-friendly output
- Optionally patches a markdown run manifest by replacing the JSON block between markers

Usage examples:
  python run_phase_gates.py --phase 2 --workspace .
  python run_phase_gates.py --phase 4 --workspace .
  python run_phase_gates.py --phase 5 --workspace .
  python run_phase_gates.py --phase 8 --workspace .
  python run_phase_gates.py --phase 9 --workspace . --deliver-dir <dir> --patent-title <title>

Patch run manifest (A-mode):
  python run_phase_gates.py --phase 4 --workspace . --manifest artifacts/run_manifest.md

Run all phases (skips phase 9 unless deliver args provided):
  python run_phase_gates.py --phase all --workspace . --manifest artifacts/run_manifest.md

Exit codes:
  0 = all gates passed
  2 = any gate failed
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


JSON_BEGIN = "<!-- GATE_RESULTS_JSON_BEGIN -->"
JSON_END = "<!-- GATE_RESULTS_JSON_END -->"


def _run(cmd: list[str]) -> dict:
    started = datetime.now(timezone.utc)
    try:
        # Force UTF-8 to avoid mojibake in captured logs on Windows.
        # Also ensure we run a UTF-8 mode Python even if host default is cp936.
        if cmd and cmd[0] == "python":
            cmd = [sys.executable, *cmd[1:]]

        try:
            import os

            env = {**os.environ, **{"PYTHONUTF8": "1"}}
        except Exception:
            env = {"PYTHONUTF8": "1"}

        p = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        out = (p.stdout or "").strip()
        err = (p.stderr or "").strip()
        return {
            "cmd": cmd,
            "exitCode": p.returncode,
            "stdout": out,
            "stderr": err,
            "startedAt": started.isoformat(),
            "finishedAt": datetime.now(timezone.utc).isoformat(),
            "passed": p.returncode == 0,
        }
    except Exception as e:
        return {
            "cmd": cmd,
            "exitCode": 99,
            "stdout": "",
            "stderr": str(e),
            "startedAt": started.isoformat(),
            "finishedAt": datetime.now(timezone.utc).isoformat(),
            "passed": False,
        }


def _patch_manifest(manifest_path: Path, summary_json: str) -> None:
    """Replace the JSON code block between markers.

    If markers are missing, append a new block at the end.
    """
    text = manifest_path.read_text(encoding="utf-8") if manifest_path.exists() else ""

    block = (
        f"{JSON_BEGIN}\n"
        "```json\n"
        f"{summary_json}\n"
        "```\n"
        f"{JSON_END}\n"
    )

    if JSON_BEGIN in text and JSON_END in text:
        pre = text.split(JSON_BEGIN, 1)[0]
        post = text.split(JSON_END, 1)[1]
        new_text = pre + block + post.lstrip("\r\n")
    else:
        sep = "\n" if text and not text.endswith("\n") else ""
        new_text = text + sep + "\n" + block

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(new_text, encoding="utf-8")


def _scripts_dir(ws: Path) -> Path:
    return ws / "skills" / "patent-workflow" / "scripts"


def _artifact_paths(ws: Path) -> dict:
    return {
        "research_pack": ws / "artifacts" / "research" / "phase_02_research_pack.json",
        "candidate_pool": ws / "artifacts" / "prior_art" / "phase_02_patent_candidate_pool.json",
        "evidence_pack": ws / "artifacts" / "prior_art" / "phase_02_evidence_pack.json",
        "facts_ledger": ws / "artifacts" / "draft" / "facts_ledger.json",
        "edit_plan": ws / "artifacts" / "revision" / "phase_08_edit_plan.json",
        "structured_diff": ws / "artifacts" / "revision" / "phase_08_structured_diff.json",
        "consistency_report": ws / "artifacts" / "audit" / "phase_06_consistency_audit_report.md",
        "ipr_report": ws / "artifacts" / "audit" / "phase_07_ipr_review_report.md",
        "health_report": ws / "artifacts" / "delivery" / "phase_09_delivery_health_report.json",
    }


def _run_phase(phase: int, ws: Path, deliver_dir: Optional[str], patent_title: Optional[str]) -> list[dict]:
    scripts = _scripts_dir(ws)
    ap = _artifact_paths(ws)
    runs: list[dict] = []

    if phase == 2:
        # 1. Schema compliance check
        runs.append(_run(["python", str(scripts / "validate_research_pack.py"), str(ap["research_pack"])]))
        # 2. Patent candidate pool + freshness check
        runs.append(_run(["python", str(scripts / "validate_patent_candidates.py"), str(ap["candidate_pool"])]))
        # 3. Evidence pack completeness
        runs.append(_run(["python", str(scripts / "validate_evidence_pack.py"), str(ap["evidence_pack"])]))
        # 4. Inline: search_log completeness (all backend providers present via provider_stats[])
        runs.append(_check_search_log(ap["research_pack"]))
        # 5. Inline: raw JSON archive exists
        runs.append(_check_raw_archive(ws))
        # 6. Inline: freshness enforcement on candidate pool
        runs.append(_check_freshness(ap["candidate_pool"]))
        # 7. Inline: evidence date freshness (each source_reading_note / evidence must be recent)
        runs.append(_check_evidence_dates(ap["research_pack"]))
        # 8. Inline: CNIPA patent verification — candidate patents must have verification records
        #    from Google Patents/CNIPA lookup showing actual titles/abstracts.
        #    This prevents fabricated patent descriptions in the background section.
        runs.append(_check_patent_verification(ws))

    elif phase == 4:
        # Optional domain-aware scoring profile for relevance gating.
        # Default behavior remains legacy unless manifest clearly indicates plan/constraint/conflict.
        profile = None
        if (ws / "artifacts" / "run_manifest.md").exists():
            try:
                txt = (ws / "artifacts" / "run_manifest.md").read_text(encoding="utf-8", errors="replace")
                if "项目计划" in txt and ("约束" in txt or "冲突" in txt or "修复" in txt):
                    profile = "ai_project_plan_constraints"
            except Exception:
                profile = None

        cmd = ["python", str(scripts / "validate_patent_candidates.py"), str(ap["candidate_pool"])]
        if profile:
            cmd += ["--profile", profile]
        runs.append(_run(cmd))
        runs.append(_run(["python", str(scripts / "validate_evidence_pack.py"), str(ap["evidence_pack"])]))

    elif phase == 5:
        runs.append(
            _run(
                [
                    "python",
                    str(scripts / "validate_facts_ledger.py"),
                    str(ap["facts_ledger"]),
                    "--base-dir",
                    str(ws),
                    "--require-docx-visible-mermaid",
                ]
            )
        )

    elif phase == 6:
        # 一致性审计门禁：检查报告是否存在且通过
        report_path = ap["consistency_report"]
        report_passed = False
        report_detail = "report missing"
        if report_path.exists():
            try:
                text = report_path.read_text(encoding="utf-8")
                report_passed = "pass_fail: pass" in text or "pass_fail_suggested: pass" in text
                report_detail = "report found"
            except Exception as e:
                report_detail = str(e)
        runs.append({
            "cmd": ["inline", "consistency_report_check"],
            "exitCode": 0 if report_passed else 2,
            "stdout": report_detail,
            "stderr": "",
            "startedAt": datetime.now(timezone.utc).isoformat(),
            "finishedAt": datetime.now(timezone.utc).isoformat(),
            "passed": report_passed,
        })

    elif phase == 7:
        # IPR 审查门禁：检查报告是否存在且通过
        report_path = ap["ipr_report"]
        report_passed = False
        report_detail = "report missing"
        if report_path.exists():
            try:
                text = report_path.read_text(encoding="utf-8")
                report_passed = "pass_fail: pass" in text or "pass_fail_suggested: pass" in text
                report_detail = "report found"
            except Exception as e:
                report_detail = str(e)
        runs.append({
            "cmd": ["inline", "ipr_report_check"],
            "exitCode": 0 if report_passed else 2,
            "stdout": report_detail,
            "stderr": "",
            "startedAt": datetime.now(timezone.utc).isoformat(),
            "finishedAt": datetime.now(timezone.utc).isoformat(),
            "passed": report_passed,
        })

    elif phase == 8:
        runs.append(_run(["python", str(scripts / "validate_edit_plan.py"), str(ap["edit_plan"])]))
        runs.append(
            _run(
                [
                    "python",
                    str(scripts / "validate_structured_diff.py"),
                    str(ap["structured_diff"]),
                    "--edit-plan",
                    str(ap["edit_plan"]),
                    "--post-fix-check",
                    str(ws / "artifacts" / "revision" / "phase_08_post_fix_check.json"),
                ]
            )
        )

    elif phase == 9:
        if not deliver_dir or not patent_title:
            # skip phase 9 when running "all" unless args provided
            return []
        runs.append(
            _run(
                [
                    "python",
                    str(scripts / "health_check_delivery_package.py"),
                    "--deliver-dir",
                    deliver_dir,
                    "--patent-title",
                    patent_title,
                    "--facts-ledger",
                    str(ap["facts_ledger"]),
                    "--consistency-report",
                    str(ap["consistency_report"]),
                    "--ipr-report",
                    str(ap["ipr_report"]),
                    "--out",
                    str(ap["health_report"]),
                    "--base-dir",
                    str(ws),
                ]
            )
        )

    return runs


# ── Phase 2 增强门禁：内联检查函数 ──────────────────

AGE_CUTOFF_MONTHS = 18


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _check_search_log(research_pack_path: Path) -> dict:
    """检查 search_log 是否完整记录了所有 smart-search 返回的后端。
    动态读取 `provider_stats[]`，不写死任何后端名称。"""
    started = _now_iso()
    try:
        if not research_pack_path.exists():
            return {"cmd": ["inline", "search_log_check"], "exitCode": 2, "stdout": "research_pack not found",
                    "stderr": "", "startedAt": started, "finishedAt": _now_iso(), "passed": False}
        data = json.loads(research_pack_path.read_text(encoding="utf-8"))
        search_log = data.get("search_log") or []
        if not isinstance(search_log, list) or len(search_log) < 1:
            return {"cmd": ["inline", "search_log_check"], "exitCode": 2,
                    "stdout": f"search_log missing or empty (found {len(search_log) if isinstance(search_log, list) else type(search_log).__name__})",
                    "stderr": "", "startedAt": started, "finishedAt": _now_iso(), "passed": False}

        errors = []
        warnings = []
        for i, entry in enumerate(search_log):
            # Support new format (provider_stats[]) and legacy (backends{})
            prov_stats = entry.get("provider_stats") or []
            if not prov_stats:
                # Fallback: read legacy backends{} format
                backends = entry.get("backends", {})
                if not backends:
                    errors.append(f"search_log[{i}]: missing provider_stats[] or backends{{}}")
                    continue
                for bk, bv in backends.items():
                    if not bv.get("ok"):
                        errors.append(f"search_log[{i}]: backend '{bk}' not ok")
            else:
                main_ok = any(s.get("status") == "ok" for s in prov_stats if s.get("capability") == "main_search")
                web_ok = any(s.get("status") == "ok" for s in prov_stats if s.get("capability") == "web_search")
                if not main_ok:
                    errors.append(f"search_log[{i}]: no ok main_search backend")
                if not web_ok:
                    errors.append(f"search_log[{i}]: no ok web_search backend")

                # Content quantity checks (warnings, not hard errors)
                for s in prov_stats:
                    cap = s.get("capability", "")
                    if cap == "main_search":
                        chars = s.get("content_chars", 0)
                        if chars > 0 and chars < 500:
                            warnings.append(f"search_log[{i}]: {s.get('model','?')} content_chars={chars} < 500 (回答过短)")
                    elif cap == "web_search":
                        sc = s.get("sources_count", 0)
                        if sc < 3:
                            warnings.append(f"search_log[{i}]: web_search sources_count={sc} < 3 (网页源偏少)")

            if "domain" not in entry:
                errors.append(f"search_log[{i}]: missing 'domain' field")
            if "total_sources" not in entry:
                errors.append(f"search_log[{i}]: missing 'total_sources' field")
            else:
                total = entry["total_sources"]
                if isinstance(total, (int, float)) and total < 10:
                    warnings.append(f"search_log[{i}]: total_sources={total} < 10 (源数量偏少)")

            patent_ids = entry.get("key_patent_ids_found") or []
            if len(patent_ids) < 2:
                warnings.append(f"search_log[{i}]: key_patent_ids_found={len(patent_ids)} < 2 (未搜到足够专利)")

        if errors:
            return {"cmd": ["inline", "search_log_check"], "exitCode": 2,
                    "stdout": f"search_log issues: {'; '.join(errors[:8])}",
                    "stderr": "", "startedAt": started, "finishedAt": _now_iso(), "passed": False}
        out = f"search_log OK: {len(search_log)} entries"
        if warnings:
            out += f"\n  search_log 内容数量警告 (Phase 3 确认):\n    " + "\n    ".join(warnings)
        return {"cmd": ["inline", "search_log_check"], "exitCode": 0,
                "stdout": out,
                "stderr": "", "startedAt": started, "finishedAt": _now_iso(), "passed": True}
    except Exception as e:
        return {"cmd": ["inline", "search_log_check"], "exitCode": 2, "stdout": str(e),
                "stderr": "", "startedAt": started, "finishedAt": _now_iso(), "passed": False}


def _check_raw_archive(ws: Path) -> dict:
    """检查 artifacts/research/raw/ 目录是否存在且非空。"""
    started = _now_iso()
    try:
        raw_dir = ws / "artifacts" / "research" / "raw"
        if not raw_dir.is_dir():
            return {"cmd": ["inline", "raw_archive_check"], "exitCode": 2,
                    "stdout": f"raw archive directory not found: {raw_dir}",
                    "stderr": "", "startedAt": started, "finishedAt": _now_iso(), "passed": False}
        json_files = list(raw_dir.glob("*.json"))
        if not json_files:
            return {"cmd": ["inline", "raw_archive_check"], "exitCode": 2,
                    "stdout": "raw archive is empty (no JSON files)",
                    "stderr": "", "startedAt": started, "finishedAt": _now_iso(), "passed": False}
        total_size = sum(f.stat().st_size for f in json_files)
        return {"cmd": ["inline", "raw_archive_check"], "exitCode": 0,
                "stdout": f"raw archive OK: {len(json_files)} files, {total_size} bytes",
                "stderr": "", "startedAt": started, "finishedAt": _now_iso(), "passed": True}
    except Exception as e:
        return {"cmd": ["inline", "raw_archive_check"], "exitCode": 2, "stdout": str(e),
                "stderr": "", "startedAt": started, "finishedAt": _now_iso(), "passed": False}


def _check_freshness(candidate_pool_path: Path) -> dict:
    """检查候选池中所有专利的 publication_date 是否在 AGE_CUTOFF_MONTHS 个月内。"""
    started = _now_iso()
    try:
        import re as _re
        if not candidate_pool_path.exists():
            return {"cmd": ["inline", "freshness_check"], "exitCode": 2,
                    "stdout": "candidate_pool not found",
                    "stderr": "", "startedAt": started, "finishedAt": _now_iso(), "passed": False}
        data = json.loads(candidate_pool_path.read_text(encoding="utf-8"))
        patents = data.get("patents") or []
        if not patents:
            return {"cmd": ["inline", "freshness_check"], "exitCode": 2,
                    "stdout": "candidate_pool has no patents",
                    "stderr": "", "startedAt": started, "finishedAt": _now_iso(), "passed": False}

        # Parse cutoff date from pool, or compute from now
        cutoff = None
        cutoff_str = data.get("age_cutoff_date")
        if cutoff_str:
            try:
                cutoff = datetime.fromisoformat(cutoff_str)
            except Exception:
                cutoff = None
        if cutoff is None:
            from datetime import timedelta
            cutoff = datetime.now() - timedelta(days=AGE_CUTOFF_MONTHS * 30)

        stale = []
        no_date = []
        for i, p in enumerate(patents):
            pid = p.get("patent_id", f"patent[{i}]")
            pub_date = p.get("publication_date", "")
            if not pub_date:
                no_date.append(pid)
                continue
            # Parse YYYY-MM or YYYY-MM-DD
            m = _re.match(r'(\d{4})-(\d{2})(?:-(\d{2}))?', str(pub_date))
            if not m:
                no_date.append(f"{pid} (unparseable: {pub_date})")
                continue
            y, mo, d = int(m.group(1)), int(m.group(2) or 1), int(m.group(3) or 1)
            try:
                pd = datetime(y, mo, d)
            except Exception:
                no_date.append(f"{pid} (invalid date: {pub_date})")
                continue
            if pd < cutoff:
                stale.append(f"{pid}: {pub_date} < cutoff ~{cutoff.strftime('%Y-%m')}")

        errors = []
        if no_date:
            errors.append(f"{len(no_date)} patents missing/unparseable date: {', '.join(no_date[:5])}")
        if stale:
            errors.append(f"{len(stale)} patents too old: {'; '.join(stale[:5])}")

        if errors:
            return {"cmd": ["inline", "freshness_check"], "exitCode": 2,
                    "stdout": f"freshness FAIL: {' | '.join(errors)}",
                    "stderr": "", "startedAt": started, "finishedAt": _now_iso(), "passed": False}
        return {"cmd": ["inline", "freshness_check"], "exitCode": 0,
                "stdout": f"freshness OK: {len(patents)} patents all within {AGE_CUTOFF_MONTHS} months",
                "stderr": "", "startedAt": started, "finishedAt": _now_iso(), "passed": True}
    except Exception as e:
        return {"cmd": ["inline", "freshness_check"], "exitCode": 2, "stdout": str(e),
                "stderr": "", "startedAt": started, "finishedAt": _now_iso(), "passed": False}


def _check_evidence_dates(research_pack_path: Path) -> dict:
    """检查 source_reading_notes[] 和 evidence[] 中每条数据的日期是否在 18 个月内。
    日期字段：source_date (ISO 8601 或 YYYY-MM)。缺日期标记为警告，过期标记为阻断。
    """
    started = _now_iso()
    try:
        if not research_pack_path.exists():
            return {"cmd": ["inline", "evidence_date_check"], "exitCode": 2,
                    "stdout": "research_pack not found",
                    "stderr": "", "startedAt": started, "finishedAt": _now_iso(), "passed": False}
        data = json.loads(research_pack_path.read_text(encoding="utf-8"))
        from datetime import timedelta
        cutoff = datetime.now() - timedelta(days=AGE_CUTOFF_MONTHS * 30)

        notes = data.get("source_reading_notes") or []
        evidence_list = data.get("evidence") or []
        all_items = list(notes) + list(evidence_list)

        if not all_items:
            return {"cmd": ["inline", "evidence_date_check"], "exitCode": 2,
                    "stdout": "no source_reading_notes or evidence entries found",
                    "stderr": "", "startedAt": started, "finishedAt": _now_iso(), "passed": False}

        import re as _re
        missing_date = []
        stale = []
        for i, item in enumerate(all_items):
            url = item.get("url", "") or item.get("title", "") or f"item[{i}]"
            sd = item.get("source_date", "")
            if not sd:
                missing_date.append(str(url)[:60])
                continue
            m = _re.match(r'(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?', str(sd))
            if not m:
                missing_date.append(f"{str(url)[:40]} (unparseable: {sd})")
                continue
            y, mo, d = int(m.group(1)), int(m.group(2) or 1), int(m.group(3) or 1)
            try:
                pd = datetime(y, mo, d)
            except Exception:
                missing_date.append(f"{str(url)[:40]} (invalid: {sd})")
                continue
            if pd < cutoff:
                stale.append(f"{str(url)[:50]}: {sd} < cutoff ~{cutoff.strftime('%Y-%m')}")

        errors = []
        if missing_date:
            errors.append(f"{len(missing_date)} entries missing/unparseable source_date")
        if stale:
            errors.append(f"{len(stale)} entries too old: {'; '.join(stale[:3])}")

        if errors:
            return {"cmd": ["inline", "evidence_date_check"], "exitCode": 2,
                    "stdout": f"evidence_date FAIL: {' | '.join(errors)}",
                    "stderr": "", "startedAt": started, "finishedAt": _now_iso(), "passed": False}
        return {"cmd": ["inline", "evidence_date_check"], "exitCode": 0,
                "stdout": f"evidence_date OK: {len(all_items)} entries all within {AGE_CUTOFF_MONTHS} months",
                "stderr": "", "startedAt": started, "finishedAt": _now_iso(), "passed": True}
    except Exception as e:
        return {"cmd": ["inline", "evidence_date_check"], "exitCode": 2, "stdout": str(e),
                "stderr": "", "startedAt": started, "finishedAt": _now_iso(), "passed": False}


def _check_patent_verification(ws: Path) -> dict:
    """检查候选池中的专利是否经过 Google Patents / CNIPA 实际查证。
    
    必须有 verification records，每条记录包含从官方来源查到的：
    - patent_id: 专利号
    - verified_title: 查到的实际标题
    - verified_abstract: 查到的实际摘要（至少 50 字符）
    - verification_source: Google Patents / CNIPA 等
    - verification_date: 查证时间
    - matched_in_direction: 被哪个候选方向引用
    
    这是防止 agent 编造专利描述的硬性检查。
    """
    started = _now_iso()
    try:
        ver_path = ws / "artifacts" / "prior_art" / "phase_02_patent_verification.json"
        candidate_path = ws / "artifacts" / "prior_art" / "phase_02_patent_candidate_pool.json"

        # Get the patents that need verification
        candidate_patents = []
        if candidate_path.exists():
            try:
                pool = json.loads(candidate_path.read_text(encoding="utf-8"))
                candidate_patents = pool.get("patents") or []
            except Exception:
                pass

        if not ver_path.exists():
            n_patents = len(candidate_patents)
            return {
                "cmd": ["inline", "patent_verification_check"], "exitCode": 2,
                "stdout": f"phase_02_patent_verification.json not found. "
                          f"{n_patents} candidate patents have NOT been verified against CNIPA/Google Patents. "
                          f"This means background patent descriptions may be fabricated.",
                "stderr": "", "startedAt": started, "finishedAt": _now_iso(), "passed": False}

        ver_data = json.loads(ver_path.read_text(encoding="utf-8"))
        records = ver_data.get("verification_records") or []

        errors = []
        warnings = []

        # Check structure
        if not isinstance(records, list):
            errors.append("verification_records is not a list")
        elif len(records) == 0:
            errors.append("verification_records is empty — no patents were verified")
        else:
            for i, rec in enumerate(records):
                pid = rec.get("patent_id", f"record[{i}]")
                required_fields = ["patent_id", "verified_title", "verified_abstract",
                                   "verification_source", "verification_date"]
                missing = [f for f in required_fields if not rec.get(f)]
                if missing:
                    errors.append(f"{pid}: missing fields {missing}")
                    continue
                # Content quality checks
                abstract = rec.get("verified_abstract", "")
                if len(str(abstract)) < 50:
                    warnings.append(f"{pid}: abstract too short ({len(str(abstract))} chars) — may not be from real lookup")
                title = rec.get("verified_title", "")
                if len(str(title)) < 10:
                    warnings.append(f"{pid}: title too short — suspicious")

            # Check that candidate pool patents are covered
            verified_ids = {r.get("patent_id", "") for r in records}
            candidate_ids = {p.get("patent_id", "") for p in candidate_patents if p.get("patent_id")}
            unverified = candidate_ids - verified_ids
            if unverified:
                warnings.append(f"{len(unverified)} candidate patents not in verification records: {', '.join(sorted(unverified)[:5])}")

        if errors:
            return {
                "cmd": ["inline", "patent_verification_check"], "exitCode": 2,
                "stdout": f"patent_verification FAIL: {'; '.join(errors[:5])}",
                "stderr": "", "startedAt": started, "finishedAt": _now_iso(), "passed": False}

        out = f"patent_verification OK: {len(records)} patents verified"
        if warnings:
            out += f"\n  patent_verification 警告 (Phase 3 确认):\n    " + "\n    ".join(warnings)
        return {
            "cmd": ["inline", "patent_verification_check"], "exitCode": 0,
            "stdout": out, "stderr": "",
            "startedAt": started, "finishedAt": _now_iso(), "passed": True}

    except Exception as e:
        return {"cmd": ["inline", "patent_verification_check"], "exitCode": 2,
                "stdout": str(e), "stderr": "", "startedAt": started, "finishedAt": _now_iso(), "passed": False}


def main() -> int:
    ap = argparse.ArgumentParser(description="Run patent-workflow phase gate validators")
    ap.add_argument("--phase", required=True, help="2|4|5|6|7|8|9|all")
    ap.add_argument("--workspace", default=".", help="Workspace root (base dir)")

    # phase 9 extras
    ap.add_argument("--deliver-dir", help="Delivery dir (phase 9)")
    ap.add_argument("--patent-title", help="Final patent title (phase 9)")

    ap.add_argument("--out", help="Optional output path for JSON summary")
    ap.add_argument("--manifest", help="Optional markdown run manifest path to patch JSON block")
    args = ap.parse_args()

    ws = Path(args.workspace)

    phases: list[int]
    if args.phase == "all":
        phases = [2, 4, 5, 6, 7, 8, 9]
    else:
        try:
            phases = [int(args.phase)]
        except ValueError:
            raise SystemExit("--phase must be one of: 2,4,5,6,7,8,9,all")

    all_runs: list[dict] = []
    phase_results: list[dict] = []

    for p in phases:
        # Cold-start hard gate: output_dir must be explicitly set by user in run manifest.
        # Apply this before phase 9 (delivery) and also when running all phases.
        if args.manifest and p == 9:
            check = _run(["python", str(_scripts_dir(ws) / "assert_output_dir_in_manifest.py"), args.manifest])
            phase_results.append({"phase": "manifest_output_dir_check", "skipped": False, "passed": check.get("passed"), "runs": [check]})
            all_runs.append(check)
            if not check.get("passed"):
                break

        runs = _run_phase(p, ws, args.deliver_dir, args.patent_title)
        # if skipped (phase 9 without args), record as skipped
        if p == 9 and not runs and args.phase == "all":
            phase_results.append({"phase": 9, "skipped": True, "reason": "missing --deliver-dir/--patent-title"})
            continue

        p_passed = all(r.get("passed") for r in runs) if runs else False
        
        # Phase 2: warnings-only, never hard-block. Let Phase 3 (user) decide.
        if p == 2 and not p_passed:
            for r in runs:
                if not r.get("passed"):
                    r["warning"] = True
            p_passed = True  # Always pass Phase 2 gate
        
        phase_results.append({"phase": p, "skipped": False, "passed": p_passed, "runs": runs})
        all_runs.extend(runs)

        # fail-fast
        if not p_passed:
            break

    passed = all(r.get("passed") for r in all_runs) if all_runs else False

    summary = {
        "runner": "run_phase_gates.py",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "workspace": str(ws.resolve()),
        "phase": args.phase,
        "passed": passed,
        "phaseResults": phase_results,
    }

    summary_json = json.dumps(summary, ensure_ascii=False, indent=2)

    if args.manifest:
        _patch_manifest(Path(args.manifest), summary_json)

    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(summary_json, encoding="utf-8")
    else:
        print(summary_json)

    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
