"""Build a resumable, field-specific FTS5 index for the read-only vault API.

Unlike the legacy keyword index, every semantic field is a separate FTS column.
Imported Svalbard records put a complete proposal into ``method.high_level_flow``;
the technique view therefore uses only explicit Method/Model details sections.
The full source remains in the vault and is never modified by this builder.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import signal
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ideascientist.vault.fields import FIELD_NAMES, field_texts

EXTRACTION_VERSION = "technique-fields-v1"
INDEX_VERSION = "technique-fts-v1"
FTS_COLUMNS = ("title", *FIELD_NAMES)
_HEADING = re.compile(r"^ {0,3}(#{1,6})\s+(.+?)\s*#*\s*$", re.MULTILINE)


def _heading_key(value: str) -> str:
    value = re.sub(r"^\s*\d+(?:\.\d+)*[.)]?\s*", "", value)
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def proposal_sections(proposal: str) -> dict[str, str]:
    """Read Markdown sections, retaining subordinate headings in their parent.

    A section ends at the next heading of equal or higher level. Only heading
    boundaries are recognized; words in body prose never become section labels.
    """
    headings = list(_HEADING.finditer(proposal))
    sections: dict[str, str] = {}
    for i, match in enumerate(headings):
        level = len(match.group(1))
        end = len(proposal)
        for following in headings[i + 1:]:
            if len(following.group(1)) <= level:
                end = following.start()
                break
        key = _heading_key(match.group(2))
        content = proposal[match.end():end].strip()
        if content:
            sections[key] = content
    return sections


def technique_fields(record: dict[str, Any]) -> dict[str, str]:
    """Return searchable fields and explicit source labels, deterministically.

    For imported proposals with no Method section, solution is intentionally
    empty. The full proposal is not silently substituted as technique evidence.
    Native structured records use the repository's canonical field mapper.
    """
    result = field_texts(record)
    result.update(solution_source="structured_method_and_model_details",
                  challenge_source="structured_core_problem",
                  intuition_source="structured_key_novelty")
    imported = record.get("_svalbard")
    if not isinstance(imported, dict):
        return result
    result["challenge_source"] = "imported_problem_definition_fallback"
    result["intuition_source"] = "imported_intuition_fallback"
    proposal = imported.get("proposal_masked") or ""
    sections = proposal_sections(proposal) if isinstance(proposal, str) else {}
    methods = []
    for key in ("method", "methods", "methodology", "research method", "proposed method",
                "proposed methodology", "model details"):
        if sections.get(key):
            methods.append((key, sections[key]))
    result["solution"] = "\n\n".join(f"## {key.title()}\n{text}" for key, text in methods)
    result["solution_source"] = ("proposal_sections:" + ",".join(key for key, _ in methods)
                                 if methods else "missing_method_section")
    if sections.get("problem"):
        result["challenge"] = sections["problem"]
        result["challenge_source"] = "proposal_section:problem"
    if sections.get("key novelty"):
        result["intuition"] = sections["key novelty"]
        result["intuition_source"] = "proposal_section:key novelty"
    return result


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _fingerprint(source: Path) -> dict:
    result = {"path": str(source.resolve()), "size": source.stat().st_size,
              "mtime_ns": source.stat().st_mtime_ns}
    wal = Path(str(source) + "-wal")
    if wal.exists() and wal.stat().st_size:
        result["wal"] = {"size": wal.stat().st_size, "mtime_ns": wal.stat().st_mtime_ns}
    return result


def _read_meta(con: sqlite3.Connection) -> dict:
    return {key: json.loads(value) for key, value in con.execute("SELECT key,value FROM build_meta")}


def _save_meta(con: sqlite3.Connection, values: dict) -> None:
    con.executemany("INSERT OR REPLACE INTO build_meta(key,value) VALUES (?,?)",
                    [(key, json.dumps(value, ensure_ascii=False)) for key, value in values.items()])


def build(source: Path, output: Path, *, batch_size: int = 2000) -> dict:
    """Resume committed batches in OUTPUT.building, then atomically publish.

    Existing complete indexes are never replaced. To rebuild with changed source
    data, choose a new output path and switch the service after verification.
    """
    source, output = source.resolve(), output.resolve()
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    if not source.is_file():
        raise FileNotFoundError(source)
    if source == output:
        raise ValueError("Source and output must differ")
    output.parent.mkdir(parents=True, exist_ok=True)
    snapshot = _fingerprint(source)
    with Path(str(output) + ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if output.exists():
            completed = sqlite3.connect(output.as_uri() + "?mode=ro", uri=True)
            try:
                info = _read_meta(completed)
            finally:
                completed.close()
            if (info.get("status") == "complete" and info.get("source_fingerprint") == snapshot
                    and info.get("extraction_version") == EXTRACTION_VERSION):
                return info
            raise ValueError("Output exists with different source/version or incomplete state; use a new output path")
        temporary = Path(str(output) + ".building")
        incoming = sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)
        incoming.execute("PRAGMA query_only=ON")
        incoming.execute("PRAGMA cache_size=-65536")
        con = sqlite3.connect(temporary)
        try:
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("PRAGMA synchronous=NORMAL")
            con.execute("PRAGMA cache_size=-131072")
            con.execute("PRAGMA temp_store=MEMORY")
            con.execute("CREATE TABLE IF NOT EXISTS build_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)")
            info = _read_meta(con)
            if info:
                if (info.get("source_fingerprint") != snapshot
                        or info.get("extraction_version") != EXTRACTION_VERSION):
                    raise ValueError("Source or extraction changed since checkpoint; use a new output path")
            else:
                con.execute("CREATE VIRTUAL TABLE IF NOT EXISTS techniques_fts USING fts5(title,problem_definition,challenge,intuition,solution,content='',tokenize='porter unicode61 remove_diacritics 2')")
                con.execute("CREATE TABLE IF NOT EXISTS techniques_meta(paper_id INTEGER PRIMARY KEY,title TEXT NOT NULL,date TEXT NOT NULL,arxiv_id TEXT,categories TEXT NOT NULL,solution_source TEXT NOT NULL)")
                info = {"status": "building", "index_version": INDEX_VERSION,
                        "extraction_version": EXTRACTION_VERSION, "source_fingerprint": snapshot,
                        "started_at": _now(), "updated_at": _now(), "count": 0, "last_id": 0,
                        "source_count": incoming.execute("SELECT count(*) FROM papers").fetchone()[0],
                        "field_counts": {field: 0 for field in FIELD_NAMES},
                        "solution_sources": {}, "missing_metadata": 0}
                _save_meta(con, info)
                con.commit()
            start, start_count = time.monotonic(), info["count"]
            while True:
                rows = incoming.execute(
                    "SELECT p.id,p.title,p.date,p.arxiv_id,b.fields_json FROM papers p "
                    "LEFT JOIN metadata_results_masked b ON b.paper_id=p.id "
                    "WHERE p.id>? ORDER BY p.id LIMIT ?", (info["last_id"], batch_size)).fetchall()
                if not rows:
                    break
                fts_rows, meta_rows = [], []
                for pid, title, date, arxiv_id, fields_json in rows:
                    record = json.loads(fields_json) if fields_json else {}
                    if not isinstance(record, dict):
                        raise ValueError(f"Non-object metadata for paper {pid}")
                    fields = technique_fields(record)
                    categories = record.get("_svalbard", {}).get("categories", [])
                    if not isinstance(categories, list):
                        categories = []
                    fts_rows.append((pid, title or "", *(fields[field] for field in FIELD_NAMES)))
                    meta_rows.append((pid, title or "", date or "", arxiv_id,
                                      json.dumps(categories, ensure_ascii=False), fields["solution_source"]))
                    for field in FIELD_NAMES:
                        info["field_counts"][field] += bool(fields[field])
                    label = fields["solution_source"]
                    info["solution_sources"][label] = info["solution_sources"].get(label, 0) + 1
                    info["missing_metadata"] += fields_json is None
                con.executemany("INSERT INTO techniques_fts(rowid,title,problem_definition,challenge,intuition,solution) VALUES (?,?,?,?,?,?)", fts_rows)
                con.executemany("INSERT INTO techniques_meta VALUES (?,?,?,?,?,?)", meta_rows)
                info.update(count=info["count"] + len(rows), last_id=rows[-1][0], updated_at=_now())
                _save_meta(con, info)
                con.commit()
                if info["count"] % 10000 < batch_size or len(rows) < batch_size:
                    elapsed = max(time.monotonic() - start, .001)
                    rate = (info["count"] - start_count) / elapsed
                    print(json.dumps({"count": info["count"], "total": info["source_count"],
                                      "papers_per_second": round(rate, 1),
                                      "elapsed_seconds": round(elapsed, 1)}, ensure_ascii=False), flush=True)
            if _fingerprint(source) != snapshot:
                raise ValueError("Source changed during build; cannot publish a mixed snapshot")
            if info["count"] != info["source_count"]:
                raise ValueError("Indexed row count differs from frozen source count")
            info.update(status="optimizing", updated_at=_now())
            _save_meta(con, info)
            con.commit()
            print("Optimizing complete field index", flush=True)
            con.execute("INSERT INTO techniques_fts(techniques_fts) VALUES ('optimize')")
            con.execute("INSERT INTO techniques_fts(techniques_fts) VALUES ('integrity-check')")
            actual = con.execute("SELECT count(*) FROM techniques_meta").fetchone()[0]
            if actual != info["source_count"]:
                raise ValueError("Metadata row count mismatch")
            info.update(status="complete", completed_at=_now(), updated_at=_now())
            _save_meta(con, info)
            con.commit()
            con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            con.execute("PRAGMA journal_mode=DELETE")
            con.close()
            with temporary.open("rb") as handle:
                os.fsync(handle.fileno())
            temporary.replace(output)
            print(json.dumps(info, ensure_ascii=False), flush=True)
            return info
        finally:
            con.close()
            incoming.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=2000)
    args = parser.parse_args()
    def interrupted(_signum, _frame):
        raise KeyboardInterrupt("Interrupted; resume with the same command")
    signal.signal(signal.SIGTERM, interrupted)
    build(args.db, args.out, batch_size=args.batch_size)


if __name__ == "__main__":
    main()
