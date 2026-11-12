"""Deliver a stateless Responses stream only after its completed terminal event.

Failed upstream responses never reach the client, so their tool calls cannot run.
Retries use the identical request supplied by the caller. A downstream failure
after delivery starts is never retried here.
"""
import asyncio
import hashlib
import json
import re
import tempfile
import time

MAX_BYTES = 64 * 1024 * 1024
RETRY_DELAYS = (2, 8, 20, 60, 120, 180, 240, 300, 300)
ATTEMPT_TIMEOUT_SECONDS = 1800
TOTAL_TIMEOUT_SECONDS = 7200
# Codex measures idle time between parsed SSE events; comments alone do not reset it.
# Cover all withheld attempts, upstream close time and the retry delays.
CLIENT_IDLE_TIMEOUT_MS = 7_500_000
FRAME_END = re.compile(br'\r?\n\r?\n')
FATAL_CODES = {'invalid_api_key', 'authentication_error', 'insufficient_quota',
               'context_length_exceeded', 'invalid_request_error', 'unsupported_parameter'}


class IncompleteResponse(Exception):
    def __init__(self, reason, retryable=True, status=None):
        super().__init__(reason)
        self.retryable, self.status = retryable, status


class DownstreamClosed(Exception):
    pass


def eligible(request):
    return (request.get('stream') is True and not request.get('conversation')
            and not request.get('background')
            and all(t.get('type') in ('function', 'custom', 'local_shell') for t in request.get('tools', [])))


class StreamVerifier:
    def __init__(self):
        self.pending = b''
        self.completed = False
        self.response_id = None

    def feed(self, chunk):
        self.pending += chunk
        while match := FRAME_END.search(self.pending):
            block, self.pending = self.pending[:match.start()], self.pending[match.end():]
            parts = [line[5:].lstrip() for line in block.splitlines() if line.startswith(b'data:')]
            if not parts:
                continue  # SSE comments and keepalives are not model output.
            data = b'\n'.join(parts)
            if data == b'[DONE]':
                continue
            try:
                event = json.loads(data)
            except (ValueError, UnicodeDecodeError) as exc:
                raise IncompleteResponse('malformed_sse_json') from exc
            if not isinstance(event, dict):
                raise IncompleteResponse('invalid_sse_event')
            kind = event.get('type')
            response = event.get('response') or {}
            if not isinstance(response, dict):
                raise IncompleteResponse('invalid_response_object')
            rid = response.get('id')
            if rid:
                if self.response_id and rid != self.response_id:
                    raise IncompleteResponse('response_id_changed')
                self.response_id = rid
            if kind in ('error', 'response.failed', 'response.incomplete'):
                error = event.get('error') or response.get('error') or event
                code = error.get('code') if isinstance(error, dict) else None
                raise IncompleteResponse(f'{kind}:{code or "unspecified"}',
                                         retryable=kind != 'response.incomplete' and code not in FATAL_CODES)
            if self.completed:
                raise IncompleteResponse('event_after_completed')
            if kind == 'response.completed':
                if (not isinstance(rid, str) or not rid or response.get('status') != 'completed'
                        or response.get('error') or response.get('incomplete_details')):
                    raise IncompleteResponse('invalid_completed_terminal')
                self.completed = True

    def finish(self):
        if self.pending.strip() or not self.completed:
            raise IncompleteResponse('stream_ended_without_complete_terminal')


async def body_chunks(reader, headers):
    if 'chunked' in headers.get('transfer-encoding', '').lower():
        while True:
            line = await reader.readline()
            if not line:
                raise IncompleteResponse('truncated_chunk_header')
            try:
                size = int(line.split(b';', 1)[0].strip(), 16)
            except ValueError as exc:
                raise IncompleteResponse('invalid_chunk_size') from exc
            if size < 0 or size > MAX_BYTES:
                raise IncompleteResponse('response_size_limit', retryable=False)
            if size == 0:
                # Consume trailers through their terminating blank line.
                while True:
                    trailer = await reader.readline()
                    if trailer == b'\r\n':
                        return
                    if not trailer:
                        raise IncompleteResponse('truncated_chunk_trailers')
            chunk = await reader.readexactly(size)
            if await reader.readexactly(2) != b'\r\n':
                raise IncompleteResponse('invalid_chunk_delimiter')
            yield chunk
    elif 'content-length' in headers:
        remaining = int(headers['content-length'])
        if remaining < 0 or remaining > MAX_BYTES:
            raise IncompleteResponse('response_size_limit', retryable=False)
        while remaining:
            chunk = await reader.readexactly(min(65536, remaining))
            remaining -= len(chunk)
            yield chunk
    else:
        while chunk := await reader.read(65536):
            yield chunk


