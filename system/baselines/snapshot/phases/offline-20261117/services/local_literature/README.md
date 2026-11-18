# Frozen local literature service

This service serves original paper metadata, original abstracts and available local text extractions. It performs no public-network request, model call, download or generated fallback. The default broad corpus has 283,008 records; 282,988 have abstracts and 1,948 have a local text extraction bound to exactly one paper ID. The database is read-only.

## Commands

From the offline phase root:

```bash
python services/local_literature/cli.py --corpus inputs/corpus/corpus.sqlite search --query 'Agent Workflow Memory' --limit 10
python services/local_literature/cli.py --corpus inputs/corpus/corpus.sqlite read --id https://arxiv.org/pdf/2409.07429v1.pdf --max-chars 12000
python services/local_literature/cli.py --corpus inputs/corpus/corpus.sqlite read --id 89614 --require-full-text
python services/local_literature/server.py --corpus inputs/corpus/corpus.sqlite --port 8766 --audit-log state/literature_http.jsonl
```

The server binds only `127.0.0.1`. Supported routes are `GET /health`, `GET /stats`, `GET /search?q=...&limit=10&mode=any`, `GET /read?id=...&max_chars=12000`, and `GET /v1/papers/{id}`. The `/v1/search` and `/v1/read` aliases share the same behavior. The server has no compressed-content mode and no network client.

CLI parameters `--corpus`, `--audit-log` and `--insights` go before the `search` or `read` command. Search supports `--limit`, `--offset`, `--mode any|all`, `--date-before`, and `--scope`. Read supports `--offset-chars`, `--max-chars`, and `--require-full-text`. Without a character limit, read returns the entire stored text. The API explicitly labels pagination and provides the complete-content and returned-text hashes. Search snippets are at most 1,200 characters of the original abstract, with truncation declared.

## Response contract

Successful responses contain `ok: true`, `corpus_id`, `offline: true`, `network_fallback: false` and `data`. Search `data` is an ordered array of paper records; read `data` is a paper record with `text`, `content_sha256`, `returned_text_sha256`, `provenance` and `metadata_provenance`. Every record includes stable `paper_id`, title, source date with its actual precision, optional source URL, `read_depth`, `full_text_available` and `missing_full_text`. Original numeric IDs are retained as strings. `local_read_id` is always available; a missing external URL is not invented.

Unknown identifiers and unavailable full text return structured errors with `ok: false` and never trigger network or synthetic evidence. CLI errors exit 2. An identifier matching multiple original rows returns `ambiguous_identifier` with exact IDs. Identifiers accept original paper IDs, `paper:ID`, existing mapped work IDs, arXiv IDs/versioned abs/pdf/html URLs, and recorded DOI/source-URL aliases. Unrecorded external pages remain unavailable.

HTTP errors return 400 for invalid requests/unavailable required text and 404 for missing papers/endpoints. Compressed `entries`, candidate endpoints, `view=insights`, and legacy `/papers/batch` are unavailable. This is a raw evidence API, **not** an emulation of the old compressed LitGraph schema. The scoring collector must explicitly adapt to `/search` and `/read`.

## Scopes and representations

- `all_local_metadata` is the default main-experiment scope: all original metadata in this frozen `library_snapshot/data/allpapers/papers.jsonl`, plus successfully bound local text. Most records are abstract-only, and 20 are metadata-only.
- `same_source_fulltext` is a separate strict subset: 1,877 papers with both a usable local text extraction and an existing compressed source card bound to the identical original paper ID. It is not substituted for the 38-domain main corpus.
- The 255,435 compressed cards live only in `inputs/insightpro_private/insights.sqlite`. They are absent from the raw database. An explicitly permitted InsightPro CLI profile may pass `--insights inputs/insightpro_private/insights.sqlite` and `--view insights`. Baseline namespaces must never mount that directory, the old combined build draft, or the original source-card databases.
- Raw and compressed search views have exactly the same raw BM25 paper ranking. Compression changes the returned representation, not the retrieved paper identities. Paper-ID alignment does not establish that every compressed claim is supported by the available extraction. Abstract-only rows are not full-text-equivalent compression controls. No old InsightPro result is declared directly comparable to the new phase.

Ranking uses SQLite FTS5 BM25 over original title, abstract and available full text, weights 5/2/1, ordered by score then original paper ID. All agents use this same implementation. `any` means literal OR and `all` literal AND. Search terms are quoted so operator-like user text cannot become SQL/FTS syntax. Publication years remain year-precision; a date cutoff includes only years definitely preceding the cutoff year, excluding ambiguous same-year records.

## Provenance and exclusions

`inputs/corpus/manifest.json` records source-file paths, SHA256, sizes, mtimes, freeze time, raw/insight database hashes and caveats. Each raw row retains its original file/line/hash and explicitly excludes `problem_definition` and `intuition`; neither those nor source-card claims enter the raw search index. All 283,008 stored paper IDs, abstracts and arXiv identifiers were compared against original rows without modification. Acquired-at timestamps not present in source metadata remain null rather than being inferred from filesystem mtimes.

The snapshot has 3,668 candidate text files. The frozen raw corpus includes 1,948; it excludes 1,324 with NUL corruption, 391 without an exact raw-paper identity, 2 ambiguous identities and 3 duplicate texts. These exclusions are in `text_manifest.json` and `excluded_records.json`. Included extractions are byte-identical and contain no NUL; completeness of every original PDF was not manually validated. A source-library text is not claimed to be the original binary PDF.

Coverage labels come from the existing frozen InsightPro `domain_papers` index. They are historical taxonomy labels, not original author labels and not new model inference. The benchmark's composite efficiency domain uses its four already-frozen source subdomains, with paper-ID deduplication. Labels serve only coverage auditing and do not constrain or alter raw search. See `reports/local_corpus_coverage.md` for all 38 domains and explicit missing-full-text counts.

## Validation and mounting

`state/local_corpus_acceptance.json` records 12 real-data checks: all raw-row identities and abstracts; all included text hashes; unchanged database hashes; deterministic retrieval; honest missing texts; private-card denial; and raw/InsightPro rank parity. `state/local_literature_http_acceptance.json` records actual loopback service tests with outbound socket connection blocked. Both used zero model calls and zero public-network requests.

A raw baseline needs only `corpus.sqlite` and the service files (`cli.py`; add `server.py` for HTTP), with optional public manifest/coverage/protocol files. Mount individual files read-only; do not mount the entire phase inputs tree or source snapshot. Namespace-level network denial remains the execution wrapper's responsibility, including native Bash; the service itself has no outbound functionality.
