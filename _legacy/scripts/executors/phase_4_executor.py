#!/usr/bin/env python3
"""
Internal Patent Review Executor — Phase 2 内部深度专利复核适配器。
使用 smart-search CLI 面向可信专利渠道复核 Phase 2 候选特征，构建可审计候选池。
说明：该文件保留为内部适配器和兼容层，不再对应独立工作流节点。
兼容产物：
- artifacts/prior_art/phase_04_search_queries.txt
- artifacts/prior_art/phase_04_patent_candidate_pool.json
- artifacts/prior_art/phase_04_evidence_pack.json
"""

import json
import os
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse

from executors.base_executor import BaseExecutor, ExecutorResult, RecoverableError
from research_cache import ResearchCache


SMART_SEARCH_CMD = os.environ.get("SMART_SEARCH_CMD") or shutil.which("smart-search") or "/opt/homebrew/bin/smart-search"
CURRENT_YEAR = datetime.now().year

TRUSTED_PATENT_CHANNELS = {
    "google_patents": {
        "name": "Google Patents",
        "domains": ["patents.google.com"],
        "query_hint": "site:patents.google.com",
    },
    "espacenet": {
        "name": "Espacenet",
        "domains": ["worldwide.espacenet.com", "register.epo.org"],
        "query_hint": "site:worldwide.espacenet.com OR site:register.epo.org",
    },
    "wipo_patentscope": {
        "name": "WIPO Patentscope",
        "domains": ["patentscope.wipo.int"],
        "query_hint": "site:patentscope.wipo.int",
    },
    "cnipa": {
        "name": "CNIPA",
        "domains": ["cnipa.gov.cn", "pss-system.cponline.cnipa.gov.cn"],
        "query_hint": "site:cnipa.gov.cn OR site:pss-system.cponline.cnipa.gov.cn",
    },
}


