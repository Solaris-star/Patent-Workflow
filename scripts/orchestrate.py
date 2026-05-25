#!/usr/bin/env python3
"""
Patent Workflow Orchestrator — 专利工作流主编排器。

核心设计：
- 状态机驱动，阶段推进由代码强制执行，Agent 不介入阶段选择
- 每阶段前自动验证 HANDOFF_CONTRACT，失败则硬阻断（exit 1）
- 每阶段后自动运行门禁，失败则硬阻断
- 支持 --dry-run（只打印不执行）、--step（单步调试）、--batch-mode（非交互）
- 支持状态快照（每阶段前自动备份）
- 支持 trace log（全程操作留痕）

使用方式：
    # 冷启动（从阶段0开始）
    python orchestrate.py --workspace . --manifest artifacts/run_manifest.md --from-phase 0

    # 从阶段5恢复（阶段2已完成候选挖掘与内部专利复核，阶段3已确认题目）
    python orchestrate.py --workspace . --manifest artifacts/run_manifest.md --from-phase 5

    # 只验证当前状态，不推进
    python orchestrate.py --workspace . --manifest artifacts/run_manifest.md --validate-only

    # 单步调试（每阶段暂停等待确认）
    python orchestrate.py --workspace . --manifest artifacts/run_manifest.md --from-phase 2 --step

    # 非交互模式（测试用，所有用户确认使用默认值）
    python orchestrate.py --workspace . --manifest artifacts/run_manifest.md --batch-mode
"""

import os
import sys
import json
import shutil
import argparse
import traceback
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

# 将当前脚本目录加入路径，以便导入 validators 和 executors
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from validators.preflight_validator import PreflightValidator
from validators.handoff_validator import HandoffValidator, load_manifest
from validators.gate_runner import GateRunner
from executors.phase_0_executor import PhaseExecutor as Phase0Executor

# ── 阶段定义 ──────────────────────────────────

STAGES = [
    {
        "id": "phase_0",
        "name": "材料预处理与运行清单初始化",
        "executor": "preprocess",
        "needs_user_input": False,
    },
    {
        "id": "phase_1",
        "name": "范围确认",
        "executor": None,
        "needs_user_input": True,
        "user_prompt": "本轮准备写哪些领域的专利？（可指定领域，或留空由系统推荐）",
        "default_response": "",
        "manifest_field": "domain_scope",
    },

    {
        "id": "phase_2",
        "name": "候选专利挖掘、查新与内部专利复核",
        "executor": None,
        "needs_user_input": False,
        "gate_critical": True,
        "agent_driven": True,  # Agent 直接使用 web_search / smart-search 执行，不走脚本转发
    },
    {
        "id": "phase_3",
        "name": "方向与题目收敛",
        "executor": None,
        "needs_user_input": True,
        "user_prompt": "请确认推荐方向和专利题目（或提出修改意见）",
        "default_response": "确认",
        "manifest_fields": ["selected_direction", "patent_title", "phase_03_confirmation"],
    },
    {
        "id": "phase_4",
        "name": "内部专利复核",
        "executor": "patent_review",
        "needs_user_input": False,
        "gate_critical": True,
    },
    {
        "id": "phase_5",
        "name": "正文草稿撰写",
        "executor": "modular_writer",
        "agent_driven": True,
        "needs_user_input": False,
        "gate_critical": True,
    },
    {
        "id": "phase_6",
        "name": "一致性审计",
        "executor": "consistency_audit",
        "needs_user_input": False,
        "gate_critical": True,
    },
    {
        "id": "phase_7",
        "name": "IPR模拟审查",
        "executor": "ipr_review",
        "needs_user_input": False,
        "gate_critical": True,
    },
    {
        "id": "phase_8",
        "name": "审后修订与复审闭环",
        "executor": "revision",
        "needs_user_input": False,
        "gate_critical": True,
    },
    {
        "id": "phase_9",
        "name": "最终导出与交付",
        "executor": "delivery",
        "needs_user_input": False,
        "gate_critical": True,
    },
]


