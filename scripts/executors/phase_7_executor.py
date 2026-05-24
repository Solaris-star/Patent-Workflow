#!/usr/bin/env python3
"""
Phase 7 Executor — IPR 模拟审查。
读取 draft 分块文件，执行基于《专利审查指南》的形式+实质审查模拟，产出：
- artifacts/audit/phase_07_ipr_review_report.md
"""

import json
import re
from pathlib import Path
from typing import Dict, Any, List, Tuple

from executors.base_executor import BaseExecutor, ExecutorResult


IPR_LEGAL_RULES: Dict[str, Dict[str, Any]] = {
    "CN-PA-002-TECH-SOLUTION": {
        "law": "中华人民共和国专利法",
        "article": "第2条第2款",
        "topic": "发明是对产品、方法或者其改进所提出的新的技术方案",
        "check_goal": "核对文本是否呈现技术问题、技术手段和技术效果",
        "implementation": "_check_tech_solution",
        "input_files": ["part_03_发明内容.md"],
        "risk_level_if_failed": "high",
    },
    "CN-PA-022-NOVELTY": {
        "law": "中华人民共和国专利法",
        "article": "第22条第2款",
        "topic": "新颖性",
        "check_goal": "核对发明内容是否写出区别特征，且未照搬背景专利摘录",
        "implementation": "_check_novelty",
        "input_files": ["part_02_背景技术.md", "part_03_发明内容.md", "artifacts/prior_art/phase_02_evidence_pack.json"],
        "risk_level_if_failed": "medium",
    },
    "CN-PA-022-INVENTIVENESS": {
        "law": "中华人民共和国专利法",
        "article": "第22条第3款",
        "topic": "创造性",
        "check_goal": "核对区别特征是否体现协同、耦合、联动或组合效果",
        "implementation": "_check_inventiveness",
        "input_files": ["part_03_发明内容.md"],
        "risk_level_if_failed": "medium",
    },
    "CN-PA-022-PRACTICALITY": {
        "law": "中华人民共和国专利法",
        "article": "第22条第4款",
        "topic": "实用性",
        "check_goal": "核对具体实施方式是否具备可执行步骤和可使用的技术对象",
        "implementation": "_check_practicality",
        "input_files": ["part_05_具体实施方式.md"],
        "risk_level_if_failed": "medium",
    },
    "CN-PA-026-SUFFICIENCY": {
        "law": "中华人民共和国专利法",
        "article": "第26条第3款",
        "topic": "说明书充分公开",
        "check_goal": "核对具体实施方式是否达到基本展开篇幅和实现支撑",
        "implementation": "_check_sufficiency",
        "input_files": ["part_05_具体实施方式.md"],
        "risk_level_if_failed": "medium",
    },
    "CN-PA-026-SUPPORT": {
        "law": "中华人民共和国专利法",
        "article": "第26条第4款",
        "topic": "权利要求得到说明书支持",
        "check_goal": "以交底书技术方案代替权利要求草案，核对关键技术特征是否有定义",
        "implementation": "_check_support",
        "input_files": ["part_03_发明内容.md"],
        "risk_level_if_failed": "medium",
    },
    "CN-PA-031-UNITY": {
        "law": "中华人民共和国专利法",
        "article": "第31条",
        "topic": "单一性",
        "check_goal": "核对文本是否围绕同一技术问题和共同技术构思展开",
        "implementation": "_check_unity",
        "input_files": ["part_03_发明内容.md", "part_05_具体实施方式.md"],
        "risk_level_if_failed": "medium",
    },
    "CN-PA-033-AMENDMENT-BASIS": {
        "law": "中华人民共和国专利法",
        "article": "第33条",
        "topic": "修改不得超范围",
        "check_goal": "核对文本是否出现明显无原始依据的扩展式表述",
        "implementation": "_check_amendment_basis",
        "input_files": ["part_*.md"],
        "risk_level_if_failed": "medium",
    },
    "CN-PA-020-HONESTY": {
        "law": "中华人民共和国专利法",
        "article": "第20条",
        "topic": "诚实信用原则",
        "check_goal": "核对背景专利证据是否有可信 URL，且专利号与正文一致",
        "implementation": "_check_honesty",
        "input_files": ["part_02_背景技术.md", "artifacts/prior_art/phase_02_evidence_pack.json"],
        "risk_level_if_failed": "medium",
    },
}


