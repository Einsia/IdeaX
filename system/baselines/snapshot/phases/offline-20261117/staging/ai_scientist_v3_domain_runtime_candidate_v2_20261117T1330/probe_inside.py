"""Offline first-stage runtime and recording fixture transport, used only in bwrap."""
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import datetime
import fcntl
import hashlib
import http.client
import json
import os
import socket
import subprocess
import sys
import threading
import uuid
from transport_policy import validate

D = Path(__file__).resolve().parent
RUN = Path(os.environ['SAKANA_RUN'])
MODE = os.environ['SAKANA_TRANSPORT_MODE']
EVENTS = RUN / 'transport'
EVENTS.mkdir(exist_ok=False)
counter = 0
guard = threading.Lock()
sessions = {}
root_session = None


def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()


def journal(event, identity, **fields):
    row = {'at': now(), 'event': event, **identity, 'bridge_request_id': None,
        'provider_status': None, 'provider_http_status': None, 'provider_response_id': None,
        'usage': None, 'usage_known': False, 'usd': None, **fields}
    with (EVENTS / 'events.jsonl').open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX); stream.write(json.dumps(row, ensure_ascii=False) + '\n'); stream.flush()


class UnixHTTPConnection(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect('/model.sock')


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    def log_message(self, *args): pass
    def do_GET(self):
        self.send_response(404); self.send_header('Content-Length', '0'); self.end_headers()
    def do_POST(self):
        global counter, root_session
        body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
        with guard: counter += 1; serial = counter
        entry = EVENTS / f'{serial:04}'
        entry.mkdir()
        (entry / 'request.body').write_bytes(body)
        request = json.loads(body)
        processes = []
        for process in Path('/proc').iterdir():
            if not process.name.isdigit(): continue
            try:
                argv = (process / 'cmdline').read_bytes().decode().strip('\0').split('\0')
                if any('codex' in x or 'headless' in x or 'file_tools.py' in x for x in argv):
                    processes.append({'pid': int(process.name), 'argv': argv,
                        'netns': os.readlink(process / 'ns/net'), 'status': (process / 'status').read_text()})
            except OSError: pass
        (entry / 'process_snapshot.json').write_text(json.dumps(processes, indent=2) + '\n')
        session_key = request.get('client_metadata', {}).get('thread_id', request.get('prompt_cache_key', 'missing'))
        with guard:
            if root_session is None: root_session = session_key
            sessions[session_key] = sessions.get(session_key, 0) + 1
            step = sessions[session_key]
        (entry / 'request.json').write_text(json.dumps(request, ensure_ascii=False, indent=2) + '\n')
        begin = {'at': now(), 'endpoint': self.path, 'mode': MODE, 'wire_sha256': hashlib.sha256(body).hexdigest()}
        (entry / 'started.json').write_text(json.dumps(begin, indent=2) + '\n')
        ident = {'method_id': 'ai_scientist_v3_native_ideation', 'run_id': os.environ['SAKANA_RUN_ID'],
            'admission_id': os.environ['SAKANA_ADMISSION_ID'], 'stage': 'recording_preflight' if MODE == 'recording' else 'controlled_native_idea',
            'fixture': MODE == 'recording', 'model': 'gpt-6-astra', 'reasoning_effort': 'xhigh',
            'logical_request_id': 'payload_group:' + begin['wire_sha256'], 'logical_identity_kind': 'payload_group',
            'physical_attempt_id': f'{serial:04}-' + uuid.uuid4().hex, 'request_wire_sha256': begin['wire_sha256'],
            'native_thread_id': session_key, 'native_client_metadata': request.get('client_metadata', {}), 'endpoint': self.path}
        journal('attempt_start', ident)
        try: validate(self.path, request)
        except ValueError as error:
            journal('attempt_error', ident, provider_status='blocked_by_local_policy', error_type=type(error).__name__)
            self.send_response(403); self.send_header('Content-Length', '0'); self.end_headers(); return
        if MODE == 'recording':
            rid = 'resp_fixture_' + uuid.uuid4().hex
            output = [{'id': 'msg_fixture_' + str(serial), 'type': 'message', 'status': 'completed',
                       'role': 'assistant', 'content': [{'type': 'output_text', 'text': 'Offline transport fixture completed. No scientific result.', 'annotations': []}]}]
            if session_key == root_session and step == 1:
                output = [{'id': 'fc_fixture_spawn', 'type': 'function_call', 'status': 'completed',
                    'call_id': 'fixture_spawn', 'name': 'spawn_agent', 'namespace': 'collaboration',
                    'arguments': json.dumps({'task_name': 'offline_guard_probe', 'message': 'Synthetic guard probe only. Do not call any tool; return fixture acknowledgement.'})}]
            elif session_key == root_session and step == 2:
                patch = '*** Begin Patch\n*** Update File: ../task/task.md\n@@\n-# Goal\n+# FIXTURE MUTATION MUST BE REJECTED\n*** End Patch'
                read_script = 'try { text(await tools.apply_patch('+json.dumps(patch)+')); } catch (e) { text("EXPECTED_READONLY_REJECTION: " + e.message); } text(ALL_TOOLS.map(x => x.name)); text(await tools.mcp__native_files__read_file({path:".codex/skills/create-idea/SKILL.md"})); text(await tools.mcp__native_files__read_file({path:".codex/skills/memory-log/SKILL.md"})); text(await tools.mcp__native_files__read_file({path:"../task/task.md"}));'
                output = [{'id': 'ct_fixture_1', 'type': 'custom_tool_call', 'status': 'completed',
                    'call_id': 'fixture_discover', 'name': 'exec', 'namespace': 'functions',
                    'input': read_script}]
            elif session_key == root_session and step == 3:
                rubrics = [{'id': 'fixture_metric', 'description': 'Fixture metric only; no experiment has run.', 'type': 'metric'},
                           {'id': 'fixture_implementation', 'description': 'Fixture implementation criterion only.', 'type': 'implementation'}]
                bundle = {'idea_id': 'fixture_0001', 'title': 'Offline fixture only', 'hypothesis': 'Synthetic transport and artifact check; not a research proposal.',
                          'implementation_plan': ['No experiment is executed.'], 'target_rubrics': rubrics, 'notes_for_agent': 'Do not score or compare this synthetic fixture.'}
                statements = []
                for path, value in [('idea_bundle.json', bundle), ('target_rubrics.json', rubrics)]:
                    statements.append('text(await tools.mcp__native_files__write_file('+json.dumps({'path':path,'content':json.dumps(value,ensure_ascii=False)})+'));')
                statements += ['text(await tools.mcp__native_files__read_file({path:"idea_bundle.json"}));']
                output = [{'id': 'ct_fixture_2', 'type': 'custom_tool_call', 'status': 'completed',
                    'call_id': 'fixture_write', 'name': 'exec', 'namespace': 'functions', 'input': '\n'.join(statements)}]
            response = {'id': rid, 'object': 'response', 'created_at': int(datetime.datetime.now().timestamp()),
                'status': 'completed', 'model': 'gpt-6-astra', 'output': output,
                'usage': {'input_tokens': 1, 'output_tokens': 1, 'total_tokens': 2}}
            events = [
                {'type': 'response.created', 'response': {**response, 'status': 'in_progress', 'output': []}},
                {'type': 'response.output_item.added', 'output_index': 0, 'item': output[0]},
                {'type': 'response.output_item.done', 'output_index': 0, 'item': output[0]},
                {'type': 'response.completed', 'response': response},
            ]
            raw = ''.join('event: ' + e['type'] + '\ndata: ' + json.dumps(e) + '\n\n' for e in events).encode()
            self.send_response(200); self.send_header('Content-Type', 'text/event-stream'); self.send_header('Content-Length', str(len(raw))); self.end_headers()
            self.wfile.write(raw); self.wfile.flush()
            (entry / 'response.sse').write_bytes(raw)
            (entry / 'ended.json').write_text(json.dumps({'at': now(), 'mock': True, 'paid_model_calls': 0, 'status': 200}) + '\n')
            journal('attempt_end', ident, provider_status='fixture_completed', provider_http_status=200,
                provider_response_id=rid, usage=response['usage'], usage_known=True, completed=True)
        else:
            conn = None; bridge_id = None; status = None; usage = None; response_id = None; completed = False; response_state = None
            try:
                if MODE != 'controlled_real' or not Path('/model.sock').is_socket():
                    raise ValueError('Only controller-admitted real runs may mount the fixed model socket')
                conn = UnixHTTPConnection('localhost', timeout=1800)
                conn.request('POST', self.path, body=body, headers={'Content-Type': 'application/json', 'Accept': 'text/event-stream', 'Accept-Encoding': 'identity'})
                response = conn.getresponse(); status = response.status
                bridge_id = response.getheader('X-Offline-Bridge-Request-Id')
                headers = {'Content-Type': response.getheader('Content-Type', 'application/json'), 'Connection': 'close'}
                self.send_response(status)
                for key, value in headers.items(): self.send_header(key, value)
                if bridge_id: self.send_header('X-Offline-Bridge-Request-Id', bridge_id)
                for header in ('Retry-After', 'X-Request-Id'):
                    if response.getheader(header): self.send_header(header, response.getheader(header))
                self.end_headers(); self.close_connection = True
                pending = b''; raw_json = bytearray(); streamed = 'text/event-stream' in headers['Content-Type']
                with (entry / 'response.body').open('wb') as saved:
                    while True:
                        chunk = response.read1(65536)
                        if not chunk: break
                        saved.write(chunk); saved.flush(); self.wfile.write(chunk); self.wfile.flush()
                        if not streamed: raw_json.extend(chunk); continue
                        pending += chunk
                        while b'\n' in pending:
                            line, pending = pending.split(b'\n',1)
                            if not line.startswith(b'data:'): continue
                            data = line[5:].strip()
                            if data == b'[DONE]': continue
                            try: part = json.loads(data)
                            except ValueError: continue
                            nested = part.get('response', {})
                            usage = part.get('usage') or nested.get('usage') or usage
                            response_id = nested.get('id') or part.get('id') or response_id
                            response_state = nested.get('status') or response_state
                            if part.get('type') in ('response.completed', 'response.incomplete', 'response.failed'):
                                response_state = part['type'].split('.', 1)[1]
                            completed = response_state == 'completed'
                    if not streamed:
                        try:
                            value = json.loads(raw_json); usage = value.get('usage'); response_id = value.get('id'); response_state = value.get('status'); completed = status == 200 and response_state == 'completed'
                        except ValueError: pass
                journal('attempt_end', ident, bridge_request_id=bridge_id, provider_status='completed' if completed and status == 200 else (response_state if response_state in ('failed', 'incomplete') else 'incomplete'),
                    provider_http_status=status, provider_response_id=response_id, usage=usage, usage_known=usage is not None, completed=completed)
            except Exception as error:
                journal('attempt_error', ident, bridge_request_id=bridge_id, provider_status='transport_error',
                    provider_http_status=status, provider_response_id=response_id, usage=usage, usage_known=usage is not None,
                    completed=False, error_type=type(error).__name__)
                self.close_connection = True
            finally:
                if conn: conn.close()


def main():
    route = Path('/proc/net/route').read_text()
    assert not any(line.split()[1] == '00000000' for line in route.splitlines()[1:] if line.split())
    boundary = {'at': now(), 'network_namespace': os.readlink('/proc/self/ns/net'), 'route': route,
        'netdev': Path('/proc/net/dev').read_text(), 'mountinfo': Path('/proc/self/mountinfo').read_text(),
        'mode': MODE, 'model_socket_present': Path('/model.sock').exists(), 'no_paid_model_calls_in_recording': MODE == 'recording'}
    (RUN / 'offline_boundary.json').write_text(json.dumps(boundary, indent=2) + '\n')
    server = ThreadingHTTPServer(('127.0.0.1', 8765), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    command = ['bash', str(D / 'official_source/src/scripts/idea.sh'), '--agent', 'codex',
        '--agent-model', 'gpt-6-astra', '--reasoning-effort', 'xhigh',
        '--task-dir', str(RUN / 'task_source'), '--results-dir', str(RUN / 'results'),
        '--global-memory-dir', str(RUN / 'results'), '--conclusions-dir', str(RUN / 'results'),
        '--cycle-index', '1', '--output-dir', str(RUN / 'results/idea')]
    (RUN / 'native_command.json').write_text(json.dumps(command, indent=2) + '\n')
    with (RUN / 'native_script.log').open('wb') as log:
        proc = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
    server.shutdown()
    (RUN / 'process_receipt.json').write_text(json.dumps({'at': now(), 'returncode': proc.returncode,
        'transport_requests': counter, 'mode': MODE, 'paid_model_calls': 0 if MODE == 'recording' else None,
        'native_script_unmodified': True}, indent=2) + '\n')
    return proc.returncode


if __name__ == '__main__': raise SystemExit(main())
