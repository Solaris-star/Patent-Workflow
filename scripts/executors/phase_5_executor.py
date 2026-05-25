#!/usr/bin/env python3
"""
Phase 5 Executor - 正文草稿撰写(分块撰写)。
读取 Phase 2/4 研究资料,为每个正文块生成干净上下文、草稿骨架和分块审核记录。
产出:
- part_01_技术领域.md ~ part_05_具体实施方式.md
- artifacts/draft/block_contexts/*.json
- artifacts/draft/block_reviews/*.json
- artifacts/draft/facts_ledger.json
- artifacts/draft/step_registry.json
- artifacts/draft/figure_registry.json
- artifacts/draft/terminology_registry.json
"""

import hashlib
import json
import re
import shutil
from typing import Any, Dict, List, Tuple

from executors.base_executor import BaseExecutor, ExecutorResult


DRAFT_BLOCKS = [
    {
        "id": "part_01",
        "name": "技术领域",
        "file": "part_01_技术领域.md",
        "min_words": 50,
        "max_words": 150,
        "target_min_chars": 50,
        "target_max_chars": 150,
        "length_reason": "技术领域只用于限定所属技术领域,避免展开应用场景清单。",
    },
    {
        "id": "part_02",
        "name": "背景技术",
        "file": "part_02_背景技术.md",
        "min_words": 500,
        "max_words": 900,
        "target_min_chars": 500,
        "target_max_chars": 900,
        "length_reason": "背景技术应结合 1-2 件最相关现有专利说明已有方案和不足,避免泛泛写行业问题。",
    },
    {
        "id": "part_03",
        "name": "发明内容",
        "file": "part_03_发明内容.md",
        "min_words": 800,
        "max_words": 1400,
        "target_min_chars": 800,
        "target_max_chars": 1400,
        "length_reason": "发明内容需要覆盖技术问题、技术方案和有益效果,不能只写功能口号。",
    },
    {
        "id": "part_04",
        "name": "附图说明",
        "file": "part_04_附图说明.md",
        "min_words": 30,
        "max_words": 120,
        "target_min_chars": 30,
        "target_max_chars": 120,
        "target_min_figures": 4,
        "requires_mmd_per_figure": True,
        "length_reason": "附图说明以图号、图题和 Mermaid/mmd 源码为主,自然语言只保留必要图注。",
    },
    {
        "id": "part_05",
        "name": "具体实施方式",
        "file": "part_05_具体实施方式.md",
        "min_words": 1800,
        "max_words": 3500,
        "target_min_chars": 1800,
        "target_max_chars": 3500,
        "length_reason": "具体实施方式是支撑发明内容和后续权利要求的核心部分,应详细展开步骤、模块和附图引用。",
    },
]

BLOCK_EVIDENCE_NEEDS = {
    "part_01": ["research"],
    "part_02": ["patent", "research"],
    "part_03": ["research", "patent"],
    "part_04": ["figure", "research"],
    "part_05": ["research", "figure"],
}


