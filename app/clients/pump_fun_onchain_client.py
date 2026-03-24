"""Pump.fun on-chain client — real-time market cap via bonding curve.

Reads the Pump.fun bonding curve account directly from Solana via Helius RPC.
Works instantly for any Pump.fun token, even brand new ones (no indexing delay).

Price = virtual_sol_reserves / virtual_token_reserves
Market cap = price_sol * 1_000_000_000 * sol_price_usd
"""

import base64
import logging
import struct
import time

import httpx
from solders.pubkey import Pubkey

from app.core.config import settings

_logger = logging.getLogger(__name__)

_PUMP_PROGRAM = Pubkey.from_string("6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P")
_PUMP_SUPPLY = 1_000_000_000
_SOL_DECIMALS = 1_000_000_000
_TOKEN_DECIMALS = 1_000_000
_TIMEOUT = 5.0

# SOL/USD price cache — refreshed at most every 60s
_sol_price_cache: dict = {"price": None, "updated_at": 0.0}
_SOL_CACHE_TTL = 60.0


async def get_market_cap(token_address: str) -> float | None:
    """Returns the market cap in USD from the Pump.fun bonding curve.

    Returns None if the token is not a Pump.fun token, the account is not found,
    or the bonding curve is already complete (token migrated to Raydium).
    """
    try:
        bonding_curve = _derive_bonding_curve(token_address)
    except Exception as exc:
        _logger.warning("Pump.fun: PDA derivation failed for %s: %s", token_address[:8], exc)
        return None

    data = await _get_account_data(str(bonding_curve))
    if data is None:
        return None

    price_sol = _parse_price(data)
    if price_sol is None:
        _logger.debug("Pump.fun: bonding curve complete or empty for %s", token_address[:8])
        return None

    sol_usd = await _get_sol_price()
    if sol_usd is None:
        return None

    market_cap = price_sol * _PUMP_SUPPLY * sol_usd
    _logger.info("Pump.fun on-chain MC for %s: $%.0f", token_address[:8], market_cap)
    return market_cap


def _derive_bonding_curve(token_address: str) -> Pubkey:
    mint = Pubkey.from_string(token_address)
    bonding_curve, _ = Pubkey.find_program_address(
        [b"bonding-curve", bytes(mint)],
        _PUMP_PROGRAM,
    )
    return bonding_curve


def _parse_price(data: bytes) -> float | None:
    if len(data) < 49:
        return None

    # Anchor discriminator = 8 bytes, then:
    # virtual_token_reserves: u64 @ offset 8
    # virtual_sol_reserves:   u64 @ offset 16
    # complete:               bool @ offset 48
    virtual_token_reserves = struct.unpack_from("<Q", data, 8)[0]
    virtual_sol_reserves = struct.unpack_from("<Q", data, 16)[0]
    complete = struct.unpack_from("?", data, 48)[0]

    if complete or virtual_token_reserves == 0:
        return None

    price_sol = (virtual_sol_reserves / _SOL_DECIMALS) / (virtual_token_reserves / _TOKEN_DECIMALS)
    return price_sol


async def _get_account_data(address: str) -> bytes | None:
    url = f"https://mainnet.helius-rpc.com/?api-key={settings.HELIUS_API_KEY}"
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getAccountInfo",
        "params": [address, {"encoding": "base64"}],
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            result = resp.json().get("result") or {}
            value = result.get("value")
            if not value:
                _logger.info("Pump.fun: bonding curve account not found for %s", address[:8])
                return None
            raw_data = value.get("data", [None])[0]
            if not raw_data:
                return None
            return base64.b64decode(raw_data)
    except Exception as exc:
        _logger.warning("Pump.fun: getAccountInfo failed for %s: %s", address[:8], exc)
        return None


async def _get_sol_price() -> float | None:
    now = time.monotonic()
    if _sol_price_cache["price"] and now - _sol_price_cache["updated_at"] < _SOL_CACHE_TTL:
        return _sol_price_cache["price"]

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                "https://api.binance.com/api/v3/ticker/price",
                params={"symbol": "SOLUSDT"},
            )
            resp.raise_for_status()
            price = float(resp.json()["price"])
            _sol_price_cache["price"] = price
            _sol_price_cache["updated_at"] = now
            return price
    except Exception as exc:
        _logger.warning("SOL price fetch failed: %s", exc)
        return _sol_price_cache.get("price")
