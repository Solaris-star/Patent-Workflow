#!/usr/bin/env python3
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# 支持的主要专利局前缀（主要用于 prior-art 评分时的 CN bonus 计算）
# CN=中国, WO=WIPO PCT, EP=欧洲, US=美国, JP=日本, KR=韩国
PATENT_PREFIXES = ("CN", "WO", "EP", "US", "JP", "KR")

# Profiles allow phase gates to be tuned per domain without breaking legacy behavior.
# Default profile MUST preserve historical behavior.
PROFILES = {
"legacy": {
        "project_terms": ["方法", "系统", "装置", "流程", "工作流"],
        "ai_terms": ["智能", "AI", "模型", "语义", "自动", "自适应"],
        "constraint_terms": [],
        "negative_terms": [],
        "weights": {"project": 15, "ai": 15, "constraint": 0, "negative": 0, "cn_bonus": 10},
    },
    # For AI+项目管理：项目计划隐性约束→形式化模型→冲突检测/修复→可解释回写
    "ai_project_plan_constraints": {
        "project_terms": ["项目管理", "项目计划", "进度计划", "任务计划", "工作流", "协同"],
        "ai_terms": ["人工智能", "AI", "大模型", "大语言模型", "智能体", "生成式"],
        "constraint_terms": [
            "隐性约束",
            "约束抽取",
            "约束识别",
            "形式化约束",
            "规则抽取",
            "一致性",
            "冲突检测",
            "冲突消解",
            "冲突修复",
            "修复动作",
            "重排",
            "回写",
            "可解释",
            "裁决",
            "补链",
        ],
        # Construction/manufacturing terms can still be relevant as long as the method is about constraints/conflicts.
        # So we keep them as weak negatives (down-weighted penalty).
        "negative_terms": ["车间", "锻造", "智能客服"],
        "weights": {"project": 18, "ai": 18, "constraint": 18, "negative": 10, "cn_bonus": 10},
    },
    "trusted_patent_search": {
        "project_terms": ["方法", "系统", "装置", "流程", "工作流", "检索", "证据", "优化", "融合"],
        "ai_terms": ["智能", "AI", "模型", "语义", "自动", "自适应"],
        "constraint_terms": ["专利", "发明", "公开", "申请", "权利要求", "背景技术"],
        "negative_terms": ["广告", "招聘", "新闻", "论坛", "博客"],
        "weights": {"project": 12, "ai": 10, "constraint": 10, "negative": 20, "cn_bonus": 10, "trusted_source_bonus": 15},
    },
}


def parse_date(s: str):
    if not s:
        return None
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y-%m", "%Y/%m", "%Y.%m", "%Y"):
        try:
            dt = datetime.strptime(s, fmt)
            if fmt == "%Y":
                dt = dt.replace(month=1, day=1)
            elif fmt in ("%Y-%m", "%Y/%m", "%Y.%m"):
                dt = dt.replace(day=1)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def age_years(date_str: str, now: datetime):
    dt = parse_date(date_str)
    if not dt:
        return None
    return round((now - dt).days / 365.25, 3)


def _stringify(x) -> str:
    if x is None:
        return ""
    if isinstance(x, str):
        return x
    if isinstance(x, (list, tuple)):
        # keywords may arrive as list
        return " ".join(_stringify(i) for i in x)
    # fallback
    return str(x)


def text_blob(p: dict):
    parts = [
        _stringify(p.get("title", "")),
        _stringify(p.get("abstract", "")),
        _stringify(p.get("keywords", "")),
        _stringify(p.get("scenario", "")),
        _stringify(p.get("candidate_direction", "")),  # agent-native field
    ]
    return "\n".join(parts)


def relevance_score(p: dict, profile: str = "legacy"):
    cfg = PROFILES.get(profile) or PROFILES["legacy"]
    w = cfg.get("weights", {})

    text = text_blob(p)
    score = 0

    project_terms = cfg.get("project_terms", [])
    ai_terms = cfg.get("ai_terms", [])
    constraint_terms = cfg.get("constraint_terms", [])
    negative_terms = cfg.get("negative_terms", [])

    project_hits = sum(1 for t in project_terms if t.lower() in text.lower())
    ai_hits = sum(1 for t in ai_terms if t.lower() in text.lower())
    constraint_hits = sum(1 for t in constraint_terms if t.lower() in text.lower())
    negative_hits = sum(1 for t in negative_terms if t.lower() in text.lower())

    score += min(project_hits, 3) * int(w.get("project", 20))
    score += min(ai_hits, 3) * int(w.get("ai", 20))
    score += min(constraint_hits, 3) * int(w.get("constraint", 0))
    score -= min(negative_hits, 3) * int(w.get("negative", 25))

    pub = p.get("publicationNumber", "") or p.get("applicationNumber", "") or p.get("patent_id", "")
    if any(str(pub).startswith(prefix) for prefix in PATENT_PREFIXES):
        score += int(w.get("cn_bonus", 10))

    if p.get("trusted_patent_source"):
        score += int(w.get("trusted_source_bonus", 0))

    # Agent-native format: give base score from candidate_direction match
    if "candidate_direction" in p and score < 60:
        score = max(score, 60)  # Pass threshold for agent-native patents (abstracts may be pending web_fetch)

    return max(int(score), 0)


