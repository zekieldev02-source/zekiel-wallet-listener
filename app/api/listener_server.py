import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any

from aiohttp import web

_logger = logging.getLogger(__name__)

type RefreshCallback = Callable[[], Coroutine[Any, Any, None]]
type UnsubscribeCallback = Callable[[str, int], Coroutine[Any, Any, None]]


async def _handle_subscribe(request: web.Request) -> web.Response:
    on_subscribe: RefreshCallback = request.app["on_subscribe"]
    _logger.info("Immediate refresh triggered via POST /subscribe.")
    try:
        await on_subscribe()
    except Exception:
        _logger.exception("Error during HTTP-triggered refresh.")
        return web.json_response({"ok": False}, status=500)
    return web.json_response({"ok": True})


async def _handle_unsubscribe(request: web.Request) -> web.Response:
    on_unsubscribe: UnsubscribeCallback = request.app["on_unsubscribe"]

    try:
        data: dict = await request.json()
    except Exception:
        return web.json_response({"ok": False, "error": "Invalid JSON."}, status=400)

    wallet_address: str | None = data.get("wallet_address")
    telegram_id_raw = data.get("telegram_id")

    if not wallet_address or telegram_id_raw is None:
        return web.json_response(
            {"ok": False, "error": "wallet_address and telegram_id are required."},
            status=400,
        )

    try:
        telegram_id = int(telegram_id_raw)
    except (TypeError, ValueError):
        return web.json_response(
            {"ok": False, "error": "telegram_id must be an integer."},
            status=400,
        )

    _logger.info(
        "Immediate unsubscribe triggered via POST /unsubscribe — "
        "telegram_id=%d wallet=%s...%s.",
        telegram_id, wallet_address[:4], wallet_address[-4:],
    )

    try:
        await on_unsubscribe(wallet_address, telegram_id)
    except Exception:
        _logger.exception("Error during HTTP-triggered unsubscribe.")
        return web.json_response({"ok": False}, status=500)

    return web.json_response({"ok": True})


async def _handle_health(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


async def run_server(
    port: int,
    on_subscribe: RefreshCallback,
    on_unsubscribe: UnsubscribeCallback,
) -> None:
    """Starts the HTTP server and keeps it running until the worker stops.

    POST /subscribe   — immediate refresh after /startbot.
    POST /unsubscribe — immediate unsubscribe after /stopbot.
    GET  /health      — health check.
    """
    app = web.Application()
    app["on_subscribe"] = on_subscribe
    app["on_unsubscribe"] = on_unsubscribe
    app.router.add_post("/subscribe", _handle_subscribe)
    app.router.add_post("/unsubscribe", _handle_unsubscribe)
    app.router.add_get("/health", _handle_health)

    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    _logger.info("HTTP listener server started on port %d.", port)

    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await runner.cleanup()
