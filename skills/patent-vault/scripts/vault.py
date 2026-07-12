#!/usr/bin/env python3
"""patent-vault storage CLI: directions pool, case registry, title dedup.

Data root resolution (first match wins):
  1. --vault-dir
  2. env PATENT_VAULT_DIR
  3. ~/.patent-vault/redirect.txt  (single line: absolute path to follow, once)
  4. ~/.patent-vault/

Subcommands:
  init                                   create data root + empty data files
  check-title  "<title>"                 normalized bigram-Jaccard coarse screen (>=0.35)
  add-direction [--json-file f]          append one direction JSON (file preferred; stdin fallback)
                                         origin=mine REQUIRES origin_sensitive_map_path
  pick-direction <id> --target-workspace <dir>
                                         copy research snapshot into target workspace, mark picked;
                                         fails (without burning the direction) if a declared snapshot
                                         is missing; surfaces mine lineage for manifest inheritance
  list [--pool] [--status <s>]           list directions (with computed freshness) or cases
  register-case [--json-file f]          append one case JSON (file preferred; stdin fallback)
  update-case <case_id> [--status s] [--event e] [--set k=v ...]
  import-titles [--json-file f]          merge {"titles":[...]} into titles_used

All writes are atomic (temp + os.replace). Output: JSON to stdout. Exit 0 ok / 2 error.
"""

import argparse
import json
import os
import re
import shutil
import sys
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

for _s in (sys.stdout, sys.stderr, sys.stdin):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass

DEFAULT_ROOT = Path.home() / ".patent-vault"
JACCARD_THRESHOLD = 0.35
DEFAULT_VALID_DAYS = 180

# generic patent-title boilerplate stripped before similarity comparison
_BOILERPLATE = re.compile(
    r"一种|方法及系统|方法与系统|方法及装置|方法和装置|系统及方法|的方法|的系统|的装置|方法|系统|装置|设备|介质|终端|及其?"
)
_WS = re.compile(r"[\s　，,。.·、;；:：()（）\[\]【】\-—_/\\]+")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_root(cli_dir: str | None) -> Path:
    if cli_dir:
        return Path(cli_dir)
    env = os.environ.get("PATENT_VAULT_DIR")
    if env:
        return Path(env)
    redirect = DEFAULT_ROOT / "redirect.txt"
    if redirect.exists():
        target = redirect.read_text(encoding="utf-8", errors="replace").strip()
        if target:
            return Path(target)
    return DEFAULT_ROOT


def _atomic_write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp-{uuid.uuid4().hex[:8]}")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _load(path: Path, fallback: dict) -> dict:
    if not path.exists():
        return dict(fallback)
    return json.loads(path.read_text(encoding="utf-8"))


def _pool_path(root: Path) -> Path:
    return root / "directions_pool.json"


def _cases_path(root: Path) -> Path:
    return root / "cases.json"


def _titles_path(root: Path) -> Path:
    return root / "titles_used.json"


EMPTY_POOL = {"vault_type": "directions_pool", "schema_version": 1, "updated_at": "", "directions": []}
EMPTY_CASES = {"vault_type": "cases", "schema_version": 1, "updated_at": "", "cases": []}
EMPTY_TITLES = {"vault_type": "titles_used", "schema_version": 1, "updated_at": "", "titles": []}


def _normalize_title(t: str) -> str:
    t = _WS.sub("", t or "")
    t = _BOILERPLATE.sub("", t)
    return t.casefold()


def _bigrams(s: str) -> set[str]:
    if len(s) < 2:
        return {s} if s else set()
    return {s[i:i + 2] for i in range(len(s) - 1)}