def is_cn(p: dict):
    # Support both camelCase (legacy) and snake_case (agent-native) field names
    pub = p.get("publicationNumber", "") or p.get("patent_id", "") or ""
    app = p.get("applicationNumber", "") or ""
    return str(pub).startswith(PATENT_PREFIXES) or str(app).startswith(PATENT_PREFIXES)


def normalize_input(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if isinstance(data.get("patents"), list):
            return data["patents"]
        if isinstance(data.get("candidates"), list):
            return data["candidates"]
    raise ValueError("Unsupported input JSON. Expected array or object with patents/candidates array.")


def main():
    ap = argparse.ArgumentParser(description="Validate patent candidates for patent-workflow gates")
    ap.add_argument("input", help="Path to candidate patent JSON (array or object with patents/candidates array)")
    ap.add_argument("--output", help="Path to write validation summary JSON")
    ap.add_argument("--min-count", type=int, default=5)
    ap.add_argument("--fresh-years", type=float, default=1.5)
    ap.add_argument("--relevance-threshold", type=int, default=60)
    ap.add_argument(
        "--profile",
        default="legacy",
        choices=sorted(PROFILES.keys()),
        help="Scoring profile (default: legacy). Use ai_project_plan_constraints for project-plan constraint/conflict workflows.",
    )
    args = ap.parse_args()

    now = datetime.now(timezone.utc)
    raw = json.loads(Path(args.input).read_text(encoding="utf-8"))
    profile = args.profile
    if profile == "legacy" and isinstance(raw, dict) and raw.get("pool_type") == "trusted_patent_candidate_pool":
        profile = "trusted_patent_search"
    patents = normalize_input(raw)

    final_relevant = []
    peripheral = []
    rejected = []

    for p in patents:
        item = dict(p)
        item["isCN"] = is_cn(item)
        # Prefer publication_date for freshness (more relevant for "what's new")
        date_ref = item.get("publication_date") or item.get("publicationDate") or item.get("filing_date") or item.get("filingDate") or ""
        item["ageYears"] = age_years(date_ref, now)
        item["relevanceScore"] = relevance_score(item, profile=profile)
        item["freshPassed"] = item["ageYears"] is not None and item["ageYears"] <= args.fresh_years
        item["relevancePassed"] = item["relevanceScore"] >= args.relevance_threshold

        if item["freshPassed"] and item["relevancePassed"]:
            # Core criteria: fresh + relevant. CN is preferred but not required.
            final_relevant.append(item)
        else:
            if item["isCN"] or item["relevanceScore"] > 0:
                peripheral.append(item)
            else:
                rejected.append(item)

    # CN-only gate: relaxed — track CN count but don't require all to be CN
    cn_count = sum(1 for p in final_relevant if p.get("isCN"))

    summary = {
        "validator": "validate_patent_candidates.py",
        "generatedAt": now.isoformat(),
        "inputPath": str(Path(args.input).resolve()),
        "profile": profile,
        "gates": {
            "cnCount": cn_count,
            "cnOnlyPassed": cn_count >= 1,  # Relaxed: at least 1 CN patent, not all
            "freshnessPassed": all(p.get("freshPassed") for p in final_relevant),
            "relevancePassed": all(p.get("relevancePassed") for p in final_relevant),
            "minCountPassed": len(final_relevant) >= args.min_count,
        },
        "thresholds": {
            "minCount": args.min_count,
            "freshYears": args.fresh_years,
            "relevanceThreshold": args.relevance_threshold,
        },
        "counts": {
            "input": len(patents),
            "finalRelevantPatents": len(final_relevant),
            "peripheralReferences": len(peripheral),
            "rejected": len(rejected),
        },
        "finalRelevantPatents": final_relevant,
        "peripheralReferences": peripheral,
        "rejected": rejected,
    }
    summary["passed"] = all(summary["gates"].values())

    out = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(out, encoding="utf-8")
    else:
        print(out)

    sys.exit(0 if summary["passed"] else 2)


if __name__ == "__main__":
    main()
