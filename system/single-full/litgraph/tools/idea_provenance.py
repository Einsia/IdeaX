"""Validate the paper identity and explicit prior-work comparisons of an idea.

This checks provenance and required analysis, not the truth of a novelty claim.
"""
import re
import unicodedata
import json
import sqlite3
from pathlib import Path
from contextlib import contextmanager
from functools import lru_cache
from urllib.parse import urlsplit


def title_key(value):
    return ' '.join(unicodedata.normalize('NFKC', str(value)).casefold().split())


def titles_match(left, right):
    """PDF small-caps extraction can insert spaces inside otherwise identical words."""
    a, b = title_key(left), title_key(right)
    return bool(a and b) and (a == b or ''.join(a.split()) == ''.join(b.split()))


def text_field(item, key):
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'previous_work / novelty_check requires nonempty {key}')


ENTRY_ROLES = {
    'target_problem', 'mechanism', 'mechanism_boundary', 'boundary',
    'counter_evidence', 'alternative', 'experiment_design', 'novelty_audit',
}


def validate_entry_usage(card, lookup):
    """Validate the semantic link from a card to LitGraph entries.

    A successful HTTP request is not evidence that a model used an entry.  New
    API runs therefore record the IDs separately by kind and explain the role
    each entry played.  ``lookup`` is deliberately injected so this works with
    both the live read-only API and a cutoff snapshot.
    """
    source = card.get('source_entry_ids')
    if not isinstance(source, dict):
        raise ValueError('source_entry_ids must contain problems and insights arrays')
    all_ids = {}
    for kind in ('problem', 'insight'):
        values = source.get(kind + 's')
        if not isinstance(values, list) or not values:
            raise ValueError(f'source_entry_ids.{kind}s must be a nonempty list')
        if any(not isinstance(value, str) or not value.strip() for value in values):
            raise ValueError(f'source_entry_ids.{kind}s contains an empty/non-string ID')
        if len(set(values)) != len(values):
            raise ValueError(f'source_entry_ids.{kind}s contains duplicate IDs')
        for identifier in values:
            if identifier in all_ids:
                raise ValueError(f'entry ID listed as both kinds: {identifier}')
            try:
                record = lookup(identifier)
            except Exception as exc:
                raise ValueError(f'could not read LitGraph entry {identifier}: {exc}') from exc
            if not isinstance(record, dict) or record.get('id') != identifier:
                raise ValueError(f'unknown LitGraph entry: {identifier}')
            if record.get('kind') != kind:
                raise ValueError(f'entry {identifier} is {record.get("kind")!r}, expected {kind!r}')
            all_ids[identifier] = kind

    usage = card.get('entry_usage')
    if not isinstance(usage, list) or not usage:
        raise ValueError('entry_usage must explain how cited problem/insight entries affected the card')
    seen = set()
    for item in usage:
        if not isinstance(item, dict):
            raise ValueError('each entry_usage item must be an object')
        identifier = item.get('id')
        if identifier not in all_ids:
            raise ValueError(f'entry_usage refers to an uncited/unknown entry: {identifier}')
        if item.get('kind') != all_ids[identifier]:
            raise ValueError(f'entry_usage kind mismatch for {identifier}')
        if item.get('role') not in ENTRY_ROLES:
            raise ValueError(f'entry_usage role for {identifier} must be one of {sorted(ENTRY_ROLES)}')
        use = item.get('use')
        if not isinstance(use, str) or len(use.strip()) < 12:
            raise ValueError(f'entry_usage.use for {identifier} must describe a concrete influence')
        if identifier in seen:
            raise ValueError(f'duplicate entry_usage item: {identifier}')
        seen.add(identifier)
    missing = sorted(set(all_ids) - seen)
    if missing:
        raise ValueError('source entries without an entry_usage explanation: ' + ', '.join(missing))

    queries = card.get('litgraph_queries')
    if not isinstance(queries, list) or not queries:
        raise ValueError('litgraph_queries must record the purpose and result of API searches')
    for query in queries:
        if not isinstance(query, dict):
            raise ValueError('each litgraph_queries item must be an object')
        endpoint = query.get('endpoint')
        if not isinstance(endpoint, str) or not endpoint.startswith('/api/v1/'):
            raise ValueError('litgraph_queries.endpoint must be a /api/v1/ path')
        for field in ('purpose', 'read_depth'):
            if not isinstance(query.get(field), str) or not query[field].strip():
                raise ValueError(f'litgraph_queries.{field} is required')
        if not isinstance(query.get('result_ids'), list):
            raise ValueError('litgraph_queries.result_ids must be an array')
    return card