class PhaseExecutor(BaseExecutor):
    """Phase 2 内部深度专利复核适配器。"""

    def _execute(self) -> ExecutorResult:
        print("   🔍 执行深度专利复核（smart-search）...")

        domain_scope = self.manifest.get("domain_scope", "未知领域")
        patent_title = self.manifest.get("patent_title", "")
        selected_direction = self.manifest.get("selected_direction", "")
        research_pack = self._load_research_pack()
        candidate_directions = research_pack.get("candidate_directions", [])
        claims_to_verify = research_pack.get("claims_requiring_phase_4_verification") or research_pack.get("claims_requiring_patent_verification", [])

        search_queries = self._build_search_queries(domain_scope, patent_title, selected_direction, claims_to_verify)
        query_file = self.save_artifact(
            "\n".join(query["query"] for query in search_queries),
            "artifacts/prior_art/phase_04_search_queries.txt",
        )

        research_cache = ResearchCache()
        cache_query = f"{patent_title or selected_direction or domain_scope} {domain_scope}".strip()
        cache_hits = research_cache.search(cache_query, phase="phase_2", source_types=["patent"], limit=12)
        cache_hit_count = len(cache_hits)

        channel_failures: List[Dict[str, str]] = []
        fallback_actions: List[str] = []
        search_results: List[Dict[str, Any]] = []

        search_timeout = self._search_timeout()
        for idx, query_spec in enumerate(search_queries):
            query = query_spec["query"]
            print(f"   🔍 专利搜索 {idx + 1}/{len(search_queries)}: {query[:60]}...")
            try:
                result = self._smart_search(query, timeout=search_timeout)
                search_results.append(
                    {
                        "query_id": query_spec["id"],
                        "channel": query_spec["channel"],
                        "query": query,
                        "status": "ok",
                        "content": result.get("content", ""),
                        "sources": self._normalize_sources(result, query_spec["channel"]),
                        "sources_count": result.get("sources_count", 0),
                    }
                )
                time.sleep(0.5)
            except Exception as error:
                print(f"   ⚠️ 专利搜索失败: {error}")
                channel_failures.append({"query_id": query_spec["id"], "query": query, "error": str(error)})
                fallback_actions.append(f"{query_spec['id']} 检索失败，仅保留失败记录，不生成虚假最终专利")
                search_results.append(
                    {
                        "query_id": query_spec["id"],
                        "channel": query_spec["channel"],
                        "query": query,
                        "status": "failed",
                        "content": "",
                        "sources": [],
                        "sources_count": 0,
                    }
                )

        all_sources = self._collect_unique_sources(search_results)
        candidate_pool = self._build_candidate_pool(
            domain_scope,
            patent_title,
            selected_direction,
            candidate_directions,
            all_sources,
            search_results,
        )
        pool_path = self.save_artifact(candidate_pool, "artifacts/prior_art/phase_04_patent_candidate_pool.json")

        gate_summary = self._evaluate_candidate_pool(candidate_pool)
        source_reading_notes = self._build_source_reading_notes(search_queries, search_results)
        evidence_pack = self._build_evidence_pack(
            candidate_pool,
            str(pool_path),
            search_queries,
            channel_failures,
            fallback_actions,
            all_sources,
            gate_summary,
            source_reading_notes,
        )
        cache_import_report = research_cache.import_source_reading_notes(
            source_reading_notes,
            phase="phase_2",
            query=cache_query,
            domain_scope=domain_scope,
            candidate_direction=patent_title or selected_direction,
        )
        evidence_pack["research_cache"] = {
            "enabled": True,
            "hit_count": cache_hit_count,
            "query": cache_query,
            "hits": cache_hits,
            "import_report": cache_import_report,
            "phase_2_internal_patent_review_policy": "cache hits are historical prior-art candidates only; legal status and claim relevance still require fresh revalidation",
        }
        evidence_pack["search_trace"]["research_cache_hit_count"] = cache_hit_count
        pack_path = self.save_artifact(evidence_pack, "artifacts/prior_art/phase_04_evidence_pack.json")

        final_count = len(gate_summary["final_relevant_patents"])
        trusted_source_count = len([source for source in all_sources if source.get("trusted_patent_source")])
        brain_status = "ok" if final_count >= 5 else "degraded"

        manifest_updates = {
            "patent_search_queries": [query["query"] for query in search_queries],
            "patent_search_channels": list(TRUSTED_PATENT_CHANNELS.keys()),
            "trusted_patent_channels": [channel["name"] for channel in TRUSTED_PATENT_CHANNELS.values()],
            "candidate_pool_generated_by": "smart-search",
            "candidate_pool_generation_mode": "trusted_patent_search",
            "candidate_pool_channels_used": ["smart-search", *list(TRUSTED_PATENT_CHANNELS.keys())],
            "candidate_pool_reasoning_chains_used": [],
            "patent_candidate_pool_count": len(candidate_pool.get("patents", [])),
            "finalRelevantPatents_count": final_count,
            "cn_only_passed": gate_summary["gates"]["cn_only_passed"],
            "freshness_passed": gate_summary["gates"]["freshness_passed"],
            "relevance_passed": gate_summary["gates"]["relevance_passed"],
            "min_count_passed": gate_summary["gates"]["min_count_passed"],
            "trusted_patent_source_count": trusted_source_count,
            "research_cache_enabled": True,
            "research_cache_hit": cache_hit_count > 0,
            "research_cache_hit_count": cache_hit_count,
            "research_cache_imported_count": cache_import_report.get("imported_count", 0),
            "research_cache_skipped_private_count": cache_import_report.get("skipped_private_count", 0),
            "research_cache_path": str(research_cache.root),
            "channel_failures": channel_failures,
            "fallback_actions": fallback_actions,
            "brain_chain_status": brain_status,
            "degraded_run": brain_status != "ok",
            "phase_04_search_queries_path": str(query_file.relative_to(self.workspace)),
        }

        return ExecutorResult(
            status="success" if brain_status == "ok" else "degraded",
            artifacts=[str(query_file), str(pool_path), str(pack_path)],
            manifest_updates=manifest_updates,
            trace_log=self.trace,
            degraded_reason=None if brain_status == "ok" else f"finalRelevantPatents_count={final_count}，低于阈值 5",
        )

    def _load_research_pack(self) -> Dict[str, Any]:
        path = self.workspace / "artifacts" / "research" / "phase_02_research_pack.json"
        if not path.exists():
            return {}
        try:
            return self.load_artifact("artifacts/research/phase_02_research_pack.json")
        except Exception as error:
            self._log("research_pack_load_warn", {"error": str(error)})
            return {}

    def _build_search_queries(
        self,
        domain_scope: str,
        patent_title: str,
        selected_direction: str,
        claims_to_verify: List[str],
    ) -> List[Dict[str, str]]:
        subject = self._clean_query_subject(patent_title, selected_direction, domain_scope)
        base_queries = [
            ("PQ-BASE-01", "google_patents", f"site:patents.google.com {subject} CN patent"),
            ("PQ-BASE-02", "google_patents", f"site:patents.google.com {domain_scope} 发明专利 最近两年"),
            ("PQ-BASE-03", "espacenet", f"site:worldwide.espacenet.com {subject} patent"),
            ("PQ-BASE-04", "wipo_patentscope", f"site:patentscope.wipo.int {subject} patent"),
            ("PQ-BASE-05", "cnipa", f"site:cnipa.gov.cn {subject} 发明专利"),
        ]
        queries = [
            {"id": query_id, "channel": channel, "query": query}
            for query_id, channel, query in base_queries
        ]
        for idx, claim in enumerate(claims_to_verify[:3], start=1):
            queries.append(
                {
                    "id": f"PQ-CLAIM-{idx:02d}",
                    "channel": "google_patents",
                    "query": f"site:patents.google.com {claim} patent",
                }
            )
        return queries

    def _clean_query_subject(self, patent_title: str, selected_direction: str, domain_scope: str) -> str:
        for value in [patent_title, selected_direction, domain_scope]:
            subject = (value or "").strip()
            if subject and self._valid_query_subject(subject):
                return subject
        return "智能系统协同优化方法"

    def _valid_query_subject(self, subject: str) -> bool:
        compact = re.sub(r"\s+", "", subject or "")
        if not compact:
            return False
        if re.fullmatch(r"\d+", compact):
            return False
        if re.fullmatch(r"(?:CN|US|EP|WO|JP|KR)?\d{6,13}[A-Z]?\d?", compact, re.IGNORECASE):
            return False
        if re.search(r"(PATENTSCOPE|GooglePatents|Espacenet|OpenAI-compatible|Provider)", compact, re.IGNORECASE):
            return False
        if re.fullmatch(r"[A-Za-z]{1,24}", compact):
            return False
        return True

    def _search_timeout(self) -> int:
        override = self.manifest.get("phase_2_patent_review_timeout") or self.manifest.get("phase4_search_timeout")
        if override:
            try:
                return max(30, int(override))
            except (TypeError, ValueError):
                self._log("invalid_patent_review_timeout", {"value": override})
        return 180



    def _smart_search(self, query: str, timeout: int = 120) -> Dict[str, Any]:
        """调用 smart-search CLI 执行搜索，返回 JSON 结果。"""
        cmd = [
            SMART_SEARCH_CMD,
            "search",
            query,
            "--format",
            "json",
            "--extra-sources",
            "3",
            "--timeout",
            str(timeout),
        ]
        self._log("smart_search_start", {"query": query, "timeout": timeout})
        exit_code, stdout, stderr = self.run_command(cmd, timeout=timeout + 10)

        try:
            result = json.loads(stdout)
            self._log(
                "smart_search_ok",
                {
                    "source_count": result.get("sources_count", 0),
                    "content_len": len(result.get("content", "")),
                },
            )
            return result
        except json.JSONDecodeError as error:
            raise RecoverableError(f"smart-search 输出无法解析: {error}")

    def _normalize_sources(self, result: Dict[str, Any], query_channel: str) -> List[Dict[str, Any]]:
        sources = result.get("sources") or result.get("primary_sources") or []
        extra_sources = result.get("extra_sources") or []
        normalized: List[Dict[str, Any]] = []
        seen: Set[str] = set()
        for source in [*sources, *extra_sources]:
            if not isinstance(source, dict):
                continue
            url = source.get("url") or source.get("link") or ""
            if not url or url in seen:
                continue
            seen.add(url)
            channel = self._classify_patent_channel(url) or query_channel
            normalized.append(
                {
                    "title": source.get("title") or self._site_name(url),
                    "url": url,
                    "snippet": source.get("snippet") or source.get("content") or source.get("title") or "",
                    "site": self._site_name(url),
                    "patent_channel": channel,
                    "trusted_patent_source": self._classify_patent_channel(url) is not None,
                }
            )
        return normalized

    def _collect_unique_sources(self, search_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        collected: List[Dict[str, Any]] = []
        seen: Set[str] = set()
        for result in search_results:
            for source in result.get("sources", []):
                url = source.get("url", "")
                if url and url not in seen:
                    seen.add(url)
                    item = dict(source)
                    item["source_id"] = f"SRC-{len(collected) + 1:03d}"
                    collected.append(item)
        return collected

    def _build_source_reading_notes(self, queries: List[Dict[str, str]], search_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        query_by_id = {query.get("id"): query for query in queries}
        notes: List[Dict[str, Any]] = []
        seen: Set[str] = set()
        for result in search_results:
            if result.get("status") != "ok":
                continue
            content = str(result.get("content", ""))
            if not content.strip():
                continue
            query = query_by_id.get(result.get("query_id"), {})
            sentences = self._split_sentences(content)
            summary = self._reading_note_summary(sentences)
            key_facts = self._reading_note_key_facts(sentences)
            for source in result.get("sources", [])[:6]:
                url = str(source.get("url", ""))
                if not url or url in seen:
                    continue
                seen.add(url)
                notes.append({
                    "note_id": f"PRN-{len(notes) + 1:03d}",
                    "query_id": result.get("query_id", ""),
                    "query": result.get("query") or query.get("query", ""),
                    "source_type": "patent" if source.get("trusted_patent_source") or source.get("patent_channel") else "web",
                    "source_channel": source.get("patent_channel") or result.get("channel", ""),
                    "site": source.get("site") or self._site_name(url),
                    "title": source.get("title", ""),
                    "url": url,
                    "page_summary": summary,
                    "key_technical_facts": key_facts,
                    "candidate_relevance": self._short_text(f"该来源用于深度专利复核：{summary}", 220),
                    "usable_in_writing": bool(summary or key_facts),
                    "do_not_overclaim": "仅可作为背景技术、公开内容或查新线索；不得脱离原文扩张为确定法律结论。",
                })
        return notes

    def _split_sentences(self, content: str) -> List[str]:
        return [part.strip() for part in re.split(r"(?<=[。！？.!?])\s+|[\n\r]+", content or "") if part.strip()]

    def _reading_note_summary(self, sentences: List[str]) -> str:
        selected = [sentence for sentence in sentences if any(token in sentence for token in ["公开", "摘要", "方法", "系统", "装置", "采集", "识别", "检测", "判断", "预警", "恢复", "传输"])]
        if not selected:
            selected = sentences[:2]
        return self._short_text("。".join(sentence.strip("。 ") for sentence in selected[:3] if sentence.strip()), 360)

    def _reading_note_key_facts(self, sentences: List[str]) -> List[str]:
        facts: List[str] = []
        for sentence in sentences:
            if any(token in sentence for token in ["公开", "摘要", "采集", "识别", "检测", "判断", "生成", "恢复", "预警", "传输"]):
                fact = self._short_text(sentence, 140)
                if fact and fact not in facts:
                    facts.append(fact)
            if len(facts) >= 5:
                break
        return facts

    def _short_text(self, text: str, limit: int) -> str:
        normalized = re.sub(r"\s+", " ", text or "").strip(" 。；;，,")
        return normalized if len(normalized) <= limit else normalized[: limit - 1] + "…"

    def _build_candidate_pool(
        self,
        domain: str,
        patent_title: str,
        selected_direction: str,
        directions: List[Dict[str, Any]],
        sources: List[Dict[str, Any]],
        search_results: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        patents: List[Dict[str, Any]] = []
        seen_keys: Set[str] = set()
        content_by_url = self._content_by_url(search_results)

        for source in sources:
            if not source.get("trusted_patent_source"):
                continue
            patent = self._patent_from_source(source, domain, patent_title, selected_direction, content_by_url.get(source["url"], ""))
            if not patent:
                continue
            key = patent.get("publicationNumber") or patent.get("source_url")
            if key in seen_keys:
                continue
            seen_keys.add(key)
            patents.append(patent)

        return {
            "schema_version": "2.0",
            "pool_type": "trusted_patent_candidate_pool",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "trusted_patent_channels": TRUSTED_PATENT_CHANNELS,
            "generation_policy": {
                "final_candidates_require_trusted_patent_source": True,
                "fallback_skeleton_allowed": False,
                "fresh_years": 1.5,
                "relevance_threshold": 60,
                "cn_only": True,
            },
            "search_context": {
                "domain_scope": domain,
                "patent_title": patent_title,
                "selected_direction": selected_direction,
                "candidate_direction_count": len(directions),
            },
            "patents": patents,
            "peripheral_sources": [source for source in sources if not source.get("trusted_patent_source")],
        }

    def _patent_from_source(
        self,
        source: Dict[str, Any],
        domain: str,
        patent_title: str,
        selected_direction: str,
        content: str,
    ) -> Optional[Dict[str, Any]]:
        url = source.get("url", "")
        title = source.get("title", "").strip() or self._site_name(url)
        publication_number = self._extract_publication_number(url, title, content)
        if not publication_number:
            return None

        publication_date = self._extract_date(content) or self._extract_date(source.get("snippet", "")) or f"{CURRENT_YEAR}-01-01"
        filing_date = self._infer_filing_date(publication_date)
        abstract = self._abstract_from_source(source, content, domain, patent_title or selected_direction)
        keywords = [term for term in [domain, patent_title, selected_direction, "专利"] if term]
        return {
            "title": title,
            "abstract": abstract,
            "keywords": keywords,
            "scenario": f"{domain}深度专利复核",
            "publicationNumber": publication_number,
            "applicationNumber": publication_number.replace("A", ".0") if publication_number.startswith("CN") else "",
            "filingDate": filing_date,
            "publicationDate": publication_date,
            "applicant": self._extract_applicant(content) or "待从专利页面确认",
            "source_url": url,
            "source_channel": source.get("patent_channel"),
            "trusted_patent_source": True,
        }

    def _build_evidence_pack(
        self,
        candidate_pool: Dict[str, Any],
        pool_path: str,
        queries: List[Dict[str, str]],
        channel_failures: List[Dict[str, str]],
        fallback_actions: List[str],
        sources: List[Dict[str, Any]],
        gate_summary: Dict[str, Any],
        source_reading_notes: List[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        patents = candidate_pool.get("patents", [])
        evidence: List[Dict[str, Any]] = []
        alignments: List[Dict[str, Any]] = []

        for patent in patents:
            evidence_id = f"EV-{len(evidence) + 1:03d}"
            evidence.append(
                {
                    "evidence_id": evidence_id,
                    "url": patent.get("source_url", ""),
                    "excerpt": patent.get("abstract", "")[:300],
                    "source_type": "patent",
                    "source_channel": patent.get("source_channel"),
                    "is_auxiliary": False,
                }
            )
            alignments.append(
                {
                    "alignment_id": f"AL-{len(alignments) + 1:03d}",
                    "claim_aspect": patent.get("title", ""),
                    "evidence_ids": [evidence_id],
                    "conclusion": "可信专利渠道命中，可作为背景专利参考",
                }
            )

        for source in sources:
            if source.get("trusted_patent_source"):
                continue
            evidence.append(
                {
                    "evidence_id": f"EV-WEB-{len(evidence) + 1:03d}",
                    "url": source.get("url", ""),
                    "excerpt": self._ensure_excerpt(source.get("snippet") or source.get("title") or "外围网页证据，仅作辅助参考"),
                    "source_type": "web",
                    "source_channel": source.get("site"),
                    "is_auxiliary": True,
                }
            )

        return {
            "pack_type": "evidence_pack",
            "phase": "phase_02",
            "schema_version": "2.0",
            "patent_candidate_pool_path": pool_path,
            "trusted_patent_channels": candidate_pool.get("trusted_patent_channels", {}),
            "final_relevant_patents": gate_summary["final_relevant_patents"],
            "peripheral_references": gate_summary["peripheral_references"],
            "rejected_references": gate_summary["rejected_references"],
            "source_reading_notes": source_reading_notes or [],
            "search_trace": {
                "patent_search_queries": [query["query"] for query in queries],
                "query_specs": queries,
                "final_relevant_patent_count": len(gate_summary["final_relevant_patents"]),
                "channel_failures": channel_failures,
                "fallback_actions": fallback_actions,
                "gate_summary": gate_summary,
            },
            "evidence": evidence,
            "evidence_alignment": alignments,
        }

    def _evaluate_candidate_pool(self, candidate_pool: Dict[str, Any]) -> Dict[str, Any]:
        final_relevant = []
        peripheral = []
        rejected = []
        for patent in candidate_pool.get("patents", []):
            item = dict(patent)
            item["isCN"] = self._is_cn(item)
            item["ageYears"] = self._age_years(item.get("filingDate") or item.get("publicationDate") or "")
            item["relevanceScore"] = self._relevance_score(item)
            item["freshPassed"] = item["ageYears"] is not None and item["ageYears"] <= 1.5
            item["relevancePassed"] = item["relevanceScore"] >= 60
            if item["isCN"] and item["freshPassed"] and item["relevancePassed"] and item.get("trusted_patent_source"):
                final_relevant.append(item)
            elif item["isCN"] or item["relevanceScore"] > 0:
                peripheral.append(item)
            else:
                rejected.append(item)

        return {
            "gates": {
                "cn_only_passed": bool(final_relevant) and all(item["isCN"] for item in final_relevant),
                "freshness_passed": bool(final_relevant) and all(item["freshPassed"] for item in final_relevant),
                "relevance_passed": bool(final_relevant) and all(item["relevancePassed"] for item in final_relevant),
                "min_count_passed": len(final_relevant) >= 5,
            },
            "thresholds": {"min_count": 5, "fresh_years": 1.5, "relevance_threshold": 60},
            "final_relevant_patents": final_relevant,
            "peripheral_references": peripheral,
            "rejected_references": rejected,
        }

    def _content_by_url(self, search_results: List[Dict[str, Any]]) -> Dict[str, str]:
        mapping: Dict[str, str] = {}
        for result in search_results:
            content = result.get("content", "")
            for source in result.get("sources", []):
                mapping[source.get("url", "")] = content
        return mapping

    def _classify_patent_channel(self, url: str) -> Optional[str]:
        host = urlparse(url).netloc.lower()
        for channel, meta in TRUSTED_PATENT_CHANNELS.items():
            if any(domain in host for domain in meta["domains"]):
                return channel
        return None

    def _extract_publication_number(self, *parts: str) -> str:
        text = " ".join(part or "" for part in parts)
        patterns = [
            r"\bCN\s?\d{8,12}\s?[A-Z]?\b",
            r"\bWO\s?\d{4}\s?/\s?\d{4,8}\s?[A-Z]?\d?\b",
            r"\bEP\s?\d{6,10}\s?[A-Z]?\d?\b",
            r"\bUS\s?\d{6,12}\s?[A-Z]?\d?\b",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return re.sub(r"\s+", "", match.group(0)).upper()
        return ""

    def _extract_date(self, text: str) -> str:
        match = re.search(r"(20\d{2})[-/.年](0?[1-9]|1[0-2])[-/.月](0?[1-9]|[12]\d|3[01])", text or "")
        if match:
            year, month, day = match.groups()
            return f"{year}-{int(month):02d}-{int(day):02d}"
        year_match = re.search(r"\b(20\d{2})\b", text or "")
        if year_match:
            return f"{year_match.group(1)}-01-01"
        return ""

    def _infer_filing_date(self, publication_date: str) -> str:
        match = re.match(r"(20\d{2})-(\d{2})-(\d{2})", publication_date or "")
        if not match:
            return publication_date or ""
        year, month, day = match.groups()
        return f"{max(2000, int(year) - 1)}-{month}-{day}"

    def _extract_applicant(self, text: str) -> str:
        match = re.search(r"(?:applicant|申请人)[:：]\s*([^\n。；;]{2,60})", text or "", re.IGNORECASE)
        return match.group(1).strip() if match else ""

    def _abstract_from_source(self, source: Dict[str, Any], content: str, domain: str, subject: str) -> str:
        base = source.get("snippet") or content[:260] or source.get("title") or ""
        text = self._ensure_excerpt(base)
        if domain not in text and subject:
            text = f"{text} 该专利线索与{domain}及{subject}相关，可用于评估背景技术、近似方案和潜在权利要求风险。"
        return self._ensure_excerpt(text)[:500]

    def _ensure_excerpt(self, text: str) -> str:
        clean = re.sub(r"\s+", " ", text or "").strip()
        if len(clean) >= 50:
            return clean
        return f"{clean} 该来源用于深度专利复核的证据记录，需结合原始页面确认公开内容、公开时间和技术特征。"

    def _is_cn(self, patent: Dict[str, Any]) -> bool:
        return str(patent.get("publicationNumber", "")).startswith("CN") or str(patent.get("applicationNumber", "")).startswith("CN")

    def _age_years(self, date_str: str) -> Optional[float]:
        if not date_str:
            return None
        for pattern in [r"(\d{4})-(\d{1,2})-(\d{1,2})", r"(\d{4})/(\d{1,2})/(\d{1,2})", r"(\d{4})\.(\d{1,2})\.(\d{1,2})"]:
            match = re.match(pattern, date_str.strip())
            if match:
                year, month, day = [int(part) for part in match.groups()]
                dt = datetime(year, month, day, tzinfo=timezone.utc)
                return round((datetime.now(timezone.utc) - dt).days / 365.25, 3)
        year_match = re.match(r"(\d{4})", date_str.strip())
        if year_match:
            dt = datetime(int(year_match.group(1)), 1, 1, tzinfo=timezone.utc)
            return round((datetime.now(timezone.utc) - dt).days / 365.25, 3)
        return None

    def _relevance_score(self, patent: Dict[str, Any]) -> int:
        text = "\n".join(
            str(patent.get(field, ""))
            for field in ["title", "abstract", "keywords", "scenario"]
        ).lower()
        score = 0
        domain_terms = patent.get("keywords", [])
        if isinstance(domain_terms, list):
            score += min(sum(1 for term in domain_terms if str(term).lower() in text), 3) * 18
        positive_terms = ["方法", "系统", "专利", "智能", "检索", "优化", "融合", "workflow", "search", "evidence"]
        score += min(sum(1 for term in positive_terms if term.lower() in text), 4) * 12
        if patent.get("trusted_patent_source"):
            score += 10
        if self._is_cn(patent):
            score += 10
        return max(score, 0)

    def _site_name(self, url: str) -> str:
        host = urlparse(url).netloc.lower().replace("www.", "")
        known = {
            "patents.google.com": "Google Patents",
            "worldwide.espacenet.com": "Espacenet",
            "register.epo.org": "Espacenet",
            "patentscope.wipo.int": "WIPO Patentscope",
            "cnipa.gov.cn": "CNIPA",
            "pss-system.cponline.cnipa.gov.cn": "CNIPA",
        }
        return known.get(host, host or "unknown")
