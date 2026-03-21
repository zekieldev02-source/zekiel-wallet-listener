import logging
from datetime import datetime, timezone

from app.core.constants import BUY_EVENT_TYPES, WSOL_MINT
from app.schemas.wallet_event import WalletEvent

_logger = logging.getLogger(__name__)


def parse(raw: dict, watched_wallets: set[str]) -> WalletEvent | None:
    """Returns a WalletEvent or None if the transaction is not a trackable buy.

    Expects Helius Enhanced Transaction format (atlas endpoint, transactionNotification).
    entry_price is computed from tokenTransfers; market_cap is always None here —
    both are enriched later by zekiel-market-stream via Birdeye.
    """
    try:
        return _parse_inner(raw, watched_wallets)
    except Exception:
        _logger.debug("Helius event parse error (ignored): %s", raw.get("signature"))
        return None


def _parse_inner(raw: dict, watched_wallets: set[str]) -> WalletEvent | None:
    event_type = raw.get("type", "")
    if event_type not in BUY_EVENT_TYPES:
        return None

    signature = raw.get("signature", "")
    if not signature:
        return None

    fee_payer: str = raw.get("feePayer", "")
    if fee_payer not in watched_wallets:
        return None

    timestamp_unix = raw.get("timestamp")
    if timestamp_unix:
        event_time = datetime.fromtimestamp(timestamp_unix, tz=timezone.utc)
    else:
        event_time = datetime.now(tz=timezone.utc)

    token_transfers: list[dict] = raw.get("tokenTransfers", [])

    token_received = _find_token_received(fee_payer, token_transfers)
    if token_received is None:
        return None

    token_address: str = token_received.get("mint", "")
    if not token_address or token_address == WSOL_MINT:
        return None

    token_symbol: str | None = token_received.get("symbol") or None
    tokens_received: float = float(token_received.get("tokenAmount", 0))

    native_transfers: list[dict] = raw.get("nativeTransfers", [])
    entry_price = _compute_entry_price(fee_payer, token_transfers, native_transfers, tokens_received)

    return WalletEvent(
        wallet_address=fee_payer,
        signature=signature,
        token_address=token_address,
        token_symbol=token_symbol,
        entry_price=entry_price,
        market_cap=None,
        timestamp=event_time,
        raw_type=event_type,
    )


def _find_token_received(wallet: str, transfers: list[dict]) -> dict | None:
    """Returns the first non-WSOL token received by the wallet (buy-side of the swap)."""
    for t in transfers:
        if t.get("toUserAccount") == wallet and t.get("mint") != WSOL_MINT:
            amount = float(t.get("tokenAmount", 0))
            if amount > 0:
                return t
    return None


_LAMPORTS_PER_SOL = 1_000_000_000


def _compute_entry_price(
    wallet: str,
    token_transfers: list[dict],
    native_transfers: list[dict],
    tokens_received: float,
) -> float | None:
    """Approximates entry price as SOL sent ÷ tokens received.

    Covers WSOL→TOKEN (tokenTransfers) and native SOL→TOKEN (nativeTransfers, lamports).
    Does not cover USDC→TOKEN. Subject to protocol-fee imprecision.
    """
    if tokens_received <= 0:
        return None

    sol_sent: float = 0.0

    for t in token_transfers:
        if t.get("fromUserAccount") == wallet and t.get("mint") == WSOL_MINT:
            sol_sent += float(t.get("tokenAmount", 0))

    for t in native_transfers:
        if t.get("fromUserAccount") == wallet:
            sol_sent += float(t.get("amount", 0)) / _LAMPORTS_PER_SOL

    if sol_sent <= 0:
        return None

    return sol_sent / tokens_received
