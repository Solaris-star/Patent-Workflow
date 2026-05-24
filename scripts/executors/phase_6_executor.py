#!/usr/bin/env python3
"""
Phase 6 Executor — 一致性审计。
读取 draft 分块文件与 facts_ledger.json，执行内部一致性检查，产出：
- artifacts/audit/phase_06_consistency_audit_report.md
"""

import json
import re
from pathlib import Path
from typing import Dict, Any, List, Optional

from executors.base_executor import BaseExecutor, ExecutorResult


class PhaseExecutor(BaseExecutor):
    """阶段 6 执行器：一致性审计。"""

    def _execute(self) -> ExecutorResult:
        print("   🔍 执行一致性审计...")

        # ── 读取输入 ──────────────────────────
        draft_dir = self.run_dir
        domain_scope = self.manifest.get("domain_scope", "")
        if not domain_scope:
            self._log("missing_domain_scope", {"error": "manifest.domain_scope is empty, using empty string"})
        ledger_path = draft_dir / "artifacts" / "draft" / "facts_ledger.json"
        ledger = {}
        if ledger_path.exists():
            try:
                ledger = self.load_artifact("artifacts/draft/facts_ledger.json")
            except Exception as e:
                self._log("ledger_load_error", {"error": str(e)})

        # 从独立 registry 文件读取（优先）
        step_registry = ledger.get("step_registry", [])
        if not step_registry:
            step_reg_path = draft_dir / "artifacts" / "draft" / "step_registry.json"
            if step_reg_path.exists():
                try:
                    with open(step_reg_path, "r", encoding="utf-8") as f:
                        step_registry = json.load(f)
                except Exception as e:
                    self._log("step_registry_load_error", {"error": str(e)})

        # 读取所有分块文件
        block_files = [
            "part_01_技术领域.md",
            "part_02_背景技术.md",
            "part_03_发明内容.md",
            "part_04_附图说明.md",
            "part_05_具体实施方式.md",
        ]
        blocks: Dict[str, str] = {}
        for bf in block_files:
            p = draft_dir / bf
            if p.exists():
                blocks[bf] = p.read_text(encoding="utf-8")
            else:
                blocks[bf] = ""

        # ── 执行审计项 ──────────────────────
        issues: List[Dict[str, Any]] = []
        scores = {}

        # 1. 术语一致性
        terminology = ledger.get("terminology", [])
        term_issues = self._check_terminology(blocks, terminology)
        issues.extend(term_issues)
        scores["terminology"] = 10 if not term_issues else max(0, 10 - len(term_issues) * 2)

        # 2. 图号/图名/正文引用一致性
        figure_issues = self._check_figures(blocks, ledger.get("figure_registry", []))
        issues.extend(figure_issues)
        scores["figure_text"] = 10 if not figure_issues else max(0, 10 - len(figure_issues) * 2)

        # 3. 交叉引用一致性
        xref_issues = self._check_cross_references(blocks)
        issues.extend(xref_issues)
        scores["cross_reference"] = 10 if not xref_issues else max(0, 10 - len(xref_issues) * 2)

        # 4. 章节标题与目录一致性
        heading_issues = self._check_headings(blocks)
        issues.extend(heading_issues)
        scores["section_heading"] = 10 if not heading_issues else max(0, 10 - len(heading_issues) * 2)

        # 5. 模块/部件命名一致性
        module_issues = self._check_module_naming(blocks)
        issues.extend(module_issues)
        scores["module_naming"] = 10 if not module_issues else max(0, 10 - len(module_issues) * 2)

        # 6. 字数检查
        word_count_issues = self._check_word_counts(blocks, ledger)
        issues.extend(word_count_issues)
        scores["deliverable_structure"] = 10 if not word_count_issues else max(0, 10 - len(word_count_issues) * 2)

        # 7. 风格/AI 腔检测
        style_issues = self._check_style(blocks)
        issues.extend(style_issues)
        scores["style_tone"] = 10 if not style_issues else max(0, 10 - len(style_issues) * 2)

        # 8. 证据引用一致性
        evidence_pack = self._load_evidence_pack(ledger)
        evidence_issues = self._check_evidence_citations(blocks, evidence_pack)
        issues.extend(evidence_issues)
        scores["evidence_citation"] = 10 if not evidence_issues else max(0, 10 - len(evidence_issues) * 2)

        # 9. 附图工件完整性
        artifact_issues = self._check_figure_artifacts(ledger)
        issues.extend(artifact_issues)
        scores["figure_artifact"] = 10 if not artifact_issues else max(0, 10 - len(artifact_issues) * 2)

        # 10. 公式/参数一致性
        formula_issues = self._check_formula_parameter_consistency(blocks)
        issues.extend(formula_issues)
        scores["formula_symbol"] = 10 if not formula_issues else 0

        # 11. 技术方案闭环完整性
        closure_issues = self._check_technical_closure(blocks)
        issues.extend(closure_issues)
        scores["technical_closure"] = 10 if not closure_issues else 0

        # 12. CNIPA 摘要理解一致性
        abstract_issues = self._check_cnipa_abstract_alignment(blocks, evidence_pack)
        issues.extend(abstract_issues)
        scores["cnipa_abstract_alignment"] = 10 if not abstract_issues else 0

        # 12.5. 背景专利描述准确性 — 交叉验证 part_02 中的专利描述与 verification records 中的
        #       实际标题/摘要是否一致。防止 agent 编造专利内容来贴合自己的方向。
        accuracy_issues = self._check_patent_description_accuracy(blocks)
        issues.extend(accuracy_issues)
        scores["patent_description_accuracy"] = 10 if not accuracy_issues else 0

        # 13. 迭代修订留档合规性
        revision_log_issues = self._check_revision_log_compliance(draft_dir)
        issues.extend(revision_log_issues)
        scores["revision_log"] = 10 if not revision_log_issues else 0

        # 14. 本地项目脱敏残留检查（仅当 Phase 5 生成 redaction_policy 时启用）
        redaction_policy = self._load_redaction_policy(draft_dir)
        redaction_issues = self._check_redaction_residue(blocks, redaction_policy)
        issues.extend(redaction_issues)
        scores["redaction"] = 10 if not redaction_issues else 0

        # 12. 步骤编号一致性（使用从文件或 ledger 读取的 step_registry）
        step_issues = self._check_step_numbering(blocks, step_registry)
        issues.extend(step_issues)
        scores["step_numbering"] = 10 if not step_issues else max(0, 10 - len(step_issues) * 3)

        # 12. 风格遵从度
        style_compliance_issues = self._check_style_compliance(blocks)
        issues.extend(style_compliance_issues)
        scores["style_compliance"] = 10 if not style_compliance_issues else max(0, 10 - len(style_compliance_issues) * 2)

        # 13. 章节结构
        structure_issues = self._check_section_structure(blocks)
        issues.extend(structure_issues)
        scores["section_structure"] = 10 if not structure_issues else max(0, 10 - len(structure_issues) * 3)

        # 14. 领域语义与模板硬门禁
        semantic_issues = self._check_domain_semantics(blocks, domain_scope)
        issues.extend(semantic_issues)
        scores["domain_semantics"] = 10 if not semantic_issues else 0

        # 15. 背景技术实质性与附图充分性硬门禁
        substance_issues = self._check_background_and_figure_substance(blocks)
        issues.extend(substance_issues)
        scores["background_figure_substance"] = 10 if not substance_issues else 0

        # 归一化总分到 0-100（保持阈值 80 不变）
        raw_score = sum(scores.values())
        overall_score = int(raw_score / len(scores) * 10) if scores else 0
        hard_fail = any(
            issue.get("severity") == "high"
            for issue in [
                *semantic_issues,
                *substance_issues,
                *redaction_issues,
                *formula_issues,
                *closure_issues,
                *abstract_issues,
                *revision_log_issues,
            ]
        )
        passed = overall_score >= 80 and not hard_fail

        # ── 产出审计报告 ──────────────────────
        report = self._build_report(overall_score, scores, issues, passed)
        report_path = self.save_artifact(report, "artifacts/audit/phase_06_consistency_audit_report.md")

        # ── 更新 manifest ─────────────────────
        manifest_updates = {
            "consistency_audit_score": overall_score,
            "consistency_audit_passed": passed,
            "top_issues": [
                {"issue": i["symptom"], "severity": i["severity"], "location": i["location"]}
                for i in issues[:5]
            ],
        }

        status = "success" if passed else "partial"
        degraded_reason = None if passed else f"一致性审计得分 {overall_score}/100，低于阈值 80"

        return ExecutorResult(
            status=status,
            artifacts=[str(report_path)],
            manifest_updates=manifest_updates,
            trace_log=self.trace,
            degraded_reason=degraded_reason,
        )

    # ── 审计子方法 ──────────────────────────
    def _check_technical_closure(self, blocks: Dict[str, str]) -> List[Dict]:
        text = "\n".join(blocks.values())
        part05 = blocks.get("part_05_具体实施方式.md", "")
        required_groups = {
            "输入/采集": ["采集", "获取", "输入", "接收"],
            "处理/判断": ["处理", "判断", "识别", "检测", "融合", "计算", "生成"],
            "输出/记录": ["输出", "记录", "保存", "追溯", "反馈", "告警", "恢复"],
        }
        missing = [name for name, tokens in required_groups.items() if not any(token in text for token in tokens)]
        if missing:
            return [{
                "severity": "high",
                "location": "具体实施方式/发明内容",
                "symptom": f"技术方案闭环不完整，缺少：{'、'.join(missing)}",
                "fix_suggestion": "补齐从输入/采集、处理/判断到输出/记录/反馈的完整步骤链路。",
            }]
        if not any(token in part05 for token in ["异常", "边界", "低置信", "冲突", "复核", "失败", "告警"]):
            return [{
                "severity": "high",
                "location": "part_05_具体实施方式.md",
                "symptom": "技术方案闭环不完整，未说明异常、边界样本或低置信度分支处理路径",
                "fix_suggestion": "补充异常分支、低置信度样本、冲突或失败情况下的处理路径。",
            }]
        return []

    def _check_formula_parameter_consistency(self, blocks: Dict[str, str]) -> List[Dict]:
        text_by_file = {name: content for name, content in blocks.items() if content}
        range_pattern = re.compile(r"(?:阈值|范围|系数)[^。；;\n]{0,20}?(\d+(?:\.\d+)?\s*[-~～至]\s*\d+(?:\.\d+)?)")
        ranges: Dict[str, List[str]] = {}
        for filename, content in text_by_file.items():
            for value in range_pattern.findall(content):
                normalized = re.sub(r"\s+", "", value).replace("～", "-").replace("~", "-").replace("至", "-")
                ranges.setdefault(normalized, []).append(filename)
        if len(ranges) > 1:
            return [{
                "severity": "high",
                "location": "全局",
                "symptom": f"公式或参数表述不一致：出现多个阈值/范围 {', '.join(ranges.keys())}",
                "fix_suggestion": "统一阈值范围，并确保实施例数值与关键技术参数一致。",
            }]
        if "置信度权重α" in text_by_file.get("part_03_发明内容.md", "") and "置信度权重β" in text_by_file.get("part_05_具体实施方式.md", ""):
            return [{
                "severity": "high",
                "location": "发明内容/具体实施方式",
                "symptom": "公式或参数表述不一致：同一置信度权重参数命名不统一",
                "fix_suggestion": "统一参数符号与参数名称，避免同义不同名。",
            }]
        return []

    def _check_cnipa_abstract_alignment(self, blocks: Dict[str, str], evidence_pack: Dict[str, Any]) -> List[Dict]:
        part02 = blocks.get("part_02_背景技术.md", "")
        issues: List[Dict] = []
        for item in evidence_pack.get("evidence", []):
            if not isinstance(item, dict):
                continue
            abstract = str(item.get("abstract") or item.get("摘要") or "")
            if not abstract:
                continue
            patent_no = self._evidence_patent_number(item)
            # Skip evidence items without a CN patent number, or whose patent number
            # is not cited in the background section
            if not patent_no or patent_no not in part02:
                continue
            abstract_terms = self._cnipa_alignment_terms(abstract)
            if not abstract_terms:
                continue
            window = part02
            if patent_no and patent_no in part02:
                start = max(0, part02.find(patent_no) - 80)
                window = part02[start:start + 360]
            matched = [term for term in abstract_terms if term in window]
            if len(matched) < max(1, min(2, len(abstract_terms))):
                issues.append({
                    "severity": "high",
                    "location": "part_02_背景技术.md",
                    "symptom": f"CNIPA 摘要理解不一致：{patent_no or '相关专利'} 的背景概括未体现摘要关键词 {', '.join(abstract_terms[:4])}",
                    "fix_suggestion": "按 CNIPA 摘要重写该专利公开内容和局限，避免只依据标题或跑偏概括。",
                })
        return issues

    def _evidence_patent_number(self, item: Dict[str, Any]) -> str:
        text = " ".join(str(item.get(key, "")) for key in ["publicationNumber", "applicationNumber", "url", "excerpt", "title"])
        match = re.search(r"CN\d{6,}[A-Z]?", text)
        return match.group(0) if match else ""

    def _cnipa_alignment_terms(self, abstract: str) -> List[str]:
        candidates = [
            # 通用技术术语
            "数据", "图像", "采集", "识别", "检测", "融合", "分类", "传输", "调度",
            "控制", "预警", "告警", "共享", "通信", "协同", "同步", "处理", "生成",
            "模型", "算法", "规则", "策略", "异常", "恢复", "评估", "反馈",
        ]
        return [term for term in candidates if term in abstract][:6]

    def _check_patent_description_accuracy(self, blocks: Dict[str, str]) -> List[Dict]:
        """交叉验证背景技术中引用的专利描述与 verification records 中的实际标题/摘要。
        
        读取 phase_02_patent_verification.json，对于 part_02 中引用的每个 CN 专利号：
        1. 提取 part_02 中对该专利的描述段落
        2. 与 verification record 中的 verified_title + verified_abstract 做关键词重叠检查
        3. 重叠度低于阈值 → 报告 HIGH severity 问题（可能编造了专利内容）
        """
        issues = []
        ver_path = self.workspace / "artifacts" / "prior_art" / "phase_02_patent_verification.json"
        if not ver_path.exists():
            # verification records don't exist → this is itself a critical issue
            # But we still try to detect if part_02 cites patents at all
            cn_patents_in_draft = re.findall(r"CN\d{6,}[A-Z]?", blocks.get("part_02", ""))
            if cn_patents_in_draft:
                issues.append({
                    "severity": "high",
                    "location": "part_02_背景技术.md",
                    "symptom": f"背景技术引用了 {len(cn_patents_in_draft)} 个CN专利但未找到 verification records（phase_02_patent_verification.json），"
                                "无法确认这些专利描述是否基于实际查新结果。",
                    "fix_suggestion": "必须回到 Phase 2 Step 5，对每个引用专利在 Google Patents / CNIPA 上查证，"
                                    "记录实际标题和摘要到 phase_02_patent_verification.json。",
                })
            return issues

        try:
            ver_data = json.loads(ver_path.read_text(encoding="utf-8"))
        except Exception as e:
            issues.append({"severity": "high", "location": "part_02_背景技术.md",
                          "symptom": f"无法解析 verification records: {e}", "fix_suggestion": "修复或重建 phase_02_patent_verification.json。"})
            return issues

        records = ver_data.get("verification_records") or []
        if not records:
            return issues  # gate already caught this; don't double-report

        part02_text = blocks.get("part_02", "")
        # Find all CN patent numbers cited in part_02
        cited_patents = set(re.findall(r"CN\d{6,}[A-Z]?", part02_text))
        if not cited_patents:
            return issues  # no patents cited, nothing to check

        # Build lookup from verification records
        verified = {}
        for rec in records:
            pid = rec.get("patent_id", "")
            if pid:
                verified[pid] = rec

        for patent_no in cited_patents:
            if patent_no not in verified:
                issues.append({
                    "severity": "high",
                    "location": "part_02_背景技术.md",
                    "symptom": f"背景技术引用了 {patent_no}，但 verification records 中无此专利的查证记录。"
                                f"可能使用了未经验证的专利号。",
                    "fix_suggestion": f"在 Google Patents 上查证 {patent_no} 的实际内容，"
                                    f"确认其标题和技术领域与背景描述一致后补充 verification record。",
                })
                continue

            rec = verified[patent_no]
            verified_title = rec.get("verified_title", "")
            verified_abstract = rec.get("verified_abstract", "")

            # Extract the sentence(s) in part_02 describing this patent
            # Look for text around the patent number, up to the next period or patent number
            desc_pattern = re.compile(
                rf"如?中国专利{re.escape(patent_no)}[^。；;]*[。；;]",
                re.DOTALL
            )
            desc_match = desc_pattern.search(part02_text)
            if not desc_match:
                # Try broader pattern
                desc_pattern2 = re.compile(
                    rf"{re.escape(patent_no)}[^。；;]*[。；;]",
                    re.DOTALL
                )
                desc_match = desc_pattern2.search(part02_text)
            described_text = desc_match.group(0) if desc_match else ""

            if not described_text:
                continue  # can't find description → skip this check

            # Keyword overlap analysis
            # Extract meaningful Chinese words from both texts
            def extract_keywords(text: str) -> set:
                # Extract 2+ char Chinese words and alphanumeric terms
                words = set()
                # Chinese bigrams
                cleaned = re.sub(r"[，。；：、！？\n\r（）\(\)\[\]【】\"\"''\s]", " ", text)
                for token in cleaned.split():
                    if len(token) >= 2 and not token.startswith("http"):
                        words.add(token)
                # Also add significant single terms
                for m in re.finditer(r"[\u4e00-\u9fff]{2,}", text):
                    words.add(m.group(0))
                return words

            verified_kws = extract_keywords(verified_title + " " + verified_abstract)
            described_kws = extract_keywords(described_text)

            if not verified_kws or not described_kws:
                continue

            overlap = verified_kws & described_kws
            overlap_ratio = len(overlap) / len(verified_kws) if verified_kws else 0

            # Threshold: at least 15% keyword overlap expected between the real patent
            # content and what the draft describes. Below this = likely fabricated.
            if overlap_ratio < 0.15 and len(verified_kws) >= 5:
                issues.append({
                    "severity": "high",
                    "location": "part_02_背景技术.md",
                    "symptom": f"{patent_no} 的背景描述与 verification record 中的实际标题/摘要"
                                f"关键词重叠率仅 {overlap_ratio:.0%}（阈值 15%）。"
                                f"\n  实际标题: {verified_title[:80]}"
                                f"\n  实际摘要关键词: {', '.join(sorted(verified_kws)[:8])}"
                                f"\n  正文描述关键词: {', '.join(sorted(described_kws)[:8])}"
                                f"\n  重合词: {', '.join(sorted(overlap)[:8]) if overlap else '(无)'}",
                    "fix_suggestion": f"{patent_no} 的实际内容为「{verified_title[:60]}」，"
                                    f"与背景技术中的描述不匹配。必须根据 verification record 中的实际摘要重写该专利的背景描述，"
                                    f"或者用与此方向更相关的专利替换它。",
                })

        return issues

    def _check_revision_log_compliance(self, draft_dir: Path) -> List[Dict]:
        if not self.manifest.get("revision_mode") and not self.manifest.get("phase_08_revision_applied"):
            return []
        candidates = [
            draft_dir / "交底书修订对话记录.md",
            draft_dir / "outputs" / "交底书修订对话记录.md",
            draft_dir / "artifacts" / "revision" / "交底书修订对话记录.md",
            draft_dir / "artifacts" / "revision" / "disclosure_revision_log.md",
        ]
        if any(path.exists() for path in candidates):
            return []
        return [{
            "severity": "high",
            "location": "交付目录/修订目录",
            "symptom": "缺少修订对话记录",
            "fix_suggestion": "迭代修订后追加交底书修订对话记录.md，包含时间、用户说明摘要、本轮交付文件和修订摘要。",
        }]

    def _load_redaction_policy(self, draft_dir: Path) -> Dict[str, Any]:
        policy_path = draft_dir / "artifacts" / "draft" / "redaction_policy.json"
        if not policy_path.exists():
            return {"enabled": False}
        try:
            with open(policy_path, "r", encoding="utf-8") as file:
                policy = json.load(file)
            return policy if isinstance(policy, dict) else {"enabled": False}
        except Exception as error:
            self._log("redaction_policy_load_error", {"error": str(error)})
            return {"enabled": False}

    def _check_redaction_residue(self, blocks: Dict[str, str], policy: Dict[str, Any]) -> List[Dict]:
        if not policy.get("enabled"):
            return []
        issues: List[Dict] = []
        sensitive_terms = [str(term) for term in policy.get("sensitive_terms", []) if str(term).strip()]
        patterns = [
            (r"(?:/[A-Za-z0-9._-]+){2,}", "内部路径"),
            (r"[A-Za-z]:\\(?:[^\\\s]+\\)+[^\\\s]+", "内部路径"),
            (r"每日\s*\d+(?:\.\d+)?\s*(?:件|条|次|单|人|辆|GB|MB)", "具体业务规模"),
            (r"类别\s*[0-9一二三四五六七八九十]+", "真实分类标签"),
        ]
        for filename, content in blocks.items():
            for term in sensitive_terms:
                if term and term in content:
                    issues.append({
                        "severity": "high",
                        "location": filename,
                        "symptom": f"本地项目敏感信息残留：{term}",
                        "fix_suggestion": "按脱敏规则替换为某系统、对象A、分类A或一定规模等通用表述。",
                    })
            for pattern, label in patterns:
                if re.search(pattern, content, flags=re.IGNORECASE):
                    issues.append({
                        "severity": "high",
                        "location": filename,
                        "symptom": f"本地项目敏感信息残留：{label}",
                        "fix_suggestion": "按脱敏规则替换为通用表述后再交付。",
                    })
        return issues

    def _check_terminology(self, blocks: Dict[str, str], terminology: List[Dict]) -> List[Dict]:
        issues = []
        for term_entry in terminology:
            term = term_entry.get("term", "")
            if not term:
                continue
            occurrences = sum(1 for content in blocks.values() if term in content)
            if occurrences == 0:
                issues.append(
                    {
                        "severity": "medium",
                        "location": "全局",
                        "symptom": f"术语 '{term}' 在正文中未出现",
                        "fix_suggestion": f"确保术语 '{term}' 在相关章节中正确使用",
                    }
                )
        return issues

    def _check_figures(self, blocks: Dict[str, str], figure_registry: List[Dict]) -> List[Dict]:
        issues = []
        all_text = "\n".join(blocks.values())
        # 检查图号引用
        for fig in figure_registry:
            fid = fig.get("figure_id", "")
            if fid and f"{fid}" not in all_text:
                issues.append(
                    {
                        "severity": "high",
                        "location": fig.get("file", "附图说明"),
                        "symptom": f"图号 '{fid}' 在正文中未被引用",
                        "fix_suggestion": f"在正文中添加 '{fid}' 的引用，如'如图 X 所示'",
                    }
                )
        # 检查附图说明中的图号
        part04 = blocks.get("part_04_附图说明.md", "")
        fig_mentions = re.findall(r"图\s*(\d+)", part04)
        if not fig_mentions:
            issues.append(
                {
                    "severity": "high",
                    "location": "part_04_附图说明.md",
                    "symptom": "附图说明中未提及任何图号",
                    "fix_suggestion": "为每张图添加'图 X 为...'的文字说明",
                }
            )
        return issues

    def _check_cross_references(self, blocks: Dict[str, str]) -> List[Dict]:
        issues = []
        all_text = "\n".join(blocks.values())
        # 检查是否有 dangling 的 "如图" 引用
        fig_refs = re.findall(r"如图\s*(\d+)\s*所示", all_text)
        part04 = blocks.get("part_04_附图说明.md", "")
        for ref in set(fig_refs):
            if f"图 {ref}" not in part04 and f"图{ref}" not in part04:
                issues.append(
                    {
                        "severity": "medium",
                        "location": "正文交叉引用",
                        "symptom": f"正文引用'如图 {ref} 所示'，但附图说明中无对应图号",
                        "fix_suggestion": f"在附图说明中添加图 {ref} 的说明，或删除正文中多余的引用",
                    }
                )
        return issues

    def _check_headings(self, blocks: Dict[str, str]) -> List[Dict]:
        issues = []
        expected = {
            "part_01_技术领域.md": ["一、技术领域"],
            "part_02_背景技术.md": ["二、背景技术"],
            "part_03_发明内容.md": ["三、发明内容", "3.1", "3.2", "3.3"],
            "part_04_附图说明.md": [("四、附图说明", "四、专利附图")],
            "part_05_具体实施方式.md": ["五、具体实施方式"],
        }
        for fname, keywords in expected.items():
            content = blocks.get(fname, "")
            for kw in keywords:
                if isinstance(kw, tuple):
                    matched = any(option in content for option in kw)
                    label = " / ".join(kw)
                else:
                    matched = kw in content
                    label = kw
                if not matched:
                    issues.append(
                        {
                            "severity": "high",
                            "location": fname,
                            "symptom": f"缺少章节标记 '{label}'",
                            "fix_suggestion": f"在 {fname} 中添加 '{label}' 章节标题之一",
                        }
                    )
        return issues

    def _check_module_naming(self, blocks: Dict[str, str]) -> List[Dict]:
        issues = []
        # 简单启发式：检查 part_03 和 part_05 中的模块名称是否一致
        part03 = blocks.get("part_03_发明内容.md", "")
        part05 = blocks.get("part_05_具体实施方式.md", "")
        modules_03 = set(re.findall(r"([\u4e00-\u9fa5]+(?:模块|单元|组件|系统))", part03))
        modules_05 = set(re.findall(r"([\u4e00-\u9fa5]+(?:模块|单元|组件|系统))", part05))
        if modules_03 and modules_05:
            diff = modules_03.symmetric_difference(modules_05)
            if diff:
                issues.append(
                    {
                        "severity": "medium",
                        "location": "part_03 / part_05",
                        "symptom": f"模块命名不一致: {', '.join(list(diff)[:3])}",
                        "fix_suggestion": "统一 part_03 和 part_05 中的模块/组件命名",
                    }
                )
        return issues

    def _plain_text_for_word_count(self, fname: str, content: str) -> str:
        if fname == "part_04_附图说明.md":
            return re.sub(r"```(?:mermaid|mmd)?[\s\S]*?```", "", content, flags=re.IGNORECASE).strip()
        return content

    def _check_word_counts(self, blocks: Dict[str, str], ledger: Optional[Dict[str, Any]] = None) -> List[Dict]:
        issues = []
        default_thresholds = {
            "part_01_技术领域.md": (50, 150, "技术领域只用于限定所属技术领域，避免展开应用场景清单。"),
            "part_02_背景技术.md": (500, 900, "背景技术应结合 1–2 件最相关现有专利说明已有方案和不足。"),
            "part_03_发明内容.md": (800, 1400, "发明内容需要覆盖技术问题、技术方案和有益效果。"),
            "part_04_附图说明.md": (120, 400, "附图说明以图注和 Mermaid/mmd 源码为主，自然语言应简洁，不要求长篇展开。"),
            "part_05_具体实施方式.md": (1800, 3500, "具体实施方式应详细支撑步骤、模块和附图引用。"),
        }
        thresholds = dict(default_thresholds)
        ledger_counts: Dict[str, int] = {}
        for status in (ledger or {}).get("block_statuses", []):
            fname = status.get("file")
            if not fname:
                continue
            min_chars = status.get("target_min_chars")
            max_chars = status.get("target_max_chars")
            reason = status.get("length_reason") or default_thresholds.get(fname, (0, 0, ""))[2]
            char_count = status.get("char_count")
            if isinstance(char_count, int):
                ledger_counts[fname] = char_count
            if isinstance(min_chars, int) and isinstance(max_chars, int):
                thresholds[fname] = (min_chars, max_chars, reason)
        for fname, (min_w, max_w, reason) in thresholds.items():
            content = blocks.get(fname, "")
            wc = ledger_counts.get(fname)
            if not isinstance(wc, int):
                wc = len(self._plain_text_for_word_count(fname, content))
            if wc < min_w:
                issues.append(
                    {
                        "severity": "high",
                        "location": fname,
                        "symptom": f"字数不足: {wc} 字 (建议 {min_w}-{max_w} 字)",
                        "fix_suggestion": f"扩展 {fname} 内容至建议范围；{reason}",
                    }
                )
            elif wc > max_w:
                issues.append(
                    {
                        "severity": "low",
                        "location": fname,
                        "symptom": f"字数偏多: {wc} 字 (建议 {min_w}-{max_w} 字)",
                        "fix_suggestion": f"适当精简 {fname} 内容；{reason}",
                    }
                )
        return issues

    def _check_style(self, blocks: Dict[str, str]) -> List[Dict]:
        issues = []
        forbidden = ["客户", "贵方"]
        for fname, content in blocks.items():
            for word in forbidden:
                if word in content:
                    issues.append(
                        {
                            "severity": "medium",
                            "location": fname,
                            "symptom": f"发现禁用用语: '{word}'",
                            "fix_suggestion": f"将 '{word}' 替换为专利规范用语，如'所述'、'本实施例'",
                        }
                    )
        # AI 腔检测：过度排比
        all_text = "\n".join(blocks.values())
        if re.search(r"第一[，、]\s*第二[，、]\s*第三", all_text):
            issues.append(
                {
                    "severity": "low",
                    "location": "全局",
                    "symptom": "检测到排比结构（第一、第二、第三），可能为 AI 生成痕迹",
                    "fix_suggestion": "改为连贯段落叙述，避免列表式排比",
                }
            )
        return issues

    def _load_evidence_pack(self, ledger: Dict) -> Dict[str, Any]:
        """读取 Phase 2 内部专利复核证据包，用于校验正文引用是否可追溯。"""
        candidates = []
        ledger_path = ledger.get("research_inputs", {}).get("evidence_pack_path")
        if ledger_path:
            candidates.append(ledger_path)
        candidates.append("artifacts/prior_art/phase_02_evidence_pack.json")
        candidates.append("artifacts/prior_art/phase_04_evidence_pack.json")

        for path in candidates:
            full_path = self.workspace / path
            if not full_path.exists():
                continue
            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    pack = json.load(f)
                if isinstance(pack, dict):
                    return pack
            except Exception as e:
                self._log("evidence_pack_load_error", {"path": path, "error": str(e)})
        return {}

    def _check_evidence_citations(self, blocks: Dict[str, str], evidence_pack: Dict[str, Any]) -> List[Dict]:
        issues = []
        all_text = "\n".join(blocks.values())
        part02 = blocks.get("part_02_背景技术.md", "")

        if "CN" not in part02:
            issues.append(
                {
                    "severity": "high",
                    "location": "part_02_背景技术.md",
                    "symptom": "背景技术未引用任何中国专利（未出现 CN 专利号）",
                    "fix_suggestion": "引用至少 2-3 篇已有 CN 专利文件，说明其与本申请接近之处和不足。",
                }
            )

        evidence_items = [item for item in evidence_pack.get("evidence", []) if isinstance(item, dict)]
        if evidence_pack and not evidence_items:
            issues.append(
                {
                    "severity": "high",
                    "location": "artifacts/prior_art/phase_02_evidence_pack.json",
                    "symptom": "证据包存在但 evidence[] 为空或结构异常",
                    "fix_suggestion": "重新生成 Phase 2 内部专利复核 evidence_pack，确保包含专利证据。",
                }
            )

        patent_numbers = []
        for item in evidence_items:
            if item.get("source_type") != "patent":
                continue
            patent_no = self._extract_patent_number_from_evidence(item)
            if patent_no and patent_no not in patent_numbers:
                patent_numbers.append(patent_no)

        cited_patents = [patent_no for patent_no in patent_numbers if patent_no in all_text]
        if patent_numbers and not cited_patents:
            issues.append(
                {
                    "severity": "high",
                    "location": "part_02_背景技术.md",
                    "symptom": "背景技术未引用 evidence_pack 中登记的任何 CN 专利号",
                    "fix_suggestion": "至少选择最接近的 CN 专利号写入背景技术，内部 evidence_id 不应写入正式正文。",
                }
            )

        if len(cited_patents) < min(2, len(patent_numbers)):
            issues.append(
                {
                    "severity": "medium",
                    "location": "part_02_背景技术.md",
                    "symptom": "背景技术引用的相关 CN 专利数量偏少",
                    "fix_suggestion": "优先引用 2-3 篇最接近 CN 专利文件，避免罗列无关证据。",
                }
            )

        known_ids = {item.get("evidence_id") for item in evidence_items if item.get("evidence_id")}
        cited_ids = set(re.findall(r"\b(?:EV|PAT)-[A-Z0-9-]*\d{3}\b", all_text))
        unknown_ids = sorted(cited_ids - known_ids)
        for evidence_id in unknown_ids[:5]:
            issues.append(
                {
                    "severity": "medium",
                    "location": "全文证据引用",
                    "symptom": f"正文引用了未登记证据编号 '{evidence_id}'",
                    "fix_suggestion": f"将 '{evidence_id}' 登记到 evidence_pack，或从正式正文移除内部证据编号。",
                }
            )

        return issues

    def _extract_patent_number_from_evidence(self, item: Dict[str, Any]) -> str:
        candidates = [
            item.get("publicationNumber", ""),
            item.get("url", ""),
            item.get("excerpt", ""),
            item.get("title", ""),
        ]
        for value in candidates:
            if not value:
                continue
            match = re.search(r"CN\s?\d{5,}[A-Z]?", value, re.IGNORECASE)
            if match:
                return match.group(0).replace(" ", "").upper()
        return ""

    def _check_figure_artifacts(self, ledger: Dict) -> List[Dict]:
        issues = []
        fig_registry = ledger.get("figure_registry", [])
        for fig in fig_registry:
            art = fig.get("artifacts", {})
            for key in ["mmd"]:
                path = art.get(key, "")
                if path and not (self.workspace / path).exists():
                    issues.append(
                        {
                            "severity": "medium",
                            "location": f"figure_registry/{fig.get('figure_id', '?')}",
                            "symptom": f"缺失 {key} 工件: {path}",
                            "fix_suggestion": f"生成 {path} 文件",
                        }
                    )
            if fig.get("mermaid_source_embedded_in_docx") is not True:
                issues.append(
                    {
                        "severity": "medium",
                        "location": f"figure_registry/{fig.get('figure_id', '?')}",
                        "symptom": "附图说明未声明内嵌 Mermaid 源码",
                        "fix_suggestion": "将 Mermaid/mmd 源码写入附图说明正文",
                    }
                )
        return issues

    def _check_step_numbering(self, blocks: Dict[str, str], step_registry: Any) -> List[Dict]:
        """检查步骤编号 S101-S10x 的贯穿一致性。"""
        issues = []
        if not step_registry:
            return issues

        all_text = "\n".join(blocks.values())
        part03 = blocks.get("part_03_发明内容.md", "")
        part04 = blocks.get("part_04_附图说明.md", "")
        part05 = blocks.get("part_05_具体实施方式.md", "")

        # 提取所有步骤号
        step_ids = []
        if isinstance(step_registry, list):
            for entry in step_registry:
                if isinstance(entry, dict):
                    sid = entry.get("step_id", "")
                    if sid:
                        step_ids.append(sid)
                elif isinstance(entry, str):
                    step_ids.append(entry)
        elif isinstance(step_registry, dict):
            step_ids = list(step_registry.keys())

        if not step_ids:
            return issues

        # 检查技术方案（B2）中是否出现所有步骤号
        for sid in step_ids:
            if sid not in part03:
                issues.append(
                    {
                        "severity": "high",
                        "location": "part_03_发明内容.md（B2 技术方案）",
                        "symptom": f"步骤编号 '{sid}' 在技术方案中未出现",
                        "fix_suggestion": f"在技术方案 B2 中加入 '{sid}' 的步骤描述",
                    }
                )

        # 检查附图说明（图2）中是否出现步骤范围
        if part04 and "图2" in part04:
            has_range = any(f"步骤{sid}" in part04 or f"{sid}" in part04 for sid in step_ids)
            if not has_range:
                issues.append(
                    {
                        "severity": "medium",
                        "location": "part_04_附图说明.md（图2）",
                        "symptom": "图2（方法流程图）说明中未提及步骤编号范围",
                        "fix_suggestion": f"在图2说明中写明'其中包括步骤{step_ids[0]}至步骤{step_ids[-1]}'",
                    }
                )

        # 检查具体实施方式中是否按步骤号顺序展开
        for sid in step_ids:
            pattern = f"{sid}"
            if pattern not in part05:
                issues.append(
                    {
                        "severity": "high",
                        "location": "part_05_具体实施方式.md",
                        "symptom": f"步骤编号 '{sid}' 在具体实施方式中未出现",
                        "fix_suggestion": f"在 part_05 中增加 '{sid}' 的展开说明段落",
                    }
                )

        # 检查是否跳号
        numeric_ids = []
        for sid in step_ids:
            m = re.match(r"S(\d+)", sid)
            if m:
                numeric_ids.append(int(m.group(1)))
        if numeric_ids:
            expected = list(range(min(numeric_ids), max(numeric_ids) + 1))
            actual = sorted(numeric_ids)
            if actual != expected:
                missing = [f"S{n:03d}" for n in expected if n not in actual]
                issues.append(
                    {
                        "severity": "high",
                        "location": "step_registry",
                        "symptom": f"步骤编号跳号，缺失: {', '.join(missing)}",
                        "fix_suggestion": "补齐缺失的步骤编号，或调整编号使其连续",
                    }
                )

        return issues

    def _check_style_compliance(self, blocks: Dict[str, str]) -> List[Dict]:
        """检查风格遵从度（针对 CN121526509A 风格画像）。"""
        issues = []
        part05 = blocks.get("part_05_具体实施方式.md", "")
        if not part05:
            return issues

        # 1. 固定起手句
        if not re.search(r"下面对照附图", part05):
            issues.append(
                {
                    "severity": "medium",
                    "location": "part_05_具体实施方式.md",
                    "symptom": "缺少参考专利式固定起手句（'下面对照附图...'）",
                    "fix_suggestion": "具体实施方式第一段使用'下面对照附图，通过对较优实施例的描述，对本申请的具体实施方式作进一步详细说明。'",
                }
            )

        # 2. 总述句
        if not re.search(r"本实施例提供的一种.*方法，包括以下步骤：", part05):
            issues.append(
                {
                    "severity": "high",
                    "location": "part_05_具体实施方式.md",
                    "symptom": "缺少步骤总述句（'本实施例提供的一种…方法，包括以下步骤：'）",
                    "fix_suggestion": "在具体实施方式第二段加入总述句，按 S101、S102… 列出方法步骤",
                }
            )

        # 3. "…具体如下：" 句式
        if "具体如下：" not in part05:
            issues.append(
                {
                    "severity": "medium",
                    "location": "part_05_具体实施方式.md",
                    "symptom": "未出现'…步骤具体如下：'展开句式",
                    "fix_suggestion": "在每个关键步骤后使用'…步骤具体如下：'进行二级展开",
                }
            )

        # 4. "…的核心逻辑是：" 句式
        if "核心逻辑是" not in part05 and "核心是" not in part05:
            issues.append(
                {
                    "severity": "medium",
                    "location": "part_05_具体实施方式.md",
                    "symptom": "未出现解释型核心逻辑句式（'…的核心逻辑是…'）",
                    "fix_suggestion": "至少 2-4 处使用'…的核心逻辑是…'解释步骤的技术意义",
                }
            )

        # 5. "前者…；后者…；二者协同…" 对偶句
        if not re.search(r"前者.*；.*后者.*；.*二者", part05):
            issues.append(
                {
                    "severity": "low",
                    "location": "part_05_具体实施方式.md",
                    "symptom": "未出现'前者…；后者…；二者协同…'对偶归纳句式",
                    "fix_suggestion": "至少 3 处使用'前者…；后者…；二者协同…'解释模块/步骤关系",
                }
            )

        # 6. 末尾 "进一步" 段落
        if "进一步" not in part05:
            issues.append(
                {
                    "severity": "low",
                    "location": "part_05_具体实施方式.md",
                    "symptom": "末尾缺少'进一步，…'补充段落",
                    "fix_suggestion": "在末尾增加多个'进一步，…'段落，补充参数范围、系统组成、变形方案",
                }
            )

        # 7. 禁止句式（AI 腔）
        forbidden_patterns = [
            (r"在一个实施例中，提供一种", "使用了非参考专利的展开句式"),
            (r"在较优实施例中，.*可以采用", "使用了非参考专利的参数展开方式"),
            (r"本申请还可应用于.*场景", "使用了场景应用式结尾"),
        ]
        for pattern, desc in forbidden_patterns:
            if re.search(pattern, part05):
                issues.append(
                    {
                        "severity": "medium",
                        "location": "part_05_具体实施方式.md",
                        "symptom": f"检测到禁用句式: {desc}",
                        "fix_suggestion": "改用参考专利风格：'本实施例提供…包括以下步骤：' + '…步骤具体如下：' + '核心逻辑是…'",
                    }
                )

        return issues

    def _check_section_structure(self, blocks: Dict[str, str]) -> List[Dict]:
        """检查章节结构合规性。"""
        issues = []
        all_text = "\n".join(blocks.values())

        # 1. 章节顺序检查
        expected_order = [
            (("一、技术领域",), "part_01_技术领域.md"),
            (("二、背景技术",), "part_02_背景技术.md"),
            (("三、发明内容",), "part_03_发明内容.md"),
            (("四、附图说明", "四、专利附图"), "part_04_附图说明.md"),
            (("五、具体实施方式",), "part_05_具体实施方式.md"),
        ]
        positions = []
        cursor = 0
        for titles, fname in expected_order:
            content = blocks.get(fname, "")
            local_positions = [content.find(title) for title in titles if content and content.find(title) >= 0]
            pos = cursor + min(local_positions) if local_positions else -1
            positions.append((" / ".join(titles), fname, pos))
            cursor += len(content) + 1

        valid_positions = [(t, f, p) for t, f, p in positions if p >= 0]
        for i in range(1, len(valid_positions)):
            prev = valid_positions[i - 1]
            curr = valid_positions[i]
            if curr[2] < prev[2]:
                issues.append(
                    {
                        "severity": "high",
                        "location": f"{curr[1]} / {prev[1]}",
                        "symptom": f"章节顺序异常: '{curr[0]}' 出现在 '{prev[0]}' 之前",
                        "fix_suggestion": "按模板固定顺序排列：技术领域→背景技术→发明内容→专利附图→具体实施方式",
                    }
                )

        # 2. 检查是否存在"权利要求书"
        if "权利要求书" in all_text:
            issues.append(
                {
                    "severity": "high",
                    "location": "全局",
                    "symptom": "交底书中包含'权利要求书'，应由专利代理师撰写",
                    "fix_suggestion": "删除交底书中的权利要求书部分",
                }
            )

        # 3. 检查具体实施方式是否在附图章节之后
        part04 = blocks.get("part_04_附图说明.md", "")
        if part04 and blocks.get("part_05_具体实施方式.md", ""):
            part04_pos = all_text.find("四、专利附图") if "四、专利附图" in all_text else all_text.find("四、附图说明")
            part05_pos = all_text.find("五、具体实施方式")
            if part04_pos >= 0 and part05_pos >= 0 and part05_pos < part04_pos:
                issues.append(
                    {
                        "severity": "high",
                        "location": "全局",
                        "symptom": "具体实施方式出现在专利附图之前",
                        "fix_suggestion": "将专利附图移到具体实施方式之前",
                    }
                )

        return issues

    def _check_domain_semantics(self, blocks: Dict[str, str], domain_scope: str = "") -> List[Dict]:
        """核对正文是否聚焦当前技术领域，而不是工作流/写作系统说明。"""
        all_text = "\n".join(blocks.values())
        issues: List[Dict] = []
        internal_terms = [
            "Phase 2", "Phase 3", "Phase 5", "Phase 6", "Phase 7", "Phase 8", "Phase 9",
            "research_pack", "patent_candidate_pool", "evidence_pack", "block_context",
            "shared_context", "facts_ledger", "figure_registry", "terminology_registry",
            "block_review", "evidence_id", "写作依据", "正文分块", "IPR 模拟审查",
            "最终交付健康检查", "专利正文的一致性审计", "分块审核",
        ]
        hits = [term for term in internal_terms if term in all_text]
        if hits:
            issues.append({
                "severity": "high",
                "location": "全文",
                "symptom": "正文混入工作流内部术语: " + "、".join(hits[:8]),
                "fix_suggestion": f"删除工作流内部实现内容，改写为{domain_scope}技术方案。",
            })

        required_sections = {
            "part_02_背景技术.md": ["2.1 与本申请相关的现有技术背景知识", "2.2 与本申请相关的最接近的现有技术", "2.3 现有技术的缺陷和不足"],
            "part_03_发明内容.md": ["3.1 本申请所需要解决的技术问题", "3.2 本申请的技术方案", "3.3 本申请的技术效果"],
        }
        for filename, headings in required_sections.items():
            content = blocks.get(filename, "")
            missing = [heading for heading in headings if heading not in content]
            if missing:
                issues.append({
                    "severity": "high",
                    "location": filename,
                    "symptom": "缺少模板要求小节: " + "、".join(missing),
                    "fix_suggestion": "按技术交底书框架补齐对应小节，不得使用自定义小节替代。",
                })

        figure_text = blocks.get("part_04_附图说明.md", "")
        if any(term in figure_text for term in ["读取研究资料", "生成分块上下文", "分块撰写", "分块审核"]):
            issues.append({
                "severity": "high",
                "location": "part_04_附图说明.md",
                "symptom": "附图描述的是写作工作流，不是 {} 技术方案。".format(domain_scope),
                "fix_suggestion": "附图应展示本专利的技术系统架构、方法流程、数据处理关系等技术内容，而非写作工作流。",
            })

        # 从账本中动态读取领域术语，不再硬编码特定领域
        _ledger = {}
        _ledger_path = self.workspace / "artifacts" / "draft" / "facts_ledger.json"
        if _ledger_path.exists():
            try:
                with open(_ledger_path, "r", encoding="utf-8") as f:
                    _ledger = json.load(f)
            except Exception:
                pass
        terminology_entries = _ledger.get("terminology", [])
        domain_terms = []
        for entry in terminology_entries:
            term = entry.get("term", "")
            if term:
                domain_terms.append(term)
        # 无账本术语时，从 domain_scope 拆词作为回退
        if not domain_terms:
            domain_terms = re.findall(r'[\u4e00-\u9fa5]{2,4}', domain_scope)
        threshold = max(2, len(domain_terms) // 2)
        if sum(1 for term in domain_terms if term in all_text) < threshold:
            issues.append({
                "severity": "high",
                "location": "全文",
                "symptom": f"领域关键术语覆盖不足（期望≥{threshold}个，实际命中{sum(1 for term in domain_terms if term in all_text)}个），疑似技术领域偏移。",
                "fix_suggestion": "围绕说明书中的核心技术术语重写正文，确保关键术语在相关章节中正确使用。",
            })
        return issues

    def _check_background_and_figure_substance(self, blocks: Dict[str, str]) -> List[Dict]:
        """检查背景技术是否基于具体 CN 专利事实，附图是否足以支撑方案。"""
        issues: List[Dict] = []
        part02 = blocks.get("part_02_背景技术.md", "")
        part04 = blocks.get("part_04_附图说明.md", "")
        all_text = "\n".join(blocks.values())

        cited_patents = sorted(set(re.findall(r"CN\d{6,}[A-Z]?", part02)))
        if len(cited_patents) < 1:
            issues.append({
                "severity": "high",
                "location": "part_02_背景技术.md",
                "symptom": "背景技术没有引用具体 CN 现有专利",
                "fix_suggestion": "至少引用 1-2 件最接近 CN 专利，并说明其公开内容和不足。",
            })
        if len(cited_patents) > 2:
            issues.append({
                "severity": "medium",
                "location": "part_02_背景技术.md",
                "symptom": "背景技术引用专利过多，疑似罗列检索结果",
                "fix_suggestion": "只保留 1-2 件最接近现有技术。",
            })
        generic_phrases = ["与{}或智能检测相关的方案".format(domain_scope[:4]), "可以对{}对象或检测信息进行识别、采集或辅助判断".format(domain_scope[:4])]
        if any(phrase in part02 for phrase in generic_phrases):
            issues.append({
                "severity": "high",
                "location": "part_02_背景技术.md",
                "symptom": "背景专利描述仍是泛化占位，没有写出现有专利实际公开内容",
                "fix_suggestion": "按每件专利的实际技术对象、处理流程和局限性重写。",
            })
        if not re.search(r"公开了.*(采集|识别|检测|判断|质检|拆解|调度|分配|协调|分解|执行|规划|任务|资源)", part02):
            issues.append({
                "severity": "high",
                "location": "part_02_背景技术.md",
                "symptom": "背景技术未说明现有专利公开了什么技术内容",
                "fix_suggestion": "使用‘如中国专利 CN... 公开了...，其可以...，但是...’句式。",
            })

        figure_ids = sorted(set(re.findall(r"图\s*(\d+)", part04)))
        if len(figure_ids) < 4:
            issues.append({
                "severity": "high",
                "location": "part_04_附图说明.md",
                "symptom": f"附图数量不足，当前仅 {len(figure_ids)} 张",
                "fix_suggestion": "至少给出系统架构、方法流程、证据记录结构、追溯关系 4 张图。",
            })
        if part04.count("```mermaid") < 4:
            issues.append({
                "severity": "high",
                "location": "part_04_附图说明.md",
                "symptom": "附图说明中 Mermaid/mmd 源码数量不足",
                "fix_suggestion": "每个图注后均附对应 Mermaid 源码。",
            })
        normalized_text = re.sub(r"\s+", "", all_text)
        for fig_no in ["1", "2", "3", "4"]:
            if f"图{fig_no}" not in normalized_text:
                issues.append({
                    "severity": "medium",
                    "location": "具体实施方式/附图说明",
                    "symptom": f"正文未引用图 {fig_no}",
                    "fix_suggestion": f"在具体实施方式中补充‘如图 {fig_no} 所示’或组合图号引用。",
                })
        return issues

    def _build_report(
        self, overall_score: int, scores: Dict[str, int], issues: List[Dict], passed: bool
    ) -> str:
        lines = [
            "# 一致性审计报告",
            "",
            f"- `consistency_audit_report_path`: artifacts/audit/phase_06_consistency_audit_report.md",
            f"- `draft_title`: {self.manifest.get('patent_title', '未命名')}",
            f"- `draft_version`: 1",
            "",
            "## 审计项结果",
            "",
            f"- `terminology_consistency`: {'通过' if scores['terminology'] >= 8 else '警告'}",
            f"- `figure_text_consistency`: {'通过' if scores['figure_text'] >= 8 else '警告'}",
            f"- `step_numbering_consistency`: {'通过' if scores.get('step_numbering', 10) >= 8 else '警告'}",
            f"- `style_compliance_consistency`: {'通过' if scores.get('style_compliance', 10) >= 8 else '警告'}",
            f"- `section_structure_consistency`: {'通过' if scores.get('section_structure', 10) >= 8 else '警告'}",
            f"- `cross_reference_consistency`: {'通过' if scores['cross_reference'] >= 8 else '警告'}",
            f"- `section_heading_consistency`: {'通过' if scores['section_heading'] >= 8 else '警告'}",
            f"- `module_naming_consistency`: {'通过' if scores['module_naming'] >= 8 else '警告'}",
            f"- `style_tone_consistency`: {'通过' if scores['style_tone'] >= 8 else '警告'}",
            f"- `evidence_citation_consistency`: {'通过' if scores['evidence_citation'] >= 8 else '警告'}",
            f"- `figure_artifact_consistency`: {'通过' if scores['figure_artifact'] >= 8 else '警告'}",
            f"- `formula_parameter_consistency`: {'通过' if scores.get('formula_symbol', 10) >= 8 else '警告'}",
            f"- `technical_closure_consistency`: {'通过' if scores.get('technical_closure', 10) >= 8 else '警告'}",
            f"- `cnipa_abstract_alignment_consistency`: {'通过' if scores.get('cnipa_abstract_alignment', 10) >= 8 else '警告'}",
            f"- `patent_description_accuracy`: {'通过' if scores.get('patent_description_accuracy', 10) >= 8 else '警告'}",
            f"- `revision_log_consistency`: {'通过' if scores.get('revision_log', 10) >= 8 else '警告'}",
            f"- `redaction_consistency`: {'通过' if scores.get('redaction', 10) >= 8 else '警告'}",
            "",
            "## 评分（100 分制）",
            "",
            f"- `scoring_scale`: 0-100",
            f"- `overall_score`: {overall_score}",
            "",
            "### 分项评分（0-10）",
            "",
        ]
        for key, val in scores.items():
            label = {
                "terminology": "术语一致性",
                "figure_text": "图号/图名/正文引用一致性",
                "step_numbering": "步骤编号贯穿一致性",
                "style_compliance": "风格遵从度",
                "section_structure": "章节结构合规性",
                "cross_reference": "交叉引用一致性",
                "section_heading": "章节标题与目录一致性",
                "module_naming": "模块/部件命名一致性",
                "style_tone": "行文风格一致性",
                "deliverable_structure": "交付结构一致性",
                "evidence_citation": "背景专利引用一致性",
                "figure_artifact": "附图工件完整性",
                "background_figure_substance": "背景技术实质性与附图充分性",
                "technical_closure": "技术方案闭环完整性",
                "cnipa_abstract_alignment": "CNIPA 摘要理解一致性",
                "revision_log": "迭代修订留档合规性",
                "redaction": "本地项目脱敏残留检查",
                "formula_symbol": "公式/参数一致性",
            }.get(key, key)
            lines.append(f"- `{key}_score`: {val}  # {label}")

        lines.extend(["", "### Top 问题", ""])
        prioritized_issues = sorted(issues, key=lambda item: {"high": 0, "medium": 1, "low": 2}.get(item.get("severity", "medium"), 1))
        for i, issue in enumerate(prioritized_issues[:5], 1):
            lines.append(f"{i}. **{issue['severity'].upper()}** | {issue['location']}")
            lines.append(f"   - 症状: {issue['symptom']}")
            lines.append(f"   - 建议: {issue['fix_suggestion']}")
            lines.append("")

        lines.extend(
            [
                "## 结论",
                "",
                f"- `pass_fail`: {'pass' if passed else 'fail'}",
                f"- pass_fail: {'pass' if passed else 'fail'}",
                "- `pass_threshold_suggested`: 80",
                f"- `pass_fail_suggested`: {'pass' if passed else 'fail'}",
                f"- pass_fail_suggested: {'pass' if passed else 'fail'}",
            ]
        )
        return "\n".join(lines)
