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

type OnMessageCallback = Callable[[dict], Coroutine[Any, Any, None]]


class HeliusWsClient:
    """WebSocket client for Helius Enhanced Transactions (atlas endpoint).

    Protocol: transactionSubscribe (Helius-specific, Geyser-backed).
    Endpoint: wss://atlas-mainnet.helius-rpc.com/?api-key=...

    To migrate to Helius LaserStream (gRPC), replace this class without
    touching call sites — subscription_service and wallet_listener_worker
    only use connect(), resubscribe(), and listen_forever().
    """

    def __init__(self) -> None:
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._subscription_id: int | None = None
        self._request_id: int = 0

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def connect(self) -> None:
        """Opens the WebSocket connection to Helius."""
        url = settings.helius_ws_endpoint
        _logger.info("Connecting to Helius WebSocket: %s", url.split("?")[0])
        self._ws = await websockets.connect(
            url,
            ping_interval=20,
            ping_timeout=10,
            close_timeout=5,
        )
        self._subscription_id = None
        _logger.info("Helius WebSocket connected.")

    async def subscribe_wallets(self, addresses: set[str]) -> None:
        """Subscribes to transactions for the given wallet addresses via transactionSubscribe."""
        if not addresses:
            return
        if self._ws is None:
            raise RuntimeError("WebSocket not connected. Call connect() first.")

        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "transactionSubscribe",
            "params": [
                {
                    "vote": False,
                    "failed": False,
                    "accountInclude": list(addresses),
                },
                {
                    "commitment": "confirmed",
                    "encoding": "jsonParsed",
                    "transactionDetails": "full",
                    "showRewards": False,
                    "maxSupportedTransactionVersion": 0,
                },
            ],
        }
        await self._ws.send(json.dumps(payload))
        _logger.info("Helius subscription sent for %d wallet(s).", len(addresses))

    async def unsubscribe(self) -> None:
        """Cancels the active subscription if one exists."""
        if self._ws is None or self._subscription_id is None:
            return

        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "transactionUnsubscribe",
            "params": [self._subscription_id],
        }
        try:
            await self._ws.send(json.dumps(payload))
            _logger.debug("Unsubscribe sent (subscription_id=%s).", self._subscription_id)
        except websockets.exceptions.WebSocketException:
            pass
        finally:
            self._subscription_id = None

    async def resubscribe(self, addresses: set[str]) -> None:
        """Cancels the active subscription and re-subscribes with the new wallet list.

        If addresses is empty, only unsubscribes.
        """
        await self.unsubscribe()
        if addresses:
            await self.subscribe_wallets(addresses)

    async def listen_forever(self, on_message: OnMessageCallback) -> None:
        """Listens for Helius messages and dispatches transactionNotification events to the callback.

        Subscription confirmations update _subscription_id; unknown messages are silently ignored.
        Raises websockets.exceptions.ConnectionClosed on disconnect so the worker can reconnect.
        """
        if self._ws is None:
            raise RuntimeError("WebSocket not connected.")

        async for raw in self._ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                _logger.warning("Non-JSON message from Helius ignored.")
                continue

            if "result" in msg and isinstance(msg["result"], int):
                self._subscription_id = msg["result"]
                _logger.info("Helius subscription confirmed (id=%s).", self._subscription_id)
                continue

            if msg.get("method") == "transactionNotification":
                result = msg.get("params", {}).get("result")
                if result:
                    try:
                        await on_message(result)
                    except Exception:
                        _logger.exception("Error in on_message callback.")
                continue

            if "error" in msg:
                _logger.warning("Helius error received: %s", msg["error"])

    def is_connected(self) -> bool:
        return self._ws is not None and self._ws.state == State.OPEN

    async def close(self) -> None:
        """Closes the WebSocket connection cleanly."""
        if self._ws is not None:
            await self._ws.close()
            self._ws = None
            _logger.info("Helius connection closed.")


async def wait_with_reconnect_log(seconds: int) -> None:
    _logger.info("Reconnecting to Helius in %ds...", seconds)
    await asyncio.sleep(seconds)
