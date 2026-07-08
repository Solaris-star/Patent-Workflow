#!/usr/bin/env python3
"""
Phase 0 Executor — 材料预处理与运行清单初始化。

负责把输入材料、模板规则和风格画像统一前置准备，避免单独的模板风格阶段空转。
产出或确认：
- preprocess_notes / preprocess_cache_status
- source_fingerprints.json（含 sha256）
- template_rules.json
- style_profile.json / style_profile.md
- run_manifest.json
- template_rules_ready / style_profile_ready
"""

import hashlib
import json
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List

import pdfplumber
from docx import Document
from pypdf import PdfReader

from executors.base_executor import BaseExecutor, ExecutorResult


STYLE_PROFILE_SCHEMA_VERSION = "1.0"
TEMPLATE_RULES_SCHEMA_VERSION = "1.0"


DEFAULT_STYLE_PROFILE = {
    "schema_version": STYLE_PROFILE_SCHEMA_VERSION,
    "profile_id": "CN121526509A",
    "profile_name": "默认专利撰写风格画像",
    "source": "writing-style-analyzer/profiles/CN121526509A.json",
    "source_usage": "style_only",
    "content_usage": "forbidden_as_technical_fact",
    "generation_mode": "builtin_default",
    "applies_to": ["具体实施方式"],
    "writing_principles": [
        "解释型说明书笔法",
        "步骤总述链",
        "技术效果递进说明",
        "术语前后一致",
    ],
    "required_patterns": {
        "opening_sentence": "下面对照附图",
        "step_overview_sentence": "本实施例提供的一种……方法，包括以下步骤：",
        "detail_transition": "具体如下：",
        "step_numbering": "S101...S10x",
    },
    "reference_style_rules": {
        "technical_field": "采用短句限定所属技术领域，例如‘本发明涉及……技术领域，特别涉及一种……方法及系统。’，不得扩写应用行业清单。",
        "background": "先写行业场景和客观痛点，再以‘当前虽有部分……如中国专利……公开了……，其可以……但是其无法解决……’方式引用 1-2 件最接近 CN 专利；不得用‘相关方案’等泛化占位描述替代实际公开内容。",
        "invention_content": "采用‘本发明的目的在于……以解决……实现……’和‘为了实现上述目的，本发明采用的技术方案为：……’的说明书句式。",
        "embodiment": "采用‘下面对照附图……作进一步详细说明’起手，先总述实施例，再按 S101-S10x 分步骤说明并引用图号。",
        "figures": "附图说明通常不少于 4 张图，至少覆盖系统架构、方法流程、证据记录结构、追溯关系；每个图注后附 Mermaid/mmd 源码，不输出独立图片占位物。",
    },
    "forbidden_tone": [
        "口语化表达",
        "营销化表达",
        "客户沟通式表达",
    ],
    "fallback_reason": "未提供用户指定参考风格时使用内置默认画像",
    "usage_boundary": [
        "仅提取说明书表达风格、段落组织和步骤句式。",
        "不得提取或复用参考专利的技术领域、发明名称、技术问题、技术方案、实施例参数或附图内容。",
        "不得将参考专利号写入本轮背景技术，除非 Phase 2 内部专利复核将其作为本轮真实现有技术重新检索并选中。"
    ],
}


