"""DexScreener client for token enrichment at buy time.

Called once per buy signal to retrieve token_symbol and market_cap.
No API key required (public API).
"""

import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

import httpx

_logger = logging.getLogger(__name__)

_BASE_URL = "https://api.dexscreener.com"
_TIMEOUT = 5.0


@dataclass(frozen=True)
class TokenInfo:
    symbol: str | None
    market_cap: float | None


async def get_token_info(token_address: str) -> TokenInfo:
    """Fetches token symbol and market cap from DexScreener.

    Returns TokenInfo with None fields if the token is not found or the request fails.
    """
    try:
        async with httpx.AsyncClient(base_url=_BASE_URL, timeout=_TIMEOUT) as client:
            resp = await client.get(f"/latest/dex/tokens/{token_address}")
            resp.raise_for_status()
            pairs: list[dict] = resp.json().get("pairs") or []
    except Exception as exc:
        _logger.warning("DexScreener request failed for %s: %s", token_address[:8], exc)
        return TokenInfo(symbol=None, market_cap=None)

    token_lower = token_address.lower()
    solana_pairs = [
        p for p in pairs
        if p.get("chainId") == "solana"
        and (p.get("baseToken") or {}).get("address", "").lower() == token_lower
    ]

    if not solana_pairs:
        _logger.warning("DexScreener: no Solana pair found for %s", token_address[:8])
        return TokenInfo(symbol=None, market_cap=None)

    best = max(
        solana_pairs,
        key=lambda p: float((p.get("liquidity") or {}).get("usd") or 0),
    )

    symbol: str | None = (best.get("baseToken") or {}).get("symbol") or None

    mc_raw = best.get("marketCap") or best.get("fdv")
    market_cap: float | None = None
    if mc_raw is not None:
        try:
            market_cap = float(Decimal(str(mc_raw)))
        except (InvalidOperation, TypeError):
            pass

    return TokenInfo(symbol=symbol, market_cap=market_cap)
