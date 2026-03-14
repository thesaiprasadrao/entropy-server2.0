"""
CTFd session verification dependency.

Extracts and validates the authenticated username from the CTFd session
cookie forwarded by Nginx. Caches verified sessions briefly to avoid
hitting CTFd on every request.
"""

import logging
import time
import threading
from typing import Optional

import httpx
from fastapi import HTTPException, Request, status

logger = logging.getLogger(__name__)

CTFD_INTERNAL_URL = "http://ctfd:8000"
REQUEST_TIMEOUT = 5.0

# Simple TTL cache: {session_cookie_value: (username, expires_at)}
_cache_lock = threading.Lock()
_session_cache: dict[str, tuple[str, float]] = {}
_CACHE_TTL = 60  # seconds


def _get_ctfd_username(cookies: dict) -> Optional[str]:
    """Call CTFd /api/v1/users/me with the user's cookies to get their username."""
    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
            resp = client.get(
                f"{CTFD_INTERNAL_URL}/api/v1/users/me",
                cookies=cookies,
            )
        if resp.status_code != 200:
            return None
        data = resp.json().get("data", {})
        if not data.get("id"):
            return None
        return data.get("name")
    except Exception as exc:
        logger.warning("CTFd session verification failed: %s", exc)
        return None


def verify_ctfd_session(request: Request) -> str:
    """
    FastAPI dependency that verifies the caller is logged into CTFd.
    Returns the authenticated username.
    Raises HTTP 401 if not authenticated.
    """
    cookies = dict(request.cookies)
    session_val = cookies.get("session", "")

    if not session_val:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not logged in. Please log in via CTFd first.",
        )

    # Check cache
    now = time.monotonic()
    with _cache_lock:
        cached = _session_cache.get(session_val)
        if cached and cached[1] > now:
            return cached[0]

    # Verify with CTFd
    username = _get_ctfd_username(cookies)
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired session. Please log in via CTFd.",
        )

    # Cache the result, then evict only expired entries if cache is large.
    # Never clear() the whole dict — that would log out all active users at once.
    with _cache_lock:
        _session_cache[session_val] = (username, now + _CACHE_TTL)

        if len(_session_cache) > 500:
            expired_keys = [k for k, (_, exp) in _session_cache.items() if exp <= now]
            for k in expired_keys:
                del _session_cache[k]

    return username
