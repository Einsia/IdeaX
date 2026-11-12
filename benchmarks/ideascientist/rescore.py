"""Frozen IdeaScientist scoring prompts and validators (portable adapter)."""
import argparse

from collections import Counter, defaultdict

import csv

from datetime import datetime, timezone

import fcntl

import hashlib

import importlib.util

import json

import math

import os

from pathlib import Path

import re

import shutil

import statistics

import subprocess

import sys

import time

HERE = Path(__file__).resolve().parent

BENCH = HERE.parent

MODELS = {'astra': 'gpt-6-astra', 'opus': 'claude-opus-5-5'}

METRICS = ('quality', 'relevance', 'novelty_current', 'transfer')

DIMS = ('actionability', 'specificity', 'clarity', 'impact', 'soundness')

FIELDS = (*DIMS, 'relevance', 'quality_mean', 'novelty_current', 'transfer')

VERSION = 'ideascientist-existing-output-rubrics-v1'

def now(): return datetime.now(timezone.utc).isoformat()

def read(p): return json.loads(Path(p).read_text())

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def digest(s): return hashlib.sha256(s.encode()).hexdigest()

def save(p, obj):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + f'.{os.getpid()}.tmp')
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n'); tmp.replace(p)

def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module

P = load_module('isci_frozen_prompts', HERE / 'vendor/prompts.py')

def text(value):
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)

def mechanism_block(idea_text):
    obj = json.loads(idea_text)
    keys = ('title', 'one_sentence_thesis', 'problem', 'core_problem',
            'problem_definition', 'mechanism', 'method', 'key_novelty', 'comparison_to_sota')
    result = '\n\n'.join(f'## {k}\n{text(obj[k])}' for k in keys if obj.get(k))
    if not result: raise ValueError('Missing explicit mechanism fields')
    # Preserve complete supplied mechanism; do not truncate Chinese content at 5k chars.
    return result

def reference_block(packet):
    papers = [r for r in packet['reference_materials'] if r.get('kind') == 'paper'
              and r['doc_id'].startswith('paper:') and r.get('content', {}).get('title')]
    if not papers: raise ValueError('Cannot score novelty with an empty comparison set')
    blocks = []
    for r in papers:
        c = r['content']; problem = c.get('problem') or {}; insight = c.get('insight') or {}
        problem = problem if isinstance(problem, dict) else {'statement': problem}
        insight = insight if isinstance(insight, dict) else {'statement': insight}
        # Exclude abstract, measured observations, evaluation outcomes and evidence quotes.
        obj = {'doc_id': r['doc_id'], 'title': c['title'], 'year': c.get('year'),
               'arxiv': c.get('arxiv'), 'read_depth': r['read_depth'],
               'problem_definition': {'statement': problem.get('statement'), 'scope': problem.get('scope')},
               'challenge': {'why_hard': problem.get('why_hard'), 'prior_attempts': problem.get('prior_attempts')},
               'solution': {'thesis': c.get('thesis'), 'mechanism': insight.get('mechanism'),
                            'statement': insight.get('statement'), 'technique': c.get('technique')}}
        blocks.append(text(obj))
    return '\n\n'.join(blocks), len(papers)

def requests(packet, domain):
    report = packet['idea_text']; mechanism = mechanism_block(report)
    refs, count = reference_block(packet)
    # Use the assigned domain task, never a problem inferred backwards from the answer.
    task = domain['prompt']
    challenge = 'Specific research problem is chosen by the author within this assigned domain; no narrower challenge was assigned.\n' + domain.get('scope_boundary', '')
    return {
        'quality': {'system': P.proposal_quality_system(), 'user': P.proposal_quality_user(report)},
        'relevance': {'system': P.relevance_system(), 'user': P.relevance_user(task, challenge, report)},
        'novelty_current': {'system': P.novelty_system(), 'user': P.novelty_user(report, refs), 'reference_count': count},
        'transfer': {'system': P.in_domain_transfer_system(), 'user': P.in_domain_transfer_user(mechanism), 'mechanism': mechanism},
    }

def normalized(s): return re.sub(r'\s+', ' ', s).strip().casefold()

def valid_score(value, low, high):
    if type(value) not in (int, float) or not math.isfinite(value) or value != int(value) or not low <= value <= high:
        raise ValueError(f'Expected integer score in [{low},{high}], got {value!r}')
    return int(value)

def validate(metric, raw, request):
    if not isinstance(raw, dict): raise ValueError('Expected JSON object')
    if metric == 'transfer':
        score = valid_score(raw.get('score'), 0, 1)
        if not isinstance(raw.get('reasoning'), str) or not raw['reasoning'].strip(): raise ValueError('Missing transfer reason')
        quote = raw.get('evidence_quote') or ''
        grounded = isinstance(quote, str) and len(quote.split()) <= 35 and len(normalized(quote)) >= 4 and normalized(quote) in normalized(request['mechanism'])
        fields = all(isinstance(raw.get(k), str) and raw[k].strip() for k in
                     ('source_setting', 'target_setting', 'transferred_mechanism', 'shared_structure', 'adaptation'))
        return {'score': int(score == 1 and grounded and fields), 'judge_score': score,
                'quote_grounded': bool(grounded), 'structural_fields_present': bool(fields), 'raw': raw}
    keys = DIMS if metric == 'quality' else ('relevance',) if metric == 'relevance' else ('novelty',)
    for key in keys:
        entry = raw.get(key)
        if not isinstance(entry, dict): raise ValueError('Missing metric ' + key)
        valid_score(entry.get('score'), 1, 10)
        if not isinstance(entry.get('reasoning'), str) or not entry['reasoning'].strip(): raise ValueError('Missing reason ' + key)
    return raw
