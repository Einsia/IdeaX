#!/usr/bin/env python3
"""Deterministically map native CoI output without adding research content.

Missing explicit fields stay null. Literature evidence comes only from the
retrieval JSONL, never from generated paper names in idea_chain.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


def tag(text, name):
    if not isinstance(text, str):
        return None
    match = re.search(rf"<{re.escape(name)}>\s*(.*?)\s*</{re.escape(name)}>", text, flags=re.S | re.I)
    return match.group(1).strip() if match and match.group(1).strip() else None


def title_from_idea(idea):
    title = tag(idea, "title")
    if title:
        return title
    if not isinstance(idea, str):
        return None
    first = next((line.strip() for line in idea.splitlines() if line.strip()), "")
    match = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", first)
    if not match:
        match = re.match(r"^(?:\*\*)?(?:研究题目|研究标题|论文标题|标题|题目|Title)\s*[:：]\s*(.+?)(?:\*\*)?$", first, re.I)
    if match:
        return match.group(1).strip().strip("*").strip() or None
    return None


def validate_native(source):
    if not isinstance(source, dict):
        return False, "native result is not an object"
    for field in ("idea", "experiment"):
        value = source.get(field)
        if not isinstance(value, str) or value.strip().lower() in {"", "null", "none"}:
            return False, f"native result has no nonempty {field} text"
    return True, None


def load_trace(path):
    """Ignore malformed/torn lines, while reporting their line numbers."""
    if not path.is_file():
        return [], ["retrieval_trace.jsonl 未找到；无法补认阅读来源。"]
    rows, warnings = [], []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return [], ["retrieval_trace.jsonl 无法读取；无法补认阅读来源。"]
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError("not an object")
        except (ValueError, TypeError):
            warnings.append(f"轨迹第 {number} 行无效，未将其作为来源证据。")
            continue
        rows.append({**row, "trace_line": number})
    return rows, warnings


def _path_key(value):
    return str(Path(value).resolve()) if isinstance(value, str) and value else None


def _source_key(url, path=None, title=None):
    if url:
        match = re.search(r"(?:arxiv\.org/(?:abs|pdf)/)(\d{4}\.\d{4,5})(?:v\d+)?", url, re.I)
        if match:
            return "arxiv:" + match.group(1)
        return "url:" + url.rstrip("/")
    return "path:" + path if path else "title:" + str(title)


def sources_from_trace(rows):
    """Preserve trace evidence; downloads alone never imply paper reading."""
    download_urls = {}
    for row in rows:
        if row.get("event") == "paper_download" and row.get("ok") is True and row.get("url"):
            for field in ("local_path", "cached_path"):
                path = _path_key(row.get(field))
                if path:
                    download_urls[path] = row["url"]
    sources = {}

    def add(row, title=None, url=None, path=None, scope=None, state="metadata", query=None):
        if not (title or url or path):
            return
        key = _source_key(url, path, title)
        entry = sources.setdefault(key, {"source_id": key, "title": title, "url": url,
            "reading_status": "metadata_only", "reading_scopes": [], "queries": [],
            "events": [], "trace_lines": [], "local_paths": [], "parsers": [],
            "text_sha256": [], "characters": [], "selected_by_coi": False, "trace_records": []})
        if title and (not entry["title"] or row.get("event", "").startswith("selected_")):
            entry["title"] = title
        if url and not entry["url"]:
            entry["url"] = url
        rank = {"metadata_only": 0, "downloaded_only": 1, "full_text_parsed": 2}
        target = {"metadata": "metadata_only", "download": "downloaded_only", "read": "full_text_parsed"}[state]
        if rank[target] > rank[entry["reading_status"]]:
            entry["reading_status"] = target
        for field, value in (("reading_scopes", scope), ("queries", query),
                             ("events", row.get("event")), ("trace_lines", row.get("trace_line")),
                             ("local_paths", path), ("parsers", row.get("parser")),
                             ("text_sha256", row.get("text_sha256")), ("characters", row.get("characters"))):
            if value is not None and value != "" and value not in entry[field]:
                entry[field].append(value)
        if row.get("event", "").startswith("selected_"):
            entry["selected_by_coi"] = True
        evidence = {"file": row.get("trace_file"), "line": row.get("trace_line"), "event": row.get("event")}
        if evidence not in entry["trace_records"]:
            entry["trace_records"].append(evidence)

    for row in rows:
        event = row.get("event")
        if event == "search_results":
            for item in row.get("results", []):
                if isinstance(item, dict):
                    add(row, title=item.get("title"), url=item.get("url"),
                        scope=row.get("reading_scope") or "检索结果元数据；未据此认定阅读全文", query=row.get("query"))
        elif event == "citation_graph":
            add(row, title=row.get("matched_title"), url=row.get("matched_id"),
                scope=row.get("reading_scope") or "引文索引元数据", query=row.get("query_title"))
        elif event == "paper_download" and row.get("ok") is True:
            add(row, url=row.get("url"), path=_path_key(row.get("local_path")),
                scope="PDF 下载记录；单独下载不构成阅读证据", state="download")
        elif event == "paper_read" and row.get("ok") is not False:
            path = _path_key(row.get("path"))
            url = row.get("source_url") or download_urls.get(path)
            add(row, title=row.get("title"), url=url, path=path,
                scope=row.get("reading_scope") or "解析器返回论文文本；轨迹未进一步说明阅读范围", state="read")
        elif event in {"selected_search_paper", "selected_graph_paper"}:
            # Selection is not independently proof that all source content was read.
            add(row, title=row.get("title"), url=row.get("source_url"),
                scope="CoI 选中论文；是否有全文解析证据另见 reading_status")
    return list(sources.values())


def normalize_result(source, result_path, rows=None):
    valid, reason = validate_native(source)
    if not valid:
        raise ValueError(reason)
    idea = source["idea"]
    return {
        "title": title_from_idea(idea),
        "problem": tag(idea, "motivation") or tag(idea, "problem"),
        "gap": tag(idea, "gap"),
        "core_idea": tag(idea, "novelty") or idea,
        "method": tag(idea, "method"),
        "mechanism": tag(idea, "mechanism"),
        "parent_sources": None,
        "predictions": tag(idea, "predictions"),
        "experiment_plan": source["experiment"],
        "limitations": tag(idea, "limitations"),
        "citations": sources_from_trace(rows or []),
        "self_checks": None,
        "native_format": "coi.result.json",
        "native_result": str(result_path),
        "native_idea_chain": source.get("idea_chain"),
        "native_trend": source.get("trend"),
        "native_future": source.get("future"),
        "normalization": "Deterministic extraction only; absent explicit fields remain null. Citations describe trace evidence and do not establish claim-level attribution.",
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("result", type=Path)
    ap.add_argument("output", type=Path)
    ap.add_argument("--trace", type=Path, help="default: retrieval_trace.jsonl beside result")
    args = ap.parse_args()
    source = json.loads(args.result.read_text(encoding="utf-8"))
    trace_path = args.trace or args.result.parent / "retrieval_trace.jsonl"
    rows, warnings = load_trace(trace_path)
    normalized = normalize_result(source, args.result.resolve(), rows)
    normalized["trace_warnings"] = warnings
    args.output.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
