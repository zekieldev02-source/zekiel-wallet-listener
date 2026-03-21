import logging

import httpx

from app.core.config import settings

_logger = logging.getLogger(__name__)

_TIMEOUT = 8.0


async def fetch_enhanced_transaction(signature: str) -> dict | None:
    """Fetches the Helius Enhanced Transaction for a given signature.

    The WebSocket sends raw Solana format only (slot, signature, transactionIndex).
    This REST call enriches it with type, feePayer, and tokenTransfers.
    Returns the Enhanced Transaction dict or None on error/not found.
    """
    url = settings.helius_enhanced_tx_url
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(url, json={"transactions": [signature]})

        if resp.status_code != 200:
            _logger.warning(
                "Helius Enhanced Transactions API: status %s for sig=%s",
                resp.status_code,
                signature[:16],
            )
            return None

        results: list = resp.json()
        if not results:
            _logger.debug("Helius Enhanced Transactions: no result for sig=%s", signature[:16])
            return None

        return results[0]

    except httpx.RequestError as exc:
        _logger.warning("Helius Enhanced Transactions request error: %s", exc)
        return None
