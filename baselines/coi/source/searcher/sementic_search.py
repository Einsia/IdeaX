"""CoI retrieval interface with explicit, traceable deployment adapters.

The upstream defaults remain Semantic Scholar + SciPDF/GROBID + embeddings.
Set COI_RETRIEVAL_BACKEND=arxiv_openalex, COI_PAPER_PARSER=pymupdf and
COI_RERANKER=lexical to run without a Semantic Scholar key, GROBID or an
embedding endpoint.  arXiv supplies discovery and original paper text;
OpenAlex supplies *actual* citation/reference edges, never guessed edges.
"""
import asyncio
from collections import Counter
from datetime import date
from difflib import SequenceMatcher
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import time
from urllib.parse import quote
import xml.etree.ElementTree as ET

import numpy as np
import requests


def get_content_between_a_b(start_tag, end_tag, text):
    return " ".join(re.findall(re.escape(start_tag) + "(.*?)" + re.escape(end_tag), text, re.S)).strip()


def extract(text, type):
    return get_content_between_a_b(f"<{type}>", f"</{type}>", text) or text or ""


async def fetch(url):
    if os.environ.get("COI_RETRIEVAL_BACKEND") == "local_cutoff":
        raise RuntimeError("Network fetch is disabled by the local_cutoff retrieval backend")
    try:
        response = await asyncio.to_thread(requests.get, url, timeout=(8, 35), headers={"User-Agent": "CoI-Agent-benchmark/1.0 (research paper retrieval)"})
        response.raise_for_status()
        if len(response.content) > 30 * 1024 * 1024:
            return None
        return response.content
    except requests.RequestException as exc:
        print(f"Paper download failed: {type(exc).__name__}: {url}", flush=True)
        return None


class Result:
    def __init__(self, title="", abstract="", article=None, citations_conut=0, year=None, source_url=None):
        self.title, self.abstract, self.article = title, abstract or "", article
        self.citations_conut, self.year, self.source_url = citations_conut or 0, year, source_url


def process_fields(fields):
    return fields if isinstance(fields, str) else ",".join(fields)


def _tokens(text):
    return re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]", (text or "").lower())


def _norm(text):
    return " ".join(_tokens(text))


