import asyncio
import dataclasses
import logging
import time

import websockets.exceptions

from app.api.listener_server import run_server
from app.clients import backend_client
from app.clients.dexscreener_client import get_token_info
from app.clients.pump_fun_client import get_token_symbol
from app.clients.pump_fun_onchain_client import get_market_cap as get_pump_market_cap
from app.clients.helius_http_client import fetch_enhanced_transaction
from app.clients.helius_ws_client import HeliusWsClient, wait_with_reconnect_log
from app.core.config import settings
from app.services import signal_engine, wallet_event_parser
from app.services.active_user_service import ActiveUserService
from app.services.subscription_service import SubscriptionService

_logger = logging.getLogger(__name__)


class WalletListenerWorker:
    """Orchestrates three concurrent loops.

    listen_loop: maintains the Helius WebSocket with auto-reconnect.
        Critical path: event → enrich → parse → signal → backend.

    refresh_loop: periodic 60s fallback re-sync from the backend in case
        an HTTP trigger was missed.

    http_server_loop: lightweight HTTP server.
        POST /subscribe   → immediate activation after /startbot (<1s).
        POST /unsubscribe → immediate deactivation after /stopbot (<1s).
    """

    def __init__(self) -> None:
        self._active_user_service = ActiveUserService()
        self._subscription_service = SubscriptionService()
        self._helius_client = HeliusWsClient()
        self._seen_signatures: dict[str, float] = {}

    async def run(self) -> None:
        _logger.info("WalletListenerWorker started.")
        await asyncio.gather(
            self._listen_loop(),
            self._refresh_loop(),
            self._http_server_loop(),
        )

    async def _listen_loop(self) -> None:
        """WebSocket loop with automatic reconnect."""
        while True:
            try:
                await self._helius_client.connect()

                self._subscription_service.clear()
                desired = self._active_user_service.get_wallet_to_user_ids_map()
                await self._subscription_service.sync(desired, self._helius_client)

                await self._helius_client.listen_forever(self._on_message)

            except websockets.exceptions.ConnectionClosed as exc:
                _logger.warning("Helius connection closed: %s.", exc)
            except OSError as exc:
                _logger.warning("Helius network error: %s.", exc)
            except Exception:
                _logger.exception("Unexpected error in listen_loop.")
            finally:
                await self._helius_client.close()

            await wait_with_reconnect_log(settings.WS_RECONNECT_SECONDS)

    async def _refresh_loop(self) -> None:
        """Full re-sync from backend every 60s (fallback in case HTTP triggers are missed)."""
        while True:
            await asyncio.sleep(settings.ACTIVE_USERS_REFRESH_SECONDS)
            try:
                await self._active_user_service.refresh()
                if self._helius_client.is_connected():
                    desired = self._active_user_service.get_wallet_to_user_ids_map()
                    await self._subscription_service.sync(desired, self._helius_client)
            except Exception:
                _logger.exception("Error in refresh_loop (continued).")

    async def _http_server_loop(self) -> None:
        """Starts the HTTP server for immediate subscribe/unsubscribe triggers."""
        await run_server(
            port=settings.LISTENER_HTTP_PORT,
            on_subscribe=self._immediate_refresh,
            on_unsubscribe=self._immediate_unsubscribe,
        )

    async def _immediate_refresh(self) -> None:
        """Triggered by POST /subscribe (after /startbot).

        Fetches the backend snapshot and syncs Helius subscriptions immediately,
        without waiting for the next refresh_loop cycle.
        """
        await self._active_user_service.refresh()
        if self._helius_client.is_connected():
            desired = self._active_user_service.get_wallet_to_user_ids_map()
            await self._subscription_service.sync(desired, self._helius_client)

    async def _immediate_unsubscribe(self, wallet_address: str, telegram_id: int) -> None:
        """Triggered by POST /unsubscribe (after /stopbot).

        Removes the user from the local snapshot and unsubscribes the wallet on Helius
        if no active users remain on it.
        """
        start = time.monotonic()

        user = self._active_user_service.remove_user_by_telegram_id(telegram_id)
        if user is None:
            _logger.debug(
                "[STOPBOT] telegram_id=%d — user not found in snapshot.",
                telegram_id,
            )
            return

        _logger.info(
            "[STOPBOT] telegram_id=%d wallet=%s...%s — removing.",
            telegram_id, wallet_address[:4], wallet_address[-4:],
        )

        if self._helius_client.is_connected():
            await self._subscription_service.remove_wallet_for_user(
                wallet_address, str(user.user_id), self._helius_client
            )

        latency_ms = (time.monotonic() - start) * 1000
        _logger.info(
            "[STOPBOT] telegram_id=%d wallet=%s...%s — done. latency=%.1fms",
            telegram_id, wallet_address[:4], wallet_address[-4:], latency_ms,
        )

    async def _on_message(self, signature: str) -> None:
        """Critical path: enrich → parse → evaluate → send signal.

        Receives a transaction signature from logsSubscribe.
        Enriched via Helius Enhanced Transactions REST API.
        Market cap via DexScreener with Pump.fun fallback.
        """
        received_at = time.monotonic()

        if not signature:
            return

        # Deduplicate: same signature arrives once per subscribed wallet that's mentioned
        now = received_at
        self._seen_signatures = {s: t for s, t in self._seen_signatures.items() if now - t < 10.0}
        if signature in self._seen_signatures:
            _logger.debug("[ON_MESSAGE] duplicate sig=%s — skipped.", signature[:16])
            return
        self._seen_signatures[signature] = now

        enhanced = await fetch_enhanced_transaction(signature)
        if enhanced is None:
            _logger.warning("[ON_MESSAGE] sig=%s — enrichment failed.", signature[:16])
            return

        watched = self._active_user_service.get_watched_wallets()
        event = wallet_event_parser.parse(enhanced, watched)
        sell_event = wallet_event_parser.parse_sell(enhanced, watched)

        if event is None and sell_event is None:
            return

        wallet_map = self._active_user_service.get_wallet_to_users_map()
        buy_signals: list = []
        sell_signals: list = []

        if event is not None:
            token_info, fallback_symbol, pump_mc = await asyncio.gather(
                get_token_info(event.token_address),
                get_token_symbol(event.token_address),
                get_pump_market_cap(event.token_address),
            )
            symbol = event.token_symbol or token_info.symbol or fallback_symbol
            market_cap = token_info.market_cap if token_info.market_cap is not None else pump_mc
            event = dataclasses.replace(event, token_symbol=symbol, market_cap=market_cap)

            buy_signals = signal_engine.evaluate(event, wallet_map)
            for signal in buy_signals:
                await backend_client.post_buy_signal(signal)

        if sell_event is not None:
            sell_signals = signal_engine.evaluate_sell(sell_event, wallet_map)
            for signal in sell_signals:
                await backend_client.post_sell_signal(signal)

        total_signals = len(buy_signals) + len(sell_signals)
        if total_signals:
            latency_ms = (time.monotonic() - received_at) * 1000
            token_addr = (event or sell_event).token_address  # type: ignore[union-attr]
            wallet_addr = (event or sell_event).wallet_address  # type: ignore[union-attr]
            _logger.info(
                "[EVENT] wallet=%s...%s token=%s buy=%d sell=%d latency=%.1fms",
                wallet_addr[:4], wallet_addr[-4:],
                token_addr[:8], len(buy_signals), len(sell_signals), latency_ms,
            )
