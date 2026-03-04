"""
In-memory per-user rate limiter.

Rule: 1 request every 5 seconds per ctfd_user_id.

Implementation:
- Dict {ctfd_user_id: last_allowed_timestamp}
- Protected by threading.Lock (uvicorn sync workers share process memory)
- FastAPI Dependency: raises HTTP 429 if cooldown has not elapsed

No Redis / external store — acceptable for single-process event scale (~100 users).
"""
import threading
import time

from fastapi import HTTPException, Request, status

RATE_LIMIT_SECONDS = 5

_lock = threading.Lock()
_last_request: dict[int, float] = {}  # {ctfd_user_id: unix timestamp}


def check_rate_limit(ctfd_user_id: int) -> None:
    """
    Raise HTTP 429 if the user made a request within the last RATE_LIMIT_SECONDS.
    Otherwise, record the current timestamp and allow the request through.
    """
    now = time.monotonic()
    with _lock:
        last = _last_request.get(ctfd_user_id, 0.0)
        elapsed = now - last
        if elapsed < RATE_LIMIT_SECONDS:
            retry_after = RATE_LIMIT_SECONDS - elapsed
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Rate limit: 1 request every {RATE_LIMIT_SECONDS}s. "
                    f"Retry in {retry_after:.1f}s."
                ),
                headers={"Retry-After": str(int(retry_after) + 1)},
            )
        _last_request[ctfd_user_id] = now
