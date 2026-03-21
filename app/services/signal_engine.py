import logging
from datetime import datetime, timezone

from app.core.constants import SIGNAL_SOURCE
from app.schemas.active_user import ActiveUser
from app.schemas.internal_buy_signal import InternalBuySignal
from app.schemas.wallet_event import WalletEvent

_logger = logging.getLogger(__name__)


def evaluate(
    event: WalletEvent,
    wallet_to_users: dict[str, list[ActiveUser]],
) -> list[InternalBuySignal]:
    """Returns one InternalBuySignal per active user following the event's wallet.

    Skips events with missing/zero entry_price or no active users on the wallet.
    One wallet followed by N users produces N distinct signals.
    """
    if event.entry_price is None or event.entry_price <= 0:
        _logger.debug(
            "Signal skipped (missing entry_price): wallet=%s token=%s sig=%s",
            event.wallet_address[:8],
            event.token_address[:8],
            event.signature[:12],
        )
        return []

    users = wallet_to_users.get(event.wallet_address, [])
    if not users:
        _logger.debug(
            "Signal skipped (no active user): wallet=%s",
            event.wallet_address[:8],
        )
        return []

    signals: list[InternalBuySignal] = []
    timestamp = event.timestamp or datetime.now(tz=timezone.utc)

    for user in users:
        signal = InternalBuySignal(
            user_id=user.user_id,
            wallet_address=event.wallet_address,
            token_address=event.token_address,
            token_symbol=event.token_symbol,
            entry_price=event.entry_price,
            market_cap=event.market_cap,
            source=SIGNAL_SOURCE,
            timestamp=timestamp,
        )
        signals.append(signal)
        _logger.debug(
            "Signal generated: user=%s token=%s price=%.10f",
            user.user_id,
            event.token_address[:8],
            event.entry_price,
        )

    return signals
