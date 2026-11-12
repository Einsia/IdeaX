"""宿主侧 API 闸门：agent 唯一的出口，挂在 unix socket 上。

agent 的命名空间没有网络；里面的 uds_bridge.py 把 127.0.0.1:<port> 转到这里。agent 看到的是
  ANTHROPIC_BASE_URL=http://127.0.0.1:<port>   ANTHROPIC_AUTH_TOKEN=<假值>   HTTPS_PROXY=http://127.0.0.1:<port>
所以：
  · POST /v1/messages…  → 检查请求体，换上真凭据，经上游代理转发到 API 中转，响应原样流回
      请求体里带服务端工具（type 不是普通函数工具的，例如 web_search / web_fetch / code_execution）
      或 mcp_servers / container 的一律 403：这些会让模型替 agent 联网
  · CONNECT 任意目标     → 403（agent 不许开隧道，所有联网企图都记在日志里）
  · 其他路径             → 403
预测轮（--allow-web，idea_run --mode predict）放开联网：服务端的 web_search / web_fetch 工具照转，
CONNECT 经上游代理开隧道（WebFetch、curl https 都走这里），每个目标都记日志；直连 API 中转的隧道仍然拒绝，
免得 agent 绕过闸门换凭据。
  · GET /v1/models、POST /v1/responses…（codex，OpenAI 兼容）→ 使用入口配置的凭据和提供方；
      请求体里的工具只放行函数类（function / custom / local_shell），web_search 只在 --allow-web 时放行；
      codex 的独立搜索接口 /v1/alpha/search 也只在 --allow-web 时放行
      LITGRAPH_CODEX_ATOMIC_RESPONSES=1 时，无可变会话状态、无服务端工具的流式 Responses 请求
      会先缓冲到 response.completed 且 HTTP 正文完整，再交付任何模型输出。未交付的失败响应最多重试
      四次相同请求，不改模型、effort 或研究会话；交付开始后不重试。其他请求按普通方式转发。
真凭据只在这个进程里，由入口指定的凭据加载器读取，命名空间里没有。
GPT 入口使用显式配置的 sbtunnel，不自动切换提供方。

  python3 api_gate.py --log <path> --sock name=path [name=path ...]
"""
import argparse, asyncio, hashlib, json, os, re, ssl, sys, time, uuid, ipaddress
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from quota import async_slot

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from isolate import api_env, sub2api_env, upstream_proxy            # noqa: E402

ALLOW_PATH = re.compile(r'^/v1/messages(/count_tokens)?(\?.*)?$')
OPENAI_PATH = re.compile(r'^/v1/(responses|models)(/[^?\s]*)?(\?.*)?$')
OPENAI_SEARCH = re.compile(r'^/v1/alpha/search(\?.*)?$')      # codex 的独立联网搜索（supports_standalone_web_search）
OPENAI_TOOLS = {'function', 'custom', 'local_shell'}       # 客户端执行的工具；其余类型由服务端执行（联网、跑代码等）
DROP_HEADERS = {'host', 'authorization', 'x-api-key', 'proxy-authorization', 'proxy-connection',
                'connection', 'keep-alive', 'transfer-encoding', 'content-length', 'te', 'upgrade',
                'accept-encoding'}          # 不要压缩：闸门要读 SSE 事件（见 relay_sse）
# 中转站会掐断思考阶段太长（约 3 分钟）的流：正文/工具调用还没开始就断了，客户端只能报
# "Connection lost mid-response"。闸门先把思考事件缓冲住，正文开始前上游断开就降一档 effort 重发，
# 客户端看到的仍是一条完整的响应。最多重发 RETRIES 次。
RETRIES = 2
# 中转站临时不可用（账号池耗尽 / 并发超限）：闸门先不回给 agent，隔一会儿重发，最多压 HOLD_SECS 秒
# （低于 CLI 单次请求 10 分钟的超时）；仍不行再把错误交给 CLI，它自己还会重试
TRANSIENT = re.compile(r'no available accounts|too many pending|insufficient (account )?balance', re.I)
HOLD_SECS, HOLD_STEP = 480, 45
EFFORT_DOWN = {'max': 'xhigh', 'xhigh': 'high', 'high': 'medium', 'medium': 'low'}


