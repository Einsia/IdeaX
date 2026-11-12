#!/usr/bin/env python3
"""Import the published SvalbardIdeaVault JSONL.zst files into the local vault DB.

The Hub corpus is already decomposed, so this import intentionally skips the
arXiv/full-text/decomposition stages. It creates the same ``papers`` and
``metadata_results_masked`` tables consumed by the harness and stores the
published record in ``fields_json``.
"""
from __future__ import annotations

import argparse
import glob
import json
import sqlite3
from pathlib import Path

import zstandard as zstd


SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
 id INTEGER PRIMARY KEY, title TEXT, authors TEXT, date TEXT, venue TEXT,
 source TEXT, url TEXT, abstract TEXT, arxiv_id TEXT, doi TEXT
);
CREATE TABLE IF NOT EXISTS metadata_results_masked (
 paper_id INTEGER PRIMARY KEY, fields_json TEXT NOT NULL, model TEXT,
 created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_papers_date ON papers(date);
CREATE UNIQUE INDEX IF NOT EXISTS idx_papers_arxiv_id ON papers(arxiv_id);
"""


def as_fields(row: dict) -> dict:
    # Keep the four published views while also presenting the shape expected
    # by ideascientist.vault.fields.field_texts.
    problem = row.get("problem_definition") or ""
    intuition = row.get("intuition") or ""
    proposal = row.get("proposal_masked") or ""
    return {
        "title": row.get("title", ""),
        "problem_definition": problem,
        "core_problem": {"problem_statement": problem, "why_it_matters": [], "concrete_example": ""},
        "key_novelty": {"main_idea": intuition, "explanation": []},
        "method": {"high_level_flow": [proposal]} if proposal else {},
        "_svalbard": {
            "arxiv_id": row.get("arxiv_id"), "arxiv_url": row.get("arxiv_url"),
            "categories": row.get("categories", []), "intuition": intuition,
            "proposal_masked": proposal,
        },
    }


def rows(path: Path):
    with path.open("rb") as raw:
        reader = zstd.ZstdDecompressor().stream_reader(raw)
        buf = b""
        while True:
            chunk = reader.read(1024 * 1024)
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if line.strip():
                    yield json.loads(line)
        if buf.strip():
            yield json.loads(buf)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", type=Path, default=Path("data/svalbard"))
    ap.add_argument("--db", type=Path, default=Path("data/idea_vault.db"))
    ap.add_argument("--split", default="corpus", choices=["corpus", "train", "validation", "test", "all"])
    ap.add_argument("--batch-size", type=int, default=2000)
    args = ap.parse_args()
    patterns = [args.split] if args.split != "all" else ["corpus", "train", "val", "test"]
    files = []
    for split in patterns:
        split = "val" if split == "validation" else split
        files.extend(sorted(Path(args.dataset, "records", split).glob("*.jsonl.zst")))
    if not files:
        raise SystemExit(f"no JSONL.zst files found under {args.dataset}")
    args.db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(args.db)
    con.executescript(SCHEMA)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    next_id = con.execute("SELECT COALESCE(MAX(id), 0) FROM papers").fetchone()[0] + 1
    processed = 0

    def flush(batch):
        nonlocal processed
        if not batch:
            return
        con.executemany(
            "INSERT OR IGNORE INTO papers VALUES (?,?,?,?,?,?,?,?,?,?)",
            [x[:10] for x in batch],
        )
        # Resolve the actual primary key after INSERT OR IGNORE. This makes
        # reruns safe: a duplicate arXiv id cannot create an orphan metadata row.
        aids = [x[8] for x in batch]
        marks = ",".join("?" for _ in aids)
        actual = {
            aid: pid
            for pid, aid in con.execute(
                f"SELECT id, arxiv_id FROM papers WHERE arxiv_id IN ({marks})", aids
            )
        }
        metadata = [
            (actual[x[8]], x[11], x[12])
            for x in batch
            if x[8] in actual
        ]
        con.executemany(
            "INSERT OR IGNORE INTO metadata_results_masked(paper_id,fields_json,model) VALUES (?,?,?)",
            metadata,
        )
        con.commit()
        processed += len(batch)
        print(f"{processed:,} records processed", flush=True)

    for path in files:
        batch = []
        for row in rows(path):
            # Corpus and train/test overlap by design; keep one row per arXiv id.
            aid = row.get("arxiv_id") or f"hf-{next_id}"
            pid = next_id; next_id += 1
            fields = as_fields(row)
            batch.append((pid, row.get("title", ""), json.dumps(row.get("authors", [])), row.get("date", ""), "arXiv", "huggingface", row.get("arxiv_url", ""), row.get("abstract", ""), aid, None, pid, json.dumps(fields, ensure_ascii=False), "svalbard-hub"))
            if len(batch) >= args.batch_size:
                flush(batch); batch=[]
        flush(batch)
    con.close()
    print(f"processed {processed:,} records into {args.db}")


if __name__ == "__main__":
    main()
