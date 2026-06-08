import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class InternalSellSignal:
    """Sell signal sent to the backend when the tracked wallet sells a token."""

    user_id: uuid.UUID
    wallet_address: str
    token_address: str
    source: str
    timestamp: datetime

    def to_payload(self) -> dict:
        return {
            "user_id": str(self.user_id),
            "wallet_address": self.wallet_address,
            "token_address": self.token_address,
            "source": self.source,
            "timestamp": self.timestamp.isoformat(),
        }
