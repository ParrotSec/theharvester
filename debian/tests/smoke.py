#!/usr/bin/python3
"""Installed-package smoke tests; use only local resources and no API keys."""

import argparse
import asyncio
import http.server
import importlib
import pkgutil
from pathlib import Path
import sys
import tempfile
import threading


async def squared(value):
    return value * value


def basic():
    import theHarvester
    import theHarvester.discovery
    from theHarvester.lib.core import Core, DATA_DIR
    from theHarvester.lib.api.api import app, limiter
    from fastapi.testclient import TestClient

    assert sys.flags.isolated
    assert sys.prefix != sys.base_prefix
    assert Path(theHarvester.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
    assert theHarvester.__version__ == '4.11.1'
    for module in pkgutil.iter_modules(theHarvester.discovery.__path__):
        importlib.import_module(f'theHarvester.discovery.{module.name}')
    assert (DATA_DIR / 'wordlists/dns-names.txt').stat().st_size > 0
    assert isinstance(Core.api_keys()['censys'], dict)
    limiter.reset()
    with TestClient(app) as client:
        responses = [client.get('/sources') for _ in range(6)]
        assert [r.status_code for r in responses] == [200] * 5 + [429]
        assert 'censys' in responses[0].json()['sources']
        assert client.get('/query').status_code == 422
        assert client.post('/additional/all', json={'domain': 'example.invalid'}).status_code == 503

    async def check_async_libraries():
        import aiosqlite
        import aiomultiprocess

        async with aiosqlite.connect(':memory:') as db:
            await db.execute('create table results (value text)')
            await db.execute('insert into results values (?)', ('example.invalid',))
            async with db.execute('select value from results') as cursor:
                assert await cursor.fetchall() == [('example.invalid',)]
        aiomultiprocess.set_context('fork')
        async with aiomultiprocess.Pool(2) as pool:
            assert await pool.map(squared, [1, 2, 3]) == [1, 4, 9]

    import uvloop
    uvloop.run(check_async_libraries())
    print('Installed CLI modules, data, API/rate limiting, SQLite and multiprocessing: OK')


def screenshots():
    from theHarvester.screenshot.screenshot import ScreenShotter

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = b'<html><body><h1>theHarvester package test</h1></body></html>'
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    with tempfile.TemporaryDirectory() as output, http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            address = f'127.0.0.1:{server.server_port}'

            async def check():
                shotter = ScreenShotter(output)
                await shotter.verify_installation()
                url, body = await shotter.visit(f'http://{address}')
                assert url and 'package test' in body
                await shotter.take_screenshot(f'http://{address}')
                image = Path(output) / f'{address}.png'
                assert image.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')

            asyncio.run(check())
        finally:
            server.shutdown()
            thread.join()
    print('Screenshot using the packaged browser and Node.js: OK')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['basic', 'screenshots'])
    args = parser.parse_args()
    if args.mode == 'basic':
        basic()
    else:
        screenshots()