def _manifest_content_hash(record):
    """Hash the stable, user-visible fields of one manifest record."""
    payload = {key: record.get(key) for key in
               ("paper_id", "date", "title", "abstract", "fulltext", "citations")}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class SementicSearcher:
    def __init__(self, save_file="papers/", ban_paper=None):
        self.save_file = str(save_file)
        Path(self.save_file).mkdir(parents=True, exist_ok=True)
        self.ban_paper = set(ban_paper or [])
        self.backend = os.environ.get("COI_RETRIEVAL_BACKEND", "semantic_scholar")
        self.parser = os.environ.get("COI_PAPER_PARSER", "scipdf")
        self.reranker = os.environ.get("COI_RERANKER", "embedding")
        default_cache = Path(self.save_file).resolve().parent / "retrieval_cache"
        self.cache = Path(os.environ.get("COI_RETRIEVAL_CACHE", str(default_cache)))
        self.cache.mkdir(parents=True, exist_ok=True)
        self.trace = Path(os.environ.get("COI_RETRIEVAL_TRACE", "retrieval_trace.jsonl"))
        self.trace.parent.mkdir(parents=True, exist_ok=True)
        self.cutoff_date = None
        self._local_records = {}
        self._local_title_index = {}
        self._local_references = {}
        self._local_citations = {}
        if self.backend == "local_cutoff":
            self.reranker = "lexical"
            self._load_local_manifest()
        self._trace("adapter_config", backend=self.backend, parser=self.parser, reranker=self.reranker,
                    caveats="Lexical ranking, PyMuPDF layout extraction and OpenAlex graph coverage differ from upstream defaults.")

    def _trace(self, event, **fields):
        row = {"time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "event": event, **fields}
        with self.trace.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    def _request(self, url, params=None, headers=None, attempts=2, cache=True):
        if self.backend == "local_cutoff":
            raise RuntimeError("Network metadata requests are disabled by the local_cutoff retrieval backend")
        params = {key: value for key, value in (params or {}).items() if value is not None}
        prepared = requests.Request("GET", url, params=params).prepare().url
        digest = hashlib.sha256(prepared.encode()).hexdigest()
        cache_file = self.cache / f"http-{digest}.json"
        if cache and cache_file.exists():
            item = json.loads(cache_file.read_text())
            self._trace("metadata_request", url=prepared, status=200, cache_hit=True)
            return item["body"], item["content_type"]
        for attempt in range(attempts):
            # arXiv asks clients to space API requests. Shared file lock also covers
            # independent batch workers that use the same cache directory.
            if "export.arxiv.org/api/" in url:
                with (self.cache / "arxiv-rate.lock").open("a+") as lock:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
                    lock.seek(0)
                    previous = float(lock.read() or "0")
                    time.sleep(max(0, previous + 3.05 - time.time()))
                    lock.seek(0)
                    lock.truncate()
                    lock.write(str(time.time()))
                    lock.flush()
            try:
                response = requests.get(url, params=params, headers=headers, timeout=(8, 35))
                self._trace("metadata_request", url=prepared, status=response.status_code, cache_hit=False)
                if response.status_code == 200:
                    item = {"body": response.text, "content_type": response.headers.get("Content-Type", "")}
                    if cache:
                        temporary = cache_file.with_suffix(f".{os.getpid()}.tmp")
                        temporary.write_text(json.dumps(item))
                        temporary.replace(cache_file)
                    return item["body"], item["content_type"]
                if response.status_code not in (429, 500, 502, 503, 504):
                    break
            except requests.RequestException as exc:
                self._trace("metadata_error", url=prepared, error=type(exc).__name__)
            if attempt + 1 < attempts:
                time.sleep(min(2 ** attempt + 1, 5))
        return None, None

    @staticmethod
    def _parse_manifest_date(value):
        text = str(value or "").strip()
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            return None
        try:
            return date.fromisoformat(text)
        except ValueError:
            return None

    def _load_local_manifest(self):
        manifest_value = os.environ.get("COI_CORPUS_MANIFEST", "").strip()
        cutoff_value = os.environ.get("COI_CUTOFF_DATE", "").strip()
        if not manifest_value:
            raise RuntimeError("COI_CORPUS_MANIFEST is required for the local_cutoff retrieval backend")
        self.cutoff_date = self._parse_manifest_date(cutoff_value)
        if self.cutoff_date is None:
            raise RuntimeError("COI_CUTOFF_DATE must be an ISO date (YYYY-MM-DD) for local_cutoff")
        manifest = Path(manifest_value).expanduser().resolve()
        if not manifest.is_file():
            raise RuntimeError(f"Local cutoff corpus does not exist: {manifest}")

        uri = "file:" + quote(str(manifest), safe="/") + "?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only = ON")
        try:
            columns = {row[1] for row in connection.execute("PRAGMA table_info(papers)")}
            required = {"paper_id", "date", "title", "abstract", "fulltext", "content_hash", "citations"}
            missing = sorted(required - columns)
            if missing:
                raise RuntimeError("Local cutoff corpus papers table is missing columns: " + ", ".join(missing))
            rows = connection.execute(
                "SELECT paper_id, date, title, abstract, fulltext, content_hash, citations FROM papers"
            )
            rejected = Counter()
            for row in rows:
                paper_id = str(row["paper_id"] or "").strip()
                paper_date = self._parse_manifest_date(row["date"])
                title = str(row["title"] or "").strip()
                if not paper_id:
                    rejected["missing_paper_id"] += 1
                    continue
                if paper_date is None:
                    rejected["missing_or_invalid_date"] += 1
                    continue
                if paper_date > self.cutoff_date:
                    rejected["after_cutoff"] += 1
                    continue
                if not title:
                    rejected["missing_title"] += 1
                    continue
                try:
                    citations = json.loads(row["citations"] or "[]")
                except (TypeError, json.JSONDecodeError) as exc:
                    raise RuntimeError(f"Invalid citations JSON for manifest paper {paper_id}") from exc
                if not isinstance(citations, list) or any(not isinstance(value, str) for value in citations):
                    raise RuntimeError(f"Manifest citations must be a JSON array of paper_id strings: {paper_id}")
                record = {"paper_id": paper_id, "date": paper_date.isoformat(), "title": title,
                          "abstract": str(row["abstract"] or ""), "fulltext": row["fulltext"],
                          "citations": citations}
                expected_hash = _manifest_content_hash(record)
                if not row["content_hash"] or row["content_hash"] != expected_hash:
                    raise RuntimeError(f"Manifest content_hash mismatch for paper {paper_id}")
                if paper_id in self._local_records:
                    raise RuntimeError(f"Duplicate paper_id in local cutoff corpus: {paper_id}")
                record["content_hash"] = expected_hash
                self._local_records[paper_id] = record
        finally:
            connection.close()

        for paper_id, record in self._local_records.items():
            normalized = _norm(record["title"])
            self._local_title_index.setdefault(normalized, []).append(paper_id)
            # Both endpoints are filtered here: the source is an accepted record,
            # and targets absent from the accepted pre-cutoff set are discarded.
            targets = tuple(dict.fromkeys(target for target in record["citations"]
                                          if target in self._local_records))
            self._local_references[paper_id] = targets
            for target in targets:
                self._local_citations.setdefault(target, []).append(paper_id)
        self._trace("local_manifest_loaded", path=str(manifest), cutoff=self.cutoff_date.isoformat(),
                    accepted=len(self._local_records), rejected=dict(rejected))

    def _local_row(self, record, edge=None):
        paper_id = record["paper_id"]
        row = {"paperId": paper_id, "title": record["title"], "abstract": record["abstract"],
               "year": int(record["date"][:4]), "publicationDate": record["date"],
               "citationCount": len(self._local_citations.get(paper_id, [])),
               "isOpenAccess": record["fulltext"] is not None, "openAccessPdf": None,
               "source_url": f"local:{paper_id}", "local_record": record}
        if edge:
            row["edge"] = edge
        return row

    @staticmethod
    def _date_in_requested_range(value, publication_date=None, year=None):
        if year is not None and str(value[:4]) != str(year):
            return False
        if not publication_date:
            return True
        requested = str(publication_date)
        if ":" in requested:
            lower, upper = requested.split(":", 1)
            return (not lower or value >= lower) and (not upper or value <= upper)
        return value.startswith(requested)

    def _local_search(self, query, limit, publication_date=None, year=None):
        query_tokens = set(_tokens(str(query or "")))
        if not query_tokens:
            return {"data": []}
        matches = []
        for record in self._local_records.values():
            if not self._date_in_requested_range(record["date"], publication_date, year):
                continue
            searchable = set(_tokens(f"{record['title']} {record['abstract']}"))
            overlap = len(query_tokens & searchable)
            if overlap:
                matches.append((overlap, record))
        matches.sort(key=lambda item: (-item[0], item[1]["paper_id"]))
        rows = [self._local_row(record) for _, record in matches]
        rows = self._lexical_rerank(str(query), rows)[:limit]
        self._trace("search_results", backend="local_cutoff", query=str(query),
                    results=[{"paper_id": row["paperId"], "title": row["title"]} for row in rows])
        return {"data": rows}

    def _local_resolve_paper(self, value):
        if value in self._local_records:
            return self._local_records[value]
        matches = self._local_title_index.get(_norm(value), [])
        if len(matches) == 1:
            return self._local_records[matches[0]]
        if len(matches) > 1:
            raise RuntimeError(f"Anchor title is ambiguous in local cutoff corpus: {value}")
        raise RuntimeError(f"Anchor paper is absent from the accepted pre-cutoff corpus: {value}")

    def _local_article(self, record):
        fulltext = record["fulltext"] or ""
        text = fulltext or record["abstract"]
        heading = "Frozen manifest full text" if fulltext else "Abstract (full text unavailable)"
        parser = "frozen_manifest_fulltext" if fulltext else "frozen_manifest_abstract"
        return {"paper_id": record["paper_id"], "title": record["title"],
                "abstract": record["abstract"], "pub_date": record["date"],
                "sections": [{"heading": heading, "text": text,
                              "publication_ref": list(self._local_references[record["paper_id"]])}],
                "references": [{"ref_id": target, "title": self._local_records[target]["title"],
                                "year": int(self._local_records[target]["date"][:4])}
                               for target in self._local_references[record["paper_id"]]],
                "source_url": f"local:{record['paper_id']}", "parser": parser,
                "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}

    def _validate_local_anchor(self, article, path):
        if self.backend != "local_cutoff":
            return article
        values = [article.get("paper_id"), article.get("title"), Path(path).stem]
        source = article.get("source_url", "")
        if source.startswith("local:"):
            values.insert(0, source[len("local:"):])
        last_error = None
        for value in filter(None, values):
            try:
                record = self._local_resolve_paper(str(value))
                article["paper_id"] = record["paper_id"]
                article["pub_date"] = record["date"]
                return article
            except RuntimeError as exc:
                last_error = exc
        raise RuntimeError(f"Anchor file {path} is not a paper in the accepted pre-cutoff corpus") from last_error

    @staticmethod
    def _arxiv_id(value):
        match = re.search(r"(?:arxiv\.org/(?:abs|pdf|html)/|arXiv:)(\d{4}\.\d{4,5}(?:v\d+)?)", value or "", re.I)
        return match.group(1) if match else None

    def _search_arxiv(self, query, limit, publicationDate=None, year=None):
        query = str(query or "").strip().strip("`\n")
        if not query:
            return {"data": []}
        if re.search(r"\b(?:all|ti|au|abs|cat|id):", query):
            search_query = query
        else:
            words = re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]*", query)
            stop = {"the", "a", "an", "of", "and", "for", "in", "on", "with", "to", "by", "from", "using"}
            words = [word for word in words if word.lower() not in stop]
            if not words:
                self._trace("search_empty", backend="arxiv", query=query, reason="No English/indexable search terms")
                return {"data": []}
            search_query = " AND ".join("all:" + word for word in words[:8])
        params = {"search_query": search_query, "start": 0, "max_results": min(limit, 30), "sortBy": "relevance", "sortOrder": "descending"}
        body, _ = self._request("https://export.arxiv.org/api/query", params)
        if body is None:
            return None
        ns = {"a": "http://www.w3.org/2005/Atom"}
        try:
            root = ET.fromstring(body)
        except ET.ParseError:
            return None
        rows = []
        for entry in root.findall("a:entry", ns):
            title = " ".join((entry.findtext("a:title", "", ns)).split())
            source_url = entry.findtext("a:id", "", ns).replace("http://", "https://")
            if "/api/errors" in source_url:
                continue
            published = entry.findtext("a:published", "", ns)
            pub_year = int(published[:4]) if published[:4].isdigit() else None
            if year and pub_year and str(pub_year) != str(year):
                continue
            if publicationDate and pub_year:
                bounds = str(publicationDate).split(":")
                if len(bounds) == 2 and bounds[1] and published[:10] > bounds[1]:
                    continue
                if len(bounds) == 2 and bounds[0] and published[:10] < bounds[0]:
                    continue
            pdf = next((link.attrib.get("href") for link in entry.findall("a:link", ns)
                        if link.attrib.get("title") == "pdf" or link.attrib.get("type") == "application/pdf"), None)
            if pdf:
                pdf = pdf.replace("http://", "https://").replace("export.arxiv.org", "arxiv.org")
            rows.append({"title": title, "paperId": source_url, "abstract": " ".join(entry.findtext("a:summary", "", ns).split()),
                         "isOpenAccess": True, "openAccessPdf": {"url": pdf} if pdf else None,
                         "year": pub_year, "publicationDate": published[:10], "citationCount": 0,
                         "source_url": source_url, "citation_count_available": False})
        self._trace("search_results", backend="arxiv", query=query, actual_query=search_query,
                    reading_scope="arXiv API title and abstract metadata", results=[{"title": row["title"], "url": row["source_url"]} for row in rows])
        return {"data": rows}

    async def search_papers_async(self, query, limit=5, offset=0, fields=None, publicationDate=None,
                                  minCitationCount=0, year=None, publicationTypes=None, fieldsOfStudy=None):
        if self.backend == "local_cutoff":
            return self._local_search(query, limit, publicationDate, year)
        if self.backend == "arxiv_openalex":
            return await asyncio.to_thread(self._search_arxiv, query, limit, publicationDate, year)
        api_key = os.environ.get("SEMENTIC_SEARCH_API_KEY")
        params = {"query": query, "limit": min(limit, 100), "offset": offset,
                  "fields": process_fields(fields or ["title", "paperId", "abstract", "isOpenAccess", "openAccessPdf", "year", "publicationDate", "citationCount"]),
                  "publicationDateOrYear": publicationDate, "minCitationCount": minCitationCount,
                  "year": year, "publicationTypes": publicationTypes, "fieldsOfStudy": fieldsOfStudy}
        body, _ = await asyncio.to_thread(self._request, "https://api.semanticscholar.org/graph/v1/paper/search", params,
                                         {"x-api-key": api_key} if api_key else None)
        return json.loads(body) if body else None

    def cal_cosine_similarity(self, vec1, vec2):
        denominator = np.linalg.norm(vec1) * np.linalg.norm(vec2)
        return float(np.dot(vec1, vec2) / denominator) if denominator else 0.0

    def cal_cosine_similarity_matric(self, matric1, matric2):
        left, right = np.atleast_2d(matric1), np.atleast_2d(matric2)
        denominator = np.outer(np.linalg.norm(left, axis=1), np.linalg.norm(right, axis=1))
        return np.divide(left @ right.T, denominator, out=np.zeros_like(denominator, dtype=float), where=denominator != 0).flatten().tolist()

    def _lexical_rerank(self, query, papers):
        # Deterministic TF-IDF cosine; deliberately named in the trace because it
        # changes the upstream embedding ranker and is not an embedding replica.
        docs = [Counter(_tokens(f"{paper.get('title', '')} {paper.get('abstract', '')}")) for paper in papers]
        query_tokens = Counter(_tokens(query))
        document_frequency = Counter(token for doc in docs for token in doc)
        idf = {token: math.log((len(docs) + 1) / (count + 1)) + 1 for token, count in document_frequency.items()}
        q = {token: count * idf.get(token, 1) for token, count in query_tokens.items()}
        qnorm = math.sqrt(sum(value * value for value in q.values()))
        def score(doc):
            vec = {token: count * idf[token] for token, count in doc.items()}
            denominator = qnorm * math.sqrt(sum(value * value for value in vec.values()))
            return sum(q.get(token, 0) * value for token, value in vec.items()) / denominator if denominator else 0
        ranked = sorted(zip(papers, docs), key=lambda pair: score(pair[1]), reverse=True)
        self._trace("rerank", method="lexical_tfidf_cosine", candidate_count=len(papers))
        return [paper for paper, _ in ranked]

    def rerank_papers(self, query_embedding, paper_list, llm):
        paper_list = [paper for paper in paper_list if paper]
        if not paper_list:
            return []
        embeddings = llm.get_embbeding([f"Title: {paper.get('title', '')}\nAbstract: {paper.get('abstract', '')}" for paper in paper_list])
        if embeddings is None or query_embedding is None:
            raise RuntimeError("Embedding reranker has no embeddings; configure an embedding endpoint or explicitly select COI_RERANKER=lexical")
        scores = self.cal_cosine_similarity_matric(query_embedding, embeddings)
        return [paper for paper, _ in sorted(zip(paper_list, scores), key=lambda pair: pair[1], reverse=True)]

    def _rank(self, papers, query, llm):
        if not query or not papers:
            return papers
        if self.backend == "local_cutoff" or self.reranker == "lexical":
            return self._lexical_rerank(query, papers)
        if llm:
            return self.rerank_papers(llm.get_embbeding(query), papers, llm)
        return papers

    @staticmethod
    def _titles(papers):
        return {_norm(paper if isinstance(paper, str) else paper.title) for paper in (papers or [])}

    @staticmethod
    def _filename(title):
        return re.sub(r"[^\w .-]", "_", title)[:150] + "-" + hashlib.sha256(title.encode()).hexdigest()[:10] + ".pdf"

    async def search_async(self, query, max_results=5, paper_list=None, rerank_query=None, llm=None, year=None,
                           publicationDate=None, need_download=True, fields=None, exact_title=None):
        print(f"Searching papers: {query}", flush=True)
        response = await self.search_papers_async(query, limit=6 * max_results, year=year,
                                                 publicationDate=publicationDate, fields=fields)
        if not response or "data" not in response:
            return []
        read = self._titles(paper_list) | {_norm(title) for title in self.ban_paper}
        candidates = [row for row in response["data"] if _norm(row.get("title", "")) not in read]
        if self.backend == "local_cutoff" and need_download:
            pass
        elif need_download:
            candidates = [row for row in candidates if row.get("openAccessPdf", {}) and row["openAccessPdf"].get("url")]
        if exact_title:
            import difflib
            def title_score(candidate):
                def normalized(value):
                    return " ".join(re.findall(r"[a-z0-9]+", str(value).lower()))
                target, actual = normalized(exact_title), normalized(candidate.get("title", ""))
                if target == actual:
                    return 1.0
                left, right = set(target.split()), set(actual.split())
                jaccard = len(left & right) / max(1, len(left | right))
                return min(difflib.SequenceMatcher(None, target, actual).ratio(), jaccard)
            matching = [row for row in candidates if title_score(row) >= 0.88]
            self._trace("reference_title_identity_check", requested_title=exact_title,
                candidates=[{"title": row.get("title"), "score": title_score(row),
                    "accepted": title_score(row) >= 0.88} for row in candidates])
            if not matching:
                precise = 'ti:"' + str(exact_title).replace('"', '') + '"'
                precise_response = await self.search_papers_async(precise, limit=12, year=year,
                    publicationDate=publicationDate, fields=fields)
                precise_rows = (precise_response or {}).get("data", [])
                matching = [row for row in precise_rows if title_score(row) >= 0.88
                    and _norm(row.get("title", "")) not in read]
                if need_download:
                    matching = [row for row in matching if row.get("openAccessPdf")
                        and row["openAccessPdf"].get("url")]
                self._trace("reference_precise_title_retry", requested_title=exact_title, query=precise,
                    candidates=[{"title": row.get("title"), "score": title_score(row)} for row in precise_rows],
                    accepted_titles=[row.get("title") for row in matching])
            candidates = matching
            if not candidates:
                self._trace("reference_title_unresolved", requested_title=exact_title,
                    reason="No sufficiently matching real paper title; no substitute is presented as this reference")
                return []
        candidates = self._rank(candidates, rerank_query, llm)
        final = []
        for row in candidates[:max(8, max_results * 2)]:
            article = None
            if self.backend == "local_cutoff" and need_download:
                article = self._local_article(row["local_record"])
                self._trace("selected_search_paper", title=row["title"], paper_id=row["paperId"],
                            date=row["publicationDate"],
                            reading_scope="Frozen manifest full text" if row["local_record"]["fulltext"]
                            else "Frozen manifest abstract (full text unavailable)")
            elif need_download:
                article = await self.read_arxiv_from_link_async(row["openAccessPdf"]["url"], self._filename(row["title"]))
                if not article:
                    continue
                article.update(title=row["title"], abstract=row.get("abstract") or article.get("abstract", ""), pub_date=row.get("year"), source_url=row.get("source_url") or row.get("url"))
                self._trace("selected_search_paper", title=row["title"], source_url=row.get("source_url") or row.get("url"),
                            year=row.get("year"), reading_scope="Original PDF full text extracted with configured parser")
            final.append(Result(row["title"], row.get("abstract", ""), article, row.get("citationCount", 0), row.get("year"), row.get("source_url") or row.get("url")))
            if len(final) >= max_results:
                break
        return final

    @staticmethod
    def _openalex_row(work):
        inverted = work.get("abstract_inverted_index") or {}
        positions = {position: word for word, indexes in inverted.items() for position in indexes}
        abstract = " ".join(positions[index] for index in sorted(positions))
        locations = [work.get("best_oa_location"), work.get("primary_location")] + (work.get("locations") or [])
        pdf, source = None, work.get("doi") or work.get("id")
        for location in filter(None, locations):
            landing = location.get("landing_page_url") or ""
            aid = SementicSearcher._arxiv_id(landing) or SementicSearcher._arxiv_id(location.get("pdf_url"))
            if aid:
                pdf, source = f"https://arxiv.org/pdf/{aid}", f"https://arxiv.org/abs/{aid}"
                break
            if not pdf and location.get("pdf_url"):
                pdf, source = location["pdf_url"], landing or source
        return {"title": work.get("title") or work.get("display_name") or "", "abstract": abstract,
                "citationCount": work.get("cited_by_count", 0), "year": work.get("publication_year"),
                "isOpenAccess": bool(pdf), "openAccessPdf": {"url": pdf} if pdf else None,
                "source_url": source, "graph_id": work.get("id")}

    def _openalex_related(self, title, need_citation, need_reference):
        body, _ = self._request("https://api.openalex.org/works", {"search": title, "per-page": 5})
        if not body:
            return []
        matches = json.loads(body).get("results", [])
        if not matches:
            return []
        work = max(matches, key=lambda row: SequenceMatcher(None, _norm(title), _norm(row.get("title", ""))).ratio())
        similarity = SequenceMatcher(None, _norm(title), _norm(work.get("title", ""))).ratio()
        if similarity < 0.84:
            self._trace("graph_match_rejected", query_title=title, matched_title=work.get("title"), similarity=similarity)
            return []
        result = []
        work_id = work["id"].rsplit("/", 1)[-1]
        if need_citation:
            body, _ = self._request("https://api.openalex.org/works", {"filter": f"cites:{work_id},is_oa:true", "per-page": 40, "sort": "cited_by_count:desc"})
            if body:
                for row in json.loads(body).get("results", []):
                    converted = self._openalex_row(row)
                    converted["edge"] = {"from": row["id"], "to": work["id"], "relation": "cites"}
                    result.append(converted)
        if need_reference:
            ids = [value.rsplit("/", 1)[-1] for value in work.get("referenced_works", [])[:40]]
            if ids:
                body, _ = self._request("https://api.openalex.org/works", {"filter": "openalex:" + "|".join(ids), "per-page": 40})
                if body:
                    for row in json.loads(body).get("results", []):
                        converted = self._openalex_row(row)
                        converted["edge"] = {"from": work["id"], "to": row["id"], "relation": "cites"}
                        result.append(converted)
        self._trace("citation_graph", provider="OpenAlex", query_title=title, matched_title=work.get("title"), matched_id=work["id"],
                    edges=[{"title": row["title"], **row["edge"]} for row in result], reading_scope="OpenAlex indexed citation/reference metadata")
        return result

    async def search_related_paper_async(self, title, need_citation=True, need_reference=True, rerank_query=None, llm=None, paper_list=None):
        if self.backend == "local_cutoff":
            anchor = self._local_resolve_paper(title)
            anchor_id = anchor["paper_id"]
            related = []
            if need_citation:
                related.extend(self._local_row(self._local_records[source],
                               {"from": source, "to": anchor_id, "relation": "cites"})
                               for source in self._local_citations.get(anchor_id, []))
            if need_reference:
                related.extend(self._local_row(self._local_records[target],
                               {"from": anchor_id, "to": target, "relation": "cites"})
                               for target in self._local_references.get(anchor_id, []))
            self._trace("citation_graph", provider="local_cutoff", paper_id=anchor_id,
                        edges=[row["edge"] for row in related])
        elif self.backend == "arxiv_openalex":
            related = await asyncio.to_thread(self._openalex_related, title, need_citation, need_reference)
        else:
            fields = ["title", "abstract", "citations.title", "citations.abstract", "citations.citationCount", "references.title", "references.abstract", "references.citationCount", "citations.isOpenAccess", "citations.openAccessPdf", "references.isOpenAccess", "references.openAccessPdf", "citations.year", "references.year"]
            response = await self.search_papers_async(title, limit=3, fields=fields)
            if not response or not response.get("data"):
                return None
            first = response["data"][0]
            related = (first.get("citations", []) if need_citation else []) + (first.get("references", []) if need_reference else [])
        banned = self._titles(paper_list) | {_norm(value) for value in self.ban_paper}
        candidates, seen = [], set()
        for row in related:
            normalized = _norm(row.get("title", ""))
            if not normalized or normalized in banned or normalized in seen:
                continue
            seen.add(normalized)
            if self.backend == "local_cutoff":
                pass
            elif not row.get("openAccessPdf") or not row["openAccessPdf"].get("url"):
                continue
            candidates.append(row)
        candidates = self._rank(candidates, rerank_query, llm) if rerank_query else sorted(candidates, key=lambda row: row.get("citationCount", 0), reverse=True)
        for row in candidates[:8]:
            if self.backend == "local_cutoff":
                article = self._local_article(row["local_record"])
            else:
                article = await self.read_arxiv_from_link_async(row["openAccessPdf"]["url"], self._filename(row["title"]))
            if article:
                pub_date = row.get("publicationDate") if self.backend == "local_cutoff" else row.get("year")
                article.update(title=row["title"], abstract=row.get("abstract") or article.get("abstract", ""),
                               pub_date=pub_date, source_url=row.get("source_url"))
                self._trace("selected_graph_paper", title=row["title"], source_url=row.get("source_url"), edge=row.get("edge"))
                return Result(row["title"], article.get("abstract", ""), article, row.get("citationCount", 0), row.get("year"), row.get("source_url"))
        return None

    async def download_pdf_async(self, pdf_link, save_path):
        if self.backend == "local_cutoff":
            raise RuntimeError("PDF download is disabled by the local_cutoff retrieval backend")
        if not pdf_link:
            return False
        save_path = Path(save_path)
        if save_path.exists():
            return True
        cached = self.cache / ("pdf-" + hashlib.sha256(pdf_link.encode()).hexdigest() + ".pdf")
        if not cached.exists():
            content = await fetch(pdf_link)
            if not content or b"%PDF-" not in content[:1024]:
                self._trace("paper_download", url=pdf_link, ok=False, reason="No PDF content returned")
                return False
            temporary = cached.with_suffix(f".{os.getpid()}.tmp")
            temporary.write_bytes(content)
            temporary.replace(cached)
        if not save_path.exists():
            save_path.symlink_to(cached.resolve())
        self._trace("paper_download", url=pdf_link, ok=True, cached_path=str(cached), local_path=str(save_path))
        return True

    async def read_arxiv_from_link_async(self, pdf_link, filename):
        path = Path(self.save_file) / Path(filename).name
        if not await self.download_pdf_async(pdf_link, path):
            return None
        article = await asyncio.to_thread(self.read_arxiv_from_path, path)
        if article:
            article["source_url"] = pdf_link
        return article

    def read_arxiv_from_path(self, pdf_path):
        path = Path(pdf_path)
        if not path.exists():
            if self.backend == "local_cutoff":
                raise RuntimeError(f"Anchor file does not exist: {path}")
            return None
        source_url = ""
        try:
            if path.suffix.lower() in (".txt", ".md"):
                # Keep *every* input character in sections. Heading heuristics must
                # never discard an entire text anchor, bibliography or appendices.
                text = path.read_text(encoding="utf-8")
                title_match = re.search(r"^Title:\s*(.+)$", text, re.M)
                source_match = re.search(r"^Source(?: URL)?:\s*(.+)$", text, re.M)
                title = title_match.group(1).strip() if title_match else path.stem
                source_url = source_match.group(1).strip() if source_match else ""
                parser = "provided_text_full_content"
            elif self.parser == "pymupdf":
                import pymupdf
                with pymupdf.open(path) as doc:
                    title = (doc.metadata or {}).get("title") or path.stem
                    text = "\n\n".join(page.get_text(sort=True) for page in doc)
                    pages = len(doc)
                parser = "pymupdf_full_document"
            else:
                import scipdf
                article = scipdf.parse_pdf_to_dict(str(path))
                self._trace("paper_read", path=str(path), parser="scipdf_grobid", title=article.get("title"), reading_scope="GROBID parsed sections")
                return self._validate_local_anchor(article, path)
            if not text.strip():
                self._trace("paper_read", path=str(path), ok=False, reason="No extractable text")
                return None
            abstract_match = re.search(r"(?:^|\n)\s*A\s*B\s*S\s*T\s*R\s*A\s*C\s*T\s*\n(.*?)(?:\n\s*(?:1\s+|I[. ]\s*)?I\s*N\s*T\s*R\s*O\s*D\s*U\s*C\s*T\s*I\s*O\s*N\b|\n\s*1\s+)", text, re.I | re.S)
            abstract = " ".join(abstract_match.group(1).split())[:12000] if abstract_match else ""
            aid = self._arxiv_id(source_url) or self._arxiv_id(text[:5000])
            date_match = re.search(r"(?:19|20)\d{2}", source_url)
            year = (2000 + int(aid[:2]) if aid and int(aid[:2]) < 91 else None) or (int(date_match.group()) if date_match else None)
            article = {"title": title, "abstract": abstract, "pub_date": year,
                       "sections": [{"heading": "Full source text (layout extraction; includes references and appendices)", "text": text, "publication_ref": []}],
                       "references": [], "source_url": source_url,
                       "parser": parser, "text_sha256": hashlib.sha256(text.encode()).hexdigest()}
            self._trace("paper_read", path=str(path.resolve()), title=title, source_url=source_url, parser=parser,
                        reading_scope="Complete supplied text" if path.suffix.lower() in (".txt", ".md") else f"All {pages} PDF pages extracted as text; images/formula/layout may be imperfect",
                        characters=len(text), text_sha256=article["text_sha256"], structured_references_available=False)
            return self._validate_local_anchor(article, path)
        except RuntimeError:
            if self.backend == "local_cutoff":
                raise
            return None
        except Exception as exc:
            self._trace("paper_read", path=str(path), ok=False, error=type(exc).__name__)
            return None

    def read_paper_title_abstract(self, article):
        return f"Title: {article.get('title', '')}\nAbstract: {article.get('abstract', '')}\n"

    def read_paper_title_abstract_introduction(self, article):
        return self.read_paper_title_abstract(article) + "Introduction: " + (article.get("sections") or [{}])[0].get("text", "")

    def read_paper_content(self, article):
        content = self.read_paper_title_abstract(article)
        for section in article.get("sections", []):
            content += f"section: {section.get('heading', '')}\n content: {section.get('text', '')}\n ref_ids: {section.get('publication_ref', [])}\n"
        return content

    def read_paper_content_with_ref(self, article):
        content = self.read_paper_content(article) + "<References>\n"
        for reference in article.get("references", []):
            content += f"Ref_id:{reference.get('ref_id')} Title: {reference.get('title')} Year: ({reference.get('year')})\n"
        return content + "</References>\n"
