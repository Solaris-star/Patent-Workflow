#!/usr/bin/env python3
"""Lightweight external research cache for patent workflow.

MVP storage: SQLite + FTS5 + append-only JSONL. This cache only stores
external public research notes; local project materials are deliberately
excluded.
"""

import hashlib
import json
import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


def _default_cache_root() -> Path:
    env = os.environ.get("PATENT_RESEARCH_CACHE_ROOT", "")
    if env:
        return Path(env)
    xdg = os.environ.get("XDG_CACHE_HOME", "")
    if xdg:
        return Path(xdg) / "patent-workflow" / "research-cache"
    return Path.home() / ".cache" / "patent-workflow" / "research-cache"
TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "ref", "fbclid", "gclid"}
TTL_BY_SOURCE_TYPE = {
    "patent": 180,
    "hotspot": 14,
    "news": 14,
    "academic": 180,
    "technical": 60,
    "industry": 90,
    "web": 60,
}


class ResearchCache:
    """SQLite/JSONL cache for external source reading notes."""

    def __init__(self, root: Optional[Path] = None):
        configured = os.environ.get("PATENT_WORKFLOW_RESEARCH_CACHE_DIR")
        self.root = Path(root or configured or _default_cache_root()).expanduser()
        self.db_path = self.root / "cache.db"
        self.records_dir = self.root / "records"
        self.root.mkdir(parents=True, exist_ok=True)
        self.records_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS research_docs (
                  rowid INTEGER PRIMARY KEY AUTOINCREMENT,
                  record_id TEXT UNIQUE,
                  source_type TEXT NOT NULL,
                  source_channel TEXT,
                  site TEXT,
                  title TEXT,
                  url TEXT,
                  canonical_url TEXT,
                  url_hash TEXT UNIQUE,
                  content_hash TEXT,
                  normalized_title_hash TEXT,
                  published_at TEXT,
                  captured_at TEXT,
                  cached_at TEXT,
                  last_used_at TEXT,
                  revalidated_at TEXT,
                  ttl_days INTEGER,
                  expires_at TEXT,
                  cache_status TEXT,
                  domain_scope_json TEXT,
                  candidate_direction TEXT,
                  page_summary TEXT,
                  key_technical_facts_json TEXT,
                  do_not_overclaim_json TEXT,
                  candidate_relevance REAL,
                  source_quality_score REAL,
                  evidence_level TEXT,
                  reusable_in_phase_json TEXT,
                  tags_json TEXT,
                  keywords_json TEXT,
                  usage_policy TEXT,
                  must_revalidate_before_use INTEGER,
                  security_json TEXT,
                  raw_json TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS patent_docs (
                  record_id TEXT PRIMARY KEY,
                  publication_number TEXT UNIQUE,
                  application_number TEXT,
                  publication_date TEXT,
                  application_date TEXT,
                  assignee TEXT,
                  legal_status TEXT,
                  status_source TEXT,
                  cnipa_hits INTEGER,
                  abstract TEXT,
                  claims_summary TEXT,
                  collision_risk TEXT,
                  collision_notes_json TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS query_runs (
                  search_run_id TEXT PRIMARY KEY,
                  phase TEXT,
                  query TEXT,
                  domain_scope_json TEXT,
                  candidate_direction TEXT,
                  started_at TEXT,
                  finished_at TEXT,
                  source_channel TEXT,
                  result_count INTEGER,
                  imported_count INTEGER
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS doc_usage (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  record_id TEXT,
                  search_run_id TEXT,
                  used_in_phase TEXT,
                  used_at TEXT,
                  use_decision TEXT,
                  notes TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS revalidation_events (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  record_id TEXT,
                  revalidated_at TEXT,
                  revalidation_type TEXT,
                  previous_status TEXT,
                  new_status TEXT,
                  source_channel TEXT,
                  result_json TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS research_docs_fts USING fts5(
                  title,
                  page_summary,
                  key_technical_facts,
                  tags,
                  keywords,
                  candidate_direction,
                  content='research_docs',
                  content_rowid='rowid'
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_docs_source_type ON research_docs(source_type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_docs_expires_at ON research_docs(expires_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_docs_cache_status ON research_docs(cache_status)")
            conn.commit()

    def import_source_reading_notes(
        self,
        notes: Iterable[Dict[str, Any]],
        phase: str,
        query: str = "",
        domain_scope: Any = None,
        candidate_direction: str = "",
    ) -> Dict[str, Any]:
        started_at = self._now()
        search_run_id = self._run_id(phase, query, started_at)
        imported = 0
        skipped_private = 0
        duplicates = 0
        input_notes = list(notes or [])
        jsonl_path = self._jsonl_path(started_at)
        with sqlite3.connect(self.db_path) as conn, jsonl_path.open("a", encoding="utf-8") as jsonl:
            for note in input_notes:
                record = self._record_from_note(note, phase, query, domain_scope, candidate_direction, search_run_id)
                if not record:
                    skipped_private += 1
                    continue
                try:
                    self._insert_record(conn, record)
                    jsonl.write(json.dumps(record, ensure_ascii=False) + "\n")
                    imported += 1
                except sqlite3.IntegrityError:
                    duplicates += 1
            conn.execute(
                "INSERT OR REPLACE INTO query_runs(search_run_id, phase, query, domain_scope_json, candidate_direction, started_at, finished_at, source_channel, result_count, imported_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    search_run_id,
                    phase,
                    query,
                    json.dumps(self._listify(domain_scope), ensure_ascii=False),
                    candidate_direction,
                    started_at,
                    self._now(),
                    "smart-search",
                    len(input_notes),
                    imported,
                ),
            )
            conn.commit()
        return {
            "search_run_id": search_run_id,
            "input_count": len(input_notes),
            "imported_count": imported,
            "duplicate_count": duplicates,
            "skipped_private_count": skipped_private,
            "jsonl_path": str(jsonl_path),
        }

    def search(self, query: str, phase: str = "", source_types: Optional[List[str]] = None, limit: int = 10) -> List[Dict[str, Any]]:
        sanitized_query = self._sanitize_query(query)
        if not sanitized_query:
            return []
        source_types = source_types or []
        type_filter = ""
        params: List[Any] = [sanitized_query]
        if source_types:
            placeholders = ",".join("?" for _ in source_types)
            type_filter = f" AND d.source_type IN ({placeholders})"
            params.extend(source_types)
        params.append(limit)
        sql = f"""
            SELECT d.record_id, d.source_type, d.source_channel, d.site, d.title, d.url,
                   d.page_summary, d.key_technical_facts_json, d.tags_json, d.keywords_json,
                   d.cache_status, d.expires_at, d.revalidated_at, d.cached_at,
                   bm25(research_docs_fts) AS lexical_score
            FROM research_docs_fts
            JOIN research_docs d ON d.rowid = research_docs_fts.rowid
            WHERE research_docs_fts MATCH ?
              AND d.cache_status != 'expired_ignore'
              {type_filter}
            ORDER BY lexical_score ASC, d.source_quality_score DESC
            LIMIT ?
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute(sql, params).fetchall()
            except sqlite3.OperationalError:
                rows = []
            if len(rows) < limit:
                rows = self._merge_fallback_rows(conn, rows, sanitized_query, source_types, limit)
        results = [self._row_to_result(row) for row in rows]
        if phase:
            self._record_usage(results, phase)
        return results

    def _merge_fallback_rows(
        self,
        conn: sqlite3.Connection,
        rows: List[sqlite3.Row],
        query: str,
        source_types: List[str],
        limit: int,
    ) -> List[sqlite3.Row]:
        terms = self._query_terms(query)
        if not terms:
            return rows
        existing_ids = {row["record_id"] for row in rows}
        type_filter = ""
        params: List[Any] = []
        if source_types:
            placeholders = ",".join("?" for _ in source_types)
            type_filter = f" AND source_type IN ({placeholders})"
            params.extend(source_types)
        like_clauses = []
        for term in terms:
            pattern = f"%{term}%"
            like_clauses.append(
                "(title LIKE ? OR page_summary LIKE ? OR key_technical_facts_json LIKE ? OR tags_json LIKE ? OR keywords_json LIKE ? OR candidate_direction LIKE ?)"
            )
            params.extend([pattern] * 6)
        params.append(limit)
        fallback_sql = f"""
            SELECT record_id, source_type, source_channel, site, title, url,
                   page_summary, key_technical_facts_json, tags_json, keywords_json,
                   cache_status, expires_at, revalidated_at, cached_at,
                   999.0 AS lexical_score
            FROM research_docs
            WHERE cache_status != 'expired_ignore'
              {type_filter}
              AND ({' OR '.join(like_clauses)})
            ORDER BY source_quality_score DESC, cached_at DESC
            LIMIT ?
        """
        fallback_rows = conn.execute(fallback_sql, params).fetchall()
        merged = list(rows)
        for row in fallback_rows:
            if row["record_id"] in existing_ids:
                continue
            merged.append(row)
            existing_ids.add(row["record_id"])
            if len(merged) >= limit:
                break
        return merged

    def _insert_record(self, conn: sqlite3.Connection, record: Dict[str, Any]) -> None:
        doc = record["doc"]
        conn.execute(
            """
            INSERT INTO research_docs(
              record_id, source_type, source_channel, site, title, url, canonical_url, url_hash,
              content_hash, normalized_title_hash, published_at, captured_at, cached_at, last_used_at,
              revalidated_at, ttl_days, expires_at, cache_status, domain_scope_json, candidate_direction,
              page_summary, key_technical_facts_json, do_not_overclaim_json, candidate_relevance,
              source_quality_score, evidence_level, reusable_in_phase_json, tags_json, keywords_json,
              usage_policy, must_revalidate_before_use, security_json, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                doc["record_id"], doc["source_type"], doc.get("source_channel", ""), doc.get("site", ""), doc.get("title", ""),
                doc.get("url", ""), doc.get("canonical_url", ""), doc.get("url_hash", ""), doc.get("content_hash", ""),
                doc.get("normalized_title_hash", ""), doc.get("published_at", ""), doc.get("captured_at", ""), doc.get("cached_at", ""),
                doc.get("last_used_at"), doc.get("revalidated_at"), doc.get("ttl_days", 60), doc.get("expires_at", ""),
                doc.get("cache_status", "fresh"), json.dumps(doc.get("domain_scope", []), ensure_ascii=False), doc.get("candidate_direction", ""),
                doc.get("page_summary", ""), json.dumps(doc.get("key_technical_facts", []), ensure_ascii=False),
                json.dumps(doc.get("do_not_overclaim", []), ensure_ascii=False), doc.get("candidate_relevance", 0.0), doc.get("source_quality_score", 0.5),
                doc.get("evidence_level", "background"), json.dumps(doc.get("reusable_in_phase", []), ensure_ascii=False),
                json.dumps(doc.get("tags", []), ensure_ascii=False), json.dumps(doc.get("keywords", []), ensure_ascii=False),
                doc.get("usage_policy", "background_only"), 1 if doc.get("must_revalidate_before_use") else 0,
                json.dumps(doc.get("security", {}), ensure_ascii=False), json.dumps(record, ensure_ascii=False),
            ),
        )
        rowid = conn.execute("SELECT rowid FROM research_docs WHERE record_id = ?", (doc["record_id"],)).fetchone()[0]
        conn.execute(
            "INSERT INTO research_docs_fts(rowid, title, page_summary, key_technical_facts, tags, keywords, candidate_direction) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                rowid,
                doc.get("title", ""),
                doc.get("page_summary", ""),
                " ".join(doc.get("key_technical_facts", [])),
                " ".join(doc.get("tags", [])),
                " ".join(doc.get("keywords", [])),
                doc.get("candidate_direction", ""),
            ),
        )
        patent = record.get("patent")
        if patent and patent.get("publication_number"):
            conn.execute(
                "INSERT OR REPLACE INTO patent_docs(record_id, publication_number, application_number, publication_date, application_date, assignee, legal_status, status_source, cnipa_hits, abstract, claims_summary, collision_risk, collision_notes_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    doc["record_id"], patent.get("publication_number", ""), patent.get("application_number", ""), patent.get("publication_date", ""),
                    patent.get("application_date", ""), patent.get("assignee", ""), patent.get("legal_status", ""), patent.get("status_source", ""),
                    patent.get("cnipa_hits", 0), patent.get("abstract", ""), patent.get("claims_summary", ""), patent.get("collision_risk", ""),
                    json.dumps(patent.get("collision_notes", []), ensure_ascii=False),
                ),
            )

    def _record_from_note(self, note: Dict[str, Any], phase: str, query: str, domain_scope: Any, candidate_direction: str, search_run_id: str) -> Optional[Dict[str, Any]]:
        if self._is_private_or_local(note):
            return None
        now = self._now()
        source_type = str(note.get("source_type") or "web")
        canonical_url = self._canonicalize_url(str(note.get("url", "")))
        title = str(note.get("title") or "")
        summary = str(note.get("page_summary") or "")
        facts = [str(item) for item in note.get("key_technical_facts", []) if str(item).strip()]
        ttl_days = TTL_BY_SOURCE_TYPE.get(source_type, 60)
        expires_at = (datetime.fromisoformat(now.replace("Z", "+00:00")) + timedelta(days=ttl_days)).isoformat().replace("+00:00", "Z")
        tags = self._derive_tags(domain_scope, note, query)
        keywords = self._derive_keywords(title, summary, facts, tags)
        record_id = self._record_id(canonical_url or title, summary)
        patent = self._patent_from_note(note, source_type)
        must_revalidate = source_type == "patent"
        doc = {
            "record_id": record_id,
            "source_type": source_type,
            "source_channel": note.get("source_channel") or note.get("source_type") or "smart-search",
            "site": note.get("site", ""),
            "title": title,
            "url": note.get("url", ""),
            "canonical_url": canonical_url,
            "url_hash": self._hash(canonical_url or title),
            "content_hash": self._hash("\n".join([summary, *facts])),
            "normalized_title_hash": self._hash(self._normalize_title(title)),
            "published_at": note.get("published_at", ""),
            "captured_at": now,
            "cached_at": now,
            "last_used_at": None,
            "revalidated_at": note.get("revalidated_at"),
            "ttl_days": ttl_days,
            "expires_at": expires_at,
            "cache_status": "fresh",
            "domain_scope": self._listify(domain_scope),
            "candidate_direction": candidate_direction,
            "page_summary": summary,
            "key_technical_facts": facts,
            "do_not_overclaim": self._listify(note.get("do_not_overclaim")),
            "candidate_relevance": float(note.get("candidate_relevance_score") or 0.6),
            "source_quality_score": self._source_quality_score(source_type, note),
            "evidence_level": "prior_art_candidate" if source_type == "patent" else "background",
            "reusable_in_phase": self._reusable_phases(source_type),
            "tags": tags,
            "keywords": keywords,
            "usage_policy": "prior_art_candidate_requires_revalidation" if source_type == "patent" else "background_only",
            "must_revalidate_before_use": must_revalidate,
            "security": {
                "contains_user_private_material": False,
                "redaction_applied": True,
                "redacted_terms_count": 0,
                "allowed_cache_scope": "external_public_only",
            },
            "search_run_id": search_run_id,
            "phase_origin": phase,
            "query": query,
        }
        return {"schema_version": "1.0", "record_kind": "external_source", "doc": doc, "patent": patent, "raw_note": note}

    def _is_private_or_local(self, note: Dict[str, Any]) -> bool:
        if str(note.get("source_type", "")) == "local_project":
            return True
        url = str(note.get("url", ""))
        if not url:
            return True
        parsed = urlparse(url)
        if parsed.scheme in {"file", ""}:
            return True
        if parsed.scheme not in {"http", "https"}:
            return True
        lowered = url.lower()
        return any(token in lowered for token in ["localhost", "127.0.0.1", "/users/", "\\users\\", "/private/", "node_modules"])

    def _patent_from_note(self, note: Dict[str, Any], source_type: str) -> Optional[Dict[str, Any]]:
        if source_type != "patent":
            return None
        text = " ".join(str(note.get(key, "")) for key in ["title", "url", "page_summary"])
        match = re.search(r"\bCN\d{6,}[A-Z]?\b", text, flags=re.IGNORECASE)
        publication_number = match.group(0).upper() if match else ""
        if not publication_number:
            return None
        return {
            "publication_number": publication_number,
            "application_number": note.get("application_number", ""),
            "publication_date": note.get("publication_date", ""),
            "application_date": note.get("application_date", ""),
            "assignee": note.get("assignee", ""),
            "legal_status": note.get("legal_status", "pending_or_unknown"),
            "status_source": note.get("status_source", "cache_import"),
            "cnipa_hits": int(note.get("cnipa_hits") or 0),
            "abstract": note.get("page_summary", ""),
            "claims_summary": note.get("claims_summary", ""),
            "collision_risk": note.get("collision_risk", "unknown"),
            "collision_notes": self._listify(note.get("collision_notes")),
        }

    def _row_to_result(self, row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "record_id": row["record_id"],
            "source_type": row["source_type"],
            "source_channel": row["source_channel"],
            "site": row["site"],
            "title": row["title"],
            "url": row["url"],
            "page_summary": row["page_summary"],
            "key_technical_facts": json.loads(row["key_technical_facts_json"] or "[]"),
            "tags": json.loads(row["tags_json"] or "[]"),
            "keywords": json.loads(row["keywords_json"] or "[]"),
            "cache_status": row["cache_status"],
            "expires_at": row["expires_at"],
            "revalidated_at": row["revalidated_at"],
            "cached_at": row["cached_at"],
            "lexical_score": row["lexical_score"],
        }

    def _record_usage(self, results: List[Dict[str, Any]], phase: str) -> None:
        if not results:
            return
        now = self._now()
        with sqlite3.connect(self.db_path) as conn:
            for result in results:
                conn.execute("UPDATE research_docs SET last_used_at = ? WHERE record_id = ?", (now, result["record_id"]))
                conn.execute(
                    "INSERT INTO doc_usage(record_id, search_run_id, used_in_phase, used_at, use_decision, notes) VALUES (?, ?, ?, ?, ?, ?)",
                    (result["record_id"], "", phase, now, "cache_hit", "used as historical research candidate"),
                )
            conn.commit()

    def _jsonl_path(self, now: str) -> Path:
        dt = datetime.fromisoformat(now.replace("Z", "+00:00"))
        path = self.records_dir / f"{dt.year:04d}" / f"{dt.month:02d}" / f"records-{dt.year:04d}-{dt.month:02d}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _canonicalize_url(self, url: str) -> str:
        parsed = urlparse(url.strip())
        query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key.lower() not in TRACKING_PARAMS]
        path = parsed.path.rstrip("/") or parsed.path
        return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), path, "", urlencode(query), ""))

    def _sanitize_query(self, query: str) -> str:
        text = re.sub(r"(?:/[A-Za-z0-9._-]+){2,}", " ", query or "")
        text = re.sub(r"[A-Za-z]:\\(?:[^\\\s]+\\)+[^\\\s]+", " ", text)
        text = re.sub(r"\b[A-Z][A-Za-z0-9_-]{2,}(?:X9|Beta|Internal|Private)\b", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    def _query_terms(self, query: str) -> List[str]:
        terms: List[str] = []
        for token in re.split(r"[,，、\s]+", query or ""):
            token = token.strip().strip('\"')
            if len(token) >= 2 and token not in terms:
                terms.append(token)
        return terms[:8]

    def _derive_tags(self, domain_scope: Any, note: Dict[str, Any], query: str) -> List[str]:
        tags = []
        for value in [*self._listify(domain_scope), query, note.get("source_type", "")]:
            for token in re.split(r"[,，、\s]+", str(value or "")):
                token = token.strip()
                if len(token) >= 2 and token not in tags:
                    tags.append(token)
        return tags[:20]

    def _derive_keywords(self, title: str, summary: str, facts: List[str], tags: List[str]) -> List[str]:
        text = " ".join([title, summary, *facts, *tags])
        keywords = list(tags)
        for token in re.findall(r"[A-Za-z][A-Za-z0-9+-]{2,}|[\u4e00-\u9fff]{2,8}", text):
            if token not in keywords and len(keywords) < 30:
                keywords.append(token)
        return keywords

    def _source_quality_score(self, source_type: str, note: Dict[str, Any]) -> float:
        base = {"patent": 0.9, "academic": 0.82, "industry": 0.72, "technical": 0.68, "news": 0.55, "hotspot": 0.5, "web": 0.45}.get(source_type, 0.45)
        if note.get("site") and any(site in str(note.get("site", "")).lower() for site in ["cnipa", "patents", "arxiv", "ieee"]):
            base += 0.05
        return min(base, 0.98)

    def _reusable_phases(self, source_type: str) -> List[str]:
        if source_type == "patent":
            return ["phase_2", "phase_5"]
        return ["phase_2", "phase_5"]

    def _normalize_title(self, title: str) -> str:
        return re.sub(r"\W+", "", (title or "").lower())

    def _hash(self, value: str) -> str:
        return "sha256:" + hashlib.sha256((value or "").encode("utf-8")).hexdigest()

    def _record_id(self, identity: str, summary: str) -> str:
        digest = hashlib.sha256(f"{identity}\n{summary}".encode("utf-8")).hexdigest()[:24]
        return f"src_{digest}"

    def _run_id(self, phase: str, query: str, now: str) -> str:
        digest = hashlib.sha256(f"{phase}\n{query}\n{now}".encode("utf-8")).hexdigest()[:12]
        return f"run_{datetime.fromisoformat(now.replace('Z', '+00:00')).strftime('%Y%m%d%H%M%S')}_{digest}"

    def _listify(self, value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value if str(item).strip()]
        if isinstance(value, tuple):
            return [str(item) for item in value if str(item).strip()]
        if isinstance(value, str):
            if not value.strip():
                return []
            return [item.strip() for item in re.split(r"[,，、]+", value) if item.strip()]
        return [str(value)]

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