def validate_previous_work(card, lookup):
    works = card.get('previous_work')
    if not isinstance(works, list) or not works:
        raise ValueError('previous_work must list real numeric litgraph paper IDs and comparisons')
    seen = set()
    for work in works:
        if not isinstance(work, dict):
            raise ValueError('Each previous_work item must be an object')
        pid = work.get('paper_id')
        if isinstance(pid, bool) or not re.fullmatch(r'[0-9]{1,20}', str(pid)):
            raise ValueError('previous_work.paper_id must be a numeric API paper ID; W IDs are not accepted')
        pid = int(pid)
        if pid in seen:
            raise ValueError(f'Duplicate previous_work paper_id: {pid}')
        seen.add(pid)
        for key in ('title', 'role', 'overlap', 'difference', 'source_location'):
            text_field(work, key)
        if work.get('read_depth') not in ('fulltext', 'abstract', 'source_card', 'metadata'):
            raise ValueError('read_depth must record fulltext, abstract, source_card or metadata')
        path = f'/api/v1/papers/{pid}'
        if work.get('api_path') and work['api_path'] != path:
            raise ValueError(f'paper_id {pid} has a mismatched api_path')
        paper = lookup(pid)
        if not paper:
            raise ValueError(f'Unknown litgraph paper_id: {pid}')
        if not titles_match(paper.get('title', ''), work['title']):
            raise ValueError(f'paper_id {pid} title differs from the library; resolve identity before citing')
        # Keep a portable path: temporary tunnel hostnames must not become paper IDs.
        work['paper_id'], work['api_path'] = pid, path
    external = card.get('external_previous_work', [])
    if not isinstance(external, list):
        raise ValueError('external_previous_work must be a list')
    for work in external:
        if not isinstance(work, dict) or work.get('paper_id') is not None:
            raise ValueError('An unmapped external work cannot claim a litgraph paper_id')
        for key in ('title', 'url', 'lookup_attempt', 'overlap', 'difference'):
            text_field(work, key)
        if urlsplit(work['url']).scheme not in ('http', 'https'):
            raise ValueError('External work needs a public paper URL')
    check = card.get('novelty_check')
    if not isinstance(check, dict):
        raise ValueError('novelty_check is required before submitting an idea')
    for key in ('reduction_test', 'remaining_contribution'):
        text_field(check, key)
    queries = check.get('search_queries')
    if not isinstance(queries, list) or not queries or any(not isinstance(q, str) or not q.strip() for q in queries):
        raise ValueError('novelty_check.search_queries must record actual nonempty queries')
    risks = check.get('unresolved_risks')
    if not isinstance(risks, list) or any(not isinstance(r, str) or not r.strip() for r in risks):
        raise ValueError('novelty_check.unresolved_risks must be an explicit list')
    return card


@contextmanager
def run_sources(work):
    """Use the saved run configuration; never substitute the host's current API."""
    work = Path(work)
    config_path = work / 'library_api.json'
    if config_path.exists():
        from library_client import LibraryClient
        config = json.loads(config_path.read_text())
        client = LibraryClient(config['base_url'], log_path=work / config.get('request_log', 'ideas/api_requests.jsonl'))
        yield lru_cache(maxsize=None)(client.paper), lru_cache(maxsize=None)(client.entry)
    else:
        con = sqlite3.connect((work / 'library.db').resolve().as_uri() + '?mode=ro', uri=True)
        try:
            def paper(pid):
                row = con.execute('select data from papers where id=?', (str(pid),)).fetchone()
                return json.loads(row[0]) if row else None

            def entry(identifier):
                row = con.execute('select id,kind from entries where id=?', (identifier,)).fetchone()
                return dict(zip(('id', 'kind'), row)) if row else None

            yield lru_cache(maxsize=None)(paper), lru_cache(maxsize=None)(entry)
        finally:
            con.close()


