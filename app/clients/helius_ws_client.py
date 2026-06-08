import asyncio
import json
import logging
from collections.abc import Callable, Coroutine
from typing import Any

import websockets
import websockets.exceptions
from websockets.connection import State

from app.core.config import settings

_logger = logging.getLogger(__name__)

type OnMessageCallback = Callable[[str], Coroutine[Any, Any, None]]


class HeliusWsClient:
    """WebSocket client using logsSubscribe (available on Helius free plan).

    Subscribes one subscription per wallet using {"mentions": [address]}.
    Each logsNotification yields a transaction signature, which is then
    enriched via the Helius Enhanced Transactions REST API.

    Endpoint: wss://mainnet.helius-rpc.com/?api-key=...
    """

    def __init__(self) -> None:
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._request_id: int = 0
        # subscription_id → wallet_address
        self._subscriptions: dict[int, str] = {}
        # pending request_id → wallet_address (before confirmation)
        self._pending: dict[int, str] = {}

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def connect(self) -> None:
        url = settings.helius_ws_endpoint
        _logger.info("Connecting to Helius WebSocket: %s", url.split("?")[0])
        self._ws = await websockets.connect(
            url,
            ping_interval=20,
            ping_timeout=10,
            close_timeout=5,
        )
        self._subscriptions.clear()
        self._pending.clear()
        _logger.info("Helius WebSocket connected.")

    async def subscribe_wallets(self, addresses: set[str]) -> None:
        """Subscribe to logs for each wallet address individually."""
        if not addresses or self._ws is None:
            return

        for address in addresses:
            req_id = self._next_id()
            self._pending[req_id] = address
            payload = {
                "jsonrpc": "2.0",
                "id": req_id,
                "method": "logsSubscribe",
                "params": [
                    {"mentions": [address]},
                    {"commitment": "confirmed"},
                ],
            }
            await self._ws.send(json.dumps(payload))

        _logger.info("Helius subscription sent for %d wallet(s).", len(addresses))

    async def unsubscribe(self) -> None:
        """Cancel all active subscriptions."""
        if self._ws is None:
            return

        for sub_id in list(self._subscriptions.keys()):
            payload = {
                "jsonrpc": "2.0",
                "id": self._next_id(),
                "method": "logsUnsubscribe",
                "params": [sub_id],
            }
            try:
                await self._ws.send(json.dumps(payload))
            except websockets.exceptions.WebSocketException:
                pass

        self._subscriptions.clear()
        self._pending.clear()

    async def resubscribe(self, addresses: set[str]) -> None:
        await self.unsubscribe()
        if addresses:
            await self.subscribe_wallets(addresses)

    async def listen_forever(self, on_message: OnMessageCallback) -> None:
        """Listen for logsNotification messages and dispatch transaction signatures.

        The callback receives the raw transaction signature (str).
        The caller is responsible for enriching it via the Helius REST API.
        """
        if self._ws is None:
            raise RuntimeError("WebSocket not connected.")

        async for raw in self._ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                _logger.warning("Non-JSON message from Helius ignored.")
                continue

            # Subscription confirmed: map request_id → subscription_id
            if "result" in msg and isinstance(msg.get("result"), int):
                req_id = msg.get("id")
                sub_id = msg["result"]
                if req_id in self._pending:
                    wallet = self._pending.pop(req_id)
                    self._subscriptions[sub_id] = wallet
                    _logger.info(
                        "Helius logsSubscribe confirmed: wallet=%s sub_id=%d",
                        wallet[:8], sub_id,
                    )
                continue

            if msg.get("method") == "logsNotification":
                value = msg.get("params", {}).get("result", {}).get("value", {})
                signature = value.get("signature")
                err = value.get("err")

                if err:
                    continue  # Skip failed transactions

                if signature:
                    try:
                        await on_message(signature)
                    except Exception:
                        _logger.exception("Error in on_message callback.")
                continue

            if "error" in msg:
                _logger.warning("Helius error received: %s", msg["error"])

    def is_connected(self) -> bool:
        return self._ws is not None and self._ws.state == State.OPEN

    async def close(self) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None
            _logger.info("Helius connection closed.")


async def wait_with_reconnect_log(seconds: int) -> None:
    _logger.info("Reconnecting to Helius in %ds...", seconds)
    await asyncio.sleep(seconds)
