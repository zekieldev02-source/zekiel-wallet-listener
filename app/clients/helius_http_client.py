import asyncio
import logging

import httpx

from app.core.config import settings

_logger = logging.getLogger(__name__)

_TIMEOUT = 8.0
_client = httpx.AsyncClient(timeout=_TIMEOUT)

_semaphore: asyncio.Semaphore | None = None

_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(2)
    return _semaphore


async def fetch_enhanced_transaction(signature: str) -> dict | None:
    url = settings.helius_enhanced_tx_url
    async with _get_semaphore():
        for attempt in range(_MAX_RETRIES):
            try:
                resp = await _client.post(url, json={"transactions": [signature]})

                if resp.status_code == 429:
                    wait = _RETRY_BASE_DELAY * (2 ** attempt)
                    _logger.warning(
                        "Helius rate limited for sig=%s — retry %d/%d in %.1fs",
                        signature[:16], attempt + 1, _MAX_RETRIES, wait,
                    )
                    await asyncio.sleep(wait)
                    continue

                if resp.status_code != 200:
                    _logger.warning(
                        "Helius Enhanced Transactions API: status %s for sig=%s — body: %s",
                        resp.status_code,
                        signature[:16],
                        resp.text[:200],
                    )
                    return None

                results: list = resp.json()
                if not results:
                    _logger.warning(
                        "Helius Enhanced Transactions API: empty result for sig=%s",
                        signature[:16],
                    )
                    return None

                return results[0]

            except httpx.RequestError as exc:
                _logger.warning("Helius Enhanced Transactions request error: %s", exc)
                return None

        _logger.warning(
            "Helius Enhanced Transactions: all %d retries exhausted for sig=%s",
            _MAX_RETRIES, signature[:16],
        )
        return None