class PhaseExecutor(BaseExecutor):
    """阶段 7 执行器：IPR 模拟审查。"""

    def _rule_meta(self, rule_id: str) -> Dict[str, Any]:
        rule = IPR_LEGAL_RULES[rule_id]
        return {
            "rule_id": rule_id,
            "legal_basis": f"{rule['law']} {rule['article']}",
            "check_goal": rule["check_goal"],
            "implementation": rule["implementation"],
            "input_files": rule["input_files"],
        }

    def _execute(self) -> ExecutorResult:
        print("   ⚖️ 执行 IPR 模拟审查...")

        # ── 读取输入 ──────────────────────────
        draft_dir = self.run_dir
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
            blocks[bf] = p.read_text(encoding="utf-8") if p.exists() else ""

        all_text = "\n".join(blocks.values())
        patent_title = self.manifest.get("patent_title", "未命名专利")
        domain_scope = self.manifest.get("domain_scope", "")
        if not domain_scope:
            self._log("missing_domain_scope", {"error": "manifest.domain_scope is empty, using empty string"})
        evidence_pack = self._load_evidence_pack()

        # ── 逐项审查 ──────────────────────────
        checks = []
        risks: List[Dict[str, Any]] = []

        # 1. 授权客体（专利法第 2 条）
        has_tech_solution = self._check_tech_solution(blocks)
        check1_pass = has_tech_solution
        checks.append(
            {
                "dimension": "授权客体（专利法第 2 条）",
                **self._rule_meta("CN-PA-002-TECH-SOLUTION"),
                "result": "通过" if check1_pass else "驳回风险",
                "detail": "属于技术方案" if check1_pass else "未明确识别技术方案三要素",
            }
        )
        if not check1_pass:
            risks.append(
                {
                    "severity": "high",
                    "impact": "授权客体驳回",
                    "evidence_or_reason": "part_03_发明内容 未清晰描述技术手段、技术问题、技术效果",
                    "fix_suggestion": "明确说明本发明解决了什么技术问题，采用了什么技术手段，获得了什么技术效果",
                }
            )

        # 2. 新颖性（专利法第 22 条第 2 款）
        novelty_pass, novelty_findings = self._check_novelty(blocks, evidence_pack)
        checks.append(
            {
                "dimension": "新颖性（专利法第 22 条第 2 款）",
                **self._rule_meta("CN-PA-022-NOVELTY"),
                "result": "通过" if novelty_pass else "警告",
                "detail": "未见明显现有技术冲突" if novelty_pass else f"存在 {len(novelty_findings)} 项新颖性风险",
            }
        )
        for f in novelty_findings:
            if f.get("severity") in ("high", "medium"):
                risks.append({
                    "severity": f["severity"],
                    "impact": f"新颖性: {f.get('check_point', '')}",
                    "evidence_or_reason": f["finding"],
                    "fix_suggestion": f.get("suggestion", ""),
                })

        # 3. 创造性（专利法第 22 条第 3 款）
        inventiveness_pass, inventiveness_findings = self._check_inventiveness(blocks)
        checks.append(
            {
                "dimension": "创造性（专利法第 22 条第 3 款）",
                **self._rule_meta("CN-PA-022-INVENTIVENESS"),
                "result": "通过" if inventiveness_pass else "警告",
                "detail": "区别特征具有非显而易见性" if inventiveness_pass else f"存在 {len(inventiveness_findings)} 项创造性风险",
            }
        )
        for f in inventiveness_findings:
            if f.get("severity") in ("high", "medium"):
                risks.append({
                    "severity": f["severity"],
                    "impact": f"创造性: {f.get('check_point', '')}",
                    "evidence_or_reason": f["finding"],
                    "fix_suggestion": f.get("suggestion", ""),
                })

        # 4. 实用性（专利法第 22 条第 4 款）
        practicality_pass, practicality_findings = self._check_practicality(blocks)
        checks.append(
            {
                "dimension": "实用性（专利法第 22 条第 4 款）",
                **self._rule_meta("CN-PA-022-PRACTICALITY"),
                "result": "通过" if practicality_pass else "警告",
                "detail": "能够制造或使用" if practicality_pass else f"存在 {len(practicality_findings)} 项实用性问题",
            }
        )
        for f in practicality_findings:
            if f.get("severity") in ("high", "medium"):
                risks.append({
                    "severity": f["severity"],
                    "impact": f"实用性: {f.get('check_point', '')}",
                    "evidence_or_reason": f["finding"],
                    "fix_suggestion": f.get("suggestion", ""),
                })

        # 5. 说明书充分公开（专利法第 26 条第 3 款）
        sufficiency_pass, sufficiency_findings = self._check_sufficiency(blocks)
        checks.append(
            {
                "dimension": "说明书充分公开（专利法第 26 条第 3 款）",
                **self._rule_meta("CN-PA-026-SUFFICIENCY"),
                "result": "通过" if sufficiency_pass else "警告",
                "detail": "清楚、完整，能够实现" if sufficiency_pass else f"存在 {len(sufficiency_findings)} 项公开缺陷",
            }
        )
        for f in sufficiency_findings:
            if f.get("severity") in ("high", "medium"):
                risks.append({
                    "severity": f["severity"],
                    "impact": f"充分公开: {f.get('check_point', '')}",
                    "evidence_or_reason": f["finding"],
                    "fix_suggestion": f.get("suggestion", ""),
                })

        # 6. 权利要求得到支持（专利法第 26 条第 4 款）
        support_pass, support_findings = self._check_support(blocks)
        checks.append(
            {
                "dimension": "权利要求得到支持（专利法第 26 条第 4 款）",
                **self._rule_meta("CN-PA-026-SUPPORT"),
                "result": "通过" if support_pass else "警告",
                "detail": "说明书支持技术方案" if support_pass else f"存在 {len(support_findings)} 项支持性缺陷",
            }
        )
        for f in support_findings:
            if f.get("severity") in ("high", "medium"):
                risks.append({
                    "severity": f["severity"],
                    "impact": f"权利要求支持: {f.get('check_point', '')}",
                    "evidence_or_reason": f["finding"],
                    "fix_suggestion": f.get("suggestion", ""),
                })

        # 7. 单一性（专利法第 31 条）
        unity_pass, unity_findings = self._check_unity(blocks)
        checks.append(
            {
                "dimension": "单一性（专利法第 31 条）",
                **self._rule_meta("CN-PA-031-UNITY"),
                "result": "通过" if unity_pass else "警告",
                "detail": "属于一个总的发明构思" if unity_pass else f"存在 {len(unity_findings)} 项单一性风险",
            }
        )
        for f in unity_findings:
            if f.get("severity") in ("high", "medium"):
                risks.append({
                    "severity": f["severity"],
                    "impact": f"单一性: {f.get('check_point', '')}",
                    "evidence_or_reason": f["finding"],
                    "fix_suggestion": f.get("suggestion", ""),
                })

        # 8. 修改超范围（专利法第 33 条）
        amendment_pass, amendment_findings = self._check_amendment_basis(blocks)
        checks.append(
            {
                "dimension": "修改超范围（专利法第 33 条）",
                **self._rule_meta("CN-PA-033-AMENDMENT-BASIS"),
                "result": "通过" if amendment_pass else "警告",
                "detail": "未见明显新增未支撑特征" if amendment_pass else f"存在 {len(amendment_findings)} 项超范围风险",
            }
        )
        for f in amendment_findings:
            if f.get("severity") in ("high", "medium"):
                risks.append({
                    "severity": f["severity"],
                    "impact": f"修改超范围: {f.get('check_point', '')}",
                    "evidence_or_reason": f["finding"],
                    "fix_suggestion": f.get("suggestion", ""),
                })

        # 9. 诚实信用（专利法第 20 条）
        honesty_pass, honesty_findings = self._check_honesty(blocks, evidence_pack)
        checks.append(
            {
                "dimension": "诚实信用（专利法第 20 条）",
                **self._rule_meta("CN-PA-020-HONESTY"),
                "result": "通过" if honesty_pass else "警告",
                "detail": "证据来源可追溯，未见明显虚构风险" if honesty_pass else "存在证据来源或事实可追溯性问题",
            }
        )
        for finding in honesty_findings:
            risks.append(finding)

        # 10. 形式审查（增强）
        form_pass = self._check_formality(blocks)
        checks.append(
            {
                "dimension": "形式审查（增强）",
                "result": "通过" if form_pass else "警告",
                "detail": "章节完整、格式规范" if form_pass else "存在格式/结构问题",
            }
        )
        if not form_pass:
            risks.append(
                {
                    "severity": "low",
                    "impact": "补正风险",
                    "evidence_or_reason": "章节不完整或格式不规范",
                    "fix_suggestion": "检查各分块字数、章节标题、附图说明格式",
                }
            )

        # 11. 术语/表达核查（来自核查清单）
        terminology_pass, terminology_findings = self._check_terminology_expression(blocks)
        checks.append(
            {
                "dimension": "术语/表达核查（核查清单增强）",
                "result": "通过" if terminology_pass else "警告",
                "detail": "术语定义、禁用词、缩写/英文表达基本合规" if terminology_pass else "存在术语/表达层面的校对问题",
            }
        )
        for finding in terminology_findings:
            risks.append(finding)

        # 12. 说明书内容核查（来自核查清单）
        spec_pass, spec_findings = self._check_spec_content(blocks)
        checks.append(
            {
                "dimension": "说明书内容核查（核查清单增强）",
                "result": "通过" if spec_pass else "警告",
                "detail": "背景技术、技术效果对应关系、实施例支撑基本合规" if spec_pass else "存在说明书内容层面的校对问题",
            }
        )
        for finding in spec_findings:
            risks.append(finding)

        # 13. 附图一致性核查（来自核查清单）
        figure_pass, figure_findings = self._check_figures_against_checklist(blocks)
        checks.append(
            {
                "dimension": "附图一致性核查（核查清单增强）",
                "result": "通过" if figure_pass else "警告",
                "detail": "附图类型、图文对应、图号引用基本合规" if figure_pass else "存在附图表达或图文对应问题",
            }
        )
        for finding in figure_findings:
            risks.append(finding)

        # 14. AI 浓度检测（增强）
        ai_risk = self._check_ai_concentration(all_text)
        checks.append(
            {
                "dimension": "AI 浓度检测（增强）",
                "result": "通过" if ai_risk == "low" else "警告",
                "detail": f"AI 生成痕迹风险: {ai_risk}",
            }
        )
        if ai_risk != "low":
            risks.append(
                {
                    "severity": "low",
                    "impact": "审查员主观印象",
                    "evidence_or_reason": "检测到排比句、过度工整结构等 AI 痕迹",
                    "fix_suggestion": "改为连贯段落叙述，避免列表式、结构化表达",
                }
            )

        # 15. 步骤编号引用一致性检查
        step_ref_pass, step_ref_findings = self._check_step_reference(blocks)
        checks.append(
            {
                "dimension": "步骤编号引用一致性",
                "result": "通过" if step_ref_pass else "警告",
                "detail": "步骤编号在技术方案、附图说明、具体实施方式中一致引用" if step_ref_pass else "步骤编号引用存在不一致或缺失",
            }
        )
        for finding in step_ref_findings:
            risks.append(finding)

        # 16. 结构规范检查
        structure_pass, structure_findings = self._check_structure_compliance(blocks)
        checks.append(
            {
                "dimension": "结构规范检查",
                "result": "通过" if structure_pass else "警告",
                "detail": "章节顺序、附图标题、权利要求书合规" if structure_pass else "存在结构规范问题",
            }
        )
        for finding in structure_findings:
            risks.append(finding)

        # 17. 领域语义与模板硬门禁
        semantic_pass, semantic_findings = self._check_domain_semantics(blocks, domain_scope)
        checks.append(
            {
                "dimension": "领域语义与模板一致性",
                "result": "通过" if semantic_pass else "驳回风险",
                "detail": "正文聚焦 {} 且符合交底书模板".format(domain_scope) if semantic_pass else "正文混入工作流内容或偏离模板/技术领域",
            }
        )
        for finding in semantic_findings:
            risks.append(finding)

        # ── 评分 ──────────────────────────────
        novelty_score = 25 if novelty_pass else 15
        inventiveness_score = 25 if inventiveness_pass else 15
        practicality_score = 25 if practicality_pass else 20
        clarity_score = 25 if sufficiency_pass and support_pass else 15

        checklist_penalty = min(20, sum(1 for r in risks if r["severity"] == "high") * 4 + sum(1 for r in risks if r["severity"] == "medium") * 2)
        overall_score = max(0, novelty_score + inventiveness_score + practicality_score + clarity_score - checklist_penalty)
        passed = overall_score >= 70 and semantic_pass and not any(r["severity"] == "high" for r in risks)

        # ── 产出审查报告 ──────────────────────
        report = self._build_report(
            patent_title, checks, risks, overall_score,
            novelty_score, inventiveness_score, practicality_score, clarity_score,
            passed
        )
        report_path = self.save_artifact(report, "artifacts/audit/phase_07_ipr_review_report.md")

        # ── 更新 manifest ─────────────────────
        manifest_updates = {
            "ipr_review_score": overall_score,
            "ipr_review_passed": passed,
            "top_risks": [
                {
                    "risk": r.get("impact", r.get("evidence_or_reason", "")),
                    "severity": r.get("severity", "medium"),
                    "evidence": r.get("evidence_or_reason", r.get("finding", "")),
                    "fix": r.get("fix_suggestion", r.get("suggestion", "")),
                }
                for r in risks[:5]
            ],
        }

        status = "success" if passed else "partial"
        degraded_reason = None if passed else f"IPR 审查得分 {overall_score}/100，低于阈值 70"

        return ExecutorResult(
            status=status,
            artifacts=[str(report_path)],
            manifest_updates=manifest_updates,
            trace_log=self.trace,
            degraded_reason=degraded_reason,
        )

    # ── 审查子方法 ──────────────────────────
    def _load_evidence_pack(self) -> Dict[str, Any]:
        """读取 Phase 2 内部专利复核证据包，用于 IPR 证据基础核查。"""
        candidates = [
            self.workspace / "artifacts" / "prior_art" / "phase_02_evidence_pack.json",
            self.workspace / "artifacts" / "prior_art" / "phase_04_evidence_pack.json",
        ]
        for path in candidates:
            if not path.exists():
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    pack = json.load(f)
                return pack if isinstance(pack, dict) else {}
            except Exception as e:
                self._log("evidence_pack_load_error", {"path": str(path), "error": str(e)})
        return {}

    def _check_tech_solution(self, blocks: Dict[str, str]) -> bool:
        """检查是否属于技术方案（三要素：技术问题、技术手段、技术效果）。"""
        part03 = blocks.get("part_03_发明内容.md", "")
        has_problem = "要解决的技术问题" in part03 or "技术问题" in part03
        has_solution = "技术方案" in part03
        has_effect = "有益效果" in part03 or "效果" in part03
        return has_problem and has_solution and has_effect

    def _check_novelty(self, blocks: Dict[str, str], evidence_pack: Dict[str, Any]) -> Tuple[bool, List[Dict]]:
        """新颖性审查：识别区别技术特征，对比现有技术，排除照搬摘录。"""
        part02 = blocks.get("part_02_背景技术.md", "")
        part03 = blocks.get("part_03_发明内容.md", "")
        findings = []

        # 1. 提取声称的区别特征
        distinction_section = part03
        # 从 S101-S105 步骤中提取技术特征
        step_features = re.findall(r'S\d{3}[，,]\s*(.+?)(?:[；;]|$)', part03)
        if not step_features:
            # fallback: extract from 技术方案 section
            solution_match = re.search(r'本申请.*?技术方案.*?\n(.*?)(?=\n##|\n###|\Z)', part03, re.DOTALL)
            if solution_match:
                step_features = [s.strip() for s in solution_match.group(1).split('\n') if s.strip() and len(s) > 15]

        # 2. 从 evidence_pack 提取现有技术的技术特征
        prior_features = []
        for item in evidence_pack.get("evidence", []):
            if not isinstance(item, dict):
                continue
            abstract = item.get("abstract", "")
            if abstract:
                # 提取摘要中的关键动作/组件
                prior_features.extend(re.findall(r'(?:通过|采用|利用|基于|包括|设有)([^，。,.;；]{10,40})', abstract))

        if not prior_features:
            findings.append({
                "severity": "low",
                "check_point": "现有技术特征库",
                "finding": "未从 evidence_pack 提取到可对比的现有技术特征，新颖性判断缺少参照基准",
                "suggestion": "确保证据包包含完整的专利摘要"
            })

        # 3. 检查正文是否照搬了证据摘录
        copied = False
        for item in evidence_pack.get("evidence", []):
            if not isinstance(item, dict):
                continue
            excerpt = item.get("excerpt", "").strip()
            if excerpt and len(excerpt) >= 30 and excerpt in part03:
                copied = True
                findings.append({
                    "severity": "high",
                    "check_point": "摘录照搬检测",
                    "finding": f"正文中照搬了证据 {item.get('evidence_id', '?')} 的摘录内容，涉嫌新颖性缺陷",
                    "suggestion": "用自己的语言重写对现有技术的引用，引用后必须指出区别"
                })

        # 4. 检查是否明确描述了与现有技术的区别
        distinction_keywords = ["区别", "不同", "改进", "解决", "相较", "不同于", "进一步限定", "而本", "本申请"]
        has_explicit_distinction = sum(1 for kw in distinction_keywords if kw in part03)
        if has_explicit_distinction < 2:
            findings.append({
                "severity": "high",
                "check_point": "区别特征表述",
                "finding": f"发明内容中仅 {has_explicit_distinction} 处提及与现有技术的区别，应在多个维度明确区别",
                "suggestion": "在技术问题、技术方案、有益效果各节均需体现与最接近现有技术的区别"
            })

        # 5. 构建区别特征列表
        distinct_features = []
        for sf in step_features[:5]:
            # 检查是否在现有技术中出现
            appears_in_prior = any(
                any(term in pf for term in sf.replace(' ', '')[:10])
                for pf in prior_features
            )
            if not appears_in_prior and len(sf) > 10:
                distinct_features.append(sf[:60])

        if distinct_features:
            findings.append({
                "severity": "info",
                "check_point": "潜在区别特征",
                "finding": f"识别到 {len(distinct_features)} 个潜在区别特征: " + "; ".join(distinct_features[:3]),
                "suggestion": "确保这些特征在技术效果部分体现其带来的技术贡献"
            })

        passed = not copied and not any(f["severity"] == "high" for f in findings)
        return passed, findings

    def _check_inventiveness(self, blocks: Dict[str, str]) -> Tuple[bool, List[Dict]]:
        """创造性审查：三步法分析 + 技术效果评估 + 组合发明判断。"""
        part03 = blocks.get("part_03_发明内容.md", "")
        part05 = blocks.get("part_05_具体实施方式.md", "")
        findings = []

        # 1. 三步法第一步：确定最接近的现有技术
        # 在发明内容和背景技术中搜索专利引用
        part02 = blocks.get("part_02_背景技术.md", "")
        prior_art_refs = re.findall(r'(CN\d{6,}[A-Z]?).*?(?:公开了|提出了|涉及)(.{10,80})', part03 + part02)
        if not prior_art_refs:
            findings.append({
                "severity": "medium",
                "check_point": "最接近现有技术（三步法·第一步）",
                "finding": "未明确指定最接近的现有技术及其公开内容",
                "suggestion": "在发明内容或背景技术中明确指出最接近的现有技术及其技术方案"
            })

        # 2. 三步法第二、三步：区别特征 → 实际解决的技术问题 → 是否显而易见
        all_text = part03 + part05
        # 检查技术效果描述
        effect_markers = ["提高", "降低", "减少", "增强", "改善", "优化", "避免", "消除", "实现", "达到"]
        effect_count = sum(1 for m in effect_markers if m in part03)
        if effect_count < 3:
            findings.append({
                "severity": "medium",
                "check_point": "技术效果（三步法·第三步）",
                "finding": f"技术效果描述不足（仅 {effect_count} 处），难以评估非显而易见性",
                "suggestion": "增加定量或定性的技术效果描述，说明区别特征带来的意外技术效果"
            })

        # 3. 检查协同效应（组合发明创造性判断）
        synergy_indicators = re.findall(
            r'(?:协同|耦合|联动|集成|融合|组合|联合|共同|相互)(.{5,30})',
            all_text
        )
        has_synergy_desc = any(len(s.strip()) > 5 for s in synergy_indicators)
        if not has_synergy_desc:
            findings.append({
                "severity": "medium",
                "check_point": "组合协同效应",
                "finding": "未描述各技术特征之间的协同作用或组合效果",
                "suggestion": "说明各特征之间如何协同工作产生 1+1>2 的技术效果，这是组合发明创造性的关键"
            })

        # 4. 检查是否仅为"简单叠加"
        all_modules = re.findall(r'(?:模块|单元|层|器|总线|Agent)', all_text)
        unique_modules = len(set(all_modules))
        if unique_modules >= 3:
            # 多个模块组合，需要说明组合效果
            if not has_synergy_desc:
                findings.append({
                    "severity": "high",
                    "check_point": "组合发明可能仅被认定为简单叠加",
                    "finding": f"识别到 {unique_modules} 种不同模块，但缺少协同效果描述，审查员可能认定为各模块的简单组合",
                    "suggestion": "必须说明各模块之间的数据流、信号流或控制流如何产生整体技术效果"
                })

        passed = not any(f["severity"] == "high" for f in findings)
        return passed, findings

    def _check_practicality(self, blocks: Dict[str, str]) -> Tuple[bool, List[Dict]]:
        """实用性审查：可实施性、可再现性、产业可用性。"""
        part05 = blocks.get("part_05_具体实施方式.md", "")
        findings = []

        # 1. 检查是否有可执行的步骤序列
        steps = re.findall(r'S\d{3}', part05)
        if len(steps) < 3:
            findings.append({
                "severity": "high",
                "check_point": "可执行步骤",
                "finding": f"具体实施方式中仅 {len(steps)} 个明确步骤编号，读者无法按步骤实施",
                "suggestion": "至少提供 S101-S10N 的完整步骤序列，每步说明输入、处理和输出"
            })

        # 2. 检查硬件/软件实施路径
        hw_sw_markers = ["模块", "组件", "单元", "步骤", "流程", "设备", "装置", "程序", "接口", "数据", "指令"]
        hw_sw_count = sum(1 for m in hw_sw_markers if m in part05)
        if hw_sw_count < 2:
            findings.append({
                "severity": "medium",
                "check_point": "产业实施路径",
                "finding": f"具体实施方式缺少可据以实施的技术细节描述",
                "suggestion": "补充所属领域技术人员可据以实施的具体方式"
            })

        # 3. 检查是否存在不可实施的主张
        impossible_claims = ["零延迟", "绝对安全", "100%准确", "无限", "完全自动"]
        for claim in impossible_claims:
            if claim in part05:
                findings.append({
                    "severity": "high",
                    "check_point": "不可实施主张",
                    "finding": f"正文包含不可实现的绝对化表述: '{claim}'",
                    "suggestion": f"将 '{claim}' 替换为可度量的技术指标或范围"
                })

        passed = not any(f["severity"] == "high" for f in findings)
        return passed, findings

    def _check_sufficiency(self, blocks: Dict[str, str]) -> Tuple[bool, List[Dict]]:
        """说明书充分公开审查：所属技术领域的技术人员能够实现。"""
        part05 = blocks.get("part_05_具体实施方式.md", "")
        part03 = blocks.get("part_03_发明内容.md", "")
        findings = []

        # 1. 检查关键参数是否公开
        key_params = re.findall(r'(?:范围|阈值|等级|区间|精度|分辨率|频率|速率)', part05)
        if len(key_params) < 2:
            findings.append({
                "severity": "medium",
                "check_point": "关键参数公开",
                "finding": "具体实施方式中缺少关键参数（范围、阈值等），本领域技术人员无法确定实施边界",
                "suggestion": "以范围或示例值的形式公开关键参数，并说明参数选取依据"
            })

        # 2. 检查是否有至少一个完整实施例
        if len(part05) < 800:
            findings.append({
                "severity": "high",
                "check_point": "实施例完整度",
                "finding": f"具体实施方式仅 {len(part05)} 字符，不足以构成一个完整的实施例",
                "suggestion": "最少提供 2000+ 字符的实施方式，涵盖系统架构、方法流程、信号交互和效果验证"
            })

        # 3. 检查技术方案是否在实施例中有对应展开
        steps_in_claim = re.findall(r'S\d{3}', part03)
        steps_in_impl = set(re.findall(r'S\d{3}', part05))
        missing_steps = [s for s in steps_in_claim if s not in steps_in_impl]
        if missing_steps:
            findings.append({
                "severity": "high",
                "check_point": "权利要求-实施例对应",
                "finding": f"发明内容中的步骤 {', '.join(missing_steps)} 在具体实施方式中未展开说明",
                "suggestion": f"在 part_05 中为每个步骤编号添加展开段落，使用'**S10X步骤**，具体如下：'句式"
            })

        passed = not any(f["severity"] == "high" for f in findings)
        return passed, findings

    def _check_support(self, blocks: Dict[str, str]) -> Tuple[bool, List[Dict]]:
        """权利要求支持审查：每一项技术特征在说明书中均有依据。"""
        part03 = blocks.get("part_03_发明内容.md", "")
        part05 = blocks.get("part_05_具体实施方式.md", "")
        all_text = part03 + "\n" + part05
        findings = []

        # 1. 提取声称的技术特征（模块/步骤）
        tech_features_raw = re.findall(r'(?:所述)?(\w{2,6}(?:模块|单元|层|器|总线|Agent|装置))', all_text)
        # 去重
        tech_features = list(dict.fromkeys(tf for tf in tech_features_raw if len(tf) > 3))

        if not tech_features:
            findings.append({
                "severity": "low",
                "check_point": "技术特征识别",
                "finding": "未识别到明确的模块/单元/装置命名"
            })
            return True, findings

        # 2. 对每个特征检查是否有定义或描述
        undefined = []
        poorly_defined = []
        for tf in tech_features[:10]:
            # 在上下文中查找该特征的定义
            idx = all_text.find(tf)
            if idx < 0:
                undefined.append(tf)
                continue
            context = all_text[max(0, idx - 30):idx + len(tf) + 80]
            definition_markers = ["用于", "配置为", "设置为", "包括", "连接", "实现", "负责"]
            has_definition = any(m in context for m in definition_markers)
            if not has_definition:
                poorly_defined.append(tf)

        if undefined:
            findings.append({
                "severity": "high",
                "check_point": "技术特征定义缺失",
                "finding": f"以下特征未找到定义: {', '.join(undefined)}",
                "suggestion": "每个模块/单元首次出现时须以'用于...'句式说明其功能"
            })
        if poorly_defined:
            findings.append({
                "severity": "medium",
                "check_point": "技术特征定义不足",
                "finding": f"以下特征缺少功能描述: {', '.join(poorly_defined[:5])}",
                "suggestion": "添加功能定义，关联其输入输出"
            })

        passed = not undefined
        return passed, findings

    def _check_unity(self, blocks: Dict[str, str]) -> Tuple[bool, List[Dict]]:
        """单一性审查：是否围绕同一发明构思。"""
        part03 = blocks.get("part_03_发明内容.md", "")
        part05 = blocks.get("part_05_具体实施方式.md", "")
        findings = []

        # 1. 提取核心问题
        problems = re.findall(r'(?:解决|针对|面对|克服|避免)(.{10,50})(?:问题|缺陷|不足|困难)', part03)
        if len(problems) == 0:
            findings.append({
                "severity": "low",
                "check_point": "技术问题",
                "finding": "未明确陈述要解决的技术问题"
            })
        elif len(problems) > 2:
            findings.append({
                "severity": "medium",
                "check_point": "技术问题数量",
                "finding": f"声称解决 {len(problems)} 个技术问题，可能存在多个独立发明",
                "suggestion": "确保所有问题围绕一个共同的技术构思（如跨域协同安全增强），否则应分案"
            })

        # 2. 检查是否有独立的技术方案分支
        branch_markers = ["另一实施例", "第二实施方式", "替代方案", "独立的"]
        merged_text = part03 + part05
        branches = [m for m in branch_markers if m in merged_text]
        if branches:
            findings.append({
                "severity": "low",
                "check_point": "实施例分支",
                "finding": f"检测到 {len(branches)} 个实施例分支表述，需确认是否属于同一发明构思",
                "suggestion": "如为替代实施方式而非独立发明，用'可选地'或'进一步地'表述"
            })

        passed = len(problems) <= 2
        return passed, findings

    def _check_amendment_basis(self, blocks: Dict[str, str]) -> Tuple[bool, List[Dict]]:
        """修改超范围审查：权利要求不超出原始公开范围。"""
        # 此检查针对代理人可能的过度扩展，在交底书阶段主要检查是否有明显无依据的扩展
        all_text = "\n".join(blocks.values())
        findings = []

        risky_labels = [
            ("绝对化扩展", "任意组合"), ("无限扩展", "不限于任何"),
            ("新增未描述特征", "新增特征"), ("范围覆盖过度", "所有可能"),
        ]
        for label, marker in risky_labels:
            if marker in all_text:
                findings.append({
                    "severity": "low",
                    "check_point": label,
                    "finding": f"正文包含 '{marker}' 表述，可能在审查中被质疑超范围",
                    "suggestion": "将宽泛表述替换为具体的技术范围或已有实施例支持的概括"
                })

        # 检查有益效果是否超出实施例描述
        effects = re.findall(r'(?:能够|可以|实现|达到|具有)(.{10,40})(?:效果|优点|益处|作用)', all_text)
        unsupported_effects = []
        for eff in effects:
            # 简单检查：效果描述对应的技术特征是否在实施例中出现
            keywords = re.findall(r'[\u4e00-\u9fff]{3,8}', eff)
            if keywords and not any(kw in all_text[:all_text.find(eff)] for kw in keywords if len(kw) > 3):
                unsupported_effects.append(eff[:30])

        if len(unsupported_effects) > 2:
            findings.append({
                "severity": "medium",
                "check_point": "效果-实施例对应",
                "finding": "部分技术效果可能缺少实施例支撑",
                "suggestion": "确保每个声明的技术效果在具体实施方式中有对应的实现描述"
            })

        passed = not findings
        return passed, findings

    def _check_honesty(self, blocks: Dict[str, str], evidence_pack: Dict[str, Any]) -> Tuple[bool, List[Dict[str, Any]]]:
        """诚实信用审查：证据可追溯 + 专利号一致性 + 无虚假数据。"""
        findings: List[Dict[str, Any]] = []
        all_text = "\n".join(blocks.values())
        evidence_items = [item for item in evidence_pack.get("evidence", []) if isinstance(item, dict)]

        if not evidence_pack or not evidence_items:
            findings.append({
                "severity": "medium",
                "check_point": "证据基础",
                "finding": "未找到 phase_02_evidence_pack.json 或证据为空，无法复核背景专利来源",
                "suggestion": "先完成 Phase 2 内部专利复核，确保每个引用专利有对应的 evidence 记录"
            })
            return False, findings

        # 1. 检查证据 URL 可信性
        trusted_domains = ["patents.google.com", "worldwide.espacenet.com", "patentscope.wipo.int", "cnipa.gov.cn", "epub.cnipa.gov.cn"]
        for item in evidence_items:
            evidence_id = item.get("evidence_id", "?")
            url = item.get("url", "")
            verification_source = item.get("verification_source", "")
            # 优先检查 CNIPA 验证来源
            if "CNIPA" in verification_source or "cnipa" in verification_source.lower():
                continue  # CNIPA verified, OK
            if not url:
                findings.append({
                    "severity": "high",
                    "check_point": "证据URL缺失",
                    "finding": f"证据 {evidence_id} 缺少 URL，无法追溯",
                    "suggestion": "每个专利证据必须包含可访问的 URL"
                })
            elif not any(domain in url for domain in trusted_domains):
                findings.append({
                    "severity": "medium",
                    "check_point": "证据来源可信度",
                    "finding": f"证据 {evidence_id} 的 URL ({url[:50]}...) 不在可信专利源列表中",
                    "suggestion": "专利证据应使用 Google Patents、CNIPA、Espacenet 或 WIPO 等可信源"
                })

        # 2. 检查正文引用的专利号是否在 evidence_pack 中有记录
        cited_patents = set(re.findall(r'CN\d{6,}[A-Z]?', all_text))
        recorded_patents = set()
        for item in evidence_items:
            pn = re.search(r'CN\d{6,}[A-Z]?', json.dumps(item, ensure_ascii=False))
            if pn:
                recorded_patents.add(pn.group(0))

        for cp in cited_patents:
            if cp not in recorded_patents:
                findings.append({
                    "severity": "high",
                    "check_point": "专利号一致性",
                    "finding": f"正文引用了 {cp}，但该专利号未出现在 evidence_pack 中",
                    "suggestion": f"将 {cp} 加入 evidence_pack 并补充摘要和 URL，或在正文中移除无证据支撑的引用"
                })

        # 3. 检查是否有虚假/不可验证的数据
        fake_patterns = [
            (r'(?:性能提升|效率提高|准确率|识别率)\s*(?:达到|超过|高达)\s*\d{2,3}%', "量化性能声明"),
            (r'(?:实测|实验|测试)\s*(?:表明|显示|证明|结果)', "实验数据声称"),
        ]
        for pattern, label in fake_patterns:
            matches = re.findall(pattern, all_text)
            if matches:
                findings.append({
                    "severity": "low",
                    "check_point": f"{label}可验证性",
                    "finding": f"正文包含 {len(matches)} 处{label}，交底书可保留但正式申请时应附实验数据或移除",
                    "suggestion": "标注为'预期效果'或'模拟结果'，避免在正式申请中做出无实验支撑的断言"
                })

        passed = not any(f["severity"] == "high" for f in findings)
        return passed, findings

    def _extract_patent_number(self, item: Dict[str, Any]) -> str:
        for value in [item.get("publicationNumber", ""), item.get("url", ""), item.get("excerpt", ""), item.get("title", "")]:
            match = re.search(r"CN\s?\d{5,}[A-Z]?", value or "", re.IGNORECASE)
            if match:
                return match.group(0).replace(" ", "").upper()
        return ""

    def _check_formality(self, blocks: Dict[str, str]) -> bool:
        """形式审查：章节完整性。"""
        required_sections = [
            "part_01_技术领域.md",
            "part_02_背景技术.md",
            "part_03_发明内容.md",
            "part_04_附图说明.md",
            "part_05_具体实施方式.md",
        ]
        for sec in required_sections:
            p = self.workspace / sec
            if not p.exists() or len(p.read_text(encoding="utf-8")) < 50:
                return False
        return True

    def _check_terminology_expression(self, blocks: Dict[str, str]) -> Tuple[bool, List[Dict[str, Any]]]:
        """核查清单：术语/表达层面检查。"""
        text = "\n".join(blocks.values())
        findings: List[Dict[str, Any]] = []

        promo_words = ["第一", "唯一", "领先", "顶级", "最佳", "革命性"]
        hit_promo = [w for w in promo_words if w in text]
        if hit_promo:
            findings.append({
                "severity": "medium",
                "impact": "商业宣传化表述风险",
                "evidence_or_reason": f"检测到宣传性表述: {', '.join(hit_promo[:5])}",
                "fix_suggestion": "改为客观技术描述，避免广告化和价值判断措辞",
            })

        vague_words = ["约", "大约", "高温", "低温", "较高", "较低", "适当", "等等"]
        hit_vague = [w for w in vague_words if w in text]
        if len(hit_vague) >= 2:
            findings.append({
                "severity": "medium",
                "impact": "术语含义不确定",
                "evidence_or_reason": f"检测到含义不确定用语: {', '.join(hit_vague[:6])}",
                "fix_suggestion": "将模糊表述替换为可测量、可限定或有上下文边界的技术表述",
            })

        model_or_brand = re.findall(r"(?:[A-Z]{2,}[\-\dA-Za-z]*|[A-Za-z]+\d+)", text)
        if len(model_or_brand) >= 3:
            findings.append({
                "severity": "low",
                "impact": "商品名/型号/英文直出风险",
                "evidence_or_reason": f"检测到可能的英文型号或缩写: {', '.join(model_or_brand[:6])}",
                "fix_suggestion": "英文术语补充中文对应、缩写补充全文及释义，必要时改为通用技术名称",
            })

        abbreviations = re.findall(r"\b([A-Z]{2,})\b", text)
        undefined_abbr = [abbr for abbr in abbreviations if f"（{abbr}）" not in text and f"({abbr})" not in text]
        if undefined_abbr:
            findings.append({
                "severity": "low",
                "impact": "缩写未释义",
                "evidence_or_reason": f"检测到未明显释义的缩写: {', '.join(sorted(set(undefined_abbr))[:6])}",
                "fix_suggestion": "首次出现时补充中文全称/英文全文及释义",
            })

        return len(findings) == 0, findings

    def _check_spec_content(self, blocks: Dict[str, str]) -> Tuple[bool, List[Dict[str, Any]]]:
        """核查清单：说明书内容层面检查。"""
        findings: List[Dict[str, Any]] = []
        part02 = blocks.get("part_02_背景技术.md", "")
        part03 = blocks.get("part_03_发明内容.md", "")
        part05 = blocks.get("part_05_具体实施方式.md", "")

        innovation_markers = ["本发明提出", "本发明提供", "本方案通过", "本发明的优点"]
        if any(marker in part02 for marker in innovation_markers):
            findings.append({
                "severity": "high",
                "impact": "背景技术夹带发明点",
                "evidence_or_reason": "背景技术部分出现本发明/本方案式表述，可能混入发明点或技术启示",
                "fix_suggestion": "背景技术仅描述现有技术及其客观缺陷，不写本发明方案和效果",
            })

        if "有益效果" in part03 and not re.search(r"(对应|由于|通过|从而|因此)", part03):
            findings.append({
                "severity": "medium",
                "impact": "技术效果与技术特征对应关系不足",
                "evidence_or_reason": "发明内容写了效果，但未明显说明由哪些技术特征导致",
                "fix_suggestion": "按'技术特征→作用机理→技术效果'补充因果链",
            })

        if len(part05) < 800:
            findings.append({
                "severity": "medium",
                "impact": "实施例支撑不足",
                "evidence_or_reason": "具体实施方式篇幅偏短，可能不足以支撑上位概括或充分公开",
                "fix_suggestion": "增加至少两个有差异化的实施例，补充分步骤、模块交互和参数边界",
            })

        algo_keywords = ["模型", "训练", "推理", "特征向量", "损失函数", "神经网络", "算法"]
        if any(k in part03 + part05 for k in algo_keywords):
            if not re.search(r"(数据.*含义|技术含义|物理含义|业务含义|传感器|控制信号|设备状态)", part03 + part05):
                findings.append({
                    "severity": "medium",
                    "impact": "算法数据技术含义不清",
                    "evidence_or_reason": "涉及算法/模型描述，但未清楚交代输入输出数据在技术场景中的确切含义",
                    "fix_suggestion": "补充数据来源、物理/业务含义、处理后的控制对象及对系统性能的影响",
                })

        return len(findings) == 0, findings

    def _check_figures_against_checklist(self, blocks: Dict[str, str]) -> Tuple[bool, List[Dict[str, Any]]]:
        """核查清单：附图和图文对应检查。"""
        findings: List[Dict[str, Any]] = []
        part04 = blocks.get("part_04_附图说明.md", "")
        all_text = "\n".join(blocks.values())

        method_markers = ["步骤", "流程", "方法", "执行", "获取", "判断", "生成"]
        if sum(1 for k in method_markers if k in all_text) >= 3:
            if not re.search(r"流程图|时序图|步骤图|图1", part04):
                findings.append({
                    "severity": "medium",
                    "impact": "方法类专利缺少流程步骤图",
                    "evidence_or_reason": "正文体现为方法/流程型方案，但附图说明未明确给出流程图或步骤图",
                    "fix_suggestion": "至少补充一张主流程图，必要时增加多端交互时序图",
                })

        fig_refs_in_text = set(re.findall(r"图\d+", all_text))
        fig_refs_in_part04 = set(re.findall(r"图\d+", part04))
        missing_in_part04 = sorted(fig_refs_in_text - fig_refs_in_part04)
        if missing_in_part04:
            findings.append({
                "severity": "medium",
                "impact": "图文不对应",
                "evidence_or_reason": f"正文引用但附图说明未覆盖: {', '.join(missing_in_part04[:6])}",
                "fix_suggestion": "补齐附图说明中的对应图号、图名和简要说明",
            })

        figure_ids = sorted(set(re.findall(r"图\s*(\d+)", part04)))
        if len(figure_ids) < 4:
            findings.append({
                "severity": "high",
                "impact": "附图支撑不足",
                "evidence_or_reason": f"附图说明仅覆盖 {len(figure_ids)} 张图，难以支撑方法、系统、数据结构和追溯关系",
                "fix_suggestion": "至少补充系统架构图、方法流程图、证据记录结构图、追溯关系图 4 张图，并在每个图注后附 Mermaid 源码",
            })
        if part04.count("```mermaid") < 4:
            findings.append({
                "severity": "high",
                "impact": "附图源码缺失",
                "evidence_or_reason": "并非每个附图均附带 Mermaid/mmd 源码",
                "fix_suggestion": "每个图注后都附对应 Mermaid 源码，不另交付图片占位物",
            })

        if re.search(r"照片|截图|原始图片", part04):
            findings.append({
                "severity": "low",
                "impact": "附图表达不规范",
                "evidence_or_reason": "附图说明中出现原始图片/照片类表述",
                "fix_suggestion": "优先改为示意图、框图、流程图；必须保留时说明必要性",
            })

        return len(findings) == 0, findings

    def _check_ai_concentration(self, text: str) -> str:
        """AI 浓度检测。"""
        risk_score = 0
        if re.search(r"第一[，、]\s*第二[，、]\s*第三", text):
            risk_score += 2
        if text.count("所述") > 20:
            risk_score += 1
        list_items = len(re.findall(r"^\d+\.", text, re.MULTILINE))
        if list_items > 10:
            risk_score += 1
        if risk_score >= 3:
            return "high"
        elif risk_score >= 2:
            return "medium"
        return "low"

    def _check_step_reference(self, blocks: Dict[str, str]) -> Tuple[bool, List[Dict[str, Any]]]:
        """检查步骤编号 S101-S10x 的引用一致性。"""
        findings: List[Dict[str, Any]] = []
        part03 = blocks.get("part_03_发明内容.md", "")
        part04 = blocks.get("part_04_附图说明.md", "")
        part05 = blocks.get("part_05_具体实施方式.md", "")

        # 从具体实施方式中提取步骤号
        step_ids = re.findall(r"S\d{3}", part05)
        unique_steps = sorted(set(step_ids))

        if not unique_steps:
            return True, findings

        # 检查技术方案中是否有所有步骤号
        for sid in unique_steps:
            if sid not in part03:
                findings.append({
                    "severity": "medium",
                    "impact": "步骤编号引用不一致",
                    "evidence_or_reason": f"步骤编号 '{sid}' 在具体实施方式中出现，但在技术方案（B2）中未引用",
                    "fix_suggestion": f"在技术方案 B2 中加入 '{sid}' 的步骤描述，确保与技术方案一致",
                })

        # 检查附图说明中是否提及步骤范围
        if part04 and "图2" in part04:
            has_any_step = any(sid in part04 for sid in unique_steps)
            if not has_any_step:
                findings.append({
                    "severity": "low",
                    "impact": "附图说明未覆盖步骤编号",
                    "evidence_or_reason": "图2（方法流程图）说明中未提及任何步骤编号",
                    "fix_suggestion": f"在图2说明中写明'其中包括步骤{unique_steps[0]}至步骤{unique_steps[-1]}'",
                })

        return len(findings) == 0, findings

    def _check_structure_compliance(self, blocks: Dict[str, str]) -> Tuple[bool, List[Dict[str, Any]]]:
        """检查章节结构合规性。"""
        findings: List[Dict[str, Any]] = []
        all_text = "\n".join(blocks.values())

        # 1. 章节顺序检查
        expected_titles = [
            ("一、技术领域",),
            ("二、背景技术",),
            ("三、发明内容",),
            ("四、附图说明", "四、专利附图"),
            ("五、具体实施方式",),
        ]
        found_positions = []
        for titles in expected_titles:
            matches = [(title, all_text.find(title)) for title in titles if all_text.find(title) >= 0]
            if matches:
                title, pos = min(matches, key=lambda item: item[1])
                found_positions.append((title, pos))

        for i in range(1, len(found_positions)):
            if found_positions[i][1] < found_positions[i - 1][1]:
                findings.append({
                    "severity": "medium",
                    "impact": "章节顺序不合规",
                    "evidence_or_reason": f"章节顺序异常: '{found_positions[i][0]}' 出现在 '{found_positions[i - 1][0]}' 之前",
                    "fix_suggestion": "按固定顺序排列：技术领域→背景技术→发明内容→专利附图→具体实施方式",
                })

        # 2. 检查是否存在"权利要求书"
        if "权利要求书" in all_text:
            findings.append({
                "severity": "medium",
                "impact": "包含权利要求书",
                "evidence_or_reason": "交底书中包含'权利要求书'，应由专利代理师撰写",
                "fix_suggestion": "删除交底书中的权利要求书部分",
            })

        # 3. 检查附图标题
        part04 = blocks.get("part_04_附图说明.md", "")
        if part04 and not ("四、附图说明" in part04 or "四、专利附图" in part04):
            findings.append({
                "severity": "low",
                "impact": "附图标题缺失",
                "evidence_or_reason": "附图章节缺少'四、附图说明'或'四、专利附图'标题",
                "fix_suggestion": "补充规范的附图章节标题",
            })

        return len(findings) == 0, findings

    def _check_domain_semantics(self, blocks: Dict[str, str], domain_scope: str = "") -> Tuple[bool, List[Dict[str, Any]]]:
        """核对交底书是否聚焦目标技术领域，并符合用户模板核心小节。"""
        all_text = "\n".join(blocks.values())
        findings: List[Dict[str, Any]] = []
        internal_terms = [
            "Phase 2", "Phase 3", "Phase 5", "Phase 6", "Phase 7", "Phase 8", "Phase 9",
            "research_pack", "patent_candidate_pool", "evidence_pack", "block_context",
            "shared_context", "facts_ledger", "figure_registry", "terminology_registry",
            "block_review", "evidence_id", "写作依据", "正文分块", "IPR 模拟审查",
            "最终交付健康检查", "专利正文的一致性审计", "分块审核",
        ]
        hits = [term for term in internal_terms if term in all_text]
        if hits:
            findings.append({
                "severity": "high",
                "impact": "技术方案主题偏移",
                "evidence_or_reason": "正文混入工作流内部术语: " + "、".join(hits[:8]),
                "fix_suggestion": f"删除工作流内部机制，重写为{domain_scope}方法及系统的技术特征。",
            })

        required_sections = {
            "part_02_背景技术.md": ["2.1 与本申请相关的现有技术背景知识", "2.2 与本申请相关的最接近的现有技术", "2.3 现有技术的缺陷和不足"],
            "part_03_发明内容.md": ["3.1 本申请所需要解决的技术问题", "3.2 本申请的技术方案", "3.3 本申请的技术效果"],
        }
        for filename, headings in required_sections.items():
            content = blocks.get(filename, "")
            missing = [heading for heading in headings if heading not in content]
            if missing:
                findings.append({
                    "severity": "high",
                    "impact": "交底书模板不合规",
                    "evidence_or_reason": f"{filename} 缺少模板小节: " + "、".join(missing),
                    "fix_suggestion": "按用户提供的技术交底书框架补齐小节。",
                })

        figure_text = blocks.get("part_04_附图说明.md", "")
        if any(term in figure_text for term in ["读取研究资料", "生成分块上下文", "分块撰写", "分块审核"]):
            findings.append({
                "severity": "high",
                "impact": "附图技术内容错误",
                "evidence_or_reason": f"附图描述写作工作流而非{domain_scope}系统或方法。",
                "fix_suggestion": "重画系统架构图和方法流程图，内容应为采集、标准化、融合、结论生成和追溯。",
            })

        part02 = blocks.get("part_02_背景技术.md", "")
        domain_generic_phrases = [
            "与{}或智能检测相关的方案".format(domain_scope[:4]),
            "可以对{}对象或检测信息进行识别、采集或辅助判断".format(domain_scope[:4])
        ]
        if any(phrase in part02 for phrase in domain_generic_phrases):
            findings.append({
                "severity": "high",
                "impact": "背景技术事实不充分",
                "evidence_or_reason": "背景专利描述仍是泛化占位，没有说明具体 CN 专利公开内容和局限",
                "fix_suggestion": "按现有专利实际公开内容重写背景技术，保留 1-2 件最接近 CN 专利。",
            })

        # 从账本中动态读取领域术语
        _ledger = {}
        _ledger_path = self.workspace / "artifacts" / "draft" / "facts_ledger.json"
        if _ledger_path.exists():
            try:
                with open(_ledger_path, "r", encoding="utf-8") as f:
                    _ledger = json.load(f)
            except Exception:
                pass
        domain_terms = []
        for entry in _ledger.get("terminology", []):
            term = entry.get("term", "")
            if term:
                domain_terms.append(term)
        if not domain_terms:
            domain_terms = ["任务", "资源", "调度", "分解", "模块"]
        threshold = max(2, len(domain_terms) // 2)
        if sum(1 for term in domain_terms if term in all_text) < threshold:
            findings.append({
                "severity": "high",
                "impact": "技术领域偏移",
                "evidence_or_reason": f"领域关键术语覆盖不足（期望≥{threshold}个）。",
                "fix_suggestion": "围绕说明书中的核心技术术语重写正文，确保关键术语在相关章节中正确使用。",
            })
        return len(findings) == 0, findings

    def _build_report(
        self,
        title: str,
        checks: List[Dict],
        risks: List[Dict],
        overall: int,
        novelty: int,
        inventiveness: int,
        practicality: int,
        clarity: int,
        passed: bool,
    ) -> str:
        lines = [
            "# IPR 模拟审查报告（基于《专利审查指南》2023 + 核查清单校对规则）",
            "",
            f"- `ipr_review_report_path`: artifacts/audit/phase_07_ipr_review_report.md",
            f"- `patent_title`: {title}",
            "- `review_round`: 1",
            "- `review_input_path`: 各 part_*.md 分块文件",
            "- `review_scope`: 形式审查 + 实质审查（9 项法定 + 5 项增强，含核查清单校对规则）",
            "",
            "## 证据基础",
            "",
            "- `prior_art_refs`: 参见 phase_02 背景专利候选池",
            "- `prior_art_pack_ref`: artifacts/prior_art/phase_02_evidence_pack.json",
            "- `evidence_basis`: phase_02 内部专利复核结果 + phase_03 收敛方向",
            "- `evidence_granularity`: abstract_only",
            "",
            "## 法规依据与规则映射",
            "",
            "说明：本阶段不内置法规全文；仅保留条款标签、审查目标、实现函数和输入文件映射，用于可复现的 IPR 风险模拟。",
            "",
        ]
        for rule_id, rule in IPR_LEGAL_RULES.items():
            lines.append(f"- `{rule_id}`: {rule['law']} {rule['article']}｜{rule['topic']}｜实现 `{rule['implementation']}`")
        lines.extend([
            "",
            "## 法定审查项",
            "",
        ])
        for c in checks:
            icon = "✅" if c["result"] == "通过" else "🟡" if "警告" in c["result"] else "❌"
            lines.append(f"### {icon} {c['dimension']} — {c['result']}")
            if c.get("rule_id"):
                lines.append(f"- 规则 ID: `{c['rule_id']}`")
                lines.append(f"- 法规依据: {c['legal_basis']}")
                lines.append(f"- 核查目标: {c['check_goal']}")
                lines.append(f"- 实现函数: `{c['implementation']}`")
                lines.append(f"- 输入文件: {', '.join(c.get('input_files', []))}")
            lines.append(f"- 判断: {c['detail']}")
            lines.append("")

        lines.extend(
            [
                "## 评分（100 分制）",
                "",
                "> 评分目的：对'可授权性风险'做可读的量化表达，用于迭代优先级排序；不等同于真实审查结论。",
                "",
                "- `scoring_scale`: 0-100",
                f"- `overall_score`: {overall}",
                "",
                "### 分项评分（0-25）",
                "",
                f"- `novelty_score`: {novelty}  # 新颖性",
                f"- `inventiveness_score`: {inventiveness}  # 创造性",
                f"- `practicality_score`: {practicality}  # 实用性",
                f"- `clarity_score`: {clarity}  # 清楚性",
                "",
                "### 支持性风险",
                "",
            ]
        )
        if risks:
            for r in risks:
                lines.append(f"- `{r.get('impact', r.get('evidence_or_reason', '?'))}`: {r.get('severity', '?')} — {r.get('evidence_or_reason', r.get('finding', '?'))}")
        else:
            lines.append("- `support_risk`: low")

        lines.extend(
            [
                "",
                "## Top 风险点",
                "",
            ]
        )
        for i, r in enumerate(risks[:5], 1):
            lines.append(f"{i}. **{r.get('severity', '?').upper()}** | {r.get('impact', r.get('evidence_or_reason', r.get('finding', '?')))}")
            lines.append(f"   - 原因: {r.get('evidence_or_reason', r.get('finding', '?'))}")
            lines.append(f"   - 建议: {r.get('fix_suggestion', r.get('suggestion', '?'))}")
            lines.append("")

        lines.extend(
            [
                "## 结论",
                "",
                f"- `pass_threshold_suggested`: 70",
                f"- `pass_fail_suggested`: {'pass' if passed else 'fail'}",
                f"- pass_fail_suggested: {'pass' if passed else 'fail'}",
                f"- 综合评级: {'🟢 通过' if passed else '🟡 需修改后通过' if overall >= 50 else '🔴 驳回风险'}",
            ]
        )
        return "\n".join(lines)