DEFAULT_TEMPLATE_RULES = {
    "schema_version": TEMPLATE_RULES_SCHEMA_VERSION,
    "profile": "CN121526509A",
    "source": "writing-style-analyzer/profiles/CN121526509A.json",
    "source_usage": "style_only",
    "content_usage": "forbidden_as_technical_fact",
    "document_type": "patent_disclosure",
    "sections": [
        {"id": "part_01", "name": "技术领域", "required": True, "order": 1},
        {"id": "part_02", "name": "背景技术", "required": True, "order": 2},
        {"id": "part_03", "name": "发明内容", "required": True, "order": 3},
        {"id": "part_04", "name": "专利附图", "required": True, "order": 4},
        {"id": "part_05", "name": "具体实施方式", "required": True, "order": 5},
    ],
    "forbidden_sections": ["权利要求书"],
    "numbering_rules": {
        "steps": "S101...S10x",
        "figures": "图1...图N",
        "terms": "首次出现时定义，后文保持一致",
    },
    "style_requirements": [
        "固定起手句",
        "步骤总述句",
        "具体如下句式",
        "解释型说明书笔法",
    ],
    "reference_patent_boundary": {
        "reference_profile": "CN121526509A",
        "allowed": ["段落组织", "步骤化表达", "说明书衔接句式", "附图对照叙述方式"],
        "forbidden": ["技术领域", "发明名称", "技术问题", "技术方案", "实施例参数", "附图内容", "项目管理主题"],
        "rule": "参考专利只作为风格样本，不作为本轮技术事实来源。"
    },
    "handoff_requirements": {
        "phase_5": [
            "template_rules_ready",
            "style_profile_ready",
            "facts_ledger_ready",
        ],
        "phase_6": [
            "step_registry_ready",
            "figure_registry_ready",
            "terminology_registry_ready",
        ],
    },
}