class Orchestrator:
    """专利工作流编排器。"""

    def __init__(
        self,
        workspace: Path,
        manifest_path: Path,
        from_phase: str = "phase_0",
        batch_mode: bool = False,
        step_mode: bool = False,
        dry_run: bool = False,
        validate_only: bool = False,
        user_timeout: int = 1800,  # 30分钟超时
        domain_scope: str = "",
        local_project_paths: Optional[List[str]] = None,
    ):
        self.workspace = Path(workspace)
        self.manifest_path = Path(manifest_path)
        self.from_phase = self._normalize_phase_id(from_phase)
        self.batch_mode = batch_mode
        self.step_mode = step_mode
        self.dry_run = dry_run
        self.validate_only = validate_only
        self.user_timeout = user_timeout
        self.trace_log: List[Dict[str, Any]] = []
        self.snapshot_dir = self.workspace / "artifacts" / "snapshots"
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)

        self._bootstrap_manifest_if_needed()

        # 加载 manifest
        self.manifest = load_manifest(self.manifest_path)
        self._apply_cli_phase_1_inputs(domain_scope, local_project_paths)

    def _apply_cli_phase_1_inputs(self, domain_scope: str, local_project_paths: Optional[List[str]]) -> None:
        """允许 webchat/CI 通过 CLI 预填 Phase 1，避免交互提示卡住。"""
        if domain_scope and not self._phase_1_scope_ready():
            self.manifest.update(self._classify_phase_1_scope(domain_scope))
        if local_project_paths is not None:
            paths = [path for path in local_project_paths if path]
            self.manifest["phase_1_local_project_input"] = ", ".join(paths)
            self.manifest["phase_02_discovery_inputs"] = ["online_search", *( ["local_project"] if paths else [] )]
            if paths:
                self.manifest["local_project_paths"] = paths
                self.manifest["phase_02_local_project_mode"] = "enabled"
            else:
                self.manifest.pop("local_project_paths", None)
                self.manifest["phase_02_local_project_mode"] = "disabled"

    def _normalize_phase_id(self, phase: str) -> str:
        """兼容 --from-phase 0 和 --from-phase phase_0 两种写法。"""
        phase_text = str(phase)
        return phase_text if phase_text.startswith("phase_") else f"phase_{phase_text}"

    def _bootstrap_manifest_if_needed(self) -> None:
        """当 markdown manifest 缺失但 Phase 0 已初始化时，从 run_manifest.json 自愈补齐。"""
        if self.manifest_path.exists():
            return
        run_manifest_json_path = self.workspace / "artifacts" / "run_manifest.json"
        fingerprints_path = self.workspace / "artifacts" / "preprocess" / "source_fingerprints.json"
        notes_path = self.workspace / "artifacts" / "preprocess" / "phase_00_preprocess_notes.md"
        if not run_manifest_json_path.exists():
            return
        try:
            payload = json.loads(run_manifest_json_path.read_text(encoding="utf-8"))
        except Exception:
            return
        if not (fingerprints_path.exists() and notes_path.exists()):
            return
        if not isinstance(payload, dict):
            return
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(self._render_manifest_markdown(payload), encoding="utf-8")

    def _render_manifest_markdown(self, manifest: Dict[str, Any]) -> str:
        lines = [
            "# Patent Workflow Run Manifest",
            "",
            "## Auto Reconstructed Manifest",
            "",
        ]
        for key, value in manifest.items():
            if isinstance(value, (dict, list)):
                rendered = json.dumps(value, ensure_ascii=False)
            else:
                rendered = value
            lines.append(f"- `{key}`: {rendered}")
        lines.append("")
        return "\n".join(lines)

    def _phase_0_cache_reusable(self) -> bool:
        """判断 Phase 0 是否已完成且源材料未变化，可在默认启动时跳过。"""
        if self.manifest.get("force_preprocess") or self.manifest.get("refresh_preprocess"):
            return False

        executor = Phase0Executor("phase_0", self.workspace, self.manifest)
        fingerprints_path = self.workspace / "artifacts" / "preprocess" / "source_fingerprints.json"
        notes_path = self.workspace / "artifacts" / "preprocess" / "phase_00_preprocess_notes.md"
        run_manifest_json_path = self.workspace / "artifacts" / "run_manifest.json"
        if not executor._preprocess_cache_ready(fingerprints_path, notes_path, run_manifest_json_path):
            return False

        stored_fingerprints = self._load_phase_0_stored_fingerprints(fingerprints_path)
        if not stored_fingerprints:
            return False

        manifest_fingerprints = self.manifest.get("source_fingerprints")
        if isinstance(manifest_fingerprints, list) and manifest_fingerprints != stored_fingerprints:
            return False

        current_metadata = self._phase_0_source_metadata(executor)
        stored_metadata = self._phase_0_fingerprint_metadata(stored_fingerprints)
        return current_metadata == stored_metadata

    def _load_phase_0_stored_fingerprints(self, fingerprints_path: Path) -> List[Dict[str, Any]]:
        """读取 Phase 0 已保存指纹；失败时视为不可复用。"""
        try:
            payload = json.loads(fingerprints_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        sources = payload.get("sources")
        return sources if isinstance(sources, list) else []

    def _phase_0_source_metadata(self, executor: Phase0Executor) -> List[Dict[str, Any]]:
        """只用 path/size/mtime 快速判断源文件是否变化，避免启动时重复 sha256。"""
        metadata: List[Dict[str, Any]] = []
        for path in executor._discover_source_files():
            stat = path.stat()
            metadata.append(
                {
                    "path": path.name,
                    "relative_path": str(path.relative_to(self.workspace)),
                    "extension": path.suffix.lower(),
                    "size": stat.st_size,
                    "modified_at": int(stat.st_mtime),
                }
            )
        return metadata

    def _phase_0_fingerprint_metadata(self, fingerprints: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """从完整指纹中提取无需读文件正文的变更判定字段。"""
        fields = ("path", "relative_path", "extension", "size", "modified_at")
        metadata: List[Dict[str, Any]] = []
        for item in fingerprints:
            if isinstance(item, dict):
                metadata.append({field: item.get(field) for field in fields})
        return metadata

    def _resolve_start_phase(self) -> str:
        """默认从 phase_0 启动时，已初始化工作区自动跳过 P0。

        ⚠️ 当 --from-phase 0 时（fresh start 意图），会清除 Phase 1 领域数据，
        确保用户必须重新输入领域范围，不静默复用上一轮结果。
        同时创建新的过程产物目录，归档旧产物。
        """
        if self.from_phase != "phase_0" or self.dry_run or self.validate_only:
            return self.from_phase
        # Fresh start: 创建本轮产物目录
        self._ensure_run_dir(fresh=True)
        if self._phase_0_cache_reusable():
            # Fresh start: 清除上一轮的 Phase 1 领域数据，强制重新询问
            self._reset_phase_1_for_fresh_start()
            self._log(
                "phase_0_auto_skipped",
                {"reason": "preprocess_cache_ready_and_source_fingerprints_match", "next_phase": "phase_1"},
            )
            print("⏭️  Phase 0 已初始化且源材料未变化，自动复用预处理产物，从 phase_1 开始")
            return "phase_1"
        return self.from_phase

    def _reset_phase_1_for_fresh_start(self) -> None:
        """清除 manifest 中 Phase 1 相关字段，确保 fresh start 时重新询问领域。"""
        phase_1_fields = [
            "domain_scope",
            "idea_maturity",
            "phase_02_mode",
            "phase_1_user_input",
            "phase_1_local_project_input",
            "local_project_paths",
            "phase_02_local_project_mode",
            "phase_02_discovery_inputs",
            "selected_direction",
            "selected_title",
            "recommended_direction",
        ]
        cleared = []
        for field in phase_1_fields:
            if field in self.manifest:
                del self.manifest[field]
                cleared.append(field)
        if cleared:
            self._log("phase_1_reset_for_fresh_start", {"cleared_fields": cleared})
            print(f"   🧹 Fresh start: 已清除上一轮领域数据 ({', '.join(cleared)})")

    # ── 过程产物目录管理 ─────────────────────

    @property
    def run_dir(self) -> Path:
        """本轮过程产物根目录。每轮 --from-phase 0 创建新目录，Phase 3 后以专利名命名。"""
        rd = self.manifest.get("run_dir", "")
        if rd:
            p = Path(rd)
            if not p.is_absolute():
                p = self.workspace / p
            return p
        return self.workspace / "artifacts" / "runs" / "_current"

    def _ensure_run_dir(self, fresh: bool = False) -> Path:
        """确保本轮产物目录存在。fresh=True 时创建新目录并归档旧目录。"""
        runs_base = self.workspace / "artifacts" / "runs"
        runs_base.mkdir(parents=True, exist_ok=True)

        if fresh:
            # 归档上一轮的 _current → 时间戳目录
            old_current = runs_base / "_current"
            if old_current.exists():
                archive_ts = datetime.now().strftime("%Y%m%d-%H%M%S")
                archive_path = runs_base / f"_archived_{archive_ts}"
                old_current.rename(archive_path)
                self._log("run_dir_archived", {"from": str(old_current), "to": str(archive_path)})
                print(f"   📦 上轮产物已归档: {archive_path.name}")

            # 创建本轮目录
            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            new_dir = runs_base / ts
            new_dir.mkdir(parents=True, exist_ok=True)

            # 创建 _current 软链接方便访问
            if old_current.is_symlink() or (not old_current.exists()):
                if old_current.is_symlink():
                    old_current.unlink()
                old_current.symlink_to(new_dir.name)

            self.manifest["run_dir"] = str(new_dir)
            self.manifest["run_dir_name"] = new_dir.name
            self._log("run_dir_created", {"run_dir": str(new_dir)})
            print(f"   📂 本轮产物目录: {new_dir.name}")
            return new_dir
        else:
            # 非 fresh：确保目录存在
            rd = self.run_dir
            rd.mkdir(parents=True, exist_ok=True)
            return rd

    def _rename_run_dir_for_title(self, title: str) -> None:
        """Phase 3 确认方向后，将产物目录重命名为专利标题。"""
        if not title:
            return
        old_dir = self.run_dir
        # 清理标题中的文件系统非法字符
        safe_title = re.sub(r'[\\/:*?"<>|\s]+', '_', title.strip()).strip('_')
        if len(safe_title) > 80:
            safe_title = safe_title[:80]
        if not safe_title:
            return

        new_dir = old_dir.parent / safe_title
        if new_dir.exists():
            # 标题冲突：追加时间戳
            new_dir = old_dir.parent / f"{safe_title}_{datetime.now().strftime('%H%M%S')}"

        try:
            old_dir.rename(new_dir)
            self.manifest["run_dir"] = str(new_dir)
            self.manifest["run_dir_name"] = new_dir.name
            self._log("run_dir_renamed", {"from": old_dir.name, "to": new_dir.name})
            print(f"   📂 产物目录已命名: {new_dir.name}")
        except OSError as e:
            self._log("run_dir_rename_failed", {"error": str(e)})
            print(f"   ⚠️ 目录重命名失败: {e}")

    # ── Trace 日志 ─────────────────────────────
    def _log(self, action: str, detail: Dict[str, Any]):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "detail": detail,
        }
        self.trace_log.append(entry)
        trace_path = self.run_dir / "orchestrator_trace.json"
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        with open(trace_path, "w", encoding="utf-8") as f:
            json.dump(self.trace_log, f, ensure_ascii=False, indent=2)

    def _count_candidate_directions(self) -> int:
        """读取 Phase 2 candidate pool 中的候选方向数量。"""
        candidate_path = self.run_dir / "prior_art" / "phase_02_patent_candidate_pool.json"
        if not candidate_path.exists():
            return 0
        try:
            with open(candidate_path) as f:
                pool = json.load(f)
            return len(pool.get("candidate_directions", []))
        except Exception:
            return 0

    def _display_candidate_directions(self) -> None:
        """Phase 3 候选方向列表展示。从 research_pack 读取并格式化输出。"""
        # Try research_pack first (richer data), fall back to candidate_pool
        rp_path = self.run_dir / "research" / "phase_02_research_pack.json"
        cp_path = self.run_dir / "prior_art" / "phase_02_patent_candidate_pool.json"
        candidates = []
        source = ""
        for path in [rp_path, cp_path]:
            if path.exists():
                try:
                    with open(path) as f:
                        data = json.load(f)
                    candidates = data.get("candidate_directions", [])
                    if candidates:
                        source = path.name
                        break
                except Exception:
                    pass
        if not candidates:
            print("   ⚠️ 未找到候选方向列表（Phase 2 产物缺失 candidate_directions）")
            return

        # Domain emoji mapping
        domain_emoji = {
            "cross_domain": "🔗", "autonomous_driving": "🚗",
            "smart_cockpit": "🚘", "general_ai": "🤖",
            "cross": "🔗", "ad": "🚗", "cockpit": "🚘", "ai": "🤖",
        }

        print(f"\n   📋 候选专利方向（来源: {source}）：")
        print(f"   {'─' * 58}")
        for idx, c in enumerate(candidates, 1):
            if not isinstance(c, dict):
                continue
            title = c.get("title", c.get("direction_name", ""))[:60]
            domain = c.get("domain", "")
            score = c.get("total_score", c.get("score", "?"))
            problem = c.get("problem", "")[:70]
            improvement = c.get("improvement", "")[:80]
            patent_refs = c.get("patent_refs", [])
            non_patent_sources = c.get("non_patent_sources", [])
            emoji = domain_emoji.get(domain, "📌")

            circled = chr(0x245F + idx)  # ① ② ③ ...
            print(f"   {circled} {emoji} {title}")
            print(f"      得分: {score} | 领域: {domain}")
            if problem:
                print(f"      问题: {problem}")
            if improvement:
                print(f"      改良: {improvement}")
            if patent_refs:
                print(f"      参考专利: {', '.join(patent_refs[:3])}")
            if non_patent_sources:
                print(f"      非专利信源: {', '.join(non_patent_sources[:2])}")
            evidence_urls = c.get("evidence_urls", [])
            if evidence_urls:
                for eu in evidence_urls[:2]:
                    print(f"      证据: {eu}")
            print()

        print(f"   {'─' * 58}")
        print(f"   共 {len(candidates)} 个候选方向")
        # Show recommended
        rec = self.manifest.get("recommended_direction_detail", {})
        if isinstance(rec, dict) and rec.get("title"):
            print(f"   ⭐ 推荐: {rec['title']}")
            if rec.get("reason"):
                print(f"      {rec['reason']}")
        print()

    def _check_domain_artifact_consistency(self) -> Dict[str, Any]:
        """检查 manifest.domain_scope 与下游 artifacts 的领域一致性。
        
        当下游关键 artifact（evidence_pack, research_pack）中的领域标记与
        当前 manifest.domain_scope 不一致时，返回不一致警告。
        这防止 Phase 5 基于旧领域数据生成草稿。
        """
        result = {"consistent": True, "mismatches": []}
        current_scope = (self.manifest.get("domain_scope") or "").strip()
        if not current_scope:
            return result

        # Check evidence_pack domain
        ep_path = self.run_dir / "prior_art" / "phase_02_evidence_pack.json"
        if ep_path.exists():
            try:
                with open(ep_path) as f:
                    ep = json.load(f)
                ep_scope = ep.get("domain_scope", "")
                if ep_scope and ep_scope != current_scope:
                    result["consistent"] = False
                    result["mismatches"].append(f"evidence_pack domain_scope '{ep_scope}' != manifest '{current_scope}'")
            except Exception:
                pass

        # Check research_pack domain  
        rp_path = self.run_dir / "research" / "phase_02_research_pack.json"
        if rp_path.exists():
            try:
                with open(rp_path) as f:
                    rp = json.load(f)
                rp_scope = rp.get("research_scope_key", "")
                # Loose match: check if key terms overlap
                if rp_scope and not any(term in current_scope for term in rp_scope.replace('_', ' ').split()):
                    pass  # Too strict to hard-fail on this; just note it
            except Exception:
                pass

        return result

    def _phase_1_scope_ready(self) -> bool:
        """判断 Phase 1 是否已有可复用范围，避免恢复运行时重复等待用户输入。"""
        scope = str(self.manifest.get("domain_scope") or "").strip()
        if not scope or scope == "待系统推荐":
            return False
        return str(self.manifest.get("idea_maturity") or "").strip() != "" and str(self.manifest.get("phase_02_mode") or "").strip() != ""

    def _phase_1_local_project_ready(self) -> bool:
        """判断 Phase 1 是否已经确认过本地项目/文档入口。"""
        return (
            "phase_1_local_project_input" in self.manifest
            or "local_project_paths" in self.manifest
            or "phase_02_local_project_mode" in self.manifest
            or "phase_02_discovery_inputs" in self.manifest
        )

    def _parse_local_project_paths(self, user_response: str) -> List[str]:
        """解析用户输入的本地项目/文档路径；留空或否定词表示仅联网挖掘。"""
        raw = (user_response or "").strip()
        if not raw:
            return []
        normalized = re.sub(r"\s+", "", raw.lower())
        if normalized in {"无", "没有", "不需要", "否", "no", "none", "skip", "直接联网", "直接搜索", "联网搜索"}:
            return []
        parts = re.split(r"[\n,，;；]+", raw)
        paths: List[str] = []
        for part in parts:
            path = part.strip().strip('"\'')
            if path and path not in paths:
                paths.append(path)
        return paths

    def _collect_phase_1_local_project_input(self) -> None:
        """询问用户是否有本地项目/文档需要转化为专利点。"""
        if self._phase_1_local_project_ready():
            print("   ⏭️  Phase 1 已确认本地项目入口，跳过重复询问")
            return
        response = self._prompt_user(
            "是否有本地项目或文档需要转化为专利点？如有请输入项目/文档路径（多个用逗号分隔）；没有则直接回车，Phase 2 将仅联网搜索。",
            "",
        )
        paths = self._parse_local_project_paths(response)
        self.manifest["phase_1_local_project_input"] = response
        self.manifest["phase_02_discovery_inputs"] = ["online_search", *( ["local_project"] if paths else [] )]
        if paths:
            self.manifest["local_project_paths"] = paths
            self.manifest["phase_02_local_project_mode"] = "enabled"
            print(f"   📁 本地项目/文档挖掘已启用: {', '.join(paths)}")
        else:
            self.manifest.pop("local_project_paths", None)
            self.manifest["phase_02_local_project_mode"] = "disabled"
            print("   🌐 未提供本地项目路径，Phase 2 将仅使用联网搜索挖掘专利点")
        self._log("phase_1_local_project_collected", {"paths": paths, "enabled": bool(paths)})

    def _merge_executor_trace(self, phase_id: str, trace_log: Any):
        """将执行器内存 trace 合并到 orchestrator trace，避免长阶段看起来停在上一阶段。"""
        if not isinstance(trace_log, list):
            return
        for entry in trace_log:
            if not isinstance(entry, dict):
                continue
            detail = dict(entry)
            action = str(detail.pop("action", "executor_trace"))
            detail.setdefault("phase", detail.get("phase") or phase_id)
            self._log(action, detail)

    # ── 状态快照 ───────────────────────────────
    def _take_snapshot(self, phase_id: str):
        """在进入阶段前备份当前状态。"""
        snapshot_name = f"snapshot_{phase_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        snapshot_path = self.snapshot_dir / snapshot_name
        snapshot_path.mkdir(parents=True, exist_ok=True)

        # 备份 manifest
        if self.manifest_path.exists():
            shutil.copy2(self.manifest_path, snapshot_path / "run_manifest.md")

        manifest_only_phases = {"phase_0", "phase_1"}
        if phase_id in manifest_only_phases:
            self._log("snapshot_taken", {"phase": phase_id, "path": str(snapshot_path), "mode": "manifest_only"})
            print(f"📸 状态快照已保存: {snapshot_path}（轻量，仅 manifest）")
            return snapshot_path

        # 备份 artifacts（只备份当前阶段相关的）
        artifacts_dir = self.run_dir
        if artifacts_dir.exists():
            for subdir in ["research", "prior_art", "draft", "revision"]:
                src = artifacts_dir / subdir
                if src.exists():
                    dst = snapshot_path / subdir
                    shutil.copytree(src, dst, dirs_exist_ok=True)

        self._log("snapshot_taken", {"phase": phase_id, "path": str(snapshot_path), "mode": "artifacts_subset"})
        print(f"📸 状态快照已保存: {snapshot_path}")
        return snapshot_path

    # ── 恢复状态 ───────────────────────────────
    def _restore_snapshot(self, snapshot_path: Path):
        """从快照恢复状态。"""
        manifest_backup = snapshot_path / "run_manifest.md"
        if manifest_backup.exists():
            shutil.copy2(manifest_backup, self.manifest_path)
            self.manifest = load_manifest(self.manifest_path)
        self._log("snapshot_restored", {"path": str(snapshot_path)})
        print(f"📸 状态已从快照恢复: {snapshot_path}")

    # ── 用户输入 ───────────────────────────────
    def _prompt_user(self, prompt: str, default: str = "") -> str:
        """获取用户输入，支持 batch-mode 和超时。"""
        if self.batch_mode:
            print(f"🤖 [batch-mode] 使用默认值: '{default}'")
            self._log("user_input_batch", {"prompt": prompt, "response": default})
            return default

        print(f"\n⏸️  需要用户确认:")
        print(f"   {prompt}")
        if default:
            print(f"   [默认: {default}] (按 Enter 使用默认值)")

        if self.step_mode:
            print("   [step-mode] 按 Enter 继续，或输入 'skip' 跳过本阶段，或输入 'abort' 终止")

        try:
            import signal

            def timeout_handler(signum, frame):
                raise TimeoutError(f"用户输入超时 (> {self.user_timeout}s)")

            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(self.user_timeout)

            response = input("   > ").strip()
            signal.alarm(0)  # 取消超时

            if not response and default:
                response = default

            self._log("user_input", {"prompt": prompt, "response": response})
            return response

        except TimeoutError as e:
            print(f"   ⚠️  {e}，使用默认值: '{default}'")
            self._log("user_input_timeout", {"prompt": prompt, "default_used": default})
            return default
        except KeyboardInterrupt:
            print("\n   ❌ 用户中断")
            self._log("user_input_interrupt", {"prompt": prompt})
            sys.exit(130)
        except Exception as e:
            print(f"   ⚠️ 输入异常: {e}，使用默认值: '{default}'")
            self._log("user_input_error", {"prompt": prompt, "error": str(e), "default_used": default})
            return default

    def _classify_phase_1_scope(self, user_response: str) -> Dict[str, str]:
        """把阶段 1 的自然语言输入归类为明确题目、模糊领域或完全无想法。

        目标是：用户给出模糊行业时直接进入 Phase 2 做创新挖掘；只有完全没有
        领域边界时才进入系统推荐模式，避免把“待系统推荐”当作真实查询词。
        """
        raw = (user_response or "").strip()
        normalized = re.sub(r"\s+", "", raw.lower())
        no_idea_values = {
            "",
            "无",
            "没有",
            "没有想法",
            "没想法",
            "不知道",
            "不清楚",
            "随便",
            "你推荐",
            "系统推荐",
            "待系统推荐",
            "帮我推荐",
            "没什么想法",
            "没有具体想法",
        }
        vague_markers = (
            "没具体想法",
            "没有具体想法",
            "没idea",
            "没有idea",
            "帮我挖",
            "挖掘",
            "看看有什么",
            "找方向",
            "找创新点",
        )
        topic_markers = (
            "基于",
            "一种",
            "方法",
            "系统",
            "装置",
            "介质",
            "平台",
            "流程",
            "引擎",
        )

        if normalized in no_idea_values:
            return {
                "domain_scope": "待系统推荐",
                "fixed_topic_or_title": "",
                "idea_maturity": "no_idea",
                "phase_02_mode": "domain_recommendation",
                "phase_1_user_input": raw,
            }

        cleaned = raw
        for marker in vague_markers:
            cleaned = cleaned.replace(marker, "")
        cleaned = re.sub(r"[，,。；;：:\s]+$", "", cleaned).strip() or raw

        if any(marker in raw for marker in vague_markers):
            return {
                "domain_scope": cleaned,
                "fixed_topic_or_title": "",
                "idea_maturity": "vague_domain",
                "phase_02_mode": "broad_domain_discovery",
                "phase_1_user_input": raw,
            }

        if len(raw) >= 14 and any(marker in raw for marker in topic_markers):
            return {
                "domain_scope": raw,
                "fixed_topic_or_title": raw,
                "idea_maturity": "fixed_topic",
                "phase_02_mode": "topic_research",
                "phase_1_user_input": raw,
            }

        return {
            "domain_scope": raw,
            "fixed_topic_or_title": "",
            "idea_maturity": "vague_domain",
            "phase_02_mode": "broad_domain_discovery",
            "phase_1_user_input": raw,
        }

    # ── 预检 ─────────────────────────────────
    def _preflight(self) -> bool:
        """运行 Preflight 检查。"""
        if self.dry_run or self.validate_only:
            print("🔍 [dry-run/validate] Preflight 检查...")
        validator = PreflightValidator(self.workspace, self.manifest_path)
        passed, issues = validator.run()
        self._log("preflight", {"passed": passed, "issue_count": len(issues)})
        return passed

    def _mark_phase_running(self, phase_id: str) -> None:
        """阶段开始即持久化状态，避免长耗时执行器期间 UI 停留在上一阶段。"""
        if isinstance(self.manifest.get("phase_status"), str):
            try:
                self.manifest["phase_status"] = json.loads(self.manifest["phase_status"])
            except Exception:
                self.manifest["phase_status"] = {}
        status = self.manifest.get("phase_status")
        if not isinstance(status, dict):
            status = {}
            self.manifest["phase_status"] = status
        self.manifest["current_phase"] = phase_id
        status[phase_id] = "running"
        self._save_manifest()

    # ── 阶段执行 ───────────────────────────────
    def _run_phase(self, stage: Dict[str, Any]) -> bool:
        """执行单个阶段。返回是否成功。"""
        phase_id = stage["id"]
        phase_name = stage["name"]

        print(f"\n{'=' * 60}")
        print(f"🚀 阶段 {phase_id}: {phase_name}")
        print(f"{'=' * 60}")

        self._log("phase_start", {"phase": phase_id, "name": phase_name})
        self._mark_phase_running(phase_id)

        # 步骤 1: 状态快照
        if not self.dry_run and not self.validate_only:
            self._take_snapshot(phase_id)

        # 步骤 2: 用户输入（如果需要）
        if stage.get("needs_user_input"):
            prompt = stage.get("user_prompt", "请确认")
            default = stage.get("default_response", "")
            if phase_id == "phase_1" and self._phase_1_scope_ready():
                print("   ⏭️  Phase 1 已有范围输入，复用当前 domain_scope，跳过重复询问")
                user_response = str(self.manifest.get("phase_1_user_input") or self.manifest.get("domain_scope") or "")
                self._log("phase_1_scope_reused", {"response": user_response})
            else:
                user_response = self._prompt_user(prompt, default)
            if user_response.lower() in ("abort", "exit", "quit"):
                print("   🛑 用户终止 workflow")
                self._log("phase_user_abort", {"phase": phase_id})
                return False
            if user_response.lower() == "skip":
                print("   ⏭️  用户跳过本阶段（标记为 degraded）")
                self.manifest["degraded_run"] = True
                self.manifest.setdefault("skipped_phases", []).append(phase_id)
                self._save_manifest()
                return True
            manifest_field = stage.get("manifest_field")
            manifest_fields = stage.get("manifest_fields") or ([] if not manifest_field else [manifest_field])
            if manifest_fields:
                if phase_id == "phase_1" and manifest_field == "domain_scope":
                    scope_updates = self._classify_phase_1_scope(user_response)
                    self.manifest.update(scope_updates)
                    self._log("phase_1_scope_classified", scope_updates)
                    print(
                        "   🧭 输入分类: "
                        f"{scope_updates['idea_maturity']} / {scope_updates['phase_02_mode']} / "
                        f"domain_scope={scope_updates['domain_scope']}"
                    )
                    self._collect_phase_1_local_project_input()
                elif phase_id == "phase_3":
                    # 🆕 展示候选方向列表
                    self._display_candidate_directions()
                    confirmation = user_response or stage.get("default_response", "确认")
                    self.manifest["phase_03_confirmation"] = confirmation
                    # 如果在非交互模式下用户仅输入了默认确认，但此时还没有选定方向：
                    # 检查 manifest 中是否已有 selected_direction（来自上一轮或此前交互式设定）
                    if confirmation == "确认" and not self.manifest.get("selected_direction"):
                        # 尝试从 recommended_direction 或 candidate pool 中自动填充
                        selected = self.manifest.get("recommended_direction") or self.manifest.get("selected_title") or self.manifest.get("recommended_direction_detail", {}).get("title", "")
                        if isinstance(selected, str) and selected.strip():
                            self.manifest["selected_direction"] = selected.strip()
                            self.manifest["patent_title"] = selected.strip()
                        else:
                            # ⚠️ 关键安全阀：batch 模式下没有选定方向，拒绝自动推进
                            error_msg = (
                                "Phase 3 需要用户明确选择专利方向，但 batch 模式下未提供。"
                                "请用 --interactive 模式重新运行，或在 manifest 中设置 selected_direction 后从 Phase 3 恢复。"
                            )
                            print(f"❌ {error_msg}")
                            self._log("phase_3_blocked_no_direction", {
                                "phase": "phase_3",
                                "reason": "no selected_direction in batch mode",
                                "candidate_count": self._count_candidate_directions(),
                            })
                            sys.exit(2)
                    elif confirmation and confirmation != "确认":
                        self.manifest["selected_direction"] = confirmation
                        self.manifest["patent_title"] = confirmation
                    self._log("phase_3_confirmation_recorded", {"confirmation": confirmation, "selected_direction": self.manifest.get("selected_direction", "")})
                    # 将产物目录重命名为专利标题
                    title = self.manifest.get("patent_title") or self.manifest.get("selected_direction", "")
                    if title:
                        self._rename_run_dir_for_title(title)
                else:
                    for field in manifest_fields:
                        self.manifest[field] = user_response or stage.get("default_manifest_value", "待系统推荐")
                self._save_manifest()

        # 步骤 3: dry-run / validate-only 模式下到此为止
        if self.dry_run:
            print(f"   [dry-run] 本阶段应执行: {stage.get('executor') or '用户交互'}")
            self._log("phase_dry_run", {"phase": phase_id})
            return True

        if self.validate_only:
            print(f"   [validate-only] 跳过执行")
            self._log("phase_validate_only", {"phase": phase_id})
            return True

        # 步骤 4a: Agent 驱动阶段 — 检查产物是否已由 Agent 生成
        if stage.get("agent_driven"):
            agent_artifacts_ready = self._check_agent_artifacts(phase_id, stage)
            if agent_artifacts_ready:
                print(f"   ✅ Agent 已生成 {phase_id} 产物，跳过执行器")
                self.manifest.setdefault("phase_status", {})[phase_id] = "success"
                self._save_manifest()
            else:
                print(f"\n   🤖 {phase_id} 需要 Agent 原生执行（不走脚本转发）")
                print(f"   📋 请查看 SKILL.md 中的 Phase 2 Agent-Native 执行指南")
                print(f"   📂 产物写入后重新运行: python orchestrate.py --from-phase {phase_id} --workspace {self.workspace} --manifest {self.manifest_path}")
                self._log("phase_pending_agent", {"phase": phase_id})
                return False
        # 步骤 4b: 调用脚本执行器
        executor_name = stage.get("executor")
        if executor_name:
            # ⚠️ 领域一致性安全阀：Phase 5 执行前检查 manifest domain_scope 与
            #    evidence_pack / research_pack 的领域标记是否一致。
            #    防止因 domain_scope 变更后基于旧领域数据生成正文草稿。
            if phase_id == "phase_5":
                consistency = self._check_domain_artifact_consistency()
                if not consistency["consistent"]:
                    error_msg = (
                        f"❌ 领域不一致，Phase 5 拒绝执行:\n"
                        + "\n".join(f"   - {m}" for m in consistency["mismatches"])
                        + "\n   请更新 manifest.domain_scope 以匹配 Phase 2 产物，"
                        + "或删除旧 artifacts 后重新从 Phase 2 生成。"
                    )
                    print(error_msg)
                    self._log("phase_5_blocked_domain_mismatch", {
                        "phase": "phase_5",
                        "manifest_scope": self.manifest.get("domain_scope"),
                        "mismatches": consistency["mismatches"],
                    })
                    return False
            print(f"   🛠️  调用执行器: {executor_name}")
            result = self._run_executor(executor_name, phase_id)

            # 处理执行结果
            if result.status == "failed":
                print(f"   ❌ 执行器失败: {result.error}")
                self._log("phase_executor_failed", {"phase": phase_id, "error": result.error})
                return False

            if result.status == "degraded":
                print(f"   ⚠️ 执行器降级完成: {result.degraded_reason}")
                self.manifest["degraded_run"] = True
                degraded = self.manifest.get("degraded_phases")
                if not isinstance(degraded, list):
                    degraded = []
                    self.manifest["degraded_phases"] = degraded
                degraded.append(phase_id)

            # 更新 manifest
            self._merge_executor_trace(phase_id, result.trace_log)
            self.manifest.update(result.manifest_updates)
            # phase_status may be a JSON string from markdown parsing; coerce to dict
            if isinstance(self.manifest.get("phase_status"), str):
                try:
                    self.manifest["phase_status"] = json.loads(self.manifest["phase_status"])
                except Exception:
                    self.manifest["phase_status"] = {}
            self.manifest.setdefault("phase_status", {})[phase_id] = result.status
            self._save_manifest()
            if phase_id == "phase_2":
                self._print_phase_2_candidate_summary()

        # 步骤 5: 运行门禁
        if stage.get("gate_critical"):
            print(f"   🔒 运行门禁...")
            gate_runner = GateRunner(self.workspace, self.manifest_path)
            extra = {}
            if phase_id == "phase_9":
                final_docx_path = self.manifest.get("final_docx_path", "")
                deliver_dir = self.manifest.get("deliver_dir") or self.manifest.get("output_dir") or str(self.run_dir / "delivery")
                if final_docx_path:
                    try:
                        deliver_dir = str(Path(final_docx_path).parent)
                    except Exception:
                        pass
                patent_title = self.manifest.get("patent_title") or self._resolve_delivery_patent_title()
                extra = {
                    "deliver-dir": str(deliver_dir),
                    "patent-title": patent_title or "未命名专利",
                }
            gate_result = gate_runner.run(phase_id, extra)

            self.manifest["last_gate_result"] = gate_result.to_dict()
            self._save_manifest()

            if not gate_result.passed:
                if phase_id == "phase_2":
                    # Phase 2 gate is warnings-only. Print issues, let Phase 3 decide.
                    print(f"   ⚠️  Phase 2 门禁发现警告（不阻断），请用户在 Phase 3 确认")
                    self._log("phase_gate_warnings", {"phase": phase_id})
                else:
                    print(f"   ❌ 门禁未通过，阶段 {phase_id} 终止")
                    self._log("phase_gate_failed", {"phase": phase_id})
                    if stage.get("gate_critical"):
                        return False

            if phase_id == "phase_9":
                self._refresh_phase_9_delivery_package(deliver_dir, patent_title or "未命名专利")

        # 步骤 6: 保存状态
        self.manifest["current_phase"] = phase_id
        self.manifest["last_passed_gate"] = phase_id
        self._save_manifest()

        self._log("phase_end", {"phase": phase_id, "status": "success"})
        print(f"   ✅ 阶段 {phase_id} 完成")
        return True

    def _print_phase_2_candidate_summary(self):
        pack_path = self.run_dir / "research" / "phase_02_research_pack.json"
        if not pack_path.exists():
            return
        try:
            data = json.loads(pack_path.read_text(encoding="utf-8"))
        except Exception as e:
            self._log("phase_2_candidate_summary_failed", {"error": str(e)})
            return
        display_items = data.get("candidate_display_items") or []
        if isinstance(display_items, list) and display_items:
            print("\n   🧭 Phase 2 候选输出（合同字段）：")
            for idx, item in enumerate(display_items[:7], start=1):
                if not isinstance(item, dict):
                    continue
                print(f"   {idx}. 候选专利名称：{item.get('候选专利名称') or '未命名候选'}")
                print(f"      解决的问题：{item.get('解决的问题') or '未记录'}")
                print(f"      本候选改良点：{item.get('本候选改良点') or '未记录'}")
                print(f"      证据 URL：{item.get('证据 URL') or '未记录'}")
                print(f"      非专利热点信源：{item.get('非专利热点信源') or '未记录'}")
            print("   请从上述候选中选择一个，或说明要组合/调整哪些候选。\n")
            return

        directions = data.get("candidate_directions") or []
        if not isinstance(directions, list) or not directions:
            return
        print("\n   🧭 Phase 2 候选输出（兼容旧格式）：")
        for idx, direction in enumerate(directions[:7], start=1):
            if not isinstance(direction, dict):
                continue
            print(f"   {idx}. 候选专利名称：{direction.get('title', '未命名方向')}")
            print(f"      解决的问题：{direction.get('reference_patent_problem') or direction.get('problem') or '未记录'}")
            print(f"      本候选改良点：{direction.get('improvement_point') or direction.get('improvement') or '未记录'}")
            print(f"      证据 URL：{direction.get('evidence_url') or direction.get('reference_patent_url') or '未记录'}")
            print(f"      非专利热点信源：{direction.get('non_patent_hotspot_source') or direction.get('non_patent_hotspot') or '未记录'}")
        print("   请从上述候选中选择一个，或说明要组合/调整哪些候选。\n")


    def _resolve_delivery_patent_title(self) -> str:
        """为 Phase 9 门禁解析最终标题，避免回退成未命名专利。"""
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
            if not isinstance(data, dict):
                continue
            for key in ["patent_title", "project_name", "projectName", "selected_title"]:
                value = data.get(key)
                if isinstance(value, str) and value.strip() and value.strip() != "未命名专利":
                    return value.strip()
            direction = data.get("recommended_direction_detail") or data.get("recommended_direction")
            if isinstance(direction, dict):
                title = direction.get("title")
                if isinstance(title, str) and title.strip():
                    title = title.strip()
                    return title if title.endswith("系统") else f"{title}及系统"
        return "未命名专利"

    def _refresh_phase_9_delivery_package(self, deliver_dir: str, patent_title: str):
        """Phase 9 后置门禁会刷新健康报告；门禁通过后同步过程件和 ZIP。"""
        try:
            module = __import__("executors.phase_9_executor", fromlist=["PhaseExecutor"])
            executor_class = getattr(module, "PhaseExecutor")
            executor = executor_class("phase_9", self.workspace, self.manifest)
            deliver_path = Path(deliver_dir)
            docx_path = Path(self.manifest.get("final_docx_path") or deliver_path / f"{patent_title}技术交底书.docx")
            if not deliver_path.exists() or not docx_path.exists():
                self._log("phase_9_delivery_refresh_skipped", {"deliver_dir": str(deliver_path), "docx_path": str(docx_path)})
                return
            executor._copy_delivery_artifacts(deliver_path)
            zip_path = executor._create_ascii_safe_delivery_zip(deliver_path, docx_path, patent_title)
            self.manifest["delivery_zip_path"] = str(zip_path)
            self.manifest["delivery_zip_ascii_safe"] = True
            self._log("phase_9_delivery_refreshed", {"deliver_dir": str(deliver_path), "zip_path": str(zip_path)})
        except Exception as e:
            self._log("phase_9_delivery_refresh_failed", {"error": str(e)})
            print(f"   ⚠️ Phase 9 交付包同步失败: {e}")

    # ── 执行器路由 ───────────────────────────
    def _check_agent_artifacts(self, phase_id: str, stage: Dict[str, Any]) -> bool:
        """检查 agent-driven 阶段的产物是否已生成。"""
        from validators.handoff_validator import HANDOFF_RULES
        rules = HANDOFF_RULES.get(phase_id, {})
        required = rules.get("required_artifacts", [])
        if not required:
            return True  # 无产物要求，直接通过

        workspace = Path(self.workspace)
        missing = []
        for artifact in required:
            p = workspace / artifact
            if not p.exists():
                missing.append(artifact)

        if missing:
            print(f"   ⚠️  缺少 {len(missing)} 个产物: {', '.join(missing[:5])}")
            return False
        print(f"   ✅ {len(required)} 个产物齐全")
        return True

    def _run_executor(self, executor_name: str, phase_id: str) -> Any:
        """路由到对应的执行器。"""
        # 动态导入执行器模块
        try:
            module_path = f"executors.{phase_id}_executor"
            module = __import__(module_path, fromlist=["PhaseExecutor"])
            executor_class = getattr(module, "PhaseExecutor")
            executor = executor_class(phase_id, self.workspace, self.manifest)
            return executor.execute()
        except ImportError:
            # 如果专用执行器不存在，使用通用执行器
            print(f"   ⚠️ 专用执行器 {module_path} 不存在，使用通用执行器")
            from executors.base_executor import BaseExecutor

            class GenericExecutor(BaseExecutor):
                def _execute(self):
                    return self.run_generic(executor_name)

                def run_generic(self, name):
                    self._log("generic_executor", {"name": name})
                    # 这里可以添加通用执行逻辑
                    return self.__class__.ExecutorResult(
                        status="degraded",
                        degraded_reason=f"通用执行器占位: {name}，请实现专用执行器",
                    )

            executor = GenericExecutor(phase_id, self.workspace, self.manifest)
            return executor.execute()
        except Exception as e:
            print(f"   ❌ 执行器加载失败: {e}")
            traceback.print_exc()
            # 返回降级结果
            class FallbackResult:
                status = "failed"
                error = str(e)
                manifest_updates = {}
                trace_log = []
                degraded_reason = None

            return FallbackResult()

    # ── 保存 manifest ──────────────────────────
    def _save_manifest(self):
        """保存 manifest 到文件。"""
        # 这里简化处理：追加更新到文件末尾
        # 实际实现中应该用更结构化的方式
        with open(self.manifest_path, "a", encoding="utf-8") as f:
            f.write(f"\n\n# Orchestrator Update — {datetime.now().isoformat()}\n")
            for key, value in self.manifest.items():
                if isinstance(value, (dict, list)):
                    f.write(f"- `{key}`: {json.dumps(value, ensure_ascii=False)}\n")
                else:
                    f.write(f"- `{key}`: {value}\n")

    # ── 主入口 ─────────────────────────────────
    def run(self):
        """运行工作流。"""
        print("🏛️  Patent Workflow Orchestrator")
        print(f"   工作目录: {self.workspace}")
        print(f"   Manifest: {self.manifest_path}")
        print(f"   起始阶段: {self.from_phase}")
        print(f"   模式: {'dry-run' if self.dry_run else 'validate-only' if self.validate_only else 'batch' if self.batch_mode else 'interactive'}")

        effective_from_phase = self._resolve_start_phase()
        self._log("orchestrator_start", {
            "workspace": str(self.workspace),
            "from_phase": self.from_phase,
            "effective_from_phase": effective_from_phase,
            "mode": "dry-run" if self.dry_run else "validate-only" if self.validate_only else "batch" if self.batch_mode else "interactive",
        })

        # 预检
        if not self._preflight():
            print("\n❌ Preflight 检查失败，终止 workflow")
            self._log("orchestrator_preflight_failed", {})
            sys.exit(1)

        if self.validate_only:
            print("\n✅ validate-only 完成，当前状态验证通过")
            return

        # 找到起始阶段索引
        start_idx = 0
        for i, stage in enumerate(STAGES):
            if stage["id"] == effective_from_phase:
                start_idx = i
                break

        # 逐阶段执行
        for stage in STAGES[start_idx:]:
            success = self._run_phase(stage)
            if not success:
                print(f"\n{'=' * 60}")
                print(f"❌ Workflow 在阶段 {stage['id']} 终止")
                print(f"{'=' * 60}")
                print(f"\n💡 恢复建议:")
                print(f"   1. 查看 trace log: {self.run_dir / 'orchestrator_trace.json'}")
                print(f"   2. 查看最新快照: {self.snapshot_dir}")
                print(f"   3. 修复问题后，从本阶段恢复:")
                print(f"      python orchestrate.py --from-phase {stage['id']} --workspace {self.workspace} --manifest {self.manifest_path}")
                self._log("orchestrator_terminated", {"phase": stage["id"]})
                sys.exit(1)

            # step-mode: 暂停等待确认
            if self.step_mode:
                response = input("\n[step-mode] 按 Enter 进入下一阶段，或输入 'abort' 终止: ").strip()
                if response.lower() in ("abort", "exit", "quit"):
                    print("🛑 用户终止 workflow")
                    sys.exit(0)

        # 全部完成
        print(f"\n{'=' * 60}")
        print("🎉 Patent Workflow 全部阶段完成！")
        print(f"{'=' * 60}")
        print(f"\n📦 交付物:")
        print(f"   终稿: {self.run_dir / 'delivery'}")
        print(f"   产物目录: {self.run_dir}")
        print(f"   Manifest: {self.manifest_path}")
        print(f"   Trace: {self.run_dir / 'orchestrator_trace.json'}")
        self._log("orchestrator_complete", {})


def main():
    parser = argparse.ArgumentParser(
        description="Patent Workflow Orchestrator — 专利工作流主编排器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 冷启动
  python orchestrate.py --workspace . --manifest artifacts/run_manifest.md --from-phase 0

  # 从阶段4恢复
  python orchestrate.py --workspace . --manifest artifacts/run_manifest.md --from-phase 5

  # 只验证当前状态
  python orchestrate.py --workspace . --manifest artifacts/run_manifest.md --validate-only

  # 单步调试
  python orchestrate.py --workspace . --manifest artifacts/run_manifest.md --from-phase 2 --step

  # 非交互模式（CI/CD 用）
  python orchestrate.py --workspace . --manifest artifacts/run_manifest.md --batch-mode
        """,
    )
    parser.add_argument("--workspace", required=True, help="工作目录（绝对路径）")
    parser.add_argument("--manifest", required=True, help="Run manifest 路径")
    parser.add_argument("--from-phase", default="phase_0", help="起始阶段（默认 phase_0）")
    parser.add_argument("--batch-mode", action="store_true", help="非交互模式，所有用户确认使用默认值")
    parser.add_argument("--step", action="store_true", help="单步调试模式，每阶段暂停等待确认")
    parser.add_argument("--dry-run", action="store_true", help="只打印执行计划，不实际执行")
    parser.add_argument("--validate-only", action="store_true", help="只验证当前状态，不推进")
    parser.add_argument("--user-timeout", type=int, default=1800, help="用户输入超时秒数（默认1800=30分钟）")
    parser.add_argument("--domain-scope", default="", help="预填 Phase 1 领域/题目，适合 webchat/CI 非交互运行")
    parser.add_argument(
        "--local-project-paths",
        default=None,
        help="预填 Phase 1 本地项目/文档路径，多个路径用逗号分隔；传空字符串表示仅联网搜索",
    )
    parser.add_argument("--json-trace", action="store_true", help="以 JSON 输出 trace log")

    args = parser.parse_args()

    local_project_paths = None
    if args.local_project_paths is not None:
        local_project_paths = [path.strip() for path in re.split(r"[,，;；\n]+", args.local_project_paths) if path.strip()]
    orchestrator = Orchestrator(
        workspace=Path(args.workspace),
        manifest_path=Path(args.manifest),
        from_phase=args.from_phase,
        batch_mode=args.batch_mode,
        step_mode=args.step,
        dry_run=args.dry_run,
        validate_only=args.validate_only,
        user_timeout=args.user_timeout,
        domain_scope=args.domain_scope,
        local_project_paths=local_project_paths,
    )

    try:
        orchestrator.run()
    except Exception as e:
        print(f"\n💥 Orchestrator 未捕获异常: {e}")
        traceback.print_exc()
        trace_path = Path(args.workspace) / "artifacts" / "orchestrator_trace.json"
        print(f"\n查看 trace log 获取上下文: {trace_path}")
        sys.exit(2)


if __name__ == "__main__":
    main()
