#!/usr/bin/env python3
"""
Phase 9 Executor — 最终导出与交付。
合并分块草稿、生成 docx、运行交付健康检查，产出：
- <专利标题>技术交底书.docx
- artifacts/delivery/phase_09_delivery_health_report.json
"""

import json
import subprocess
import shutil
import re
import zipfile
from pathlib import Path
from typing import Dict, Any, List

from executors.base_executor import BaseExecutor, ExecutorResult


class PhaseExecutor(BaseExecutor):
    """阶段 9 执行器：最终导出与交付。"""

    def _execute(self) -> ExecutorResult:
        print("   📦 执行最终导出与交付...")

        patent_title = self._resolve_patent_title()
        deliver_dir_explicit = bool(self.manifest.get("deliver_dir_explicit") or self.manifest.get("output_dir"))
        output_dir = self.manifest.get("output_dir")
        deliver_dir = Path(output_dir) if output_dir else (self.workspace / "交付")
        deliver_dir.mkdir(parents=True, exist_ok=True)

        health_report_path = self.workspace / "artifacts" / "delivery" / "phase_09_delivery_health_report.json"
        docx_name = f"{patent_title}技术交底书.docx"
        docx_path = deliver_dir / docx_name
        manifest_updates = {
            "delivery_health_report_path": str(health_report_path),
            "delivery_passed": False,
            "final_docx_path": str(docx_path),
            "deliver_dir": str(deliver_dir),
            "deliver_dir_explicit": deliver_dir_explicit,
        }

        # ── 合并分块文件为完整 Markdown ─────────
        merged_md = self._merge_draft_blocks()
        merged_path = self.workspace / "技术交底书_合并版.md"
        merged_path.write_text(merged_md, encoding="utf-8")

        # ── 正文质量硬门禁 ─────────────────────
        content_gate = self._check_content_quality_gate()
        manifest_updates["content_quality_passed"] = content_gate["passed"]
        manifest_updates["content_quality_issues"] = content_gate["issues"]
        if not content_gate["passed"]:
            self._log("content_quality_gate_failed", {"issues": content_gate["issues"]})
            self._write_delivery_skip_report(health_report_path, deliver_dir, docx_path, "正文质量门禁未通过")
            return ExecutorResult(
                status="failed",
                artifacts=[str(merged_path), str(health_report_path)],
                manifest_updates=manifest_updates,
                trace_log=self.trace,
                error="正文质量门禁未通过",
            )

        # ── 生成 docx ───────────────────────────
        docx_generated = self._generate_docx(merged_path, docx_path)
        manifest_updates["docx_generated"] = docx_generated
        delivery_md = docx_path.with_suffix(".md")
        shutil.copy2(merged_path, delivery_md)
        manifest_updates["delivery_markdown_path"] = str(delivery_md)
        if not docx_generated:
            print("   ⚠️ docx 生成失败，不将 Markdown 降级视为正式交付。")
            manifest_updates["fallback_markdown_path"] = str(delivery_md)

        # ── 交付前脏树检查 ────────────────────
        dirty_tree_info = self._check_dirty_tree()
        manifest_updates["delivery_from_dirty_tree"] = dirty_tree_info["is_dirty"]
        manifest_updates["dirty_tree_summary"] = dirty_tree_info["summary"]
        if dirty_tree_info["is_dirty"]:
            self._log("delivery_from_dirty_tree", {
                "dirty": True,
                "changed_files": dirty_tree_info["changed_files"],
                "untracked_files": dirty_tree_info["untracked_files"],
            })

        # ── 附图采用 mmd-only 交付：源码已内嵌在“附图说明”正文中 ──
        figures_dst = deliver_dir / "附图"
        if figures_dst.exists():
            shutil.rmtree(figures_dst)
            self._log("figures_dir_removed", {"path": str(figures_dst), "reason": "mmd embedded in 附图说明"})

        # ── 清理旧版/过程文件 ─────────────────
        self._cleanup_deliver_dir(deliver_dir, docx_name)

        # ── 交付结构检查 ──────────────────────
        structure_check = self._check_delivery_structure(deliver_dir, docx_path)
        manifest_updates["delivery_structure_passed"] = structure_check["passed"]
        manifest_updates["delivery_structure_issues"] = structure_check["issues"]
        if not structure_check["passed"]:
            self._log("delivery_structure_issues", {"issues": structure_check["issues"]})
            for issue in structure_check["issues"]:
                print(f"   ⚠️ 交付结构问题: {issue}")

        # ── 运行交付健康检查 ──────────────────
        health_passed = False
        if docx_generated and structure_check["passed"] and deliver_dir_explicit:
            health_passed = self._run_health_check(deliver_dir, patent_title, docx_path)
        elif not deliver_dir_explicit:
            self._write_delivery_skip_report(health_report_path, deliver_dir, docx_path, "最终交付目录未明确指定")
        elif not docx_generated:
            self._write_delivery_skip_report(health_report_path, deliver_dir, docx_path, "docx 生成失败")
        else:
            self._write_delivery_skip_report(health_report_path, deliver_dir, docx_path, "交付结构检查未通过")

        # ── 生成 ASCII-safe 交付压缩包，避免 ZIP 文件名乱码 ──
        delivery_zip_path = None
        if health_passed:
            self._copy_delivery_artifacts(deliver_dir)
            delivery_zip_path = self._create_ascii_safe_delivery_zip(deliver_dir, docx_path, patent_title)
            manifest_updates["delivery_zip_path"] = str(delivery_zip_path)
            manifest_updates["delivery_zip_ascii_safe"] = True

        # ── 更新 manifest ─────────────────────
        manifest_updates["delivery_passed"] = health_passed

        failure_reason = None
        if not deliver_dir_explicit:
            failure_reason = "最终交付目录未明确指定"
        elif not docx_generated:
            failure_reason = "docx 生成失败"
        elif not structure_check["passed"]:
            failure_reason = "交付结构检查未通过"
        elif not health_passed:
            failure_reason = "交付健康检查未完全通过"

        status = "success" if health_passed else "failed"

        artifacts = [str(merged_path), str(health_report_path)]
        if docx_path.exists():
            artifacts.insert(0, str(docx_path))
        if manifest_updates.get("fallback_markdown_path"):
            artifacts.append(manifest_updates["fallback_markdown_path"])
        if delivery_zip_path:
            artifacts.insert(0, str(delivery_zip_path))
        delivery_artifacts_dir = deliver_dir / "artifacts"
        if delivery_artifacts_dir.exists():
            artifacts.append(str(delivery_artifacts_dir))

        return ExecutorResult(
            status=status,
            artifacts=artifacts,
            manifest_updates=manifest_updates,
            trace_log=self.trace,
            error=failure_reason,
        )

    def _resolve_patent_title(self) -> str:
        """解析最终标题，避免 manifest 缺标题时生成“未命名专利”。"""
        for key in ["patent_title", "selected_title", "fixed_topic_or_title", "selected_direction"]:
            value = self.manifest.get(key)
            if isinstance(value, str) and value.strip() and value.strip() != "未命名专利":
                return value.strip()

        for relative_path in [
            "artifacts/draft/facts_ledger.json",
            "artifacts/draft/shared_context.json",
            "artifacts/research/phase_02_research_pack.json",
        ]:
            path = self.workspace / relative_path
            if not path.exists():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            title = self._title_from_data(data)
            if title:
                return title
        return "未命名专利"

    def _title_from_data(self, data: Any) -> str:
        if not isinstance(data, dict):
            return ""
        for key in ["patent_title", "project_name", "projectName", "selected_title"]:
            value = data.get(key)
            if isinstance(value, str) and value.strip() and value.strip() != "未命名专利":
                return value.strip()
        direction = data.get("recommended_direction_detail") or data.get("recommended_direction")
        if isinstance(direction, dict):
            value = direction.get("title")
            if isinstance(value, str) and value.strip():
                title = value.strip()
                return title if title.endswith("系统") else f"{title}及系统"
        return ""

    def _check_content_quality_gate(self) -> Dict[str, Any]:
        """最终交付前的正文污染硬门禁。"""
        domain_scope = self.manifest.get("domain_scope", "")
        if not domain_scope:
            self._log("missing_domain_scope", {"error": "manifest.domain_scope is empty, using empty string"})
        block_files = {
            "part_01_技术领域.md": "part_01",
            "part_02_背景技术.md": "part_02",
            "part_03_发明内容.md": "part_03",
            "part_04_附图说明.md": "part_04",
            "part_05_具体实施方式.md": "part_05",
        }
        issues: List[Dict[str, str]] = []
        for filename, block_id in block_files.items():
            path = self.workspace / filename
            if not path.exists():
                issues.append({"file": filename, "issue": "分块文件缺失"})
                continue
            content = path.read_text(encoding="utf-8")
            for reason in self._content_quality_issues(block_id, content, domain_scope):
                issues.append({"file": filename, "issue": reason})
        return {"passed": not issues, "issues": issues}

    def _content_quality_issues(self, block_id: str, content: str, domain_scope: str = "") -> List[str]:
        issues: List[str] = []
        if "<!--" in content or "需扩展内容" in content:
            issues.append("正文含修订占位注释")
        if block_id == "part_02" and re.search(r"\b(WO|US|EP)\d", content):
            issues.append("背景技术引用非 CN 专利")
        if block_id == "part_03" and "本发明要解决的技术问题在于，克服" in content:
            issues.append("技术问题句式有语病")
        internal_terms = [
            "Phase 2", "Phase 3", "Phase 5", "Phase 6", "Phase 7", "Phase 8", "Phase 9",
            "research_pack", "patent_candidate_pool", "evidence_pack", "block_context",
            "shared_context", "facts_ledger", "figure_registry", "terminology_registry",
            "block_review", "evidence_id", "写作依据", "正文分块", "IPR 模拟审查",
            "最终交付健康检查", "专利正文的一致性审计", "分块审核", "读取研究资料", "生成分块上下文", "分块撰写",
        ]
        if any(term in content for term in internal_terms):
            issues.append("正文混入工作流内部术语")
        if block_id == "part_04" and "```mermaid" not in content:
            issues.append("附图说明缺少 mmd/Mermaid 源码")
        if block_id == "part_04" and any(term in content for term in ["读取研究资料", "生成分块上下文", "分块撰写", "分块审核"]):
            issues.append(f"附图内容不是{domain_scope}技术方案")
        if block_id == "part_05":
            if not re.search(r"如图\s*[12一二]", content):
                issues.append("具体实施方式未引用具体图号")
            if self._contains_unverified_numeric_claim(content):
                issues.append("具体实施方式含未经实验支撑的数据")
            if "Σ" in content or re.search(r"(?<!\w)[a-z]\s*=\s*\d", content):
                issues.append("具体实施方式含公式兼容风险")
            if self._contains_synthetic_refnums(content):
                issues.append("具体实施方式含疑似编造的附图标记编号")
        return issues

    def _contains_synthetic_refnums(self, content: str) -> bool:
        """检测疑似编造的组件编号（如 座舱域控制器100），但不匹配时间/单位。"""
        pattern = r'(?<![a-zA-Z0-9])[\u4e00-\u9fff]{2,}(?:模块|控制器|单元|器|总线)\s*\d{2,4}(?!\s*(?:ms|秒|分钟|小时|km|米|fps|Hz))'
        return len(__import__('re').findall(pattern, content)) > 0

    def _contains_unverified_numeric_claim(self, content: str) -> bool:
        patterns = [
            r"前\d+次",
            r"运行\d+天",
            r"(?:性能提升|效率提高|准确率|识别率)\s*(?:达到|超过|高达)\s*\d+",
        ]
        return any(re.search(pattern, content, flags=re.IGNORECASE) for pattern in patterns)

    def _merge_draft_blocks(self) -> str:
        """合并所有分块草稿为完整 Markdown。"""
        block_files = [
            "part_01_技术领域.md",
            "part_02_背景技术.md",
            "part_03_发明内容.md",
            "part_04_附图说明.md",
            "part_05_具体实施方式.md",
        ]
        parts = []
        patent_title = self.manifest.get("patent_title", "")
        if patent_title:
            parts.append(f"# {patent_title}")
            parts.append("")
            parts.append(f"**发明名称：** {patent_title}")
            parts.append("")

        for bf in block_files:
            p = self.workspace / bf
            if p.exists():
                content = p.read_text(encoding="utf-8").strip()
                parts.append(content)
                parts.append("")
            else:
                parts.append(f"<!-- 缺失: {bf} -->\n")

        return "\n".join(parts)

    def _figure_markdown_refs(self) -> List[str]:
        """mmd-only 交付模式不追加独立图片引用。"""
        return []

    def _generate_docx(self, md_path: Path, docx_path: Path) -> bool:
        """尝试生成 docx（优先 pandoc，其次 docx-js）。"""
        self._ensure_pandoc_available()

        # 方案 1: pandoc
        if shutil.which("pandoc"):
            try:
                cmd = [
                    "pandoc",
                    str(md_path),
                    "-o", str(docx_path),
                    "--from", "markdown",
                    "--to", "docx",
                    "--reference-doc=" if False else "",  # 占位：如有模板可添加
                ]
                cmd = [c for c in cmd if c]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                if result.returncode == 0 and docx_path.exists():
                    self._log("docx_pandoc", {"path": str(docx_path)})
                    return True
            except Exception as e:
                self._log("docx_pandoc_fail", {"error": str(e)})

        # 方案 2: docx-js（Node.js 脚本）
        docx_script = None
        env_script = os.environ.get("PATENT_DOCX_SCRIPT", "")
        if env_script:
            docx_script = Path(env_script)
        if not docx_script or not docx_script.exists():
            docx_script = self.workspace / "skills" / "docx" / "scripts" / "create-patent-docx.js"
        if docx_script.exists() and shutil.which("node"):
            try:
                cmd = ["node", str(docx_script), str(docx_path), str(md_path)]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                if result.returncode == 0 and docx_path.exists():
                    self._log("docx_js", {"path": str(docx_path)})
                    return True
            except Exception as e:
                self._log("docx_js_fail", {"error": str(e)})

        # 方案 3: LibreOffice soffice
        if (shutil.which("soffice") or shutil.which("libreoffice")) and shutil.which("pandoc"):
            try:
                soffice = shutil.which("soffice") or shutil.which("libreoffice")
                # 先生成 html 再用 soffice 转
                html_path = md_path.with_suffix(".html")
                cmd1 = ["pandoc", str(md_path), "-o", str(html_path)]
                subprocess.run(cmd1, capture_output=True, timeout=30)
                if html_path.exists():
                    cmd2 = [soffice, "--headless", "--convert-to", "docx", "--outdir", str(docx_path.parent), str(html_path)]
                    result = subprocess.run(cmd2, capture_output=True, text=True, timeout=60)
                    if result.returncode == 0:
                        generated = html_path.with_suffix(".docx")
                        if generated.exists():
                            generated.rename(docx_path)
                            self._log("docx_soffice", {"path": str(docx_path)})
                            return True
            except Exception as e:
                self._log("docx_soffice_fail", {"error": str(e)})

        return False

    def _ensure_pandoc_available(self) -> bool:
        """确保 pandoc 可用；缺失时优先用 Homebrew 自动安装。"""
        if shutil.which("pandoc"):
            return True
        brew = shutil.which("brew")
        if not brew:
            self._log("pandoc_auto_install_unavailable", {"reason": "brew_missing"})
            return False

        self._log("pandoc_auto_install_start", {"installer": brew, "package": "pandoc"})
        try:
            result = subprocess.run(
                [brew, "install", "pandoc"],
                capture_output=True,
                text=True,
                timeout=900,
            )
            self._log(
                "pandoc_auto_install_result",
                {
                    "returncode": result.returncode,
                    "stdout_tail": result.stdout[-1000:],
                    "stderr_tail": result.stderr[-1000:],
                },
            )
        except Exception as e:
            self._log("pandoc_auto_install_failed", {"error": str(e)})
            return False

        return shutil.which("pandoc") is not None

    def _write_delivery_skip_report(self, out_path: Path, deliver_dir: Path, docx_path: Path, reason: str) -> None:
        """写入未运行健康检查时的失败报告。"""
        out_path.parent.mkdir(parents=True, exist_ok=True)
        report = {
            "doc_type": "delivery_health_report",
            "phase": "phase_9",
            "deliver_dir": str(deliver_dir.resolve()),
            "final_docx_path": str(docx_path.resolve()),
            "checks": [
                {
                    "name": "delivery precondition",
                    "result": "fail",
                    "details": reason,
                }
            ],
            "pass_fail": "fail",
            "missing_items": [reason],
        }
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    def _run_health_check(self, deliver_dir: Path, patent_title: str, docx_path: Path) -> bool:
        """运行交付健康检查。"""
        health_script = Path(__file__).parent.parent / "health_check_delivery_package.py"
        if not health_script.exists():
            self._log("health_script_missing", {"path": str(health_script)})
            return False

        consistency_report = self.workspace / "artifacts" / "audit" / "phase_06_consistency_audit_report.md"
        ipr_report = self.workspace / "artifacts" / "audit" / "phase_07_ipr_review_report.md"
        facts_ledger = self.workspace / "artifacts" / "draft" / "facts_ledger.json"
        out_path = self.workspace / "artifacts" / "delivery" / "phase_09_delivery_health_report.json"

        cmd = [
            "python3",
            str(health_script),
            "--deliver-dir", str(deliver_dir),
            "--patent-title", patent_title,
            "--facts-ledger", str(facts_ledger),
            "--consistency-report", str(consistency_report),
            "--ipr-report", str(ipr_report),
            "--out", str(out_path),
            "--base-dir", str(self.run_dir),
        ]

        try:
            result = self.run_command(cmd, timeout=120)
            # health_check_delivery_package.py 返回 JSON 到 stdout
            try:
                report = json.loads(result[1])
                return report.get("pass_fail") == "pass"
            except Exception:
                return result[0] == 0
        except Exception as e:
            self._log("health_check_fail", {"error": str(e)})
            return False

    def _copy_delivery_artifacts(self, deliver_dir: Path) -> Path:
        """复制交付所需过程件到最终交付目录 artifacts/。"""
        artifacts_dir = deliver_dir / "artifacts"
        if artifacts_dir.exists():
            shutil.rmtree(artifacts_dir)
        required_files = {
            "delivery/phase_09_delivery_health_report.json": "delivery/phase_09_delivery_health_report.json",
            "preprocess/phase_00_preprocess_notes.md": "preprocess/phase_00_preprocess_notes.md",
            "preprocess/source_fingerprints.json": "preprocess/source_fingerprints.json",
            "run_manifest.json": "preprocess/run_manifest.json",
            "../template_rules.json": "preprocess/template_rules.json",
            "../style_profile.json": "preprocess/style_profile.json",
            "../style_profile.md": "preprocess/style_profile.md",
            "audit/phase_06_consistency_audit_report.md": "audit/phase_06_consistency_audit_report.md",
            "audit/phase_07_ipr_review_report.md": "audit/phase_07_ipr_review_report.md",
            "revision/phase_08_edit_plan.json": "revision/phase_08_edit_plan.json",
            "revision/phase_08_structured_diff.json": "revision/phase_08_structured_diff.json",
            "revision/phase_08_post_fix_check.json": "revision/phase_08_post_fix_check.json",
            "revision/phase_08_post_fix_check_report.md": "revision/phase_08_post_fix_check_report.md",
            "draft/facts_ledger.json": "draft/facts_ledger.json",
            "draft/shared_context.json": "draft/shared_context.json",
            "draft/phase_05_writing_plan.json": "draft/phase_05_writing_plan.json",
            "draft/step_registry.json": "draft/step_registry.json",
            "draft/figure_registry.json": "draft/figure_registry.json",
            "draft/terminology_registry.json": "draft/terminology_registry.json",
            "research/phase_02_research_pack.json": "research/phase_02_research_pack.json",
            "prior_art/phase_02_evidence_pack.json": "prior_art/phase_02_evidence_pack.json",
            "prior_art/phase_02_patent_candidate_pool.json": "prior_art/phase_02_patent_candidate_pool.json",
            "prior_art/phase_02_patent_search_queries.txt": "prior_art/phase_02_patent_search_queries.txt",
        }
        copied = []
        missing = []
        for src_rel, dst_rel in required_files.items():
            src = self.workspace / "artifacts" / src_rel
            dst = artifacts_dir / dst_rel
            if not src.exists():
                missing.append(src_rel)
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied.append(dst_rel)

        for subdir in ["draft/block_contexts", "draft/block_reviews"]:
            src_dir = self.workspace / "artifacts" / subdir
            dst_dir = artifacts_dir / subdir
            if src_dir.exists():
                shutil.copytree(src_dir, dst_dir, dirs_exist_ok=True)
                copied.append(f"{subdir}/")

        index = {
            "doc_type": "delivery_artifacts_index",
            "description": "Phase 9 交付过程件索引；正式稿在交付目录根目录，过程件统一下沉到 artifacts/。",
            "copied_items": copied,
            "missing_items": missing,
        }
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        (artifacts_dir / "DELIVERY_ARTIFACTS_INDEX.json").write_text(
            json.dumps(index, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._log("delivery_artifacts_copied", {"dir": str(artifacts_dir), "copied": len(copied), "missing": missing})
        return artifacts_dir

    def _create_ascii_safe_delivery_zip(self, deliver_dir: Path, docx_path: Path, patent_title: str) -> Path:
        """创建内部文件名全 ASCII 的交付 zip，避免 Windows/预览工具显示中文乱码。"""
        zip_path = deliver_dir / "patent_delivery_package.zip"
        if zip_path.exists():
            zip_path.unlink()
        files: List[tuple[Path, str]] = []
        files.append((docx_path, "final/patent_disclosure.docx"))
        markdown_path = docx_path.with_suffix(".md")
        if markdown_path.exists():
            files.append((markdown_path, "final/patent_disclosure.md"))
        artifacts_dir = deliver_dir / "artifacts"
        if artifacts_dir.exists():
            for file_path in sorted(p for p in artifacts_dir.rglob("*") if p.is_file()):
                rel = file_path.relative_to(artifacts_dir).as_posix()
                safe_rel = "/".join(re.sub(r"[^0-9A-Za-z._-]+", "_", part).strip("_") or "item" for part in rel.split("/"))
                files.append((file_path, f"artifacts/{safe_rel}"))
        readme = (
            "# Patent Delivery Package\n\n"
            "This zip intentionally uses ASCII-only internal filenames to avoid garbled names in unzip tools.\n\n"
            f"Original patent title: {patent_title}\n"
            f"Original docx filename: {docx_path.name}\n\n"
            "Files:\n"
            "- final/patent_disclosure.docx: final Word document\n"
            "- final/patent_disclosure.md: markdown copy when available\n"
            "- figure Mermaid/mmd source: embedded in final document section '附图说明'\n"
        )
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("README.md", readme)
            for src, arcname in files:
                if src.exists():
                    archive.write(src, arcname=arcname)
        self._log("ascii_safe_delivery_zip_created", {"path": str(zip_path), "file_count": len(files) + 1})
        return zip_path

    def _cleanup_deliver_dir(self, deliver_dir: Path, keep_docx_name: str):
        """清理交付目录中的旧版/过程文件。"""
        archive_dir = self.workspace / "artifacts" / "delivery" / "archived_delivery_files"
        archive_dir.mkdir(parents=True, exist_ok=True)
        stale_keywords = ["旧版", "修订版", "trialbak", "评价", "评估", "draft"]
        stale_suffixes = {".bak", ".tmp", "~"}

        for f in deliver_dir.iterdir():
            if not f.is_file() or f.name == keep_docx_name:
                continue
            should_archive = (
                f.suffix == ".docx"
                or f.suffix in stale_suffixes
                or any(keyword.lower() in f.name.lower() for keyword in stale_keywords)
            )
            if should_archive:
                try:
                    dst = archive_dir / f.name
                    if dst.exists():
                        dst.unlink()
                    shutil.move(str(f), str(dst))
                    self._log("archive_delivery_file", {"src": str(f), "dst": str(dst)})
                except Exception as e:
                    self._log("archive_delivery_file_failed", {"file": str(f), "error": str(e)})

        # 将过程 Markdown 下沉到 artifacts/，正式降级 Markdown 除外
        for md in deliver_dir.glob("*.md"):
            if "合并版" in md.name or "draft" in md.name.lower():
                dst = archive_dir / md.name
                try:
                    shutil.move(str(md), str(dst))
                    self._log("archive_md", {"src": str(md), "dst": str(dst)})
                except Exception:
                    pass

    def _check_dirty_tree(self) -> Dict[str, Any]:
        """检查工作区是否存在未提交的修改。"""
        result = {
            "is_dirty": False,
            "changed_files": [],
            "untracked_files": [],
            "summary": "",
        }
        try:
            # 检查是否有未提交修改
            diff_cmd = ["git", "-C", str(self.workspace), "diff", "--name-only"]
            diff_result = subprocess.run(diff_cmd, capture_output=True, text=True, timeout=10)
            if diff_result.returncode == 0 and diff_result.stdout.strip():
                result["changed_files"] = diff_result.stdout.strip().split("\n")
                result["is_dirty"] = True

            # 检查未跟踪文件
            untracked_cmd = ["git", "-C", str(self.workspace), "ls-files", "--others", "--exclude-standard"]
            untracked_result = subprocess.run(untracked_cmd, capture_output=True, text=True, timeout=10)
            if untracked_result.returncode == 0 and untracked_result.stdout.strip():
                result["untracked_files"] = untracked_result.stdout.strip().split("\n")
                result["is_dirty"] = True

            if result["is_dirty"]:
                summary_parts = []
                if result["changed_files"]:
                    summary_parts.append(f"已修改文件: {len(result['changed_files'])} 个")
                if result["untracked_files"]:
                    summary_parts.append(f"未跟踪文件: {len(result['untracked_files'])} 个")
                result["summary"] = "; ".join(summary_parts)
        except Exception as e:
            self._log("dirty_tree_check_fail", {"error": str(e)})
            result["summary"] = f"检查失败: {e}"
        return result

    def _check_delivery_structure(self, deliver_dir: Path, docx_path: Path) -> Dict[str, Any]:
        """检查交付结构完整性。"""
        issues = []

        # 1. 检查 docx 是否存在
        if not docx_path.exists():
            issues.append(f"交付文件不存在: {docx_path.name}")

        # 2. 检查附图说明：正式交付不要求独立图片目录，Mermaid 源码应内嵌正文。
        merged_md = self.workspace / "技术交底书_合并版.md"
        if not merged_md.exists() or "```mermaid" not in merged_md.read_text(encoding="utf-8", errors="ignore"):
            issues.append("附图说明缺少内嵌 Mermaid/mmd 源码")

        # 3. 检查 facts_ledger
        facts_ledger = self.workspace / "artifacts" / "draft" / "facts_ledger.json"
        if not facts_ledger.exists():
            issues.append("缺少 facts_ledger.json")

        # 4. 检查一致性审计报告
        consistency_report = self.workspace / "artifacts" / "audit" / "phase_06_consistency_audit_report.md"
        if not consistency_report.exists():
            issues.append("缺少 phase_06 一致性审计报告")

        # 5. 检查 IPR 审查报告
        ipr_report = self.workspace / "artifacts" / "audit" / "phase_07_ipr_review_report.md"
        if not ipr_report.exists():
            issues.append("缺少 phase_07 IPR 审查报告")

        return {
            "passed": len(issues) == 0,
            "issues": issues,
        }