def validate_run_cards(ideas, author=None):
    """Check persisted active cards, including JSON written without cards.py."""
    ideas = Path(ideas)
    if not (ideas / 'REQUIRE_PREVIOUS_WORK').exists() and not (ideas / 'REQUIRE_ENTRY_USAGE').exists():
        return []  # Historical runs retain their original contract.
    errors = []
    assignments_path = ideas / 'REQUIRE_SOURCES'
    assignments = json.loads(assignments_path.read_text()).get('assignments', {}) if assignments_path.exists() else None
    require_entry_usage = (ideas / 'REQUIRE_ENTRY_USAGE').exists()
    if require_entry_usage:
        try:
            config = json.loads((ideas.parent / 'library_api.json').read_text())
            log_path = ideas.parent / config.get('request_log', 'ideas/api_requests.jsonl')
            records = [json.loads(line) for line in log_path.read_text().splitlines()]
            if not any(r.get('status') == 200 and ('/api/v1/search' in r.get('url', '')
                                                   or '/api/v1/domains' in r.get('url', ''))
                       for r in records):
                return ['LitGraph API requires a successful domain/search exploration']
        except (OSError, ValueError, TypeError, KeyError) as exc:
            return [f'Cannot validate LitGraph API request log: {exc}']
    try:
        with run_sources(ideas.parent) as (paper, entry):
            for path in sorted((ideas / 'pool').glob('c-*.json')):
                try:
                    card = json.loads(path.read_text())
                    if card.get('status') != 'active' or (author and card.get('author') != author):
                        continue
                    if (ideas / 'REQUIRE_PREVIOUS_WORK').exists():
                        validate_previous_work(card, paper)
                    if require_entry_usage:
                        validate_entry_usage(card, entry)
                    if assignments is not None:
                        if not assignments.get(card.get('author')) or assignments[card['author']] != card.get('template'):
                            raise ValueError('author/rule assignment mismatch')
                        for kind in ('problem', 'insight'):
                            evidence = [e for e in card.get('evidence', []) if isinstance(e, dict) and e.get('kind') == kind]
                            if not evidence:
                                raise ValueError(f'missing {kind} evidence')
                            for e in evidence:
                                source = entry(e.get('ref', ''))
                                if not source or source.get('id') != e.get('ref') or source.get('kind') != kind:
                                    raise ValueError(f'invalid {kind} source: {e.get("ref")}')
                                for key in ('what', 'target_relevance') if kind == 'problem' else ('what',):
                                    text_field(e, key)
                except (ValueError, RuntimeError, TypeError, AttributeError) as exc:
                    errors.append(f'{path.stem}: {exc}')
    except (OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
        errors.append(f'Cannot validate library references: {exc}')
    return errors


def export_top5(path):
    """Deterministic human-readable output; no model may drop the source IDs."""
    root = Path(path)
    ideas = root / 'work/ideas'
    from idea_selection import contract_for, check_selection, input_errors
    meta = json.loads((root / 'run.json').read_text()) if (root / 'run.json').exists() else {}
    state_path = ideas / 'idea_run_state.json'
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    if contract_for(meta, state):
        errors = input_errors(root)
        if errors:
            raise ValueError('; '.join(errors))
        candidates = json.loads((root / 'selection_inputs/manifest.json').read_text())['candidates']
        why = check_selection(ideas / 'top5.json', candidates)
        if why:
            raise ValueError(why)
    errors = validate_run_cards(ideas)
    if errors:
        raise ValueError('\n'.join(errors))
    config = root / 'work/library_api.json'
    base = json.loads(config.read_text())['base_url'] if config.exists() else ''
    top = json.loads((ideas / 'top5.json').read_text())['top5']
    lines = ['# IdeaX Top-5', '', '候选想法尚需实验验证；检索未命中不能证明新颖性。', '']
    for item in top:
        card = json.loads((ideas / 'pool' / (item['card'] + '.json')).read_text())
        if card.get('status') != 'active':
            raise ValueError(f"Top-5 card is not active: {item['card']}")
        lines += [f"## {item['rank']}. {card['id']} — {card.get('thesis') or card.get('claim', '')}", '',
                  str(card.get('insight', '')), '', str(card.get('direction', '')), '']
        for key in ('novelty', 'claim'):
            if card.get(key):
                lines += [f"原卡 {key}：{card[key]}", '']
        # Historical commentary remains labelled as review, never proposal content.
        if item.get('why'):
            lines += [f"历史选择者评语（入选理由）：{item['why']}", '']
        if item.get('weakness'):
            lines += [f"历史选择者评语（弱点）：{item['weakness']}", '']
        lines += ['### Previous work', '']
        for work in card.get('previous_work', []):
            api_path = f"/api/v1/papers/{work['paper_id']}"
            ref = f"《{work['paper_id']}》 {work['title']}"
            lines += [f"- [{ref}]({base}{api_path})" if base else f'- {ref} — `{api_path}`',
                      f"  阅读：{work['read_depth']}；位置：{work['source_location']}。",
                      f"  重合：{work['overlap']}。区别：{work['difference']}。"]
        for work in card.get('external_previous_work', []):
            lines += [f"- 未入库：[{work['title']}]({work['url']})。检索记录：{work['lookup_attempt']}。",
                      f"  重合：{work['overlap']}。区别：{work['difference']}。"]
        if not card.get('previous_work'):
            lines += ['历史卡片未记录数字论文编号。']
        check = card.get('novelty_check', {})
        lines += ['', f"归约检查：{check.get('reduction_test', '未记录')}", '',
                  f"剩余贡献：{check.get('remaining_contribution', '未记录')}", '',
                  '未排除风险：' + ('；'.join(check.get('unresolved_risks', [])) or '未列出；不代表已证明新颖性'), '']
    destination = root / 'TOP5.md'
    destination.write_text('\n'.join(lines) + '\n')
    return destination
