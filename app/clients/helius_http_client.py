import asyncio
import logging

import httpx

from app.core.config import settings

_logger = logging.getLogger(__name__)

_TIMEOUT = 8.0
_client = httpx.AsyncClient(timeout=_TIMEOUT)

_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(5)
    return _semaphore


async def fetch_enhanced_transaction(signature: str) -> dict | None:
    url = settings.helius_enhanced_tx_url
    async with _get_semaphore():
        try:
            resp = await _client.post(url, json={"transactions": [signature]})

            if resp.status_code != 200:
                _logger.warning(
                    "Helius Enhanced Transactions API: status %s for sig=%s",
                    resp.status_code,
                    signature[:16],
                )
                return None

            results: list = resp.json()
            if not results:
                return None

            return results[0]

        except httpx.RequestError as exc:
            _logger.warning("Helius Enhanced Transactions request error: %s", exc)
            return None