def _jaccard(a: str, b: str) -> float:
    sa, sb = _bigrams(a), _bigrams(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def _direction_status(d: dict, now: datetime) -> str:
    if d.get("status") in ("picked", "retired"):
        return d["status"]
    anchor = d.get("revalidated_at") or d.get("harvested_at")
    valid_days = int(d.get("valid_days") or DEFAULT_VALID_DAYS)
    if anchor:
        try:
            base = datetime.fromisoformat(str(anchor).replace("Z", "+00:00"))
            if base.tzinfo is None:
                base = base.replace(tzinfo=timezone.utc)
            if now - base > timedelta(days=valid_days):
                return "expired"
        except ValueError:
            pass
    return "available"


def _ok(payload: dict) -> int:
    print(json.dumps({"ok": True, **payload}, ensure_ascii=False, indent=2))
    return 0


def _fail(msg: str) -> int:
    print(json.dumps({"ok": False, "error": msg}, ensure_ascii=False, indent=2))
    return 2


def cmd_init(root: Path) -> int:
    root.mkdir(parents=True, exist_ok=True)
    (root / "research_snapshots").mkdir(exist_ok=True)
    created = []
    for path, empty in ((_pool_path(root), EMPTY_POOL), (_cases_path(root), EMPTY_CASES), (_titles_path(root), EMPTY_TITLES)):
        if not path.exists():
            empty = dict(empty)
            empty["updated_at"] = _now()
            _atomic_write(path, empty)
            created.append(path.name)
    return _ok({"root": str(root), "created": created})


def _vault_ready(root: Path) -> bool:
    try:
        _load(_cases_path(root), EMPTY_CASES)
        return _cases_path(root).exists()
    except Exception:
        return False


def cmd_check_title(root: Path, title: str) -> int:
    norm = _normalize_title(title)
    cases = _load(_cases_path(root), EMPTY_CASES)["cases"]
    titles = _load(_titles_path(root), EMPTY_TITLES)["titles"]
    pool = _load(_pool_path(root), EMPTY_POOL)["directions"]

    candidates = []
    for source, items, title_key in (
        ("case", cases, "title"),
        ("imported", titles, "title"),
        ("direction", pool, "title_seed"),
    ):
        for it in items:
            other = it.get(title_key) or ""
            other_norm = it.get("title_normalized") or _normalize_title(other)
            score = _jaccard(norm, other_norm)
            if score >= JACCARD_THRESHOLD:
                candidates.append({
                    "source": source,
                    "title": other,
                    "similarity": round(score, 3),
                    "id": it.get("case_id") or it.get("direction_id") or "",
                    "status": it.get("status", ""),
                })
    candidates.sort(key=lambda c: -c["similarity"])
    return _ok({
        "title": title,
        "normalized": norm,
        "threshold": JACCARD_THRESHOLD,
        "collision_candidates": candidates,
        "note": "coarse screen only — the model MUST do semantic adjudication on candidates",
    })


def cmd_add_direction(root: Path, stdin_text: str) -> int:
    d = json.loads(stdin_text)
    if not isinstance(d, dict):
        return _fail("direction payload must be a JSON object")
    if not d.get("title_seed"):
        return _fail("direction.title_seed is required")
    # sensitive lineage must survive the vault detour: a mine-origin direction
    # without its map anchor could later be picked into a run that never
    # re-arms the deliver leak check
    if d.get("origin") == "mine" and not d.get("origin_sensitive_map_path"):
        return _fail("mine-origin direction requires origin_sensitive_map_path "
                     "(absolute path to the source project's confirmed sensitive_map.json)")
    pool = _load(_pool_path(root), EMPTY_POOL)
    d.setdefault("direction_id", f"DIR-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:4]}")
    d.setdefault("harvested_at", _now())
    d.setdefault("valid_days", DEFAULT_VALID_DAYS)
    d.setdefault("status", "available")
    d.setdefault("origin", "research")
    d["title_normalized"] = _normalize_title(d["title_seed"])
    pool["directions"].append(d)
    pool["updated_at"] = _now()
    _atomic_write(_pool_path(root), pool)
    return _ok({"direction_id": d["direction_id"]})


def cmd_pick_direction(root: Path, direction_id: str, target_workspace: str) -> int:
    pool = _load(_pool_path(root), EMPTY_POOL)
    now = datetime.now(timezone.utc)
    for d in pool["directions"]:
        if d.get("direction_id") == direction_id:
            status = _direction_status(d, now)
            snapshot_rel = (d.get("source_run") or {}).get("research_snapshot") or ""
            copied = None
            warnings = []
            if snapshot_rel:
                snapshot = root / snapshot_rel
                if not snapshot.exists():
                    # fail BEFORE mutating: burning the direction on a broken
                    # snapshot path would lose it with no undo command
                    return _fail(
                        f"research snapshot declared but not found: {snapshot} — direction NOT picked; "
                        "fix source_run.research_snapshot (path must be relative to the vault root, "
                        "e.g. research_snapshots/<run_id>.json)"
                    )
                dest = Path(target_workspace) / "artifacts" / "research" / "phase_02_research_pack.json"
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(snapshot, dest)
                copied = str(dest)
            else:
                warnings.append("no research snapshot declared — the new workspace must run patent-research")
            d["status"] = "picked"
            d["picked_at"] = _now()
            pool["updated_at"] = _now()
            _atomic_write(_pool_path(root), pool)
            origin = d.get("origin") or "research"
            result = {
                "direction_id": direction_id,
                "origin": origin,
                "freshness_at_pick": status,
                "snapshot_copied_to": copied,
                "revalidation_required": status == "expired",
                "warnings": warnings,
                "note": "expired direction picked — run a targeted patent-research revalidation before prior-art"
                if status == "expired" else "",
            }
            if origin == "mine":
                # sensitive lineage must be inherited by the new run's manifest,
                # otherwise the deliver leak check silently disarms
                result["sensitive_map_required"] = True
                result["origin_sensitive_map_path"] = d.get("origin_sensitive_map_path")
                result["manifest_instruction"] = (
                    "init_run_manifest.py --update --out <workspace>/artifacts/run_manifest.md "
                    "--research-origin vault_pool --vault-direction-origin mine "
                    "--sensitive-map-path <origin_sensitive_map_path>"
                )
            return _ok(result)
    return _fail(f"direction not found: {direction_id}")


def cmd_list(root: Path, pool_flag: bool, status: str | None) -> int:
    now = datetime.now(timezone.utc)
    if pool_flag:
        pool = _load(_pool_path(root), EMPTY_POOL)
        rows = []
        for d in pool["directions"]:
            st = _direction_status(d, now)
            if status and st != status:
                continue
            rows.append({"direction_id": d.get("direction_id"), "title_seed": d.get("title_seed"),
                         "origin": d.get("origin"), "domain_scope": d.get("domain_scope"),
                         "harvested_at": d.get("harvested_at"), "status": st})
        return _ok({"directions": rows, "count": len(rows)})
    cases = _load(_cases_path(root), EMPTY_CASES)["cases"]
    rows = [c for c in cases if not status or c.get("status") == status]
    slim = [{"case_id": c.get("case_id"), "title": c.get("title"), "status": c.get("status"),
             "workspace": c.get("workspace"), "delivered_at": c.get("delivered_at")} for c in rows]
    return _ok({"cases": slim, "count": len(slim)})


def cmd_register_case(root: Path, stdin_text: str) -> int:
    c = json.loads(stdin_text)
    if not c.get("title"):
        return _fail("case.title is required")
    cases = _load(_cases_path(root), EMPTY_CASES)
    c.setdefault("case_id", f"CASE-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:4]}")
    c.setdefault("status", "direction_selected")
    c.setdefault("created_at", _now())
    c["updated_at"] = _now()
    c["title_normalized"] = _normalize_title(c["title"])
    c.setdefault("events", []).append({"at": _now(), "event": "registered"})
    cases["cases"].append(c)
    cases["updated_at"] = _now()
    _atomic_write(_cases_path(root), cases)
    return _ok({"case_id": c["case_id"]})


def cmd_update_case(root: Path, case_id: str, status: str | None, event: str | None, sets: list[str]) -> int:
    cases = _load(_cases_path(root), EMPTY_CASES)
    for c in cases["cases"]:
        if c.get("case_id") == case_id:
            if status:
                c["status"] = status
            for kv in sets:
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    c[k.strip()] = v.strip()
            if event or status:
                c.setdefault("events", []).append({"at": _now(), "event": event or f"status:{status}"})
            c["updated_at"] = _now()
            cases["updated_at"] = _now()
            _atomic_write(_cases_path(root), cases)
            return _ok({"case_id": case_id, "status": c.get("status")})
    return _fail(f"case not found: {case_id}")


def cmd_import_titles(root: Path, stdin_text: str) -> int:
    data = json.loads(stdin_text)
    incoming = data.get("titles") or []
    titles = _load(_titles_path(root), EMPTY_TITLES)
    existing_norm = {t.get("title_normalized") for t in titles["titles"]}
    added = 0
    for t in incoming:
        if isinstance(t, str):
            t = {"title": t}
        norm = _normalize_title(t.get("title") or "")
        if not norm or norm in existing_norm:
            continue
        t["title_normalized"] = norm
        t.setdefault("source", "imported")
        titles["titles"].append(t)
        existing_norm.add(norm)
        added += 1
    titles["updated_at"] = _now()
    _atomic_write(_titles_path(root), titles)
    return _ok({"imported": added, "total": len(titles["titles"])})


def main() -> int:
    ap = argparse.ArgumentParser(description="patent-vault storage CLI")
    ap.add_argument("--vault-dir", help="Explicit vault data root")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init")
    p = sub.add_parser("check-title")
    p.add_argument("title")
    p = sub.add_parser("add-direction")
    p.add_argument("--json-file", help="Read direction JSON from file (preferred for CJK; avoids console-encoding issues)")
    p = sub.add_parser("pick-direction")
    p.add_argument("direction_id")
    p.add_argument("--target-workspace", required=True)
    p = sub.add_parser("list")
    p.add_argument("--pool", action="store_true")
    p.add_argument("--status")
    p = sub.add_parser("register-case")
    p.add_argument("--json-file", help="Read case JSON from file (preferred)")
    p = sub.add_parser("update-case")
    p.add_argument("case_id")
    p.add_argument("--status")
    p.add_argument("--event")
    p.add_argument("--set", dest="sets", action="append", default=[])
    p = sub.add_parser("import-titles")
    p.add_argument("--json-file", help="Read titles JSON from file (preferred)")

    args = ap.parse_args()
    root = _resolve_root(args.vault_dir)

    def _payload() -> str:
        jf = getattr(args, "json_file", None)
        if jf:
            return Path(jf).read_text(encoding="utf-8")
        return sys.stdin.read()

    try:
        if args.cmd == "init":
            return cmd_init(root)
        if not _vault_ready(root):
            return _fail(f"vault not initialized at {root} (run: vault.py init)")
        if args.cmd == "check-title":
            return cmd_check_title(root, args.title)
        if args.cmd == "add-direction":
            return cmd_add_direction(root, _payload())
        if args.cmd == "pick-direction":
            return cmd_pick_direction(root, args.direction_id, args.target_workspace)
        if args.cmd == "list":
            return cmd_list(root, args.pool, args.status)
        if args.cmd == "register-case":
            return cmd_register_case(root, _payload())
        if args.cmd == "update-case":
            return cmd_update_case(root, args.case_id, args.status, args.event, args.sets)
        if args.cmd == "import-titles":
            return cmd_import_titles(root, _payload())
        return _fail(f"unknown command: {args.cmd}")
    except json.JSONDecodeError as e:
        return _fail(f"JSON error: {e}")
    except OSError as e:
        return _fail(f"IO error: {e}")


if __name__ == "__main__":
    raise SystemExit(main())
