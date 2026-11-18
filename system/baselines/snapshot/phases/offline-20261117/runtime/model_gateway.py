"""Model-only host bridge. Research workers have no external network interface."""
import argparse
from contextlib import nullcontext
import hashlib
import http.client
from http.server import BaseHTTPRequestHandler
import json
import os
from pathlib import Path
import socketserver
import sys
import threading
import time
import uuid
from urllib.parse import urlsplit

PHASE = Path(__file__).resolve().parents[1]
CAMPAIGN = PHASE.parents[1]
sys.path.insert(0, str(CAMPAIGN / 'adapters'))
from common import admission, credentials, event, now

MODEL = 'gpt-6-astra'
ALLOWED_POSTS = {'/v1/chat/completions', '/v1/responses', '/v1/responses/compact'}


def validate_payload(path, data):
    if path not in ALLOWED_POSTS:
        raise ValueError('Only fixed model inference endpoints are available')
    if not isinstance(data, dict) or data.get('model') != MODEL:
        raise ValueError('The frozen model must be gpt-6-astra')
    if path == '/v1/chat/completions' and data.get('reasoning_effort') != 'xhigh':
        raise ValueError('Frozen reasoning effort is xhigh')
    if path == '/v1/responses' and (data.get('reasoning') or {}).get('effort') != 'xhigh':
        raise ValueError('Frozen reasoning effort is xhigh')
    def check_tools(items):
        if not isinstance(items, list):
            raise ValueError('Invalid tools array')
        for item in items:
            if not isinstance(item, dict):
                raise ValueError('Invalid tool definition')
            kind = item.get('type')
            if kind not in {'function', 'custom', 'namespace', 'local_shell'}:
                raise ValueError('Hosted tools are disabled in the offline protocol')
            if kind == 'namespace':
                check_tools(item.get('tools', []))
    check_tools(data.get('tools', []))
    # Inference inputs may not make the provider fetch remote files or images.
    def check_remote_media(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {'file_url', 'image_url', 'video_url', 'audio_url'}:
                    address = item.get('url', '') if isinstance(item, dict) else item
                    if isinstance(address, str) and address and not address.startswith('data:'):
                        raise ValueError('Remote media retrieval is disabled in the offline protocol')
                check_remote_media(item)
        elif isinstance(value, list):
            for item in value:
                check_remote_media(item)
    check_remote_media(data.get('messages', []))
    check_remote_media(data.get('input', []))
    selection = data.get('tool_choice')
    if isinstance(selection, dict) and selection.get('type') not in {'function', 'custom', 'allowed_tools'}:
        raise ValueError('Hosted tool selection is disabled')


class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    allow_reuse_address = True


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.0'
    def log_message(self, *args):
        pass
    def reply(self, code, value):
        data = json.dumps(value).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    def do_GET(self):
        if self.path == '/v1/models':
            self.reply(200, {'object': 'list', 'data': [{'id': MODEL, 'object': 'model'}]})
        elif self.path == '/health':
            self.reply(200, {'offline_model_bridge': True, 'mock': self.server.mock,
                             'request_limit': 250, 'hosted_retrieval': False})
        else:
            self.reply(403, {'error': 'Public web access is unavailable'})
    def do_CONNECT(self):
        self.reply(403, {'error': 'Tunneling is disabled'})
    def do_POST(self):
        ident = uuid.uuid4().hex
        ledger = self.server.ledger
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if self.headers.get('Transfer-Encoding') or not 0 < length <= 64 * 1024 * 1024:
                raise ValueError('A bounded Content-Length is required')
            body = self.rfile.read(length)
            if len(body) != length:
                raise ValueError('Incomplete request body')
            data = json.loads(body)
            validate_payload(self.path, data)
        except (ValueError, TypeError) as exc:
            event(ledger, 'denied', request_id=ident, endpoint=self.path, reason=str(exc))
            self.reply(403, {'error': str(exc)})
            return
        digest = hashlib.sha256(body).hexdigest()
        fields = {'request_id': ident, 'endpoint': self.path,
                  'request_sha256': digest, 'request_bytes': len(body), 'mock': self.server.mock}
        conn = None
        sent = False
        usage = None
        completed = False
        status = None
        pending = b''
        try:
            # One lock per actual HTTP request, including every native child agent.
            with admission('offline-model-bridge:' + ident):
                event(ledger, 'attempt_start', **fields, usage=None, usage_known=False)
                if self.server.mock:
                    self.reply(200, {'id': 'offline-fixture', 'model': MODEL,
                                     'choices': [{'message': {'role': 'assistant', 'content': 'fixture'},
                                                  'finish_reason': 'stop', 'index': 0}]})
                    completed = True
                    status = 200
                    return
                base, key = credentials()
                url = urlsplit(base)
                if url.scheme != 'https' or url.path.rstrip('/') != '/v1':
                    raise RuntimeError('Unrecognized fixed provider endpoint')
                conn = http.client.HTTPSConnection(url.hostname, url.port or 443, timeout=1800)
                conn.request('POST', self.path, body=body,
                             headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json',
                                      'Accept': self.headers.get('Accept', 'application/json'),
                                      'Accept-Encoding': 'identity'})
                response = conn.getresponse()
                status = response.status
                # No redirect following. A model endpoint cannot become a web proxy.
                self.send_response(status)
                self.send_header('Content-Type', response.getheader('Content-Type', 'application/json'))
                self.send_header('Connection', 'close')
                self.send_header('X-Offline-Bridge-Request-Id', ident)
                for name in ('Retry-After', 'X-Request-Id'):
                    if response.getheader(name):
                        self.send_header(name, response.getheader(name))
                self.end_headers()
                sent = True
                streamed = 'text/event-stream' in response.getheader('Content-Type', '')
                json_chunks = []
                while True:
                    chunk = response.read1(65536)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    self.wfile.flush()
                    if streamed:
                        pending += chunk
                        while b'\n' in pending:
                            line, pending = pending.split(b'\n', 1)
                            if not line.startswith(b'data:'):
                                continue
                            raw = line[5:].strip()
                            if raw == b'[DONE]':
                                completed = True
                                continue
                            try:
                                part = json.loads(raw)
                            except ValueError:
                                continue
                            found = part.get('usage') or (part.get('response') or {}).get('usage')
                            if found:
                                usage = found
                            if part.get('type') == 'response.completed':
                                completed = True
                    else:
                        json_chunks.append(chunk)
                if not streamed:
                    try:
                        value = json.loads(b''.join(json_chunks))
                        usage = value.get('usage')
                    except ValueError:
                        pass
                    completed = status == 200
        except Exception as exc:
            # No request body, credentials or upstream exception details in shared logs.
            event(ledger, 'transport_error', **fields, error_type=type(exc).__name__)
            if not sent:
                self.reply(502, {'error': 'Model transport unavailable', 'request_id': ident})
        finally:
            if conn:
                conn.close()
            event(ledger, 'attempt_end', **fields, http_status=status,
                  completed=completed, usage=usage, usage_known=bool(usage))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--socket', required=True)
    ap.add_argument('--ledger', required=True)
    ap.add_argument('--mock', action='store_true')
    args = ap.parse_args()
    path = Path(args.socket)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise SystemExit('Socket already exists; verify old service identity before replacing it')
    with Server(str(path), Handler) as server:
        os.chmod(path, 0o600)
        server.mock = args.mock
        server.ledger = Path(args.ledger)
        try:
            server.serve_forever(poll_interval=0.5)
        finally:
            path.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
