"""Immutable artifacts and append-only receipts for one independent slot."""
from dataclasses import asdict, is_dataclass
import datetime
import hashlib
import json
import os
from pathlib import Path


def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def encode(value): return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()
def digest(value): return hashlib.sha256(value).hexdigest()
def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''): h.update(block)
    return h.hexdigest()


def freeze_bytes(path, body):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open('xb') as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        if path.read_bytes() != body:
            raise RuntimeError('Immutable artifact changed: ' + str(path)) from None
    directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(directory_fd)
    finally: os.close(directory_fd)
    return digest(body)


def freeze(path, value): return freeze_bytes(path, encode(value))


def event(path, kind, **values):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = (json.dumps({'at': now(), 'event': kind, **values}, ensure_ascii=False, sort_keys=True) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        if os.write(fd, body) != len(body): raise OSError('Incomplete evidence write')
        os.fsync(fd)
    finally:
        os.close(fd)


def signature(path):
    s = Path(path).stat()
    return [s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns]