async def collect(send_request, on_stream, note, spool_dir):
    """Return an intact verified response; always close a rejected upstream."""
    stream = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, dir=spool_dir)
    verifier, digest, size, upstream = StreamVerifier(), hashlib.sha256(), 0, None
    try:
        reader, upstream, status, headers = await send_request()
        note(event='atomic_upstream_status', upstream_status=status)
        if status != 200:
            raise IncompleteResponse(f'http_{status}', (status in (408, 429) or 500 <= status <= 599), status)
        if ('text/event-stream' not in headers.get('content-type', '')
                or headers.get('content-encoding', 'identity') not in ('', 'identity')):
            raise IncompleteResponse('unsupported_stream_encoding', retryable=False)
        await on_stream()
        async for chunk in body_chunks(reader, headers):
            size += len(chunk)
            if size > MAX_BYTES:
                raise IncompleteResponse('response_size_limit', retryable=False)
            digest.update(chunk)
            stream.write(chunk)
            verifier.feed(chunk)
        verifier.finish()
        stream.seek(0)
        return stream, {'response_id': verifier.response_id, 'bytes': size, 'sha256': digest.hexdigest()}
    except BaseException:
        note(event='atomic_output_withheld', response_id=verifier.response_id,
             bytes=size, sha256=digest.hexdigest(), forwarded_model_bytes=0)
        stream.close()
        raise
    finally:
        if upstream is not None:
            upstream.close()
            try:
                await asyncio.wait_for(upstream.wait_closed(), 5)
            except (OSError, asyncio.TimeoutError):
                pass


async def relay(send_request, writer, note, spool_dir, retry_delays=RETRY_DELAYS,
                heartbeat_seconds=15, attempt_timeout=ATTEMPT_TIMEOUT_SECONDS,
                total_timeout=TOTAL_TIMEOUT_SECONDS):
    """Only comments cross the downstream connection before full verification."""
    started = False
    deadline = time.monotonic() + total_timeout

    async def start_stream():
        nonlocal started
        if not started:
            try:
                writer.write(b'HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n'
                             b'Cache-Control: no-cache\r\nConnection: close\r\n\r\n')
                await writer.drain()
            except OSError as exc:
                raise DownstreamClosed() from exc
            started = True

    async def keepalive():
        while True:
            await asyncio.sleep(heartbeat_seconds)
            if started:
                writer.write(b': awaiting a complete upstream response\n\n')
                await writer.drain()

    heart = asyncio.create_task(keepalive())
    task, buffered, last_error, committed = None, None, None, False
    try:
        for attempt in range(len(retry_delays) + 1):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                last_error = IncompleteResponse('retry_time_budget_exhausted', retryable=False)
                break
            note(event='atomic_attempt_start', attempt=attempt + 1)
            task = asyncio.create_task(asyncio.wait_for(collect(send_request, start_stream, note, spool_dir),
                                                        min(attempt_timeout, remaining)))
            done, _ = await asyncio.wait((task, heart), return_when=asyncio.FIRST_COMPLETED)
            if heart in done:
                # A disconnected client cannot receive a response or trigger retries.
                await heart
                raise ConnectionError('downstream heartbeat stopped')
            try:
                buffered, evidence = await task
            except (IncompleteResponse, OSError, asyncio.TimeoutError, asyncio.IncompleteReadError) as exc:
                last_error = exc
                retryable = getattr(exc, 'retryable', True)
                note(event='atomic_attempt_rejected', attempt=attempt + 1,
                     reason=str(exc)[:200] or type(exc).__name__, retryable=retryable,
                     forwarded_model_bytes=0)
                if not retryable or attempt == len(retry_delays):
                    break
                if retry_delays[attempt] >= deadline - time.monotonic():
                    last_error = IncompleteResponse('retry_time_budget_exhausted', retryable=False)
                    break
                delay = asyncio.create_task(asyncio.sleep(retry_delays[attempt]))
                task = delay
                done, _ = await asyncio.wait((delay, heart), return_when=asyncio.FIRST_COMPLETED)
                if heart in done:
                    await heart
                    raise ConnectionError('downstream heartbeat stopped')
                continue
            # No replay or retry is permitted after any verified model bytes are sent.
            note(event='atomic_response_verified', attempt=attempt + 1, **evidence)
            committed = True
            heart.cancel()
            while chunk := buffered.read(65536):
                writer.write(chunk)
                await writer.drain()
            note(event='atomic_response_committed', attempt=attempt + 1, **evidence)
            return True
        # Exhaustion remains a visible failed call, never a fabricated completion.
        error = {'type': 'error', 'code': 'atomic_upstream_incomplete',
                 'message': f'No complete upstream response was delivered: {last_error}'}
        if started:
            writer.write(b'event: error\ndata: ' + json.dumps(error).encode() + b'\n\n')
        else:
            data = json.dumps({'error': error}).encode()
            status = getattr(last_error, 'status', None) or 502
            writer.write(f'HTTP/1.1 {status} Upstream Error\r\nContent-Type: application/json\r\nContent-Length: {len(data)}\r\nConnection: close\r\n\r\n'.encode() + data)
        await writer.drain()
        note(event='atomic_exhausted', reason=str(last_error)[:200], forwarded_model_bytes=0)
        return False
    except (OSError, DownstreamClosed, asyncio.CancelledError):
        note(event='atomic_downstream_closed', after_commit=committed)
        raise
    finally:
        if task is not None and not task.done():
            task.cancel()
        heart.cancel()
        await asyncio.gather(*(t for t in (task, heart) if t is not None), return_exceptions=True)
        if buffered is not None:
            buffered.close()
        writer.close()
