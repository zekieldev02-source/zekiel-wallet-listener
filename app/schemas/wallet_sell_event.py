from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class WalletSellEvent:
    """Normalized sell event: tracked wallet sent a token and received SOL."""

    wallet_address: str
    signature: str
    token_address: str
    token_symbol: str | None
    timestamp: datetime
