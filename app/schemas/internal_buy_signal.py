import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class InternalBuySignal:
    """Normalized buy signal ready to be sent to the backend via POST /internal/signals/buy."""

    user_id: uuid.UUID
    wallet_address: str
    token_address: str
    token_symbol: str | None
    entry_price: float
    market_cap: float | None
    source: str
    timestamp: datetime

    def to_payload(self) -> dict:
        return {
            "user_id": str(self.user_id),
            "wallet_address": self.wallet_address,
            "token_address": self.token_address,
            "token_symbol": self.token_symbol,
            "entry_price": self.entry_price,
            "market_cap": self.market_cap,
            "source": self.source,
            "timestamp": self.timestamp.isoformat(),
        }
