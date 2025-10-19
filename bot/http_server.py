from __future__ import annotations

import asyncio
import json
from typing import Callable, Awaitable

from aiohttp import web


def create_app(secret: str, on_event: Callable[[dict], Awaitable[None]]) -> web.Application:
    app = web.Application()

    async def health(_: web.Request) -> web.Response:
        return web.json_response({"ok": True})

    async def events(req: web.Request) -> web.Response:
        auth = req.headers.get("x-bridge-secret")
        if auth != secret:
            return web.json_response({"error": "unauthorized"}, status=401)
        try:
            payload = await req.json()
        except Exception:
            return web.json_response({"error": "invalid_json"}, status=400)
        await on_event(payload)
        return web.json_response({"ok": True})

    app.add_routes([
        web.get("/health", health),
        web.post("/events", events),
    ])
    return app


async def run_server(host: str, port: int, app: web.Application) -> None:
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=host, port=port)
    await site.start()
    # Keep running
    while True:
        await asyncio.sleep(3600)