class PhaseExecutor(BaseExecutor):
    """阶段 0 执行器：材料预处理与运行清单初始化。"""

    def _execute(self) -> ExecutorResult:
        print("   📦 执行材料预处理与模板风格准备...")

        artifacts: List[str] = []
        source_files = self._discover_source_files()
        source_fingerprints = self._fingerprints(source_files)
        force_preprocess = bool(self.manifest.get("force_preprocess") or self.manifest.get("refresh_preprocess"))

        preprocess_payloads = self._build_preprocess_payloads(source_files)
        extracted_style_profile = preprocess_payloads["reference_style_profile"]
        extracted_template_rules = preprocess_payloads["template_structure_rules"]

        template_path = self._ensure_json_artifact(
            extracted_template_rules,
            "template_rules.json",
            "template_rules",
        )
        artifacts.append(str(template_path))

        style_json_path = self._ensure_json_artifact(
            extracted_style_profile,
            "style_profile.json",
            "style_profile_json",
        )
        artifacts.append(str(style_json_path))

        style_md_path = self._ensure_text_artifact(
            self._style_profile_markdown(extracted_style_profile),
            "style_profile.md",
            "style_profile_md",
        )
        artifacts.append(str(style_md_path))

        fingerprints_relative_path = "artifacts/preprocess/source_fingerprints.json"
        notes_relative_path = "artifacts/preprocess/phase_00_preprocess_notes.md"
        run_manifest_json_relative_path = "artifacts/run_manifest.json"
        fingerprints_path = self.workspace / fingerprints_relative_path
        notes_path = self.workspace / notes_relative_path
        run_manifest_json_path = self.workspace / run_manifest_json_relative_path
        cache_ready = self._preprocess_cache_ready(fingerprints_path, notes_path, run_manifest_json_path)
        fingerprints_match = self._stored_fingerprints_match(fingerprints_path, source_fingerprints)

        if force_preprocess:
            cache_status = "force_refreshed"
            reuse_status = "refreshed"
            refresh_reason = "force_preprocess_requested"
        elif cache_ready and fingerprints_match:
            cache_status = "cache_hit_reused"
            reuse_status = "reused"
            refresh_reason = "source_fingerprints_match"
        elif cache_ready:
            cache_status = "cache_miss_refreshed"
            reuse_status = "refreshed"
            refresh_reason = "source_fingerprints_changed"
        else:
            cache_status = "cache_miss_created"
            reuse_status = "created"
            refresh_reason = "preprocess_artifacts_missing"

        preprocess_artifact_paths = {
            "source_inventory": "artifacts/preprocess/source_inventory.json",
            "document_ast": "artifacts/preprocess/document_ast.json",
            "reference_style_profile": "artifacts/preprocess/reference_style_profile.json",
            "template_structure_rules": "artifacts/preprocess/template_structure_rules.json",
            "compliance_rules": "artifacts/preprocess/compliance_rules.json",
            "conflict_report": "artifacts/preprocess/conflict_report.json",
            "preprocess_index": "artifacts/preprocess/preprocess_index.json",
        }

        should_write_preprocess = reuse_status != "reused"
        if should_write_preprocess:
            fingerprints_path = self.save_workspace_artifact(
                self._source_fingerprints_payload(source_fingerprints),
                fingerprints_relative_path,
            )
            notes_path = self.save_workspace_artifact(
                self._build_preprocess_notes(
                    source_files,
                    template_path,
                    style_json_path,
                    style_md_path,
                    fingerprints_path,
                    cache_status,
                    refresh_reason,
                ),
                notes_relative_path,
            )
            for key, relative_path in preprocess_artifact_paths.items():
                self.save_workspace_artifact(preprocess_payloads[key], relative_path)
        else:
            self._log("preprocess_cache_hit", {"source_count": len(source_fingerprints)})

        artifacts.extend([str(fingerprints_path), str(notes_path)])
        artifacts.extend(str(self.workspace / relative_path) for relative_path in preprocess_artifact_paths.values())

        manifest_updates: Dict[str, Any] = {
            "run_id": self.manifest.get("run_id") or str(uuid.uuid4()),
            "output_dir": self.manifest.get("output_dir") or str(self.workspace),
            "preprocess_notes": notes_relative_path,
            "preprocess_cache_status": cache_status,
            "preprocess_reuse_status": reuse_status,
            "preprocess_refresh_reason": refresh_reason,
            "source_fingerprints": source_fingerprints,
            "source_fingerprints_path": fingerprints_relative_path,
            "template_rules_ready": True,
            "style_profile_ready": True,
            "template_rules_path": "template_rules.json",
            "style_profile_path": "style_profile.json",
            "style_profile_markdown_path": "style_profile.md",
            "template_rules_schema_version": TEMPLATE_RULES_SCHEMA_VERSION,
            "style_profile_schema_version": STYLE_PROFILE_SCHEMA_VERSION,
            "source_inventory_path": preprocess_artifact_paths["source_inventory"],
            "document_ast_path": preprocess_artifact_paths["document_ast"],
            "reference_style_profile_path": preprocess_artifact_paths["reference_style_profile"],
            "template_structure_rules_path": preprocess_artifact_paths["template_structure_rules"],
            "compliance_rules_path": preprocess_artifact_paths["compliance_rules"],
            "conflict_report_path": preprocess_artifact_paths["conflict_report"],
            "preprocess_index_path": preprocess_artifact_paths["preprocess_index"],
        }
        manifest_updates["run_manifest_json_path"] = run_manifest_json_relative_path

        if should_write_preprocess or not run_manifest_json_path.exists():
            run_manifest_json_path = self.save_workspace_artifact(
                self._build_run_manifest_json(
                    manifest_updates,
                    [*artifacts, run_manifest_json_relative_path],
                ),
                run_manifest_json_relative_path,
            )
        artifacts.append(str(run_manifest_json_path))

        return ExecutorResult(
            status="success",
            artifacts=artifacts,
            manifest_updates=manifest_updates,
            trace_log=self.trace,
        )

    def _source_fingerprints_payload(self, source_fingerprints: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "schema_version": "1.0",
            "fingerprint_method": "path + size + modified_at + sha256",
            "source_count": len(source_fingerprints),
            "sources": source_fingerprints,
        }

    def _preprocess_cache_ready(self, fingerprints_path: Path, notes_path: Path, run_manifest_json_path: Path) -> bool:
        required_paths = [
            self.workspace / "template_rules.json",
            self.workspace / "style_profile.json",
            self.workspace / "style_profile.md",
            self.workspace / "artifacts" / "preprocess" / "source_inventory.json",
            self.workspace / "artifacts" / "preprocess" / "document_ast.json",
            self.workspace / "artifacts" / "preprocess" / "reference_style_profile.json",
            self.workspace / "artifacts" / "preprocess" / "template_structure_rules.json",
            self.workspace / "artifacts" / "preprocess" / "compliance_rules.json",
            self.workspace / "artifacts" / "preprocess" / "conflict_report.json",
            self.workspace / "artifacts" / "preprocess" / "preprocess_index.json",
            fingerprints_path,
            notes_path,
            run_manifest_json_path,
        ]
        return all(path.exists() for path in required_paths)

    def _stored_fingerprints_match(self, fingerprints_path: Path, source_fingerprints: List[Dict[str, Any]]) -> bool:
        if not fingerprints_path.exists():
            return False
        try:
            payload = json.loads(fingerprints_path.read_text(encoding="utf-8"))
        except Exception:
            return False
        return payload.get("sources") == source_fingerprints

    def _ensure_json_artifact(self, data: Dict[str, Any], relative_path: str, label: str) -> Path:
        path = self.workspace / relative_path
        if path.exists():
            try:
                current = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                current = None
            if current == data:
                self._log(f"{label}_found", {"path": str(path)})
                return path
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            self._log(f"{label}_refreshed", {"path": str(path)})
            return path
        path = self.save_workspace_artifact(data, relative_path)
        self._log(f"{label}_created", {"path": str(path)})
        return path

    def _ensure_text_artifact(self, text: str, relative_path: str, label: str) -> Path:
        path = self.workspace / relative_path
        if path.exists():
            if path.read_text(encoding="utf-8") == text:
                self._log(f"{label}_found", {"path": str(path)})
                return path
            path.write_text(text, encoding="utf-8")
            self._log(f"{label}_refreshed", {"path": str(path)})
            return path
        path = self.save_workspace_artifact(text, relative_path)
        self._log(f"{label}_created", {"path": str(path)})
        return path

    def _discover_source_files(self) -> List[Path]:
        patterns = ["*.pdf", "*.docx", "*.md", "*.txt", "*.json"]
        generated_files = {
            "style_profile.md",
            "style_profile.json",
            "template_rules.json",
        }
        excluded_names = {
            "AGENTS.md", "BOOTSTRAP.md", "DREAMS.md", "HEARTBEAT.md", "IDENTITY.md",
            "MEMORY.md", "SOUL.md", "TOOLS.md", "USER.md",
        }
        excluded_prefixes = ("feishu_cli_qr_", "part_")
        excluded_suffixes = ("技术交底书_合并版.md",)
        excluded_dirs = {"artifacts", "scripts", "tests", "__pycache__", ".git"}
        files: List[Path] = []
        seen = set()
        for pattern in patterns:
            for path in self.workspace.rglob(pattern):
                if not path.is_file():
                    continue
                if any(part in excluded_dirs for part in path.relative_to(self.workspace).parts[:-1]):
                    continue
                if path.name in generated_files or path.name in excluded_names:
                    continue
                if any(path.name.startswith(prefix) for prefix in excluded_prefixes):
                    continue
                if any(path.name.endswith(suffix) for suffix in excluded_suffixes):
                    continue
                key = str(path.resolve())
                if key in seen:
                    continue
                seen.add(key)
                files.append(path)
        return sorted(files)

    def _fingerprints(self, files: List[Path]) -> List[Dict[str, Any]]:
        fingerprints: List[Dict[str, Any]] = []
        for path in files:
            stat = path.stat()
            fingerprints.append(
                {
                    "path": path.name,
                    "relative_path": str(path.relative_to(self.workspace)),
                    "extension": path.suffix.lower(),
                    "size": stat.st_size,
                    "modified_at": int(stat.st_mtime),
                    "sha256": self._sha256(path),
                }
            )
        return fingerprints

    def _sha256(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as file_obj:
            for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _build_preprocess_notes(
        self,
        source_files: List[Path],
        template_path: Path,
        style_json_path: Path,
        style_md_path: Path,
        fingerprints_path: Path,
        cache_status: str,
        refresh_reason: str,
    ) -> str:
        lines = [
            "# Phase 0 材料预处理记录",
            "",
            f"- 模板规则: {template_path.relative_to(self.workspace)}",
            f"- 风格画像 JSON: {style_json_path.relative_to(self.workspace)}",
            f"- 风格画像 Markdown: {style_md_path.relative_to(self.workspace)}",
            f"- 源文件指纹: {fingerprints_path.relative_to(self.workspace)}",
            f"- 源材料数量: {len(source_files)}",
            f"- 缓存状态: {cache_status}",
            f"- 刷新原因: {refresh_reason}",
            "",
            "## 源材料",
        ]
        if source_files:
            for path in source_files:
                lines.append(f"- {path.name}")
        else:
            lines.append("- 未发现显式上传材料，后续阶段按用户范围与默认模板继续。")
        lines.extend(
            [
                "",
                "## 说明",
                "模板与风格准备已并入 Phase 0，不再单独设置模板风格分析阶段。",
                "参考专利画像仅用于提取写作风格、段落组织和步骤句式；不得作为本轮技术事实、发明主题、现有技术结论或附图内容来源。",
                "源文件指纹使用 path + size + modified_at + sha256，用于复现、缓存判断和审计追踪。",
            ]
        )
        return "\n".join(lines) + "\n"

    def _style_profile_markdown(self, profile: Dict[str, Any]) -> str:
        lines = [
            f"# {profile['profile_name']}：{profile['profile_id']}",
            "",
            "## 适用范围",
            "",
            *[f"- {item}" for item in profile["applies_to"]],
            "",
            "## 写作原则",
            "",
            *[f"- {item}" for item in profile["writing_principles"]],
            "",
            "## 必需句式",
            "",
            f"- 固定起手句: {profile['required_patterns']['opening_sentence']}",
            f"- 步骤总述句: {profile['required_patterns']['step_overview_sentence']}",
            f"- 细化衔接句: {profile['required_patterns']['detail_transition']}",
            f"- 步骤编号: {profile['required_patterns']['step_numbering']}",
            "",
            "## 禁用语气",
            "",
            *[f"- {item}" for item in profile["forbidden_tone"]],
            "",
            "## 使用边界",
            "",
            *[f"- {item}" for item in profile.get("usage_boundary", [])],
            "",
            "## 来源",
            "",
            f"- `{profile['source']}`",
            f"- 来源用途: `{profile.get('source_usage', 'style_only')}`",
            f"- 内容用途: `{profile.get('content_usage', 'forbidden_as_technical_fact')}`",
            f"- 生成模式: `{profile['generation_mode']}`",
        ]
        return "\n".join(lines) + "\n"

    def _build_preprocess_payloads(self, source_files: List[Path]) -> Dict[str, Any]:
        source_inventory = self._build_source_inventory(source_files)
        document_ast = self._build_document_ast(source_inventory)
        reference_style_profile = self._build_reference_style_profile(document_ast)
        template_structure_rules = self._build_template_structure_rules(document_ast)
        compliance_rules = self._build_compliance_rules(document_ast)
        conflict_report = {
            "schema_version": "1.0",
            "conflicts": [],
            "status": "clear",
        }
        preprocess_index = {
            "schema_version": "1.0",
            "status": "ready",
            "summary": {
                "source_count": len(source_inventory["sources"]),
                "document_count": len(document_ast["documents"]),
                "style_rule_count": len(reference_style_profile.get("writing_principles", [])),
                "template_section_count": len(template_structure_rules.get("sections", [])),
                "compliance_rule_count": len(compliance_rules.get("rules", [])),
            },
            "artifacts": {
                "source_inventory": "artifacts/preprocess/source_inventory.json",
                "document_ast": "artifacts/preprocess/document_ast.json",
                "reference_style_profile": "artifacts/preprocess/reference_style_profile.json",
                "template_structure_rules": "artifacts/preprocess/template_structure_rules.json",
                "compliance_rules": "artifacts/preprocess/compliance_rules.json",
                "conflict_report": "artifacts/preprocess/conflict_report.json",
            },
        }
        return {
            "source_inventory": source_inventory,
            "document_ast": document_ast,
            "reference_style_profile": reference_style_profile,
            "template_structure_rules": template_structure_rules,
            "compliance_rules": compliance_rules,
            "conflict_report": conflict_report,
            "preprocess_index": preprocess_index,
        }

    def _build_source_inventory(self, source_files: List[Path]) -> Dict[str, Any]:
        sources = []
        explicit_role_map = self._explicit_role_map()
        for index, path in enumerate(source_files, start=1):
            explicit_role = explicit_role_map.get(path.name) or explicit_role_map.get(str(path.relative_to(self.workspace)))
            if explicit_role:
                role, confidence, role_source = explicit_role, 1.0, "user_declared"
            else:
                role, confidence = self._classify_source_role(path)
                role_source = "auto_classified"
            sources.append(
                {
                    "source_id": f"SRC-{index:03d}",
                    "file_name": path.name,
                    "relative_path": str(path.relative_to(self.workspace)),
                    "file_type": path.suffix.lower().lstrip("."),
                    "role": role,
                    "confidence": confidence,
                    "role_source": role_source,
                }
            )
        return {"schema_version": "1.0", "sources": sources}

    def _explicit_role_map(self) -> Dict[str, str]:
        raw = self.manifest.get("phase_0_role_map") or self.manifest.get("source_role_map") or {}
        return raw if isinstance(raw, dict) else {}

    def _classify_source_role(self, path: Path) -> tuple[str, float]:
        file_name = path.name.lower()
        if any(token in file_name for token in ["规范", "要求", "rule", "checklist"]):
            return "compliance_spec", 0.9
        if any(token in file_name for token in ["模板", "template", "交底书框架"]):
            return "template", 0.92
        if any(token in file_name for token in ["专利", "patent", "cn"]):
            return "reference_patent", 0.86
        if any(token in file_name for token in ["背景", "notes", "说明"]):
            return "background_notes", 0.72
        if any(token in file_name for token in ["交底书", "docx"]):
            return "template", 0.74
        return "source_project_material", 0.68

    def _build_document_ast(self, source_inventory: Dict[str, Any]) -> Dict[str, Any]:
        documents = []
        for source in source_inventory["sources"]:
            path = self.workspace / source["relative_path"]
            blocks = self._parse_source_blocks(path, source)
            source["parser"] = self._parser_name(path)
            source["block_count"] = len(blocks)
            source["parse_status"] = "success" if blocks else "empty"
            documents.append(
                {
                    "document_id": source["source_id"],
                    "file_name": source["file_name"],
                    "role": source["role"],
                    "blocks": blocks,
                }
            )
        return {"schema_version": "1.0", "documents": documents}

    def _parse_source_blocks(self, path: Path, source: Dict[str, Any]) -> List[Dict[str, Any]]:
        suffix = path.suffix.lower()
        if suffix in {".md", ".txt", ".json"}:
            content = path.read_text(encoding="utf-8", errors="ignore")
            return self._blocks_from_text(content, source)
        if suffix == ".pdf":
            return self._blocks_from_text(self._extract_pdf_text(path), source)
        if suffix == ".docx":
            return self._blocks_from_text(self._extract_docx_text(path), source)
        return []

    def _parser_name(self, path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            return "pdfplumber+pypdf"
        if suffix == ".docx":
            return "python-docx"
        if suffix in {".md", ".txt", ".json"}:
            return "plain-text"
        return "unknown"

    def _blocks_from_text(self, content: str, source: Dict[str, Any]) -> List[Dict[str, Any]]:
        blocks: List[Dict[str, Any]] = []
        for block_index, raw_line in enumerate(content.splitlines(), start=1):
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("#"):
                title = re.sub(r"^#+\s*", "", line)
                blocks.append(self._ast_block(source, block_index, "section", title, title))
                continue
            if len(line) <= 40 and any(token in line for token in ["技术领域", "背景技术", "发明内容", "附图", "实施方式", "审核"]):
                blocks.append(self._ast_block(source, block_index, "section", line, line))
                continue
            section_title = blocks[-1]["content"] if blocks and blocks[-1]["block_type"] == "section" else "正文"
            blocks.append(self._ast_block(source, block_index, "paragraph", section_title, line))
        return blocks

    def _extract_pdf_text(self, path: Path) -> str:
        pages: List[str] = []
        try:
            with pdfplumber.open(path) as pdf:
                for page in pdf.pages:
                    text = page.extract_text() or ""
                    if text.strip():
                        pages.append(text)
        except Exception:
            pages = []
        if pages:
            return "\n".join(pages)
        try:
            reader = PdfReader(str(path))
            fallback_pages = []
            for page in reader.pages:
                text = page.extract_text() or ""
                if text.strip():
                    fallback_pages.append(text)
            return "\n".join(fallback_pages)
        except Exception:
            return ""

    def _extract_docx_text(self, path: Path) -> str:
        try:
            document = Document(str(path))
            lines = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()]
            return "\n".join(lines)
        except Exception:
            return ""

    def _ast_block(self, source: Dict[str, Any], block_index: int, block_type: str, section_title: str, content: str) -> Dict[str, Any]:
        return {
            "block_id": f"{source['source_id']}-B{block_index:03d}",
            "block_type": block_type,
            "section_title": section_title,
            "content": content,
            "source_anchor": {
                "anchor_id": f"{source['source_id']}-A{block_index:03d}",
                "file_path": source["relative_path"],
                "file_type": source["file_type"],
                "section_title": section_title,
                "block_id": f"{source['source_id']}-B{block_index:03d}",
                "paragraph_index": block_index,
                "page_no": 1,
                "excerpt": content[:160],
                "confidence": source["confidence"],
            },
        }

    def _build_reference_style_profile(self, document_ast: Dict[str, Any]) -> Dict[str, Any]:
        profile = json.loads(json.dumps(DEFAULT_STYLE_PROFILE))
        patent_blocks = [
            block
            for document in document_ast["documents"]
            if document["role"] == "reference_patent"
            for block in document["blocks"]
            if block["block_type"] == "paragraph" and self._is_style_candidate(block["content"])
        ]
        if patent_blocks:
            excerpts = [block["content"] for block in patent_blocks[:5]]
            profile["extracted_examples"] = excerpts[:3]
            profile["patent_references"] = self._extract_reference_patent_numbers(document_ast)
            if any("下面对照附图" in text for text in excerpts):
                profile["required_patterns"]["opening_sentence"] = "下面对照附图"
            if any("包括以下步骤" in text for text in excerpts):
                profile["required_patterns"]["step_overview_sentence"] = "本实施例提供的一种……方法，包括以下步骤："
            profile["generation_mode"] = "phase_0_extracted_with_default_fallback"
        return profile

    def _extract_reference_patent_numbers(self, document_ast: Dict[str, Any]) -> List[Dict[str, str]]:
        references = []
        seen = set()
        for document in document_ast.get("documents", []):
            if document.get("role") != "reference_patent":
                continue
            patent_title = self._extract_reference_patent_title(document)
            for block in document.get("blocks", []):
                text = block.get("content", "")
                for match in re.findall(r"CN\s?\d{9,}\s?[A-Z]?", text):
                    normalized = re.sub(r"\s+", "", match)
                    if normalized in seen:
                        continue
                    seen.add(normalized)
                    references.append({"publicationNumber": normalized, "title": patent_title or self._short(text, 36)})
        return references[:5]

    def _extract_reference_patent_title(self, document: Dict[str, Any]) -> str:
        blocks = document.get("blocks", [])
        for index, block in enumerate(blocks):
            text = re.sub(r"\s+", " ", str(block.get("content") or "")).strip()
            if not text:
                continue
            if "发明名称" in text:
                candidate = text.split("发明名称", 1)[-1].strip(" ：:-")
                if self._looks_like_patent_title(candidate):
                    return self._short(candidate, 40)
                if index + 1 < len(blocks):
                    next_text = re.sub(r"\s+", " ", str(blocks[index + 1].get("content") or "")).strip()
                    if self._looks_like_patent_title(next_text):
                        return self._short(next_text, 40)
        for block in blocks:
            text = re.sub(r"\s+", " ", str(block.get("content") or "")).strip()
            if self._looks_like_patent_title(text):
                return self._short(text, 40)
        return ""

    def _looks_like_patent_title(self, text: str) -> bool:
        if not text or len(text) < 6 or len(text) > 60:
            return False
        if text.startswith("(") or text.startswith("CN") or "申请公布号" in text or "国家知识产权局" in text:
            return False
        return any(token in text for token in ["一种", "方法", "系统", "装置", "设备", "介质", "平台"])

    def _short(self, text: Any, limit: int) -> str:
        normalized = re.sub(r"\s+", " ", str(text or "")).strip()
        return normalized if len(normalized) <= limit else normalized[: limit - 1] + "…"

    def _is_style_candidate(self, text: str) -> bool:
        normalized = re.sub(r"\s+", " ", text or "").strip()
        if len(normalized) < 12:
            return False
        noise_prefixes = ["(19)", "(12)", "(10)", "国家知识产权局", "申请公布号", "发明专利申请"]
        if any(normalized.startswith(prefix) for prefix in noise_prefixes):
            return False
        if re.fullmatch(r"[A-Z0-9\-\s]+", normalized):
            return False
        return any(token in normalized for token in ["本发明", "实施例", "附图", "步骤", "技术领域", "背景技术"]) 

    def _build_template_structure_rules(self, document_ast: Dict[str, Any]) -> Dict[str, Any]:
        template_rules = json.loads(json.dumps(DEFAULT_TEMPLATE_RULES))
        template_sections = []
        for document in document_ast["documents"]:
            if document["role"] != "template":
                continue
            for block in document["blocks"]:
                if block["block_type"] == "section":
                    template_sections.append(block["content"])
        if template_sections:
            template_rules["sections"] = [
                {"id": f"part_{index:02d}", "name": name, "required": True, "order": index}
                for index, name in enumerate(template_sections, start=1)
            ]
            template_rules["generation_mode"] = "phase_0_extracted_with_default_fallback"
        return template_rules

    def _build_compliance_rules(self, document_ast: Dict[str, Any]) -> Dict[str, Any]:
        rules = []
        seen = set()
        for document in document_ast["documents"]:
            if document["role"] != "compliance_spec":
                continue
            for block in document["blocks"]:
                if block["block_type"] != "paragraph":
                    continue
                text = self._normalize_compliance_rule(block["content"])
                if not text or text in seen:
                    continue
                seen.add(text)
                rules.append(
                    {
                        "rule_id": f"CR-{len(rules)+1:03d}",
                        "text": text,
                        "source_anchor": block["source_anchor"],
                    }
                )
        if not rules:
            rules.append(
                {
                    "rule_id": "CR-001",
                    "text": "参考专利只允许作为风格样本，不得作为技术事实来源。",
                    "source_anchor": {"anchor_id": "builtin-default", "file_path": "builtin", "excerpt": "DEFAULT_TEMPLATE_RULES"},
                }
            )
        return {"schema_version": "1.0", "rules": rules}

    def _normalize_compliance_rule(self, text: str) -> str:
        normalized = re.sub(r"\s+", " ", text or "").strip(" ：:;；，,")
        if len(normalized) < 8:
            return ""
        if normalized in {"是", "否", "无", "有"}:
            return ""
        if re.fullmatch(r"[一二三四五六七八九十0-9（）()、.\-]+", normalized):
            return ""
        return normalized

    def _build_run_manifest_json(self, manifest_updates: Dict[str, Any], artifacts: List[str]) -> Dict[str, Any]:
        merged_manifest = {**self.manifest, **manifest_updates}
        return {
            "schema_version": "1.0",
            "manifest_type": "patent_workflow_run_manifest",
            "current_phase": "phase_0",
            "phase_status": {
                "phase_0": "success",
            },
            "state": merged_manifest,
            "artifacts": [
                str(Path(path).relative_to(self.workspace)) if Path(path).is_absolute() else path
                for path in artifacts
            ],
        }