WEB_TOOLS = re.compile(r'^web_(search|fetch)_')


def host_excluded(host, denied_hosts):
    name=host.lower().rstrip('.').strip('[]')
    if any(name==d or name.endswith('.'+d) for d in denied_hosts):return True
    if denied_hosts:
        # Direct IP tunnels could bypass the Web-only hostname exclusion.
        try:ipaddress.ip_address(name);return True
        except ValueError:pass
    return False


def forbidden(body, allow_web=False):
    """请求体里会让模型联网的东西。返回原因或 None。预测轮放行 web_search / web_fetch，其余服务端工具仍拒绝。"""
    try:
        d = json.loads(body or b'{}')
    except Exception:
        return '请求体不是 JSON'
    if d.get('mcp_servers'):
        return 'mcp_servers'
    if d.get('container'):
        return 'container'
    for t in d.get('tools') or []:
        typ = t.get('type')
        if typ not in (None, 'custom') and not (allow_web and WEB_TOOLS.match(typ or '')):
            return f'服务端工具 {typ}'
    return None


def forbidden_openai(body, allow_web=False):
    """OpenAI responses 请求体里会让服务端替 agent 联网或执行的工具。"""
    if not body:
        return None
    try:
        d = json.loads(body)
    except Exception:
        return '请求体不是 JSON'
    for t in d.get('tools') or []:
        typ = t.get('type') or ''
        if typ in OPENAI_TOOLS or (allow_web and typ.startswith('web_search')):
            continue
        return f'服务端工具 {typ}'
    return None


async def read_body(reader, headers):
    if 'chunked' in headers.get('transfer-encoding', '').lower():
        out = b''
        while True:
            size = int((await reader.readline()).split(b';')[0].strip() or b'0', 16)
            if size == 0:
                await reader.readline()
                return out
            out += await reader.readexactly(size)
            await reader.readline()
    n = int(headers.get('content-length') or 0)
    return await reader.readexactly(n) if n else b''


async def body_chunks(reader, headers):
    """响应体解码后的字节（处理 chunked；否则读到 EOF）。"""
    if 'chunked' in headers.get('transfer-encoding', '').lower():
        while True:
            line = await reader.readline()
            if not line:
                return
            size = int(line.split(b';')[0].strip() or b'0', 16)
            if size == 0:
                return
            yield await reader.readexactly(size)
            await reader.readline()
    else:
        while True:
            b = await reader.read(65536)
            if not b:
                return
            yield b


def lower_effort(body, step):
    """把请求的 effort 降 step 档（没写 effort 的按 high 算）。只改 output_config.effort，不碰其它字段。"""
    d = json.loads(body)
    oc = dict(d.get('output_config') or {})
    e = oc.get('effort') or 'high'
    for _ in range(step):
        e = EFFORT_DOWN.get(e, e)
    oc['effort'] = e
    d['output_config'] = oc
    return json.dumps(d, ensure_ascii=False).encode(), e


def sse_event(block):
    """(事件名, 内容块类型) —— 只在 content_block_start 时解析 data。"""
    ev, ctype = None, None
    for ln in block.split(b'\n'):
        if ln.startswith(b'event:'):
            ev = ln[6:].strip().decode('latin-1')
        elif ln.startswith(b'data:') and ev == 'content_block_start':
            try:
                ctype = json.loads(ln[5:])['content_block']['type']
            except Exception:
                pass
    return ev, ctype


