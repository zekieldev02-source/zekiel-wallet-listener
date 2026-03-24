"""Jupiter Price API client — market cap fallback for Pump.fun tokens.

Pump.fun tokens always have a fixed supply of 1,000,000,000.
Jupiter indexes them immediately from the bonding curve.
Market cap = price_usd * 1_000_000_000.
"""

import logging

import httpx

_logger = logging.getLogger(__name__)

_BASE_URL = "https://lite-api.jup.ag"
_TIMEOUT = 5.0
_PUMP_FUN_SUPPLY = 1_000_000_000


def is_pump_fun_token(token_address: str) -> bool:
    return token_address.lower().endswith("pump")


async def get_pump_fun_market_cap(token_address: str) -> float | None:
    """Fetches price from Jupiter and computes market cap for a Pump.fun token.

    Returns None if the token is not found or the request fails.
    Only call this for Pump.fun tokens (address ends with 'pump').
    """
    try:
        async with httpx.AsyncClient(base_url=_BASE_URL, timeout=_TIMEOUT) as client:
            resp = await client.get("/price/v2", params={"ids": token_address})
            resp.raise_for_status()
            data: dict = resp.json()
    except Exception as exc:
        _logger.warning("Jupiter Price API failed for %s: %s", token_address[:8], exc)
        return None

    price_str = (data.get("data") or {}).get(token_address, {}).get("price")
    if not price_str:
        _logger.warning("Jupiter: no price found for %s", token_address[:8])
        return None

    try:
        return float(price_str) * _PUMP_FUN_SUPPLY
    except (TypeError, ValueError):
        return None
