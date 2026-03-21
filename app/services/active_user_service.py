import logging

from app.clients import backend_client
from app.schemas.active_user import ActiveUser

_logger = logging.getLogger(__name__)


class ActiveUserService:
    """Maintains a local snapshot of active users fetched from the backend.

    Provides wallet_address → users mapping for signal_engine (multi-user multiplexing)
    and wallet_address → user_ids mapping for SubscriptionService.
    """

    def __init__(self) -> None:
        self._active_users: list[ActiveUser] = []

    async def refresh(self) -> None:
        """Fetches active users from the backend and updates the local snapshot.

        Retains the previous snapshot if the backend returns an empty list.
        """
        users = await backend_client.get_active_users()
        if not users and self._active_users:
            _logger.warning(
                "Refresh: backend returned empty list, keeping previous snapshot (%d users).",
                len(self._active_users),
            )
            return

        self._active_users = [u for u in users if u.wallet_address]
        _logger.info(
            "Active users: %d with wallet configured.",
            len(self._active_users),
        )

    def remove_user_by_telegram_id(self, telegram_id: int) -> ActiveUser | None:
        """Removes a user from the local snapshot immediately.

        Returns the removed user or None if not found. Idempotent.
        """
        removed: ActiveUser | None = None
        for user in self._active_users:
            if user.telegram_id == telegram_id:
                removed = user
                break

        if removed is not None:
            self._active_users = [
                u for u in self._active_users if u.telegram_id != telegram_id
            ]
            _logger.debug(
                "[STOPBOT] telegram_id=%d removed from local snapshot.", telegram_id
            )

        return removed

    def get_active_users(self) -> list[ActiveUser]:
        return list(self._active_users)

    def get_wallet_to_users_map(self) -> dict[str, list[ActiveUser]]:
        """Returns wallet_address → [ActiveUser, ...], deduplicated by (wallet, user_id)."""
        mapping: dict[str, list[ActiveUser]] = {}
        seen: set[tuple[str, str]] = set()

        for user in self._active_users:
            key = (user.wallet_address, str(user.user_id))
            if key in seen:
                continue
            seen.add(key)
            mapping.setdefault(user.wallet_address, []).append(user)

        return mapping

    def get_wallet_to_user_ids_map(self) -> dict[str, set[str]]:
        """Returns wallet_address → set[str(user_id)] for SubscriptionService."""
        mapping: dict[str, set[str]] = {}
        seen: set[tuple[str, str]] = set()

        for user in self._active_users:
            key = (user.wallet_address, str(user.user_id))
            if key in seen:
                continue
            seen.add(key)
            mapping.setdefault(user.wallet_address, set()).add(str(user.user_id))

        return mapping

    def get_watched_wallets(self) -> set[str]:
        return {u.wallet_address for u in self._active_users}
