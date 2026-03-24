"""Helius DAS client — on-chain token metadata fallback.

Calls getAsset (Metaplex DAS) to retrieve token symbol from on-chain metadata.
Works immediately for any token, including brand new Pump.fun tokens.
No additional API key required — uses the existing HELIUS_API_KEY.
"""

import logging

import httpx

from app.core.config import settings

_logger = logging.getLogger(__name__)

_TIMEOUT = 5.0
_client = httpx.AsyncClient(timeout=_TIMEOUT)


async def get_token_symbol(token_address: str) -> str | None:
    """Fetches the token symbol from Helius DAS (on-chain metadata).

    Returns the symbol string or None on failure.
    """
    url = f"https://mainnet.helius-rpc.com/?api-key={settings.HELIUS_API_KEY}"
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getAsset",
        "params": {"id": token_address},
    }
    try:
        resp = await _client.post(url, json=payload)
        resp.raise_for_status()
        data: dict = resp.json()
    except Exception as exc:
        _logger.warning("Helius getAsset failed for %s: %s", token_address[:8], exc)
        return None

    result = data.get("result") or {}
    symbol: str | None = (
        (result.get("content") or {})
        .get("metadata", {})
        .get("symbol")
    ) or None

    return symbol
