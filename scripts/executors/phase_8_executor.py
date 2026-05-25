#!/usr/bin/env python3
"""
Phase 8 Executor — 审后修订与复审闭环。
读取一致性审计报告和 IPR 审查报告，生成修改计划并应用修改，随后触发复审门禁，产出：
- artifacts/revision/phase_08_edit_plan.json
- artifacts/revision/phase_08_structured_diff.json
- artifacts/revision/phase_08_post_fix_check_report.md
"""

import json
import re
import importlib
from pathlib import Path
from typing import Dict, Any, List

from executors.base_executor import BaseExecutor, ExecutorResult


class PhaseExecutor(BaseExecutor):
    """阶段 8 执行器：审后修订与复审闭环。"""

    def _execute(self) -> ExecutorResult:
        print("   🔧 执行审后修订与复审闭环...")

        # ── 读取前置报告 ──────────────────────
        audit_report_path = self._resolve_artifact_path("artifacts/audit/phase_06_consistency_audit_report.md")
        ipr_report_path = self._resolve_artifact_path("artifacts/audit/phase_07_ipr_review_report.md")
        draft_dir = self.run_dir

        audit_issues = self._parse_issues_from_report(audit_report_path)
        ipr_risks = self._parse_risks_from_report(ipr_report_path)

        all_problems = audit_issues + ipr_risks

        # ── 生成修改计划 ──────────────────────
        edit_plan = self._build_edit_plan(all_problems)
        plan_path = self.save_artifact(edit_plan, "artifacts/revision/phase_08_edit_plan.json")

        # ── 应用修改（脚本层能做的基础修改）───
        applied_edits, structured_diff = self._apply_edits(edit_plan, draft_dir)
        diff_path = self.save_artifact(structured_diff, "artifacts/revision/phase_08_structured_diff.json")

        # ── 联动回改检测 ────────────────────────
        linked_changes = self._detect_linked_changes(edit_plan, draft_dir)
        if linked_changes:
            structured_diff["linked_changes"] = linked_changes
            # 重写 diff 文件，包含联动信息
            diff_path = self.save_artifact(structured_diff, "artifacts/revision/phase_08_structured_diff.json")

        # ── 修复后检查与复审门禁 ──────────────
        review_results = self._rerun_review_gates()
        post_fix_report = self._build_post_fix_report(applied_edits, all_problems, review_results)
        report_path = self.save_artifact(post_fix_report["report_text"], "artifacts/revision/phase_08_post_fix_check_report.md")
        json_report_path = self.save_artifact(post_fix_report, "artifacts/revision/phase_08_post_fix_check.json")

        # ── 判定状态 ──────────────────────────
        edit_plan_valid = isinstance(edit_plan.get("edits", []), list)
        diff_valid = isinstance(structured_diff.get("diffs", []), list)
        post_fix_pass = post_fix_report.get("post_fix_passed", False)
        review_passed = review_results.get("passed", False)

        passed = edit_plan_valid and diff_valid and post_fix_pass and review_passed

        remaining_after_review = self._count_remaining_after_review(review_results)
        manifest_updates = {
            "edit_plan_validated": edit_plan_valid,
            "structured_diff_validated": diff_valid,
            "post_fix_check_passed": post_fix_pass,
            "review_loop_passed": review_passed,
            "review_loop_results": review_results,
            "edits_applied_count": len(applied_edits),
            "remaining_issues_count": remaining_after_review,
            "linked_changes_detected": len(linked_changes) if linked_changes else 0,
        }

        status = "success" if passed else "partial"
        degraded_reason = None if passed else "审后修订后复审未完全通过，需继续修订或人工介入"

        return ExecutorResult(
            status=status,
            artifacts=[str(plan_path), str(diff_path), str(report_path), str(json_report_path)],
            manifest_updates=manifest_updates,
            trace_log=self.trace,
            degraded_reason=degraded_reason,
        )

    def _make_review_executor(self, phase_id: str, workspace: Path, manifest: Dict[str, Any]):
        """创建复审执行器，便于测试替换，并确保复审重新生成报告。"""
        module = importlib.import_module(f"executors.{phase_id}_executor")
        return module.PhaseExecutor(phase_id, workspace, manifest)

    def _rerun_review_gates(self) -> Dict[str, Any]:
        """修订后直接复跑 phase_6/phase_7 执行器，重新生成审查报告。"""
        phase_results: List[Dict[str, Any]] = []
        for phase_id in ("phase_6", "phase_7"):
            self._log("rerun_review_executor", {"phase": phase_id})
            try:
                executor = self._make_review_executor(phase_id, self.workspace, self.manifest)
                result = executor.execute()
                passed = result.status == "success"
                phase_results.append(
                    {
                        "phase": phase_id,
                        "passed": passed,
                        "status": result.status,
                        "rerun_mode": "executor",
                        "artifacts": result.artifacts,
                        "manifest_updates": result.manifest_updates,
                        "error": result.error,
                        "degraded_reason": result.degraded_reason,
                    }
                )
                self.manifest.update(result.manifest_updates)
            except Exception as exc:
                phase_results.append(
                    {
                        "phase": phase_id,
                        "passed": False,
                        "status": "failed",
                        "rerun_mode": "executor",
                        "artifacts": [],
                        "manifest_updates": {},
                        "error": str(exc),
                        "degraded_reason": "复审执行器运行失败",
                    }
                )

        return {
            "passed": all(item["passed"] for item in phase_results),
            "phase_results": phase_results,
        }

    def _parse_issues_from_report(self, path: Path) -> List[Dict[str, Any]]:
        """从一致性审计报告中解析问题列表（简化版）。"""
        issues = []
        if not path.exists():
            return issues
        text = path.read_text(encoding="utf-8")
        # 简单匹配 Top 问题部分
        for m in re.finditer(r"\*\*(HIGH|MEDIUM|LOW)\*\* \| ([^\n]+)\n\s+- 症状: ([^\n]+)\n\s+- 建议: ([^\n]+)", text):
            issues.append(
                {
                    "severity": m.group(1).lower(),
                    "location": m.group(2).strip(),
                    "symptom": m.group(3).strip(),
                    "fix_suggestion": m.group(4).strip(),
                    "source": "consistency_audit",
                }
            )
        return issues

    def _parse_risks_from_report(self, path: Path) -> List[Dict[str, Any]]:
        """从 IPR 审查报告中解析风险列表（简化版）。"""
        risks = []
        if not path.exists():
            return risks
        text = path.read_text(encoding="utf-8")
        for m in re.finditer(r"\*\*(HIGH|MEDIUM|LOW)\*\* \| ([^\n]+)\n\s+- 原因: ([^\n]+)\n\s+- 建议: ([^\n]+)", text):
            risks.append(
                {
                    "severity": m.group(1).lower(),
                    "location": m.group(2).strip(),
                    "symptom": m.group(3).strip(),
                    "fix_suggestion": m.group(4).strip(),
                    "source": "ipr_review",
                }
            )
        return risks

    def _build_edit_plan(self, problems: List[Dict[str, Any]]) -> Dict[str, Any]:
        """生成 edit_plan.json。"""
        edits = []
        seen = set()
        for i, p in enumerate(problems):
            # 去重：同一位置同一症状只保留一个
            key = f"{p['location']}:{p['symptom']}"
            if key in seen:
                continue
            seen.add(key)

            edit_type = "rewrite"
            fix_mode = "agent_required"
            if "字数" in p["symptom"]:
                edit_type = "expand"
            elif "禁用" in p["symptom"] or "AI" in p["symptom"]:
                edit_type = "replace"
                fix_mode = "auto"
            elif "缺失" in p["symptom"]:
                edit_type = "add"
            if p.get("severity") == "high":
                fix_mode = "manual_review" if fix_mode != "auto" else fix_mode

            # 将 location 映射到 section
            section = "part_05_具体实施方式.md"
            for candidate in ["part_01", "part_02", "part_03", "part_04", "part_05"]:
                if candidate in p["location"]:
                    section = f"{candidate}_{self._block_name(candidate)}.md"
                    break

            edits.append(
                {
                    "edit_id": f"ED-{i + 1:03d}",
                    "type": edit_type,
                    "problem": p["symptom"],
                    "change_instruction": p["fix_suggestion"],
                    "target": {
                        "section": section,
                        "paragraph_hint": p["location"],
                    },
                    "risk_if_not_fixed": p["severity"],
                    "source": p.get("source", "unknown"),
                    "fix_mode": fix_mode,
                    "auto_fixable": fix_mode == "auto",
                    "requires_regeneration": fix_mode in {"agent_required", "manual_review"},
                    "linked_change_required": any(token in p["symptom"] for token in ["步骤", "图", "术语", "模块"]),
                }
            )

        return {
            "doc_type": "edit_plan",
            "phase": "phase_8",
            "generated_at": self._now_iso(),
            "edits": edits,
            "acceptance_checks": [
                "rerun_phase_06_consistency_audit",
                "rerun_phase_07_ipr_review",
            ],
        }

    def _apply_edits(self, edit_plan: Dict[str, Any], draft_dir: Path) -> tuple:
        """应用可自动执行的修改，返回 (applied_edits, structured_diff)。"""
        applied = []
        diffs = []

        for edit in edit_plan.get("edits", []):
            eid = edit["edit_id"]
            section = edit["target"]["section"]
            section_path = draft_dir / section

            if not section_path.exists():
                continue

            original = section_path.read_text(encoding="utf-8")
            modified = original

            # 自动替换：禁用用语
            if edit["type"] == "replace":
                replacements = {
                    "客户": "用户",
                    "贵方": "",
                }
                for old, new in replacements.items():
                    if old in modified:
                        modified = modified.replace(old, new)

            if edit["type"] == "expand":
                self._log(
                    "expand_edit_requires_agent",
                    {"edit_id": eid, "section": section, "reason": "禁止用占位注释冒充内容扩写"},
                )
                continue

            if modified != original:
                section_path.write_text(modified, encoding="utf-8")
                applied.append(eid)
                diffs.append(
                    {
                        "edit_id": eid,
                        "file": section,
                        "old_hash": str(hash(original))[:8],
                        "new_hash": str(hash(modified))[:8],
                        "change_type": edit["type"],
                    }
                )

        structured_diff = {
            "doc_type": "structured_diff",
            "phase": "phase_8",
            "generated_at": self._now_iso(),
            "diffs": diffs,
            "diff_items": [
                {
                    "change_kind": {"rewrite": "replace", "expand": "add", "edit": "replace", "refine": "replace"}.get(d.get("change_type", ""), "replace"),
                    "location": {"section": d.get("file", "").replace(".md", "")},
                    "linked_edit_id": d.get("edit_id", ""),
                    "before_excerpt": "[previous content]",
                    "after_excerpt": "[revised content]"
                }
                for d in diffs
            ],
            "applied_edit_ids": applied,
            "total_edits_planned": len(edit_plan.get("edits", [])),
        }
        return applied, structured_diff

    def _detect_linked_changes(self, edit_plan: Dict[str, Any], draft_dir: Path) -> List[Dict[str, Any]]:
        """检测修改计划中的联动关系，自动定位需要同步更新的位置。"""
        linked = []
        block_files = {
            "part_01": draft_dir / "part_01_技术领域.md",
            "part_02": draft_dir / "part_02_背景技术.md",
            "part_03": draft_dir / "part_03_发明内容.md",
            "part_04": draft_dir / "part_04_附图说明.md",
            "part_05": draft_dir / "part_05_具体实施方式.md",
        }
        blocks = {}
        for key, path in block_files.items():
            blocks[key] = path.read_text(encoding="utf-8") if path.exists() else ""

        for edit in edit_plan.get("edits", []):
            problem = edit.get("problem", "")
            instruction = edit.get("change_instruction", "")
            target_section = edit.get("target", {}).get("section", "")

            # 检测步骤号修改的联动
            step_refs = re.findall(r"S\d{3}", problem + " " + instruction)
            for sid in set(step_refs):
                # 检查其他部分是否也引用了该步骤号
                for part_key, content in blocks.items():
                    part_fname = f"{part_key}_{self._block_name(part_key)}.md"
                    if part_fname == target_section:
                        continue
                    if sid in content:
                        linked.append({
                            "trigger_edit_id": edit.get("edit_id", ""),
                            "trigger_problem": problem,
                            "linked_location": part_fname,
                            "linked_symptom": f"步骤编号 '{sid}' 在 {part_fname} 中也有引用",
                            "suggested_action": f"同步检查 {part_fname} 中 '{sid}' 的描述是否与修改后的内容一致",
                            "link_type": "step_numbering",
                        })

            # 检测图号修改的联动
            fig_refs = re.findall(r"图\s*(\d+)", problem + " " + instruction)
            for fid in set(fig_refs):
                for part_key, content in blocks.items():
                    part_fname = f"{part_key}_{self._block_name(part_key)}.md"
                    if part_fname == target_section:
                        continue
                    if f"图{fid}" in content or f"图 {fid}" in content:
                        linked.append({
                            "trigger_edit_id": edit.get("edit_id", ""),
                            "trigger_problem": problem,
                            "linked_location": part_fname,
                            "linked_symptom": f"图号 '图{fid}' 在 {part_fname} 中也有引用",
                            "suggested_action": f"同步检查 {part_fname} 中 '图{fid}' 的说明和引用是否与修改后一致",
                            "link_type": "figure_numbering",
                        })

            # 检测术语修改的联动
            term_markers = re.findall(r"术语\s*['\"](.+?)['\"]|模块\s*['\"](.+?)['\"]", problem + " " + instruction)
            for match in term_markers:
                term = match[0] or match[1]
                if not term:
                    continue
                for part_key, content in blocks.items():
                    part_fname = f"{part_key}_{self._block_name(part_key)}.md"
                    if part_fname == target_section:
                        continue
                    if term in content:
                        linked.append({
                            "trigger_edit_id": edit.get("edit_id", ""),
                            "trigger_problem": problem,
                            "linked_location": part_fname,
                            "linked_symptom": f"术语/模块 '{term}' 在 {part_fname} 中也有出现",
                            "suggested_action": f"同步检查 {part_fname} 中 '{term}' 的命名和定义是否与修改后一致",
                            "link_type": "terminology",
                        })

        # 去重
        seen = set()
        unique_linked = []
        for item in linked:
            key = f"{item['trigger_edit_id']}:{item['linked_location']}:{item['linked_symptom']}"
            if key not in seen:
                seen.add(key)
                unique_linked.append(item)

        return unique_linked

    def _count_remaining_after_review(self, review_results: Dict[str, Any]) -> int:
        """根据复审执行结果统计仍失败的门禁数量。"""
        return sum(1 for item in review_results.get("phase_results", []) if not item.get("passed"))

    def _build_post_fix_report(
        self,
        applied: List[str],
        problems: List[Dict],
        review_results: Dict[str, Any],
    ) -> Dict[str, Any]:
        """构建修复后检查报告。"""
        remaining = len(problems) - len(applied)
        review_remaining = self._count_remaining_after_review(review_results)
        content_fix_passed = review_remaining == 0 if review_results.get("phase_results") else (remaining <= max(1, len(problems) * 0.2) if problems else True)
        review_passed = review_results.get("passed", False)
        passed = content_fix_passed and review_passed

        lines = [
            "# 审后修订与复审闭环报告",
            "",
            f"- `phase`: phase_8",
            f"- `generated_at`: {self._now_iso()}",
            f"- `total_issues`: {len(problems)}",
            f"- `auto_applied`: {len(applied)}",
            f"- `remaining_planned_minus_applied`: {remaining}",
            f"- `remaining_after_review`: {review_remaining}",
            f"- `content_fix_passed`: {content_fix_passed}",
            f"- `review_loop_passed`: {review_passed}",
            f"- `post_fix_passed`: {passed}",
            "",
            "## 已自动应用的修改",
            "",
        ]
        if applied:
            for eid in applied:
                lines.append(f"- {eid}")
        else:
            lines.append("- 无脚本级自动修改。")

        lines.extend(
            [
                "",
                "## 仍需人工/Agent 介入的修改",
                "",
            ]
        )
        if remaining:
            lines.append("以下问题需要 LLM 级别的内容生成，脚本层无法自动完成：")
            lines.append("")
            for problem in problems:
                if problem.get("edit_id", "") not in applied:
                    lines.append(f"- [{problem['severity'].upper()}] {problem['location']}: {problem['symptom']}")
        else:
            lines.append("- 未发现剩余问题。")

        lines.extend(
            [
                "",
                "## 复审门禁",
                "",
            ]
        )
        for item in review_results.get("phase_results", []):
            status_detail = item.get("status", f"exit={item.get('exit_code', '?')}")
            lines.append(f"- `{item['phase']}`: {'pass' if item['passed'] else 'fail'} ({status_detail}, mode={item.get('rerun_mode', 'unknown')})")

        lines.extend(
            [
                "",
                "## 结论",
                "",
                f"- `pass_fail`: {'pass' if passed else 'fail'}",
                f"- pass_fail: {'pass' if passed else 'fail'}",
                "- `pass_threshold_suggested`: 内容修订达标且 phase_6/phase_7 复审门禁通过",
                f"- `pass_fail_suggested`: {'pass' if passed else 'fail'}",
                f"- pass_fail_suggested: {'pass' if passed else 'fail'}",
            ]
        )

        return {
            "post_fix_passed": passed,
            "content_fix_passed": content_fix_passed,
            "review_loop_passed": review_passed,
            "review_loop_results": review_results,
            "report_text": "\n".join(lines),
            "total_issues": len(problems),
            "auto_applied": len(applied),
            "remaining_planned_minus_applied": remaining,
            "remaining_after_review": review_remaining,
        }

    def _block_name(self, block_id: str) -> str:
        mapping = {
            "part_01": "技术领域",
            "part_02": "背景技术",
            "part_03": "发明内容",
            "part_04": "附图说明",
            "part_05": "具体实施方式",
        }
        return mapping.get(block_id, "未知")

    def _now_iso(self) -> str:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()
