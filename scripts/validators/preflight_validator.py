#!/usr/bin/env python3
"""
Preflight Validator — 运行前检查所有依赖和配置。
解决坑点：orchestrate.py 本身有 bug / 环境缺失导致执行中途失败。
"""

import os
import sys
import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional

# 相对于 patent-workflow 目录的技能根目录
SKILL_ROOT = Path(__file__).parent.parent.parent.parent
WORKFLOW_ROOT = Path(__file__).parent.parent.parent


class PreflightIssue:
    def __init__(self, level: str, category: str, message: str, fix_hint: str):
        self.level = level  # "error" | "warning"
        self.category = category
        self.message = message
        self.fix_hint = fix_hint

    def to_dict(self):
        return {
            "level": self.level,
            "category": self.category,
            "message": self.message,
            "fix_hint": self.fix_hint,
        }


class PreflightValidator:
    """运行前检查所有依赖、配置和目录结构。"""

    def __init__(self, workspace: Path, manifest_path: Path):
        self.workspace = Path(workspace)
        self.manifest_path = Path(manifest_path)
        self.issues: List[PreflightIssue] = []
        self.passed = True

    def _add_error(self, category: str, message: str, fix_hint: str):
        self.issues.append(PreflightIssue("error", category, message, fix_hint))
        self.passed = False

    def _add_warning(self, category: str, message: str, fix_hint: str):
        self.issues.append(PreflightIssue("warning", category, message, fix_hint))

    # ── 检查 1: 工作目录 ────────────────────────
    def check_workspace(self):
        if not self.workspace.exists():
            self._add_error(
                "workspace",
                f"工作目录不存在: {self.workspace}",
                f"mkdir -p {self.workspace}",
            )
            return
        if not self.workspace.is_dir():
            self._add_error(
                "workspace",
                f"工作目录路径不是目录: {self.workspace}",
                "请指定一个有效的目录路径",
            )

    # ── 检查 2: Run Manifest ────────────────────
    def check_manifest(self):
        if not self.manifest_path.exists():
            fallback_json = self.workspace / "artifacts" / "run_manifest.json"
            fingerprints_path = self.workspace / "artifacts" / "preprocess" / "source_fingerprints.json"
            preprocess_notes = self.workspace / "artifacts" / "preprocess" / "phase_00_preprocess_notes.md"
            if fallback_json.exists() and fingerprints_path.exists() and preprocess_notes.exists():
                self._add_warning(
                    "manifest",
                    f"Run manifest markdown 缺失，但检测到可复用的 Phase 0 产物: {fallback_json}",
                    "编排器将尝试从 run_manifest.json 自动重建 run_manifest.md",
                )
                return
            self._add_error(
                "manifest",
                f"Run manifest 不存在: {self.manifest_path}",
                f"请先运行 init_run_manifest.py 初始化",
            )
            return
        try:
            with open(self.manifest_path, "r", encoding="utf-8") as f:
                content = f.read()
            if "run_id" not in content:
                self._add_error(
                    "manifest",
                    "Run manifest 缺少 run_id 字段",
                    "请重新运行 init_run_manifest.py",
                )
        except Exception as e:
            self._add_error(
                "manifest",
                f"无法读取 run manifest: {e}",
                "检查文件权限或重新生成",
            )

    # ── 检查 3: 必需技能目录 ───────────────────
    def check_skills(self):
        required_skills = [
            "smart-search",
            "modular-writer",
            "writing-style-analyzer",
            "pdf",
        ]
        for skill_name in required_skills:
            # 尝试两种路径格式（带空格和不带空格）
            skill_dir = SKILL_ROOT / skill_name
            if not skill_dir.exists():
                skill_dir = SKILL_ROOT / skill_name.replace("-", " ")
            if not skill_dir.exists():
                self._add_error(
                    "skills",
                    f"技能目录缺失: {skill_name}",
                    f"请确保 {skill_name} 已安装在 {SKILL_ROOT.parent}",
                )

    # ── 检查 4: 必需脚本 ──────────────────────
    def check_scripts(self):
        required_scripts = [
            WORKFLOW_ROOT / "scripts" / "init_run_manifest.py",
            WORKFLOW_ROOT / "scripts" / "run_phase_gates.py",
            WORKFLOW_ROOT / "scripts" / "validate_research_pack.py",
            WORKFLOW_ROOT / "scripts" / "validate_patent_candidates.py",
            WORKFLOW_ROOT / "scripts" / "validate_facts_ledger.py",
        ]
        for script in required_scripts:
            if not script.exists():
                self._add_error(
                    "scripts",
                    f"必需脚本缺失: {script.name}",
                    f"请检查 patent-workflow/scripts/ 目录",
                )

    # ── 检查 5: 绑定文件 ──────────────────────
    def check_binding_files(self):
        binding_files = [
            "HANDOFF_CONTRACT.md",
            "DELIVERY_CHECKLIST.md",
            "IPR_REVIEW_TEMPLATE.md",
            "CONSISTENCY_AUDIT_TEMPLATE.md",
            "FIGURE_DELIVERY_CHECKLIST.md",
        ]
        for fname in binding_files:
            fpath = WORKFLOW_ROOT / fname
            if not fpath.exists():
                self._add_warning(
                    "binding_files",
                    f"绑定文件缺失: {fname}",
                    f"该文件是可选但建议存在: {fpath}",
                )

    # ── 检查 6: 目录结构 ──────────────────────
    def check_directory_structure(self):
        required_dirs = [
            self.workspace / "artifacts",
            self.workspace / "artifacts" / "research",
            self.workspace / "artifacts" / "prior_art",
            self.workspace / "artifacts" / "draft",
            self.workspace / "artifacts" / "revision",
            self.workspace / "artifacts" / "delivery",
        ]
        for d in required_dirs:
            if not d.exists():
                self._add_warning(
                    "directory_structure",
                    f"建议目录缺失: {d.relative_to(self.workspace)}",
                    f"mkdir -p {d}",
                )

    # ── 检查 7: Python 依赖 ───────────────────
    def check_python_deps(self):
        required_modules = ["json", "subprocess", "pathlib"]
        for mod in required_modules:
            try:
                __import__(mod)
            except ImportError:
                self._add_error(
                    "python_deps",
                    f"Python 核心模块缺失: {mod}",
                    f"pip install {mod}",
                )
        # 可选依赖
        optional_modules = ["yaml", "requests"]
        for mod in optional_modules:
            try:
                __import__(mod)
            except ImportError:
                self._add_warning(
                    "python_deps",
                    f"Python 可选模块缺失: {mod}",
                    f"pip install {mod} (如需使用相关功能)",
                )

    # ── 检查 8: 状态机一致性 ──────────────────
    def check_state_machine(self):
        """检查 run manifest 中的状态机字段是否自洽。"""
        if not self.manifest_path.exists():
            return
        # 读取 manifest 的纯文本内容，解析关键字段
        try:
            with open(self.manifest_path, "r", encoding="utf-8") as f:
                content = f.read()
            # 简单检查：如果 current_phase 在 phase_5 之后，但 phase_2 的门禁没记录
            # 这只是一个启发式检查
            if "current_phase: phase_" in content:
                # 提取当前阶段编号
                import re
                match = re.search(r"current_phase: phase_(\d+)", content)
                if match:
                    current_num = int(match.group(1))
                    if current_num > 2 and "phase_02" not in content:
                        self._add_warning(
                            "state_machine",
                            "当前阶段在 phase_2 之后，但 manifest 中未见 phase_2 记录",
                            "可能是冷启动或 manifest 未正确更新",
                        )
        except Exception:
            pass

    # ── 检查 9: 专利标题规范 ──────────────────
    def check_patent_title(self):
        """检查专利标题是否符合 CN 专利申请格式规范。"""
        manifest_json = self.workspace / "artifacts" / "run_manifest.json"
        if not manifest_json.exists():
            return
        try:
            with open(manifest_json, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            title = manifest.get("patent_title", "")
            if not title:
                self._add_warning("patent_title", "manifest 中缺少 patent_title 字段",
                                  "在 Phase 3 收敛方向后写入 patent_title")
                return
            chinese_chars = re.findall(r'[\u4e00-\u9fff]', title)
            cn_len = len(chinese_chars)
            if cn_len > 25:
                self._add_warning("patent_title",
                    f"专利标题 {cn_len} 字，超过建议上限 25 字: {title}",
                    "精简标题至 25 字以内")
            english = re.findall(r'[a-zA-Z]+', title)
            if english:
                self._add_warning("patent_title",
                    f"专利标题含英文词汇: {', '.join(english)}",
                    "CN 专利标题应为纯中文，替换英文术语为中文")
            special = re.findall(r'[-–—/\\@#$%^&*]', title)
            if special:
                self._add_warning("patent_title",
                    f"专利标题含特殊符号: {', '.join(set(special))}",
                    "使用中文标点替代或删除")
            if not title.startswith("一种"):
                self._add_warning("patent_title",
                    f"专利标题未以'一种'开头: {title}",
                    "CN 专利标题通常以'一种'开头")
        except Exception:
            pass

    # ── 主入口 ────────────────────────────────
    def run(self) -> Tuple[bool, List[PreflightIssue]]:
        print("🔍 运行 Preflight 检查...")
        self.check_workspace()
        self.check_manifest()
        self.check_skills()
        self.check_scripts()
        self.check_binding_files()
        self.check_directory_structure()
        self.check_python_deps()
        self.check_state_machine()
        self.check_patent_title()

        # 输出报告
        errors = [i for i in self.issues if i.level == "error"]
        warnings = [i for i in self.issues if i.level == "warning"]

        if errors:
            print(f"\n❌ Preflight 检查失败: {len(errors)} 个错误")
            for e in errors:
                print(f"   [{e.category}] {e.message}")
                print(f"   → 修复建议: {e.fix_hint}")
        if warnings:
            print(f"\n⚠️  Preflight 警告: {len(warnings)} 个")
            for w in warnings:
                print(f"   [{w.category}] {w.message}")

        if self.passed:
            print("✅ Preflight 检查通过")
        else:
            print("\n💡 使用 --fix 自动修复部分问题，或手动修复后重试")

        return self.passed, self.issues

    def to_json(self) -> str:
        return json.dumps(
            {
                "passed": self.passed,
                "issues": [i.to_dict() for i in self.issues],
            },
            ensure_ascii=False,
            indent=2,
        )


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Preflight Validator")
    parser.add_argument("--workspace", required=True, help="工作目录")
    parser.add_argument("--manifest", required=True, help="Run manifest 路径")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    args = parser.parse_args()

    validator = PreflightValidator(Path(args.workspace), Path(args.manifest))
    passed, issues = validator.run()

    if args.json:
        print(validator.to_json())

    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
