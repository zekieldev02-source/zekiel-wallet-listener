import logging

from app.clients.helius_ws_client import HeliusWsClient

_logger = logging.getLogger(__name__)


class SubscriptionService:
    """Manages Helius subscriptions, tracking which users follow each wallet.

    A wallet is unsubscribed only when no active user follows it anymore.
    Helius transactionSubscribe does not support per-wallet add/remove —
    any list change triggers a full unsubscribe + resubscribe, but only when
    the wallet set actually changes.
    """

    def __init__(self) -> None:
        self._wallet_to_user_ids: dict[str, set[str]] = {}

    async def add_wallet_for_user(
        self,
        wallet: str,
        user_id: str,
        helius_client: HeliusWsClient,
    ) -> None:
        """Associates a user with a wallet and resubscribes if the wallet is new.

        No resubscribe triggered if the wallet is already tracked by other users.
        """
        was_new = wallet not in self._wallet_to_user_ids
        self._wallet_to_user_ids.setdefault(wallet, set()).add(user_id)

        if was_new and helius_client.is_connected():
            _logger.info(
                "[SUBSCRIBE] wallet=%s...%s added. Total wallets: %d.",
                wallet[:4], wallet[-4:], len(self._wallet_to_user_ids),
            )
            await helius_client.resubscribe(self._get_subscribed_wallets())

    async def remove_wallet_for_user(
        self,
        wallet: str,
        user_id: str,
        helius_client: HeliusWsClient,
    ) -> None:
        """Removes a user from a wallet and unsubscribes if no users remain.

        Idempotent: no-op if wallet or user_id is unknown.
        """
        if wallet not in self._wallet_to_user_ids:
            return

        self._wallet_to_user_ids[wallet].discard(user_id)

        if not self._wallet_to_user_ids[wallet]:
            del self._wallet_to_user_ids[wallet]
            _logger.info(
                "[UNSUBSCRIBE] wallet=%s...%s — no active users remain. Total wallets: %d.",
                wallet[:4], wallet[-4:], len(self._wallet_to_user_ids),
            )
            if helius_client.is_connected():
                await helius_client.resubscribe(self._get_subscribed_wallets())

    async def sync(
        self,
        desired: dict[str, set[str]],
        helius_client: HeliusWsClient,
    ) -> None:
        """Full re-sync from the backend snapshot.

        Called by refresh_loop (60s fallback) and on WebSocket reconnect.
        Resubscribes on Helius only if the wallet set has changed.
        """
        desired_wallets = set(desired.keys())
        current_wallets = self._get_subscribed_wallets()

        wallets_changed = desired_wallets != current_wallets
        self._wallet_to_user_ids = {w: set(uids) for w, uids in desired.items()}

        if not wallets_changed:
            return

        added = desired_wallets - current_wallets
        removed = current_wallets - desired_wallets
        _logger.info(
            "Sync subscriptions (fallback): +%d wallet(s) / -%d wallet(s). Total: %d.",
            len(added), len(removed), len(desired_wallets),
        )

        if helius_client.is_connected():
            await helius_client.resubscribe(desired_wallets)

    def get_subscribed_wallets(self) -> set[str]:
        return self._get_subscribed_wallets()

    def clear(self) -> None:
        """Resets local state — called on WebSocket reconnect."""
        self._wallet_to_user_ids.clear()

    def _get_subscribed_wallets(self) -> set[str]:
        return set(self._wallet_to_user_ids.keys())
