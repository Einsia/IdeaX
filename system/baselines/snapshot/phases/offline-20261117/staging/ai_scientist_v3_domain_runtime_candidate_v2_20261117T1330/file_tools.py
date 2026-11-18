#!/usr/bin/env python3
"""File-only MCP transport for the native idea stage; no command/network tool."""
import json
import os
from pathlib import Path
import sys

RESULTS = Path(os.environ['SAKANA_RESULTS']).resolve()
TASK = RESULTS / 'task'
WRITE_DENIED = [TASK]


def resolve(value, write=False):
    path = Path(value)
    if not path.is_absolute(): path = Path.cwd() / path
    path = path.resolve()
    if path != RESULTS and not path.is_relative_to(RESULTS):
        raise ValueError('Only the named native results, staged task, output and memory paths are available')
    if write and any(path == p or path.is_relative_to(p) for p in WRITE_DENIED):
        raise ValueError('Original task files are read-only')
    return path


TOOLS = [
    {'name': 'read_file', 'description': 'Read a named task, output, history or memory file as exact UTF-8 text.',
     'inputSchema': {'type': 'object', 'properties': {'path': {'type': 'string'}}, 'required': ['path']}},
    {'name': 'list_directory', 'description': 'List a named task, output, history or memory directory without recursion.',
     'inputSchema': {'type': 'object', 'properties': {'path': {'type': 'string'}}, 'required': ['path']}},
    {'name': 'write_file', 'description': 'Write the required idea JSON files or native memory/conclusions. Parent directories are created. Original task inputs cannot be changed.',
     'inputSchema': {'type': 'object', 'properties': {'path': {'type': 'string'}, 'content': {'type': 'string'}}, 'required': ['path', 'content']}},
    {'name': 'append_file', 'description': 'Append exact UTF-8 text to native memory or history without changing existing entries.',
     'inputSchema': {'type': 'object', 'properties': {'path': {'type': 'string'}, 'content': {'type': 'string'}}, 'required': ['path', 'content']}},
]


def main():
    for raw in sys.stdin:
        try:
            request = json.loads(raw)
            ident = request.get('id')
            method = request.get('method')
            if ident is None: continue
            if method == 'initialize':
                result = {'protocolVersion': request.get('params', {}).get('protocolVersion', '2024-11-05'),
                    'capabilities': {'tools': {}}, 'serverInfo': {'name': 'sakana-file-only', 'version': '1'}}
            elif method == 'tools/list': result = {'tools': TOOLS}
            elif method == 'tools/call':
                params = request['params']; name = params['name']; args = params.get('arguments', {})
                path = resolve(args['path'], write=name in ('write_file', 'append_file'))
                if name == 'read_file': value = path.read_text()
                elif name == 'list_directory': value = json.dumps([{'name': p.name, 'directory': p.is_dir()} for p in sorted(path.iterdir())])
                elif name in ('write_file', 'append_file'):
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with path.open('a' if name == 'append_file' else 'w') as stream: stream.write(args['content'])
                    value = 'File written.'
                else: raise ValueError('Unsupported file operation')
                result = {'content': [{'type': 'text', 'text': value}]}
            elif method == 'ping': result = {}
            else: raise ValueError('Unsupported MCP operation')
            response = {'jsonrpc': '2.0', 'id': ident, 'result': result}
        except Exception as exc:
            response = {'jsonrpc': '2.0', 'id': request.get('id'), 'error': {'code': -32602, 'message': str(exc)}}
        sys.stdout.write(json.dumps(response) + '\n'); sys.stdout.flush()


if __name__ == '__main__': main()
