"""命名空间内部的转发桥：127.0.0.1:<port> → 宿主出口闸门的 unix socket。

  python3 uds_bridge.py <port> <sock>
"""
import asyncio, sys

PORT, SOCK = int(sys.argv[1]), sys.argv[2]


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


async def handle(r, w):
    try:
        ur, uw = await asyncio.open_unix_connection(SOCK)
    except Exception:
        w.close()
        return
    await asyncio.gather(pipe(r, uw), pipe(ur, w))


async def main():
    srv = await asyncio.start_server(handle, '127.0.0.1', PORT)
    async with srv:
        await srv.serve_forever()


asyncio.run(main())