async def pipe(r, w):
    try:
        while True:
            b = await r.read(65536)
            if not b:
                break
            w.write(b)
            await w.drain()
    except Exception:
        pass
    finally:
        try:
            w.close()
        except Exception:
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--log', required=True)
    ap.add_argument('--sock', nargs='+', required=True, help='name=path，每个 agent 一个')
    ap.add_argument('--allow-web', action='store_true', help='预测轮：放行联网搜索和 https 隧道')
    a = ap.parse_args()
    env = api_env()
    m = re.match(r'https://([^/:]+)(?::(\d+))?', env['ANTHROPIC_BASE_URL'])
    host, port = m.group(1), int(m.group(2) or 443)
    auth = env.get('ANTHROPIC_AUTH_TOKEN')
    key = env.get('ANTHROPIC_API_KEY')
    up = upstream_proxy()
    up = (up.rsplit(':', 1)[0], int(up.rsplit(':', 1)[1])) if up else None
    s2a = sub2api_env()
    m = re.match(r'https://([^/:]+)(?::(\d+))?', s2a.get('SUB2API_BASE_URL', ''))
    o_host, o_port, o_key = (m.group(1), int(m.group(2) or 443), s2a.get('SUB2API_API_KEY')) if m else (None, None, None)
    tls = ssl.create_default_context()
    log = open(a.log, 'a')

    def note(**kw):
        log.write(json.dumps({'t': time.strftime('%F %T'), **kw}, ensure_ascii=False) + '\n')
        log.flush()

    note(event='provider_start', openai_host=o_host)

    async def deny(writer, agent, why, **kw):
        note(agent=agent, allowed=False, why=why, **kw)
        try:
            writer.write(b'HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
            await writer.drain()
        finally:
            writer.close()

    async def tunnel(reader, writer, agent, target):
        """预测轮的 https 隧道：经上游代理连到目标，两头原样对拷。"""
        th, _, tp = target.rpartition(':')
        denied_hosts = {h.strip().lower().rstrip('.') for h in
                        os.environ.get('LITGRAPH_WEB_DENY_HOSTS', '').split(',') if h.strip()}
        if host_excluded(th, denied_hosts):
            return await deny(writer, agent, 'host excluded by experiment condition',
                              method='CONNECT', target=target)
        if th.lower() in {host.lower(), (o_host or '').lower()}:
            return await deny(writer, agent, '不许直连 API 中转', method='CONNECT', target=target)
        try:
            if up:
                ur, uw = await asyncio.open_connection(*up)
                uw.write(f'CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n\r\n'.encode())
                await uw.drain()
                resp = await asyncio.wait_for(ur.readuntil(b'\r\n\r\n'), 30)
                if b' 200' not in resp.split(b'\r\n', 1)[0]:
                    raise RuntimeError(f'上游代理拒绝: {resp[:80]!r}')
            else:
                ur, uw = await asyncio.open_connection(th, int(tp or 443))
        except Exception as e:
            note(agent=agent, allowed=True, method='CONNECT', target=target, error=f'{type(e).__name__}: {e}'[:200])
            writer.write(b'HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
            await writer.drain()
            writer.close()
            return
        note(agent=agent, allowed=True, method='CONNECT', target=target)
        writer.write(b'HTTP/1.1 200 Connection Established\r\n\r\n')
        await writer.drain()

        async def pipe(r, w):
            try:
                while True:
                    chunk = await r.read(65536)
                    if not chunk:
                        break
                    w.write(chunk)
                    await w.drain()
            except Exception:
                pass
            finally:
                try:
                    w.close()
                except Exception:
                    pass

        await asyncio.gather(pipe(reader, uw), pipe(ur, writer))

    async def openai_request(method, path, headers, body):
        """Open one upstream request, preserving the exact body on any retry."""
        uw = None
        try:
            if up:
                ur, uw = await asyncio.open_connection(*up)
                uw.write(f'CONNECT {o_host}:{o_port} HTTP/1.1\r\nHost: {o_host}:{o_port}\r\n\r\n'.encode())
                await uw.drain()
                resp = await asyncio.wait_for(ur.readuntil(b'\r\n\r\n'), 30)
                if b' 200' not in resp.split(b'\r\n', 1)[0]:
                    raise RuntimeError(f'上游代理拒绝 CONNECT: {resp[:80]!r}')
                await uw.start_tls(tls, server_hostname=o_host)
            else:
                ur, uw = await asyncio.open_connection(o_host, o_port, ssl=tls, server_hostname=o_host)
            hs = [f'{k}: {v}' for k, v in headers.items() if k not in DROP_HEADERS]
            hs += [f'Host: {o_host}', f'Authorization: Bearer {o_key}', 'Connection: close']
            if method == 'POST':
                hs.append(f'Content-Length: {len(body)}')
            uw.write((f'{method} {path} HTTP/1.1\r\n' + '\r\n'.join(hs) + '\r\n\r\n').encode('latin-1') + body)
            await uw.drain()
            rh = await asyncio.wait_for(ur.readuntil(b'\r\n\r\n'), 600)
            rl = rh.decode('latin-1').split('\r\n')
            rhd = {k.strip().lower(): v.strip() for k, v in (ln.split(':', 1) for ln in rl[1:] if ':' in ln)}
            return ur, uw, rl, rhd
        except BaseException:
            if uw is not None:
                uw.close()
            raise

    async def unguarded_openai_forward(reader, writer, agent, method, path, headers):
        """Forward Codex requests, optionally withholding incomplete stateless streams."""
        if method not in ('GET', 'POST'):
            return await deny(writer, agent, '不是 responses/models 接口', method=method, target=path)
        body = await read_body(reader, headers) if method == 'POST' else b''
        why = forbidden_openai(body, False)
        if why:
            return await deny(writer, agent, why, method=method, target=path, bytes=len(body))
        request = json.loads(body) if body else {}
        atomic_enabled = os.environ.get('LITGRAPH_CODEX_ATOMIC_RESPONSES',
                                        os.environ.get('LITGRAPH_CODEX_REQUIRE_CLEAN_TRANSPORT', '0')) == '1'
        if (atomic_enabled
                and method == 'POST' and path.split('?', 1)[0] == '/v1/responses'):
            from responses_atomic import eligible, relay
            if eligible(request):
                request_hash = hashlib.sha256(body).hexdigest()
                request_group = uuid.uuid4().hex

                def atomic_note(**fields):
                    note(agent=agent, allowed=True, target=path, request_group=request_group,
                         request_sha256=request_hash, **fields)

                async def send_identical_request():
                    ur, uw, rl, rhd = await openai_request(method, path, headers, body)
                    return ur, uw, int(rl[0].split()[1]), rhd

                atomic_note(event='atomic_mode', model=request.get('model'),
                            effort=(request.get('reasoning') or {}).get('effort'),
                            policy='complete_response_before_any_model_output_v1')
                return await relay(send_identical_request, writer, atomic_note,
                                   os.environ.get('IDEAX_SCRATCH') or os.path.dirname(a.log))
            note(agent=agent, event='atomic_bypass', target=path,
                 reason='Only streaming requests without mutable conversation state or server tools are eligible')
        try:
            ur, uw, rl, _ = await openai_request(method, path, headers, body)
        except Exception as e:
            note(agent=agent, allowed=True, target=path, error=f'{type(e).__name__}: {e}'[:200])
            writer.write(b'HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
            await writer.drain()
            writer.close()
            return
        request_model = json.loads(body).get('model') if body and method == 'POST' else None
        note(agent=agent, allowed=True, target=path, bytes=len(body), model=request_model, upstream=rl[0][9:40])
        keep = [ln for ln in rl[1:] if ln and ln.split(':', 1)[0].strip().lower() not in ('connection', 'keep-alive')]
        writer.write(('\r\n'.join([rl[0]] + keep + ['Connection: close']) + '\r\n\r\n').encode('latin-1'))
        await writer.drain()
        await pipe(ur, writer)
        try:
            uw.close()
        except Exception:
            pass

    async def openai_forward(reader, writer, agent, method, path, headers):
        if method == 'POST' and path.split('?',1)[0] == '/v1/responses':
            role=os.environ.get('IDEAX_REQUEST_ROLE','astra_generation')
            async with async_slot(role,label=a.log+'/'+agent):
                return await unguarded_openai_forward(reader,writer,agent,method,path,headers)
        return await unguarded_openai_forward(reader,writer,agent,method,path,headers)

    async def handle(reader, writer, agent):
        try:
            head = await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'), 60)
        except Exception:
            writer.close()
            return
        lines = head.decode('latin-1').split('\r\n')
        parts = lines[0].split()
        method, target = (parts[0].upper(), parts[1]) if len(parts) >= 2 else ('?', '?')
        headers = {}
        for ln in lines[1:]:
            if ':' in ln:
                k, v = ln.split(':', 1)
                headers[k.strip().lower()] = v.strip()
        if method == 'CONNECT':
            if not a.allow_web:
                return await deny(writer, agent, '不许开隧道', method=method, target=target)
            return await tunnel(reader, writer, agent, target)
        path = re.sub(r'^https?://[^/]+', '', target)
        if o_host and OPENAI_SEARCH.match(path):
            if not a.allow_web:
                return await deny(writer, agent, '联网搜索（只在预测轮放行）', method=method, target=path)
            return await openai_forward(reader, writer, agent, method, path, headers)
        if o_host and OPENAI_PATH.match(path):
            return await openai_forward(reader, writer, agent, method, path, headers)
        if method != 'POST' or not ALLOW_PATH.match(path):
            return await deny(writer, agent, '不是 messages 接口', method=method, target=target[:200])
        body = await read_body(reader, headers)
        why = forbidden(body, a.allow_web)
        if why:
            return await deny(writer, agent, why, method=method, target=path, bytes=len(body))
        async def send_upstream(b):
            """开一条到 API 的连接，发请求，读响应头。返回 (reader, writer, 状态行+头行, 头字典)。"""
            if up:
                ur, uw = await asyncio.open_connection(*up)
                uw.write(f'CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n\r\n'.encode())
                await uw.drain()
                resp = await asyncio.wait_for(ur.readuntil(b'\r\n\r\n'), 30)
                if b' 200' not in resp.split(b'\r\n', 1)[0]:
                    raise RuntimeError(f'上游代理拒绝 CONNECT: {resp[:80]!r}')
                await uw.start_tls(tls, server_hostname=host)
            else:
                ur, uw = await asyncio.open_connection(host, port, ssl=tls, server_hostname=host)
            hs = [f'{k}: {v}' for k, v in headers.items() if k not in DROP_HEADERS]
            hs += [f'Host: {host}', f'Content-Length: {len(b)}', 'Connection: close']
            if auth:
                hs.append(f'Authorization: Bearer {auth}')
            if key:
                hs.append(f'x-api-key: {key}')
            uw.write((f'POST {path} HTTP/1.1\r\n' + '\r\n'.join(hs) + '\r\n\r\n').encode('latin-1') + b)
            await uw.drain()
            rh = await asyncio.wait_for(ur.readuntil(b'\r\n\r\n'), 600)
            rl = rh.decode('latin-1').split('\r\n')
            rhd = {k.strip().lower(): v.strip() for k, v in (ln.split(':', 1) for ln in rl[1:] if ':' in ln)}
            return ur, uw, rl, rhd

        def drop(uw):
            try:
                uw.close()
            except Exception:
                pass

        try:
            ur, uw, rl, rhd = await send_upstream(body)
        except Exception as e:
            note(agent=agent, allowed=True, target=path, error=f'{type(e).__name__}: {e}'[:200])
            writer.write(b'HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
            await writer.drain()
            writer.close()
            return
        note(agent=agent, allowed=True, target=path, bytes=len(body))

        held_body, deadline = None, time.time() + HOLD_SECS
        while (rl[0].split()[1:2] or [''])[0] in ('403', '429', '503'):
            held_body = b''.join([c async for c in body_chunks(ur, rhd)])
            drop(uw)
            if not TRANSIENT.search(held_body.decode('utf-8', 'ignore')) or time.time() + HOLD_STEP > deadline:
                break
            note(agent=agent, allowed=True, target=path, upstream=rl[0][9:40], why='中转站暂时不可用，压住请求稍后重发')
            await asyncio.sleep(HOLD_STEP)
            try:
                ur, uw, rl, rhd = await send_upstream(body)
                held_body = None
            except Exception as e:
                note(agent=agent, allowed=True, target=path, error=f'{type(e).__name__}: {e}'[:200])
                writer.write(b'HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
                await writer.drain()
                writer.close()
                return
        if held_body is not None:
            # 已经把错误响应体读出来了：自己按 Content-Length 回给客户端
            hop = ('connection', 'keep-alive', 'transfer-encoding', 'content-length')
            keep = [ln for ln in rl[1:] if ln and ln.split(':', 1)[0].strip().lower() not in hop]
            writer.write(('\r\n'.join([rl[0]] + keep + [f'Content-Length: {len(held_body)}', 'Connection: close'])
                          + '\r\n\r\n').encode('latin-1') + held_body)
            await writer.drain()
            writer.close()
            return

        sse = (' 200' in rl[0] and 'text/event-stream' in rhd.get('content-type', '')
               and rhd.get('content-encoding', 'identity') in ('', 'identity'))
        if not sse:
            # 非流式或出错的响应：原样流回。响应头里明确告诉客户端连接要关，免得它复用这条连接（闸门一个连接只转一个请求）
            keep = [ln for ln in rl[1:] if ln and ln.split(':', 1)[0].strip().lower() not in ('connection', 'keep-alive')]
            writer.write(('\r\n'.join([rl[0]] + keep + ['Connection: close']) + '\r\n\r\n').encode('latin-1'))
            await writer.drain()
            await pipe(ur, writer)
            drop(uw)
            return

        # SSE：闸门自己解码（去掉 chunked），按关连接收尾
        hop = ('connection', 'keep-alive', 'transfer-encoding', 'content-length')
        keep = [ln for ln in rl[1:] if ln and ln.split(':', 1)[0].strip().lower() not in hop]
        try:
            writer.write(('\r\n'.join([rl[0]] + keep + ['Connection: close']) + '\r\n\r\n').encode('latin-1'))
            await writer.drain()
        except Exception:
            drop(uw)
            return
        started, attempt = False, 0          # started：已经给客户端发过 message_start（重发时不再发第二个）
        while True:
            held, committed, buf, gone = [], False, b'', False
            try:
                async for chunk in body_chunks(ur, rhd):
                    buf += chunk.replace(b'\r\n', b'\n')
                    out = []
                    while b'\n\n' in buf:
                        block, buf = buf.split(b'\n\n', 1)
                        raw = block + b'\n\n'
                        ev, ctype = sse_event(block)
                        if ev == 'message_start':
                            if not started:
                                out.append(raw)
                                started = True
                        elif ev == 'ping' or committed:
                            out.append(raw)
                        elif ev == 'content_block_start' and ctype in ('thinking', 'redacted_thinking') or \
                                ev in ('content_block_delta', 'content_block_stop') and held:
                            held.append(raw)                     # 思考阶段：先压住
                        else:                                    # 正文 / 工具调用 / 结束 / 错误：放行
                            committed = True
                            out += held + [raw]
                            held = []
                    try:
                        for x in out:
                            writer.write(x)
                        await writer.drain()
                    except Exception:
                        gone = True
                        break
            except Exception as e:
                note(agent=agent, allowed=True, target=path, error=f'读响应体中断 {type(e).__name__}', attempt=attempt)
            drop(uw)
            if gone or committed:
                break
            # 正文开始前上游就断了
            if attempt >= RETRIES:
                note(agent=agent, allowed=True, target=path, error=f'思考阶段断流，重发 {attempt} 次仍失败')
                try:
                    for x in held:
                        writer.write(x)
                    await writer.drain()
                except Exception:
                    pass
                break
            attempt += 1
            nb, eff = lower_effort(body, attempt)
            note(agent=agent, allowed=True, target=path, retry=attempt, effort=eff, why='思考阶段断流，降 effort 重发')
            try:
                ur, uw, rl, rhd = await send_upstream(nb)
            except Exception as e:
                rl, rhd = [f'gate: {type(e).__name__}: {e}'[:200]], {}
            if not (' 200' in rl[0] and 'text/event-stream' in rhd.get('content-type', '')):
                # 已经回过 200 了，只能用 SSE 的 error 事件告诉客户端
                msg = json.dumps({'type': 'error', 'error': {'type': 'api_error', 'message': f'gate retry: {rl[0][:150]}'}})
                try:
                    writer.write(f'event: error\ndata: {msg}\n\n'.encode())
                    await writer.drain()
                except Exception:
                    pass
                drop(uw)
                break
        try:
            writer.close()
        except Exception:
            pass

    async def serve():
        servers = []
        for spec in a.sock:
            name, path = spec.split('=', 1)
            if os.path.exists(path):
                os.remove(path)
            servers.append(await asyncio.start_unix_server(lambda r, w, n=name: handle(r, w, n), path=path))
            os.chmod(path, 0o600)
        note(event='start', api=f'{host}:{port}', upstream=up and f'{up[0]}:{up[1]}',
             agents=[x.split('=', 1)[0] for x in a.sock])
        await asyncio.gather(*(s.serve_forever() for s in servers))

    asyncio.run(serve())


if __name__ == '__main__':
    main()
