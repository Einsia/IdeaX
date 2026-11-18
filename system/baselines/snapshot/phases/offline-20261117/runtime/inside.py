"""Private loopback model relay inside the network namespace."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import select
import socket
import socketserver
import subprocess
import threading
import time
import urllib.request


def lock_namespace():
    """Prevent descendants from joining other namespaces or adding host mounts."""
    if os.uname().machine != 'x86_64':
        raise RuntimeError('Offline syscall filter requires audited x86_64 runtime')
    class Filter(ctypes.Structure):
        _fields_ = [('code', ctypes.c_ushort), ('jt', ctypes.c_ubyte),
                    ('jf', ctypes.c_ubyte), ('k', ctypes.c_uint32)]
    class Program(ctypes.Structure):
        _fields_ = [('length', ctypes.c_ushort), ('filters', ctypes.POINTER(Filter))]
    # Verify architecture, then deny namespace switching and mount mutation.
    instructions = [(0x20, 0, 0, 4), (0x15, 1, 0, 0xc000003e), (0x06, 0, 0, 0x80000000),
                    (0x20, 0, 0, 0)]
    for syscall in (272, 308, 165, 166, 155, 428, 429, 442):
        instructions += [(0x15, 0, 1, syscall), (0x06, 0, 0, 0x00050001)]
    instructions += [(0x06, 0, 0, 0x7fff0000)]
    array = (Filter * len(instructions))(*(Filter(*row) for row in instructions))
    program = Program(len(array), array)
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(38, 1, 0, 0, 0) != 0 or libc.prctl(22, 2, ctypes.byref(program), 0, 0) != 0:
        raise OSError(ctypes.get_errno(), 'Could not lock offline namespace')


class Relay(socketserver.BaseRequestHandler):
    def handle(self):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as upstream:
            upstream.connect('/model.sock')
            peers = {self.request: upstream, upstream: self.request}
            while True:
                ready, _, _ = select.select(list(peers), [], [], 60)
                for source in ready:
                    data = source.recv(65536)
                    if not data:
                        return
                    peers[source].sendall(data)


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', required=True)
    ap.add_argument('--parent-netns', required=True)
    ap.add_argument('command', nargs=argparse.REMAINDER)
    args = ap.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    network = os.readlink('/proc/self/ns/net')
    routes = Path('/proc/net/route').read_text()
    if network == args.parent_netns or any(line.split()[1] == '00000000' for line in routes.splitlines()[1:] if line.split()):
        raise SystemExit('Offline namespace validation failed')
    output = Path(args.output)
    (output / 'offline_boundary.json').write_text(json.dumps({
        'network_namespace': network, 'parent_network_namespace': args.parent_netns,
        'no_default_route': True, 'model_endpoint': 'http://127.0.0.1:8765/v1',
        'pid': os.getpid(), 'public_network': False, 'command': command,
    }, indent=2) + '\n')
    Path('/tmp/home').mkdir(exist_ok=True)
    lock_namespace()
    phase = Path(os.environ['INSIGHTPRO_OFFLINE_PHASE'])
    corpus = phase/'inputs/corpus/corpus.sqlite'
    corpus_service = None
    if corpus.is_file():
        corpus_log = (output/'local_literature_service.log').open('ab')
        corpus_service = subprocess.Popen(['/usr/bin/python3', str(phase/'services/local_literature/server.py'),
            '--corpus', str(corpus), '--port', '8766', '--audit-log', str(output/'local_literature_requests.jsonl')],
            stdout=corpus_log, stderr=corpus_log)
        try:
            for _ in range(100):
                if corpus_service.poll() is not None:
                    raise RuntimeError('Local frozen corpus service exited before readiness')
                try:
                    with urllib.request.urlopen('http://127.0.0.1:8766/health', timeout=1) as response:
                        if json.load(response).get('offline'):
                            break
                except OSError:
                    time.sleep(0.05)
            else:
                raise RuntimeError('Local frozen corpus service failed readiness check')
        except BaseException:
            corpus_service.terminate()
            corpus_service.wait(timeout=5)
            raise
    with Server(('127.0.0.1', 8765), Relay) as server:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            status = subprocess.run(command, cwd=output).returncode
        finally:
            server.shutdown()
            if corpus_service is not None:
                corpus_service.terminate()
                corpus_service.wait(timeout=5)
    raise SystemExit(status)


if __name__ == '__main__':
    main()
