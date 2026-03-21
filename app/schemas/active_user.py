import uuid

from pydantic import BaseModel


class ActiveUser(BaseModel):
    user_id: uuid.UUID
    telegram_id: int
    wallet_address: str
    bot_active: bool
    mode: str
