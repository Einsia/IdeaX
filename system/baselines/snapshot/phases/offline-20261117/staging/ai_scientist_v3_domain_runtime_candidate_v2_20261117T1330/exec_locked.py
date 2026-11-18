"""Lock the already isolated agent process before executing native Headless."""
from pathlib import Path
import json
import os
import sys

sys.path.insert(0, os.environ['SAKANA_PHASE_RUNTIME'])
from inside import lock_namespace
lock_namespace()
run = Path(os.environ['SAKANA_RUN'])
boundary = json.dumps({
    'pid': os.getpid(), 'netns': os.readlink('/proc/self/ns/net'),
    'route': Path('/proc/net/route').read_text(), 'mountinfo': Path('/proc/self/mountinfo').read_text(),
    'status': Path('/proc/self/status').read_text(), 'command': sys.argv[1:]
}, indent=2) + '\n'
fd = int(os.environ.pop('SAKANA_BOUNDARY_FD'))
os.write(fd, boundary.encode()); os.close(fd)
os.execv(sys.argv[1], sys.argv[1:])