class PhaseExecutor(BaseExecutor):
    """阶段 5 执行器:正文草稿撰写。"""

    def _execute(self) -> ExecutorResult:
        print("   ✍️  执行正文草稿撰写准备...")

        domain_scope = self.manifest.get("domain_scope", "")
        if not domain_scope:
            self._log("missing_domain_scope", {"error": "manifest.domain_scope is empty"})
        selected_direction = self.manifest.get("selected_direction", "")

        template_ready, style_ready = self._check_template_and_style()
        research_inputs = self._load_research_inputs()
        redaction_policy = self._build_redaction_policy(research_inputs)
        redaction_path = self.save_artifact(redaction_policy, "artifacts/draft/redaction_policy.json") if redaction_policy.get("enabled") else None
        patent_title = self._resolve_patent_title(research_inputs)
        if not selected_direction:
            selected_direction = patent_title
        shared_context = self._build_shared_context(patent_title, domain_scope, selected_direction, research_inputs)
        shared_context_path = self.save_artifact(shared_context, "artifacts/draft/shared_context.json")
        writing_plan = self._build_writing_plan(patent_title, domain_scope, selected_direction, research_inputs, shared_context)
        plan_path = self.save_artifact(writing_plan, "artifacts/draft/phase_05_writing_plan.json")

        block_statuses: List[Dict[str, Any]] = []
        block_review_paths: List[str] = []
        block_context_paths: List[str] = []
        artifacts: List[str] = [str(shared_context_path), str(plan_path)]
        if redaction_path:
            artifacts.append(str(redaction_path))

        for block in DRAFT_BLOCKS:
            context = self._build_block_context(block, patent_title, domain_scope, selected_direction, research_inputs, shared_context)
            context_path = self.save_artifact(context, f"artifacts/draft/block_contexts/{block['id']}_context.json")
            block_context_paths.append(str(context_path))
            artifacts.append(str(context_path))

            block_path = self.run_dir / block["file"]
            created_from_context = False
            regenerated_reason = ""
            if block_path.exists():
                content = block_path.read_text(encoding="utf-8").strip()
                contamination = self._detect_content_contamination(block, content)
                if not contamination:
                    existing_review = self._review_block(block, content, context, shared_context)
                    contamination = self._regeneration_reasons_from_review(existing_review)
                if contamination:
                    self._backup_superseded_block(block_path, contamination)
                    content = self._make_skeleton(block, context)
                    self.save_artifact(content, block["file"])
                    created_from_context = True
                    regenerated_reason = contamination[0]
                    print(f"   ♻️ 已重生污染分块草稿: {block['file']} ({regenerated_reason})")
            else:
                content = self._make_skeleton(block, context)
                self.save_artifact(content, block["file"])
                created_from_context = True
                print(f"   📝 已创建分块草稿: {block['file']}")

            filtered_content = self._apply_redaction_filter(content, redaction_policy)
            if filtered_content != content:
                content = filtered_content
                self.save_artifact(content, block["file"])
                print(f"   🔒 已对分块草稿执行本地材料脱敏过滤: {block['file']}")

            review = self._review_block(block, content, context, shared_context)
            review_path = self.save_artifact(review, f"artifacts/draft/block_reviews/{block['id']}_review.json")
            block_review_paths.append(str(review_path))
            artifacts.extend([str(block_path), str(review_path)])

            length_status = review["length_check"]["length_status"]
            figure_structure_check = review.get("figure_structure_check", {})
            block_statuses.append(
                {
                    "block_id": block["id"],
                    "name": block["name"],
                    "file": block["file"],
                    "exists": block_path.exists(),
                    "char_count": review["char_count"],
                    "total_char_count": review.get("total_char_count", len(content)),
                    "word_count": review["char_count"],
                    "target_min_chars": block["target_min_chars"],
                    "target_max_chars": block["target_max_chars"],
                    "length_status": length_status,
                    "length_reason": block["length_reason"],
                    "figure_structure_check": figure_structure_check,
                    "figure_count": figure_structure_check.get("figure_count", 0),
                    "mmd_block_count": figure_structure_check.get("mmd_block_count", 0),
                    "figure_structure_passed": (
                        not figure_structure_check
                        or (
                            figure_structure_check.get("figure_count_passed") is True
                            and figure_structure_check.get("mmd_per_figure_passed") is True
                        )
                    ),
                    "has_min_content": length_status != "too_short",
                    "created_from_context": created_from_context,
                    "regenerated_reason": regenerated_reason,
                    "review_passed": review["passed"],
                    "review_path": str(review_path.relative_to(self.workspace)),
                    "context_path": str(context_path.relative_to(self.workspace)),
                }
            )

        facts_ledger = self._build_facts_ledger(patent_title, research_inputs, block_statuses, shared_context)
        self._ensure_figure_artifacts(facts_ledger.get("figure_registry", []))
        ledger_path = self.save_artifact(facts_ledger, "artifacts/draft/facts_ledger.json")
        step_reg_path = self.save_artifact(facts_ledger.get("step_registry", []), "artifacts/draft/step_registry.json")
        fig_reg_path = self.save_artifact(facts_ledger.get("figure_registry", []), "artifacts/draft/figure_registry.json")
        term_reg_path = self.save_artifact(facts_ledger.get("terminology", []), "artifacts/draft/terminology_registry.json")
        metadata_path = self.save_artifact(self._build_metadata(patent_title, block_statuses), "metadata.json")
        artifacts.extend([str(ledger_path), str(step_reg_path), str(fig_reg_path), str(term_reg_path), str(metadata_path)])

        blocks_completed = sum(1 for item in block_statuses if item["has_min_content"])
        reviews_passed = sum(1 for item in block_statuses if item["review_passed"])
        if blocks_completed == len(DRAFT_BLOCKS) and reviews_passed == len(DRAFT_BLOCKS):
            status = "success"
            draft_status = "completed"
            degraded_reason = None
        elif blocks_completed > 0:
            status = "partial"
            draft_status = "partial"
            degraded_reason = "部分分块内容或审核未通过"
        else:
            status = "degraded"
            draft_status = "skeleton"
            degraded_reason = "分块草稿为证据约束骨架,需 Agent 继续扩写"

        manifest_updates = {
            "draft_status": draft_status,
            "facts_ledger_ready": True,
            "step_registry_ready": True,
            "figure_registry_ready": True,
            "terminology_registry_ready": True,
            "style_profile_ready": style_ready,
            "template_rules_ready": template_ready,
            "research_inputs_ready": research_inputs["ready"],
            "shared_context_ready": True,
            "shared_context_path": "artifacts/draft/shared_context.json",
            "shared_context_within_budget": shared_context["budget"]["within_budget"],
            "phase_05_writing_plan_path": "artifacts/draft/phase_05_writing_plan.json",
            "redaction_filter_enabled": bool(redaction_policy.get("enabled")),
            "redaction_policy_path": "artifacts/draft/redaction_policy.json" if redaction_policy.get("enabled") else "",
            "block_contexts_ready": True,
            "block_reviews_ready": True,
            "block_statuses": block_statuses,
            "blocks_completed": blocks_completed,
            "blocks_total": len(DRAFT_BLOCKS),
            "block_reviews_passed": reviews_passed,
            "degraded_run": status != "success",
        }

        # 同步分块文件到工作区根目录，供 Phase 6-9 使用
        for block in DRAFT_BLOCKS:
            src = self.run_dir / block["file"]
            dst = self.workspace / block["file"]
            if src.exists() and src.resolve() != dst.resolve():
                shutil.copy2(src, dst)

        return ExecutorResult(
            status=status,
            artifacts=artifacts,
            manifest_updates=manifest_updates,
            trace_log=self.trace,
            degraded_reason=degraded_reason,
        )

    def _check_template_and_style(self) -> Tuple[bool, bool]:
        template_path = self.workspace / "template_rules.json"
        style_json_path = self.workspace / "style_profile.json"
        style_md_path = self.workspace / "style_profile.md"
        preprocess_index = self._load_preprocess_index()
        artifacts = preprocess_index.get("artifacts", {}) if isinstance(preprocess_index, dict) else {}

        if not template_path.exists() and artifacts.get("template_structure_rules"):
            template_path = self.workspace / artifacts["template_structure_rules"]
        if not style_json_path.exists() and artifacts.get("reference_style_profile"):
            style_json_path = self.workspace / artifacts["reference_style_profile"]

        template_ready = template_path.exists()
        style_ready = style_md_path.exists() or style_json_path.exists()
        if template_ready:
            self._log("template_found", {"path": str(template_path.relative_to(self.workspace)) if template_path.is_absolute() else str(template_path)})
        if style_ready:
            style_log_path = style_md_path if style_md_path.exists() else style_json_path
            self._log("style_found", {"path": str(style_log_path.relative_to(self.workspace)) if style_log_path.is_absolute() else str(style_log_path)})
        if not template_ready and not style_ready:
            print("   ⚠️ 未找到模板规则/风格画像,将使用默认规范")
        return template_ready, style_ready

    def _load_research_inputs(self) -> Dict[str, Any]:
        research_pack = self._load_json("artifacts/research/phase_02_research_pack.json", {})
        candidate_pool = self._load_json("artifacts/prior_art/phase_02_patent_candidate_pool.json", {}) or self._load_json("artifacts/prior_art/phase_04_patent_candidate_pool.json", {})
        evidence_pack = self._load_json("artifacts/prior_art/phase_02_evidence_pack.json", {}) or self._load_json("artifacts/prior_art/phase_04_evidence_pack.json", {})
        research_evidence = research_pack.get("evidence", []) if isinstance(research_pack, dict) else []
        patent_evidence = evidence_pack.get("evidence", []) if isinstance(evidence_pack, dict) else []
        final_patents = evidence_pack.get("final_relevant_patents", []) if isinstance(evidence_pack, dict) else []
        if not final_patents and isinstance(evidence_pack, dict):
            final_patents = [
                item for item in evidence_pack.get("peripheral_references", [])
                if isinstance(item, dict) and str(item.get("publicationNumber", "")).startswith("CN")
            ][:5]
        ready = bool(research_pack) or bool(evidence_pack) or bool(candidate_pool)
        source_reading_notes = []
        if isinstance(research_pack, dict):
            source_reading_notes.extend(research_pack.get("source_reading_notes", []))
        if isinstance(evidence_pack, dict):
            source_reading_notes.extend(evidence_pack.get("source_reading_notes", []))
        return {
            "ready": ready,
            "research_pack_path": "artifacts/research/phase_02_research_pack.json" if research_pack else "",
            "candidate_pool_path": "artifacts/prior_art/phase_02_patent_candidate_pool.json" if candidate_pool else "",
            "evidence_pack_path": "artifacts/prior_art/phase_02_evidence_pack.json" if evidence_pack else "",
            "recommended_direction": research_pack.get("recommended_direction_detail") or research_pack.get("recommended_direction") if isinstance(research_pack, dict) else "",
            "decision_basis": research_pack.get("decision_basis", {}) if isinstance(research_pack, dict) else {},
            "research_evidence": research_evidence,
            "patent_evidence": patent_evidence,
            "final_relevant_patents": final_patents,
            "candidate_directions": research_pack.get("candidate_directions", []) if isinstance(research_pack, dict) else [],
            "source_reading_notes": source_reading_notes,
        }

    def _build_redaction_policy(self, research_inputs: Dict[str, Any]) -> Dict[str, Any]:
        local_items = [
            item for item in research_inputs.get("research_evidence", [])
            if isinstance(item, dict) and item.get("source_type") == "local_project"
        ]
        enabled = bool(local_items or self.manifest.get("local_project_paths"))
        policy = {
            "policy_type": "local_project_redaction_policy",
            "schema_version": "1.0",
            "enabled": enabled,
            "trigger": "local_project_materials" if enabled else "online_only_no_redaction",
            "rules_source": "handsomestWei/patent-disclosure-skill disclosure_builder.md §7.5 redaction requirements",
            "rules": [
                {"name": "company_or_product", "replacement": "某系统"},
                {"name": "customer_or_business_label", "replacement": "对象A"},
                {"name": "internal_path", "replacement": "本地路径"},
                {"name": "specific_scale", "replacement": "每日一定规模"},
                {"name": "class_label", "replacement": "分类A"},
            ],
        }
        if not enabled:
            return policy
        sensitive_terms: List[str] = []
        for item in local_items:
            text = " ".join(str(item.get(key, "")) for key in ["title", "excerpt", "claim_supported", "url"])
            for term in re.findall(r"\b[A-Z][A-Za-z0-9]*(?:Vision|Cloud|AI|OS|DB|Hub|Pro|Plus)\b", text):
                if term not in sensitive_terms:
                    sensitive_terms.append(term)
            for term in re.findall(r"客户[\u4e00-\u9fffA-Za-z0-9_-]{1,12}|项目[\u4e00-\u9fffA-Za-z0-9_-]{1,12}", text):
                if term not in sensitive_terms:
                    sensitive_terms.append(term)
        policy["sensitive_terms"] = sensitive_terms[:50]
        return policy

    def _apply_redaction_filter(self, content: str, policy: Dict[str, Any]) -> str:
        if not policy.get("enabled") or not content:
            return content
        redacted = content
        for term in sorted(policy.get("sensitive_terms", []), key=len, reverse=True):
            if term:
                replacement = "对象A" if term.startswith(("客户", "项目")) else "某系统"
                redacted = redacted.replace(term, replacement)
        redacted = re.sub(r"(?:/[A-Za-z0-9._-]+){2,}", "本地路径", redacted)
        redacted = re.sub(r"[A-Za-z]:\\(?:[^\\\s]+\\)+[^\\\s]+", "本地路径", redacted)
        redacted = re.sub(r"每日\s*\d+(?:\.\d+)?\s*(?:件|条|次|单|人|辆|GB|MB)", "每日一定规模", redacted, flags=re.IGNORECASE)
        redacted = re.sub(r"\d+(?:\.\d+)?\s*(?:件/日|条/日|次/日|单/日)", "一定规模", redacted, flags=re.IGNORECASE)
        redacted = re.sub(r"类别\s*[0-9一二三四五六七八九十]+", "分类A", redacted)
        return redacted

    def _resolve_patent_title(self, research_inputs: Dict[str, Any]) -> str:
        for key in ["patent_title", "selected_title", "fixed_topic_or_title"]:
            value = self.manifest.get(key)
            if isinstance(value, str) and value.strip() and value.strip() != "未命名专利":
                return value.strip()
        direction = research_inputs.get("recommended_direction")
        if isinstance(direction, dict):
            title = direction.get("title")
            if isinstance(title, str) and title.strip():
                return title.strip() if title.strip().endswith("系统") else f"{title.strip()}及系统"
        if isinstance(direction, str) and direction.strip() and direction.strip() != "CD-01":
            return direction.strip()
        return "未命名专利"

    def _load_json(self, relative_path: str, fallback: Any) -> Any:
        path = self.workspace / relative_path
        if not path.exists():
            return fallback
        try:
            return self.load_artifact(relative_path)
        except Exception as error:
            self._log("json_load_warn", {"path": relative_path, "error": str(error)})
            return fallback

    def _load_preprocess_index(self) -> Dict[str, Any]:
        configured = self.manifest.get("preprocess_index_path") or "artifacts/preprocess/preprocess_index.json"
        data = self._load_json(configured, {})
        return data if isinstance(data, dict) else {}

    def _load_preprocess_context(self) -> Dict[str, Any]:
        preprocess_index = self._load_preprocess_index()
        artifacts = preprocess_index.get("artifacts", {}) if isinstance(preprocess_index, dict) else {}
        template_rules = self._load_json(artifacts.get("template_structure_rules", ""), {}) if artifacts.get("template_structure_rules") else {}
        style_profile = self._load_json(artifacts.get("reference_style_profile", ""), {}) if artifacts.get("reference_style_profile") else {}
        compliance_rules = self._load_json(artifacts.get("compliance_rules", ""), {}) if artifacts.get("compliance_rules") else {}
        patent_references = self._normalize_preprocess_patent_references(style_profile.get("patent_references", []))
        # 提取模板强制的章节结构
        template_sections = template_rules.get("sections", []) if isinstance(template_rules, dict) else []
        section_order = [s.get("name", "") for s in template_sections if s.get("name")]
        disabled_sections = [s.get("name", "") for s in template_sections if s.get("disabled")]
        # 提取风格画像中的写作原则
        style_principles = style_profile.get("writing_principles", []) if isinstance(style_profile, dict) else []
        style_examples = style_profile.get("extracted_examples", []) if isinstance(style_profile, dict) else []
        return {
            # 模板规则 - Phase 5 必须遵守
            "template_sections": section_order,
            "disabled_sections": disabled_sections,
            "section_order_required": section_order,
            # 风格画像 - Phase 5 写作参考
            "style_principles": style_principles[:8],
            "style_examples": style_examples[:5],
            "reference_patent_numbers": patent_references,
            # 合规规则
            "compliance_rules": [item.get("text", "") for item in compliance_rules.get("rules", []) if item.get("text")][:10] if isinstance(compliance_rules, dict) else [],
            # 锁定事实
            "locked_facts": [
                "正文章节顺序必须服从 template_sections 规定。",
                "写作风格参照 style_principles 和 style_examples。",
                "正文内容应满足 compliance_rules 规范。",
            ],
        }

    def _short(self, text: Any, limit: int) -> str:
        normalized = re.sub(r"\s+", " ", str(text or "")).strip()
        return normalized if len(normalized) <= limit else normalized[: limit - 1] + "..."

    def _first_evidence_ids(self, research_inputs: Dict[str, Any], limit: int) -> List[str]:
        ids = []
        for item in [*research_inputs.get("research_evidence", []), *research_inputs.get("patent_evidence", [])]:
            evidence_id = item.get("evidence_id")
            if evidence_id and evidence_id not in ids:
                ids.append(evidence_id)
            if len(ids) >= limit:
                break
        return ids

    def _infer_technical_problem(self, research_inputs: Dict[str, Any]) -> str:
        for item in research_inputs.get("research_evidence", []):
            claim = item.get("claim_supported") or item.get("excerpt")
            if claim:
                return claim
        return "检索结果来源复杂,证据难以追溯,正文撰写容易发生事实漂移。"

    def _build_shared_context(
        self,
        title: str,
        domain: str,
        direction: str,
        research_inputs: Dict[str, Any],
    ) -> Dict[str, Any]:
        preprocess_context = self._load_preprocess_context()
        terminology = self._extract_terminology(research_inputs)[:10]
        steps = self._build_step_registry()[:10]
        figures = [
            {"figure_id": item["figure_id"], "caption": item["caption"]}
            for item in self._build_figure_registry()[:5]
        ]
        constraints = self._build_constraints_and_effects(research_inputs)[:5]
        final_patents = research_inputs.get("final_relevant_patents", [])[:5]
        locked_facts = preprocess_context.get("locked_facts") or []
        if final_patents:
            locked_facts.append(
                "可信背景专利号:" + "、".join(
                    item.get("publicationNumber", "") for item in final_patents if item.get("publicationNumber")
                )[:120]
            )
        context = {
            "context_type": "shared_context",
            "schema_version": "1.0",
            "patent_title": self._short(title, 80),
            "selected_direction": self._short(direction or title, 100),
            "domain_scope": self._short(domain, 60),
            "technical_problem": {
                "text": self._short(self._infer_technical_problem(research_inputs), 120),
                "supporting_evidence_ids": self._first_evidence_ids(research_inputs, 4),
            },
            "core_solution": self._short(
                research_inputs.get("recommended_direction_detail", {}).get("core_idea", "") or "[待Phase 2提供]",
                120,
            ),
            "technical_effects": research_inputs.get("recommended_direction_detail", {}).get("technical_effects") or ["[待Phase 2提供技术效果]"],
            "canonical_terms": terminology,
            "steps": steps,
            "figures": figures,
            "locked_facts": [self._short(item, 120) for item in locked_facts if item],
            # ═══ Phase 0 模板与风格规则(必须遵守) ═══
            "writing_rules": {
                "section_order": preprocess_context.get("section_order_required", [
                    "技术领域", "背景技术", "发明内容", "附图说明", "具体实施方式",
                ]),
                "disabled_sections": preprocess_context.get("disabled_sections", []),
                "style_principles": preprocess_context.get("style_principles", []),
                "style_examples": preprocess_context.get("style_examples", []),
                "reference_patent_numbers": preprocess_context.get("reference_patent_numbers", []),
                "compliance_rules": preprocess_context.get("compliance_rules", []),
            },
            "forbidden": [
                "不得新增未登记术语。",
                "不得新增未登记步骤号。",
                "不得虚构专利号、申请人、公开日或证据来源。",
                "不得把普通网页写成最终相关专利。",
                "不得违反 writing_rules.section_order 规定的章节顺序。",
                "正文章节不得包含 writing_rules.disabled_sections 中禁用的章节。",
            ],
            "source_refs": {
                "research_pack_path": research_inputs.get("research_pack_path"),
                "candidate_pool_path": research_inputs.get("candidate_pool_path"),
                "evidence_pack_path": research_inputs.get("evidence_pack_path"),
            },
        }
        payload = json.dumps(context, ensure_ascii=False, sort_keys=True)
        context["budget"] = {
            "max_bytes": 5120,
            "actual_bytes": len(payload.encode("utf-8")),
            "within_budget": len(payload.encode("utf-8")) <= 5120,
        }
        context["context_hash"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return context

    def _build_writing_plan(
        self,
        title: str,
        domain: str,
        direction: str,
        research_inputs: Dict[str, Any],
        shared_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "plan_type": "phase_05_modular_writing_plan",
            "project_name": title,
            "domain_scope": domain,
            "selected_direction": direction,
            "shared_context_path": "artifacts/draft/shared_context.json",
            "shared_context_hash": shared_context.get("context_hash"),
            "context_strategy": "每块读取短 shared_context + 本块 block_context;shared_context 只放公共事实锚点,不放长证据。",
            "research_inputs": {
                "research_pack_path": research_inputs.get("research_pack_path"),
                "candidate_pool_path": research_inputs.get("candidate_pool_path"),
                "evidence_pack_path": research_inputs.get("evidence_pack_path"),
                "research_evidence_count": len(research_inputs.get("research_evidence", [])),
                "patent_evidence_count": len(research_inputs.get("patent_evidence", [])),
                "source_reading_notes_count": len(research_inputs.get("source_reading_notes", [])),
            },
            "section_word_budget": self._section_word_budget(),
            "blocks": DRAFT_BLOCKS,
        }

    def _section_word_budget(self) -> Dict[str, Dict[str, Any]]:
        budget: Dict[str, Dict[str, Any]] = {}
        for block in DRAFT_BLOCKS:
            item = {
                "name": block["name"],
                "target_min_chars": block["target_min_chars"],
                "target_max_chars": block["target_max_chars"],
                "reason": block["length_reason"],
            }
            if block["id"] == "part_04":
                item["target_min_figures"] = block.get("target_min_figures", 4)
                item["requires_mmd_per_figure"] = block.get("requires_mmd_per_figure", True)
                item["counting_rule"] = "自然语言字数不包含 Mermaid/mmd 代码块"
            budget[block["id"]] = item
        return budget

    def _plain_text_for_length(self, content: str, block: Dict[str, Any]) -> str:
        if block["id"] != "part_04":
            return content
        return re.sub(r"```(?:mermaid|mmd)?[\s\S]*?```", "", content, flags=re.IGNORECASE).strip()

    def _figure_structure_check(self, content: str, block: Dict[str, Any]) -> Dict[str, Any]:
        if block["id"] != "part_04":
            return {}
        figure_count = len(set(re.findall(r"图\s*[0-9一二三四五六七八九十]+", content)))
        mmd_block_count = len(re.findall(r"```(?:mermaid|mmd)\b[\s\S]*?```", content, flags=re.IGNORECASE))
        target_min_figures = block.get("target_min_figures", 4)
        requires_mmd = block.get("requires_mmd_per_figure", True)
        return {
            "figure_count": figure_count,
            "target_min_figures": target_min_figures,
            "mmd_block_count": mmd_block_count,
            "requires_mmd_per_figure": requires_mmd,
            "figure_count_passed": figure_count >= target_min_figures,
            "mmd_per_figure_passed": (not requires_mmd) or (figure_count > 0 and mmd_block_count >= figure_count),
        }

    def _length_status(self, char_count: int, block: Dict[str, Any]) -> str:
        if char_count < block["target_min_chars"]:
            return "too_short"
        if char_count > block["target_max_chars"]:
            return "too_long"
        return "pass"

    def _length_comment(self, status: str, block: Dict[str, Any]) -> str:
        if status == "too_short":
            return f"{block['name']}偏短,建议补充必要技术内容;{block['length_reason']}"
        if status == "too_long":
            return f"{block['name']}偏长,建议压缩与本章节无关的展开;{block['length_reason']}"
        return f"{block['name']}长度合理;{block['length_reason']}"

    def _build_block_context(
        self,
        block: Dict[str, Any],
        title: str,
        domain: str,
        direction: str,
        research_inputs: Dict[str, Any],
        shared_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        research_evidence = self._select_evidence(research_inputs.get("research_evidence", []), 4)
        patent_evidence = self._select_evidence(research_inputs.get("patent_evidence", []), 4)
        source_reading_notes = self._select_source_reading_notes(research_inputs.get("source_reading_notes", []), block["id"], 6)
        final_patents = research_inputs.get("final_relevant_patents", [])[:5]
        preprocess_patents = shared_context.get("writing_rules", {}).get("reference_patent_numbers", [])[:5]
        block_id = block["id"]
        evidence = []
        if "research" in BLOCK_EVIDENCE_NEEDS[block_id]:
            evidence.extend(research_evidence)
        if "patent" in BLOCK_EVIDENCE_NEEDS[block_id]:
            evidence.extend(patent_evidence)
        if block_id == "part_02":
            evidence.extend(self._patent_to_evidence(final_patents))
            if not self._cn_only_evidence(evidence):
                evidence.extend(self._patent_to_evidence(preprocess_patents, id_prefix="PRE-PAT"))
        return {
            "context_type": "block_context",
            "shared_context_path": "artifacts/draft/shared_context.json",
            "shared_context_hash": shared_context.get("context_hash"),
            "shared_context_refs": {
                "canonical_terms": [item.get("term", "") for item in shared_context.get("canonical_terms", [])],
                "steps": [item.get("step_id", "") for item in shared_context.get("steps", [])],
                "figures": [item.get("figure_id", "") for item in shared_context.get("figures", [])],
                "locked_fact_count": len(shared_context.get("locked_facts", [])),
            },
            "block_id": block_id,
            "block_name": block["name"],
            "target_file": block["file"],
            "word_range": {"min": block["min_words"], "max": block["max_words"]},
            "project": {"title": title, "domain_scope": domain, "selected_direction": direction},
            # Phase 0 写作规则(必须遵守)
            "writing_rules": shared_context.get("writing_rules", {}),
            "writing_instructions": self._block_instructions(block_id),
            "allowed_inputs": {
                "research_evidence_ids": [item.get("evidence_id", "") for item in research_evidence],
                "patent_evidence_ids": [item.get("evidence_id", "") for item in patent_evidence],
                "final_patent_numbers": [item.get("publicationNumber", "") for item in final_patents],
                "preprocess_patent_numbers": [item.get("publicationNumber", "") for item in preprocess_patents],
            },
            "evidence": evidence,
            "source_reading_notes": source_reading_notes,
            "writing_instructions": self._block_instructions(block_id),
            "review_rules": [
                "不得引入 context 外的新事实、专利号或来源。",
                "背景技术只引用 CN 专利号;WO/US/EP 等只能作为外围证据,不进入正文背景专利描述。",
                "每个关键事实应能映射到 evidence_id 或 final_patent_numbers。",
                "保持术语、步骤号、图号与 shared_context / registry 一致。",
                "无实验报告或用户确认数据时,禁止写准确率、延迟、样本量、百分比、具体设备参数等实验性数字。",
                "除非已有可验证公式与 docx 渲染方案,否则不写数学公式。",
            ],
        }

    def _select_source_reading_notes(self, notes: List[Dict[str, Any]], block_id: str, limit: int) -> List[Dict[str, Any]]:
        preferred_types = {
            "part_02": {"patent", "academic", "technical", "industry", "web"},
            "part_03": {"hotspot", "academic", "technical", "industry", "web"},
            "part_05": {"technical", "patent", "academic", "industry", "web"},
        }.get(block_id, {"hotspot", "academic", "technical", "industry", "patent", "web"})
        selected: List[Dict[str, Any]] = []
        seen = set()
        sorted_notes = sorted(
            [note for note in notes if isinstance(note, dict) and note.get("usable_in_writing", True)],
            key=lambda note: (note.get("source_type") in preferred_types, bool(note.get("key_technical_facts")), bool(note.get("page_summary"))),
            reverse=True,
        )
        for note in sorted_notes:
            key = note.get("note_id") or note.get("url") or json.dumps(note, ensure_ascii=False, sort_keys=True)
            if key in seen:
                continue
            seen.add(key)
            selected.append(note)
            if len(selected) >= limit:
                break
        return selected

    def _select_evidence(self, evidence: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
        selected = []
        seen = set()
        for item in evidence:
            key = item.get("evidence_id") or item.get("url") or json.dumps(item, ensure_ascii=False, sort_keys=True)
            if key in seen:
                continue
            seen.add(key)
            selected.append(item)
            if len(selected) >= limit:
                break
        return selected

    def _patent_to_evidence(self, patents: List[Dict[str, Any]], id_prefix: str = "PAT") -> List[Dict[str, Any]]:
        converted = []
        for idx, patent in enumerate(patents[:5], start=1):
            number = str(patent.get("publicationNumber") or patent.get("applicationNumber") or "").strip()
            if not number:
                continue
            converted.append(
                {
                    "evidence_id": f"{id_prefix}-{idx:03d}",
                    "source_type": "patent",
                    "url": patent.get("source_url", "") or patent.get("url", ""),
                    "excerpt": patent.get("abstract", "") or patent.get("excerpt", ""),
                    "publicationNumber": number,
                    "title": patent.get("title", ""),
                    "relevanceScore": patent.get("relevanceScore"),
                    "selection_reason": patent.get("selection_reason") or patent.get("reference_patent_selection_reason") or "",
                    "problem": patent.get("problem") or patent.get("reference_patent_problem") or "",
                    "fallback_only": id_prefix.startswith("PRE-PAT"),
                }
            )
        return converted

    def _normalize_preprocess_patent_references(self, patents: Any) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        if not isinstance(patents, list):
            return normalized
        seen = set()
        for patent in patents:
            if not isinstance(patent, dict):
                continue
            number = str(patent.get("publicationNumber") or patent.get("applicationNumber") or "").strip()
            if not number.startswith("CN") or number in seen:
                continue
            seen.add(number)
            normalized.append(
                {
                    "publicationNumber": number,
                    "applicationNumber": str(patent.get("applicationNumber") or "").strip(),
                    "title": self._sanitize_patent_title(patent.get("title") or patent.get("description") or ""),
                    "abstract": str(patent.get("abstract") or patent.get("description") or "").strip(),
                    "source_url": str(patent.get("source_url") or "").strip(),
                }
            )
        return normalized

    def _block_instructions(self, block_id: str) -> List[str]:
        return {
            "part_01": ["限定技术领域,聚焦本申请直接涉及的技术范围。", "自称使用'本申请'而非'本发明'。"],
            "part_02": ["只引用1-2件最接近的CN专利号说明现有技术及其缺陷。", "WO/US/EP 等非 CN 来源不得写入背景技术正文。", "每条现有技术末尾不附URL。", "缺陷用'第一,''第二,''第三,'排比,非'其一,''其二,'。", "用'由此可见,现有技术至少存在以下不足:'作为过渡句。", "整体保持精简,避免长篇罗列。"],
            "part_03": ["3.1用'本发明的目的在于提供......以解决......实现......'句式。", "3.2技术方案纯文字描述,不得出现'如图X所示'等图引用。", "3.2按系统组成和方法步骤展开,描述各模块功能和连接关系。", "3.3技术效果用'第一,''第二,'排比,与2.3不足逐条对应。"],
            "part_04": ["每图一组:标题行→描述段落→mermaid代码块。", "图描述格式:'图X为......,所示系统包括:......'或'图X为......,包括以下步骤:......'。", "不得出现'图X''图X'重复前缀。", "使用flowchart语法,不用graph TD。"],
            "part_05": ["按S101...S10x展开实施方式。", "起手句:'下面对照附图,通过对较优实施例的描述,对本申请的具体实施方式作进一步详细说明。'", "每个关键步骤引用对应图号,例如'如图1所示'。", "步骤用'S101步骤,'格式(非'步骤S101,')。", "5.1系统架构,5.2方法流程。", "无实验报告时禁止写准确率、延迟、样本量。", "自称用'本申请'。"],
        }.get(block_id, [])

    def _detect_content_contamination(self, block: Dict[str, Any], content: str) -> List[str]:
        """识别不能进入交底书正文的污染;命中时必须重生安全草稿。"""
        block_id = block["id"]
        reasons: List[str] = []
        internal_terms = [
            "Phase 2", "Phase 3", "Phase 5", "Phase 6", "Phase 7", "Phase 8", "Phase 9",
            "research_pack", "patent_candidate_pool", "evidence_pack", "block_context",
            "shared_context", "facts_ledger", "figure_registry", "terminology_registry",
            "block_review", "evidence_id", "写作依据", "正文分块", "IPR 模拟审查", "最终交付健康检查",
            "专利正文的一致性审计", "分块审核", "研究资料", "背景专利证据包",
        ]
        if any(term in content for term in internal_terms):
            reasons.append("正文混入工作流内部术语")
        if "<!--" in content or "需扩展内容" in content:
            reasons.append("含修订占位注释")
        if "Provider: OpenAI-compatible" in content or re.search(r"\d+\s*ms\b", content, flags=re.IGNORECASE):
            reasons.append("正文包含模型元数据或耗时数字")
        if block_id == "part_02":
            if re.search(r"\b(WO|US|EP)\d", content):
                reasons.append("背景技术引用非 CN 专利")
            for heading in ["2.1 与本申请相关的现有技术背景知识", "2.2 与本申请相关的最接近的现有技术", "2.3 现有技术的缺陷和不足"]:
                if heading not in content:
                    reasons.append(f"背景技术缺少模板小节: {heading}")
        if block_id == "part_03":
            for heading in ["3.1 本申请所需要解决的技术问题", "3.2 本申请的技术方案", "3.3 本申请的技术效果"]:
                if heading not in content:
                    reasons.append(f"发明内容缺少模板小节: {heading}")
            if "本发明要解决的技术问题在于,克服" in content:
                reasons.append("技术问题句式有语病")
        if block_id == "part_04":
            if "```mermaid" not in content:
                reasons.append("附图说明缺少 Mermaid 源码")
            if any(term in content for term in ["读取研究资料", "生成分块上下文", "分块撰写", "分块审核"]):
                reasons.append("附图内容与当前领域不符")
        if block_id == "part_05":
            if not re.search(r"如图\s*[12一二]", content):
                reasons.append("具体实施方式未引用具体图号")
            if self._contains_unverified_numeric_claim(content):
                reasons.append("具体实施方式含未经实验支撑的数据")
            if "Σ" in content or re.search(r"\b[a-zA-Z]+\s*=", content):
                reasons.append("具体实施方式含公式风险")
        return reasons

    def _regeneration_reasons_from_review(self, review: Dict[str, Any]) -> List[str]:
        """将旧稿审核中的中高风险问题转为重生原因。"""
        reasons = []
        for finding in review.get("findings", []):
            if finding.get("severity") not in {"high", "medium"}:
                continue
            issue = finding.get("issue", "")
            if any(token in issue for token in ["字数低于", "未显式引用", "未引用", "未对齐", "待补充占位"]):
                reasons.append(issue)
        return reasons

    def _backup_superseded_block(self, block_path: Any, reasons: List[str]) -> None:
        backup_dir = self.workspace / "artifacts" / "draft" / "superseded_blocks"
        backup_dir.mkdir(parents=True, exist_ok=True)
        reason_slug = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "_", "_".join(reasons))[:80]
        backup_path = backup_dir / f"{block_path.name}.{self._now_iso().replace(':', '-').replace('.', '-')}.{reason_slug}.bak"
        shutil.copy2(block_path, backup_path)
        self._log(
            "contaminated_block_regenerated",
            {"file": block_path.name, "backup": str(backup_path), "reasons": reasons},
        )

    def _make_skeleton(self, block: Dict[str, Any], context: Dict[str, Any]) -> str:
        """生成分块正文的结构模板。

        仅提供 CN 专利规范的章节标题和结构占位,不包含任何领域相关的
        具体技术内容。领域内容由 Agent 根据 Phase 2 研究结果和 shared_context
        在占位处撰写。

        格式规范由 _block_instructions() 定义,
        完整性由 _detect_content_contamination() 和 Phase 6/7 审计保证。
        """
        block_id = block["id"]
        raw_direction = context["project"].get("selected_direction") or context["project"].get("title", "[待确认]")
        # 防止 "一种一种" 重复:如果方向本身已含"一种"前缀则去掉
        direction = raw_direction.removeprefix("一种").removeprefix("一种").strip()
        domain = context["project"].get("domain_scope", "")
        instructions = self._block_instructions(block_id)

        templates = {
            "part_01": f"""# 一、技术领域

本发明涉及{domain or '[领域]'}技术领域,特别涉及一种{direction}。

> 撰写要求:限定技术领域,聚焦本申请直接涉及的技术范围,不展开适用场景或行业清单。
""",
            "part_02": """# 二、背景技术

## 2.1 与本申请相关的现有技术背景知识

[待撰写:基于 shared_context 中 domain_scope 描述本领域的通用技术背景,
说明现有主流方法或方案的基本原理和典型实现路径。
不得展开适用场景清单或行业举例。]

## 2.2 与本申请相关的最接近的现有技术

[待撰写:引用 phase_02_research_pack 和 evidence_pack 中最接近的 CN 专利,
每条引用应包含:专利号、公开的技术方案要点、与本申请的关联。
只引用 CN 专利号(如 CN110910151A),不得引用 WO/US/EP 专利。]

## 2.3 现有技术的缺陷和不足

[待撰写:逐条说明上述现有技术在本申请关注的技术问题上的不足。
使用"第一,......;第二,......;第三,......"句式,每条独立成行。
总结应自然引出本申请要解决的技术问题。]
""",
            "part_03": f"""# 三、发明内容

## 3.1 本申请所需要解决的技术问题

本发明的目的在于提供一种{direction}。

本发明要解决的技术问题在于:[待撰写:基于 shared_context 的技术问题描述,
说明现有技术无法解决的具体技术问题,以及本发明实现的技术目标]。

## 3.2 本申请的技术方案

为了实现上述目的,本发明采用的技术方案为:一种{direction}。

[待撰写:基于 facts_ledger 和 shared_context 的技术方案,
按系统组成(单元/模块)和方法步骤(S101...S10x)展开。
系统组成描述各单元的功能和连接关系。
方法步骤按 facts_ledger.step_registry 中的编号和顺序逐一描述。
禁止虚构未在图示中出现的组件或步骤。]

## 3.3 本申请的技术效果

与现有技术相比,本发明至少具有以下技术效果:

[待撰写:基于 shared_context 中 locked_facts 和 evidence 的技术效果,
使用"其一,......;其二,......;其三,......"句式,每条独立成行。
技术效果应与 2.3 中列举的现有技术不足形成对应关系。]
""",
            "part_04": self._figure_description_markdown(),
            "part_05": """# 五、具体实施方式

下面对照附图，通过对较优实施例的描述，对本申请的具体实施方式作进一步详细说明。

## 5.1 系统架构实施例

[待撰写：基于facts_ledger描述系统架构，列出各模块的部署位置、硬件平台和功能。每个模块描述其组成部件和关键参数。]

## 5.2 方法流程实施例

如图 2 所示，本申请提供的一种[方向名称]方法，包括以下步骤。

S101步骤，[步骤名称]。

[待撰写：基于facts_ledger.step_registry中S101…S10x步骤编号，按顺序展开每个步骤。每步骤包含：操作内容、关键参数/阈值、判定规则。引用对应图号，例如"如图 3 所示"。]

[后续步骤 S102-S10x 按同格式撰写]

> 撰写要求：
> - 步骤编号 S101...S10x 与 facts_ledger.step_registry 一致
> - 每步骤独立成段，步骤用"S101步骤，"格式
> - 每步骤引用对应图号，例如"如图 1 所示"、"如图 2 所示"
> - 无实验报告时禁止写准确率、延迟、样本量、百分比
> - 除非有可验证渲染方案，否则不写数学表达式
""",
        }
        return templates.get(block_id, f"# {{block['name']}}\n\n[待撰写:请根据 Phase 2 研究结果撰写本节内容。]")


    def _cn_only_evidence(self, evidence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [
            item for item in evidence
            if str(item.get("publicationNumber") or item.get("applicationNumber") or "").startswith("CN")
        ]

    def _figure_description_markdown(self) -> str:
        lines = ["# 四、附图说明", ""]
        for figure in self._build_figure_registry():
            figure_id = figure.get("figure_id", "图")
            caption = figure.get("caption", "附图")
            lines.append(f"{figure_id}为{caption}。")
            lines.append("")
            lines.append(f"{figure_id}所示系统包括：[待撰写：基于facts_ledger描述该图包含的模块/组件/步骤]")
            mmd_text = self._default_mermaid_source(figure_id)
            lines.extend(["", "```mermaid", mmd_text, "```", ""])
        return "\n".join(lines).rstrip() + "\n"

    def _default_mermaid_source(self, figure_id: str) -> str:
        """返回 Mermaid flowchart 骨架。Agent 应替换为对应领域的实际附图。"""
        if "2" in figure_id:
            return "flowchart LR\n    S101[步骤1] --> S102[步骤2]\n    S102 --> S103[步骤3]\n    S103 --> S104[步骤4]\n    S104 --> S105[步骤5]"
        if "3" in figure_id:
            return "flowchart TB\n    A[输入A] --> D[处理单元]\n    B[输入B] --> D\n    C[输入C] --> D\n    D --> E[输出结果]"
        if "4" in figure_id:
            return "flowchart TB\n    A[决策条件A] --> B[分支1]\n    A --> C[分支2]\n    B --> D[结果1]\n    C --> E[结果2]"
        return "flowchart TB\n    subgraph 系统模块\n        A[输入] --> B[处理单元]\n        B --> C[输出]\n    end"

    def _evidence_markdown(self, evidence: List[Dict[str, Any]]) -> str:
        if not evidence:
            return "- 暂无结构化证据,本块只能生成保守骨架,需补充研究资料后扩写。"
        lines = []
        for item in evidence[:6]:
            eid = item.get("evidence_id") or item.get("publicationNumber") or "EV"
            excerpt = self._sanitize_evidence_excerpt(item)
            lines.append(f"- `{eid}`:{excerpt[:120]}")
        return "\n".join(lines)

    def _sanitize_evidence_excerpt(self, item: Dict[str, Any]) -> str:
        """清理证据摘录中的模型元数据、耗时数字和过长正文。"""
        raw = item.get("claim_supported") or item.get("title") or item.get("excerpt") or "证据已登记,正文仅引用其证据编号和可核验事实"
        text = re.sub(r"\*\*Provider:[^\n]+\n*", "", str(raw), flags=re.IGNORECASE)
        text = re.sub(r"\([^)]*\b\d+\s*ms\b[^)]*\)", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\b\d+\s*ms\b", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s+", " ", text).strip(" -*:")
        if not text or text.lower().startswith("provider:"):
            text = item.get("title") or item.get("publicationNumber") or item.get("evidence_id") or "证据已登记"
        return text

    def _review_block(
        self,
        block: Dict[str, Any],
        content: str,
        context: Dict[str, Any],
        shared_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        evidence_ids = [item.get("evidence_id") for item in context.get("evidence", []) if item.get("evidence_id")]
        referenced = [eid for eid in evidence_ids if eid and eid in content]
        findings = []
        title = shared_context.get("patent_title", "")
        direction = shared_context.get("selected_direction", "")
        shared_terms = [item.get("term", "") for item in shared_context.get("canonical_terms", [])]
        shared_steps = [item.get("step_id", "") for item in shared_context.get("steps", [])]
        shared_figures = [item.get("figure_id", "") for item in shared_context.get("figures", [])]
        plain_text = self._plain_text_for_length(content, block)
        char_count = len(plain_text)
        total_char_count = len(content)
        length_status = self._length_status(char_count, block)
        figure_structure_check = self._figure_structure_check(content, block)
        figure_structure_passed = not figure_structure_check or (
            figure_structure_check["figure_count_passed"] and figure_structure_check["mmd_per_figure_passed"]
        )
        length_check = {
            "section_name": block["name"],
            "char_count": char_count,
            "total_char_count": total_char_count,
            "target_min_chars": block["target_min_chars"],
            "target_max_chars": block["target_max_chars"],
            "length_status": length_status,
            "length_comment": self._length_comment(length_status, block),
            "reason": block["length_reason"],
            "counting_rule": "自然语言字数不包含 Mermaid/mmd 代码块" if block["id"] == "part_04" else "按章节正文全文统计",
        }
        if length_status == "too_short":
            findings.append({"severity": "medium", "issue": f"{block['name']}字数低于建议范围", "fix": length_check["length_comment"]})
        elif length_status == "too_long":
            findings.append({"severity": "low", "issue": f"{block['name']}字数高于建议范围", "fix": length_check["length_comment"]})
        if evidence_ids and not referenced:
            findings.append({"severity": "medium", "issue": "未显式引用 evidence_id", "fix": "在关键事实处标注证据编号"})
        if block["id"] in {"part_01", "part_03", "part_05"} and direction and direction not in content and title not in content:
            findings.append({"severity": "medium", "issue": "未对齐 shared_context 中的标题或最终方向", "fix": "补入 patent_title 或 selected_direction"})
        if block["id"] == "part_04" and not any(figure in content for figure in shared_figures):
            findings.append({"severity": "medium", "issue": "未引用 shared_context 中登记的图号", "fix": "使用 figure_registry 中的图号"})
        if block["id"] == "part_04" and figure_structure_check:
            if not figure_structure_check["figure_count_passed"]:
                findings.append({
                    "severity": "medium",
                    "issue": "附图数量低于建议数量",
                    "fix": "补充系统架构图、方法流程图、证据记录结构图、追溯关系图等",
                })
            if not figure_structure_check["mmd_per_figure_passed"]:
                findings.append({
                    "severity": "medium",
                    "issue": "附图说明未做到每图对应 Mermaid/mmd 源码",
                    "fix": "每个图注后附对应 Mermaid/mmd 代码块",
                })
        if block["id"] == "part_05" and not any(step in content for step in shared_steps):
            findings.append({"severity": "medium", "issue": "未引用 shared_context 中登记的步骤号", "fix": "使用 step_registry 中的步骤号"})
        if "待补充" in content or "暂无结构化证据" in content:
            findings.append({"severity": "low", "issue": "仍含待补充占位", "fix": "补齐研究资料后替换占位"})
        if "<!--" in content or "需扩展内容" in content:
            findings.append({"severity": "high", "issue": "正文含修订占位注释", "fix": "删除占位注释,改由 Agent 生成真实内容"})
        if block["id"] == "part_02" and re.search(r"\b(WO|US|EP)\d", content):
            findings.append({"severity": "high", "issue": "背景技术引用非 CN 专利", "fix": "背景技术正文只保留 CN 专利号"})
        if block["id"] == "part_03" and "本发明要解决的技术问题在于,克服" in content:
            findings.append({"severity": "medium", "issue": "技术问题句式有语病", "fix": "改为'本发明要解决的技术问题在于'"})
        if block["id"] == "part_05":
            if not re.search(r"如图\s*[12一二]", content):
                findings.append({"severity": "medium", "issue": "具体实施方式未引用具体图号", "fix": "步骤描述中引用图 1 或图 2"})
            if self._contains_unverified_numeric_claim(content):
                findings.append({"severity": "high", "issue": "具体实施方式含未经实验支撑的数据", "fix": "无实验报告时删除准确率、延迟、样本量、百分比和具体设备参数"})
            if "Σ" in content or re.search(r"\b[a-zA-Z]+\s*=", content):
                findings.append({"severity": "medium", "issue": "具体实施方式含可能无法稳定渲染的公式", "fix": "无可验证公式格式时改为文字描述"})
        shared_checks = {
            "shared_context_path_present": bool(context.get("shared_context_path")),
            "shared_context_hash_matched": context.get("shared_context_hash") == shared_context.get("context_hash"),
            "shared_context_within_budget": shared_context.get("budget", {}).get("within_budget") is True,
            "canonical_terms_available": bool(shared_terms),
            "step_registry_available": bool(shared_steps),
            "figure_registry_available": bool(shared_figures),
        }
        return {
            "review_type": "block_review",
            "block_id": block["id"],
            "target_file": block["file"],
            "char_count": char_count,
            "total_char_count": total_char_count,
            "word_count": char_count,
            "min_words": block["min_words"],
            "target_min_chars": block["target_min_chars"],
            "target_max_chars": block["target_max_chars"],
            "length_check": length_check,
            "figure_structure_check": figure_structure_check,
            "context_path": f"artifacts/draft/block_contexts/{block['id']}_context.json",
            "shared_context_path": "artifacts/draft/shared_context.json",
            "evidence_ids_available": evidence_ids,
            "evidence_ids_referenced": referenced,
            "checks": {
                "min_length_passed": length_status != "too_short",
                "length_within_target_range": length_status == "pass",
                "evidence_reference_passed": not evidence_ids or bool(referenced),
                "context_isolated": True,
                "figure_structure_passed": figure_structure_passed,
                "shared_context_consistency_passed": all(shared_checks.values()),
                **shared_checks,
            },
            "passed": len([item for item in findings if item["severity"] in {"high", "medium"}]) == 0 and all(shared_checks.values()) and figure_structure_passed,
            "findings": findings,
        }

    def _contains_unverified_numeric_claim(self, content: str) -> bool:
        patterns = [
            r"\d+(?:\.\d+)?%",
            r"\d+\s*(?:毫秒|ms|秒|分钟|小时|天|周|件|次|kg|g|米/秒|MB|GB)",
            r"前\d+次",
            r"运行\d+天",
        ]
        return any(re.search(pattern, content, flags=re.IGNORECASE) for pattern in patterns)

    def _build_facts_ledger(
        self,
        title: str,
        research_inputs: Dict[str, Any],
        block_statuses: List[Dict[str, Any]],
        shared_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        terminology = self._extract_terminology(research_inputs)
        figure_registry = self._build_figure_registry()
        step_registry = self._build_step_registry()
        constraints = self._build_constraints_and_effects(research_inputs)
        return {
            "ledger_type": "facts_ledger",
            "schema_version": "2.0",
            "project_name": title,
            "generated_at": self._now_iso(),
            "research_inputs": {
                "research_pack_path": research_inputs.get("research_pack_path"),
                "candidate_pool_path": research_inputs.get("candidate_pool_path"),
                "evidence_pack_path": research_inputs.get("evidence_pack_path"),
                "research_evidence_count": len(research_inputs.get("research_evidence", [])),
                "patent_evidence_count": len(research_inputs.get("patent_evidence", [])),
                "source_reading_notes_count": len(research_inputs.get("source_reading_notes", [])),
            },
            "shared_context": {
                "path": "artifacts/draft/shared_context.json",
                "context_hash": shared_context.get("context_hash"),
                "actual_bytes": shared_context.get("budget", {}).get("actual_bytes"),
                "within_budget": shared_context.get("budget", {}).get("within_budget"),
            },
            "terminology": terminology,
            "figure_registry": figure_registry,
            "step_registry": step_registry,
            "constraints_and_effects": constraints,
            "block_statuses": block_statuses,
        }

    def _extract_terminology(self, research_inputs: Dict[str, Any]) -> List[Dict[str, Any]]:
        terms = [
            # 术语由 Agent 根据 shared_context 和 Phase 2 研究结果填充
        ]
        return [{"term": term, "definition": definition, "aliases": []} for term, definition in terms]

    def _build_figure_registry(self) -> List[Dict[str, Any]]:
        return [
            {
                "figure_id": "图 1",
                "caption": "系统架构图",
                "delivery_mode": "mmd_embedded_in_figure_description",
                "artifacts": {"mmd": "附图/fig_01_系统架构.mmd"},
                "mermaid_source_embedded_in_docx": True,
            },
            {
                "figure_id": "图 2",
                "caption": "方法流程图",
                "delivery_mode": "mmd_embedded_in_figure_description",
                "artifacts": {"mmd": "附图/fig_02_方法流程.mmd"},
                "mermaid_source_embedded_in_docx": True,
            },
            {
                "figure_id": "图 3",
                "caption": "质检证据记录结构示意图",
                "delivery_mode": "mmd_embedded_in_figure_description",
                "artifacts": {"mmd": "附图/fig_03_证据记录结构.mmd"},
                "mermaid_source_embedded_in_docx": True,
            },
            {
                "figure_id": "图 4",
                "caption": "质检结论追溯关系示意图",
                "delivery_mode": "mmd_embedded_in_figure_description",
                "artifacts": {"mmd": "附图/fig_04_追溯关系.mmd"},
                "mermaid_source_embedded_in_docx": True,
            },
        ]

    def _build_step_registry(self) -> List[Dict[str, Any]]:
        return [
            # 步骤由 Agent 根据 shared_context 和 Phase 2 研究结果填充
            {"step_id": "S101", "description": "[待填充]"},
            {"step_id": "S102", "description": "[待填充]"},
        ]

    def _ensure_figure_artifacts(self, figure_registry: List[Dict[str, Any]]) -> None:
        for figure in figure_registry:
            artifacts = figure.get("artifacts", {})
            mmd = artifacts.get("mmd")
            if mmd:
                path = self.workspace / mmd
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(self._default_mermaid_source(figure.get("figure_id", "图")) + "\n", encoding="utf-8")

    def _build_constraints_and_effects(self, research_inputs: Dict[str, Any]) -> List[Dict[str, Any]]:
        evidence = research_inputs.get("research_evidence", [])[:3]
        constraints = []
        if evidence:
            for idx, item in enumerate(evidence, start=1):
                constraints.append(
                    {
                        "constraint": item.get("claim_supported") or f"核心技术约束{idx}",
                        "effect": "降低事实漂移并提升专利正文可追溯性",
                        "evidence_ids": [item.get("evidence_id", "")],
                        "source_blocks": ["part_03", "part_05"],
                    }
                )
        else:
            constraints.append(
                {
                    "constraint": "正文事实必须来自结构化研究资料或用户确认输入",
                    "effect": "降低幻觉率并便于后续一致性审计",
                    "evidence_ids": [],
                    "source_blocks": ["part_03", "part_05"],
                }
            )
        return constraints

    def _build_metadata(self, title: str, block_statuses: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "projectName": title,
            "mode": "patent",
            "createdAt": self._now_iso(),
            "updatedAt": self._now_iso(),
            "blocks": [
                {
                    "name": status["name"],
                    "file": status["file"],
                    "status": "completed" if status["has_min_content"] else "skeleton",
                    "version": 1,
                    "lastModified": self._now_iso(),
                    "contextPath": status["context_path"],
                    "reviewPath": status["review_path"],
                }
                for status in block_statuses
            ],
            "finalMerged": False,
            "iprReviewPassed": False,
        }

    def _now_iso(self) -> str:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat()
