import logging

import httpx

from app.core.config import settings
from app.schemas.active_user import ActiveUser
from app.schemas.internal_buy_signal import InternalBuySignal
from app.schemas.internal_sell_signal import InternalSellSignal

_logger = logging.getLogger(__name__)

_HEADERS = {
    "X-Internal-API-Key": settings.INTERNAL_API_KEY,
    "Content-Type": "application/json",
}


async def get_active_users() -> list[ActiveUser]:
    """Fetches active users from the backend.

    Returns an empty list on network error or unexpected response.
    401 logs a warning (invalid API key — do not retry immediately).
    """
    url = f"{settings.BACKEND_URL}/internal/users/active"
    try:
        async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT_SECONDS) as client:
            resp = await client.get(url, headers=_HEADERS)

            if resp.status_code == 401:
                _logger.warning("Backend: 401 Unauthorized — check INTERNAL_API_KEY.")
                return []

            resp.raise_for_status()
            data = resp.json().get("data", {})
            users_raw = data.get("users", [])
            return [ActiveUser(**u) for u in users_raw]

    except httpx.HTTPStatusError as exc:
        _logger.warning("Backend get_active_users HTTP error: %s", exc.response.status_code)
        return []
    except httpx.RequestError as exc:
        _logger.warning("Backend get_active_users request error: %s", exc)
        return []


async def post_buy_signal(signal: InternalBuySignal) -> bool:
    """Sends a buy signal to the backend.

    Returns True on 202. 409 (duplicate) is silently ignored. 401 is logged.
    """
    url = f"{settings.BACKEND_URL}/internal/signals/buy"
    try:
        async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT_SECONDS) as client:
            resp = await client.post(url, headers=_HEADERS, json=signal.to_payload())

            if resp.status_code == 202:
                return True

            if resp.status_code == 409:
                _logger.debug(
                    "Signal ignored (duplicate): user=%s token=%s",
                    signal.user_id,
                    signal.token_address,
                )
                return False

            if resp.status_code == 401:
                _logger.warning("Backend post_buy_signal: 401 Unauthorized.")
                return False

            _logger.warning(
                "Backend post_buy_signal: unexpected %s for user=%s token=%s",
                resp.status_code,
                signal.user_id,
                signal.token_address,
            )
            return False

    except httpx.RequestError as exc:
        _logger.warning(
            "Backend post_buy_signal request error pour user=%s: %s",
            signal.user_id,
            exc,
        )
        return False


async def post_sell_signal(signal: InternalSellSignal) -> bool:
    """Sends a sell signal to the backend. Returns True on 202."""
    url = f"{settings.BACKEND_URL}/internal/signals/sell"
    try:
        async with httpx.AsyncClient(timeout=settings.HTTP_TIMEOUT_SECONDS) as client:
            resp = await client.post(url, headers=_HEADERS, json=signal.to_payload())

        if resp.status_code == 202:
            return True

        if resp.status_code == 404:
            _logger.debug(
                "Sell signal ignored (no open position): user=%s token=%s",
                signal.user_id, signal.token_address[:8],
            )
            return False

        if resp.status_code == 401:
            _logger.warning("Backend post_sell_signal: 401 Unauthorized.")
            return False

        _logger.warning(
            "Backend post_sell_signal: unexpected %s for user=%s token=%s",
            resp.status_code, signal.user_id, signal.token_address[:8],
        )
        return False

    except httpx.RequestError as exc:
        _logger.warning("Backend post_sell_signal request error: %s", exc)
        return False
