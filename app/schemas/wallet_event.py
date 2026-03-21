from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class WalletEvent:
    """Normalized swap event extracted from a raw Helius Enhanced Transaction.

    entry_price: SOL per token, computed from tokenTransfers. None if data is insufficient.
    market_cap:  always None at this stage — provided later by zekiel-market-stream.
    token_symbol: from the Helius `symbol` field if present, None otherwise.
    """

    wallet_address: str
    signature: str
    token_address: str
    token_symbol: str | None
    entry_price: float | None
    market_cap: float | None
    timestamp: datetime
    raw_type: str
