#!/usr/bin/env python3
import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass

CN_PREFIX = ("CN",)

# Profiles allow phase gates to be tuned per domain without breaking legacy behavior.
# Default profile MUST preserve historical behavior.
PROFILES = {
    "legacy": {
        "project_terms": ["项目管理", "项目计划", "项目实施", "项目协同", "项目执行", "项目进度", "软件开发项目", "工作流"],
        "ai_terms": ["人工智能", "AI", "大模型", "大语言模型", "智能体", "生成式", "模型"],
        "constraint_terms": [],
        "negative_terms": ["车间", "工厂", "锻造", "施工", "建筑工程施工", "生产调度", "机器人路径", "智能客服"],
        "weights": {"project": 20, "ai": 20, "constraint": 0, "negative": 25, "cn_bonus": 10},
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
    ]
    return "\n".join(parts)


def _term_matched(term: str, text: str, text_lower: str) -> bool:
    """ASCII terms match on word boundaries ('ai' must not hit 'maintains');
    CJK terms keep substring semantics (no word boundaries in Chinese)."""
    if not term:
        return False
    if all(ord(c) < 128 for c in term):
        return re.search(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", text, re.IGNORECASE) is not None
    return term.lower() in text_lower


def relevance_score(p: dict, cfg: dict):
    w = cfg.get("weights", {})

    text = text_blob(p)
    text_lower = text.lower()
    score = 0

    def _hits(terms):
        return sum(1 for t in terms if _term_matched(t, text, text_lower))

    project_hits = _hits(cfg.get("project_terms", []))
    ai_hits = _hits(cfg.get("ai_terms", []))
    constraint_hits = _hits(cfg.get("constraint_terms", []))
    negative_hits = _hits(cfg.get("negative_terms", []))

    score += min(project_hits, 3) * int(w.get("project", 20))
    score += min(ai_hits, 3) * int(w.get("ai", 20))
    score += min(constraint_hits, 3) * int(w.get("constraint", 0))
    score -= min(negative_hits, 3) * int(w.get("negative", 25))

    pub = p.get("publicationNumber", "") or p.get("applicationNumber", "")
    if any(str(pub).startswith(prefix) for prefix in CN_PREFIX):
        score += int(w.get("cn_bonus", 10))

    return max(int(score), 0)


def is_cn(p: dict):
    pub = str(p.get("publicationNumber", "") or "")
    app = str(p.get("applicationNumber", "") or "")
    return pub.startswith(CN_PREFIX) or app.startswith(CN_PREFIX)


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
        help="Built-in scoring profile (default: legacy). Ignored when --terms-file is provided.",
    )
    ap.add_argument(
        "--terms-file",
        help="Path to JSON with domain-adaptive scoring terms (same structure as a PROFILES entry: "
        "project_terms=场景/应用域词, ai_terms=技术手段词, constraint_terms=区别特征词, negative_terms, weights). "
        "Written per-run by the patent-prior-art skill; takes precedence over --profile.",
    )
    args = ap.parse_args()

    now = datetime.now(timezone.utc)

    def _die(msg: str):
        # JSON summary instead of a bare traceback (matches sibling validators)
        print(json.dumps({
            "validator": "validate_patent_candidates.py",
            "generatedAt": now.isoformat(),
            "inputPath": str(Path(args.input)),
            "passed": False,
            "errors": [msg],
        }, ensure_ascii=False, indent=2))
        sys.exit(2)

    if args.terms_file:
        tf = Path(args.terms_file)
        if not tf.exists():
            _die(f"terms file not found: {tf}")
        try:
            cfg = json.loads(tf.read_text(encoding="utf-8"))
        except Exception as e:
            _die(f"terms file JSON parse error: {e}")
        profile_label = f"terms-file:{args.terms_file}"
    else:
        cfg = PROFILES.get(args.profile) or PROFILES["legacy"]
        profile_label = args.profile

    inp = Path(args.input)
    if not inp.exists():
        _die(f"Input file not found: {inp}")
    try:
        raw = json.loads(inp.read_text(encoding="utf-8"))
        patents = normalize_input(raw)
    except Exception as e:
        _die(f"Input parse error: {e}")

    final_relevant = []
    peripheral = []
    rejected = []

    for p in patents:
        item = dict(p)
        item["isCN"] = is_cn(item)
        date_ref = item.get("filingDate") or item.get("publicationDate") or ""
        item["ageYears"] = age_years(date_ref, now)
        item["relevanceScore"] = relevance_score(item, cfg)
        item["freshPassed"] = item["ageYears"] is not None and item["ageYears"] <= args.fresh_years
        item["relevancePassed"] = item["relevanceScore"] >= args.relevance_threshold

        if item["isCN"] and item["freshPassed"] and item["relevancePassed"]:
            final_relevant.append(item)
        else:
            if item["isCN"] or item["relevanceScore"] > 0:
                peripheral.append(item)
            else:
                rejected.append(item)

    summary = {
        "validator": "validate_patent_candidates.py",
        "generatedAt": now.isoformat(),
        "inputPath": str(Path(args.input).resolve()),
        "profile": profile_label,
        "gates": {
            "cnOnlyPassed": all(p.get("isCN") for p in final_relevant),
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
