import threading
import time
from sqlalchemy.orm import Session

from app.models.admin_state import AdminState
from app.database import SessionLocal

# Short TTL cache to avoid hitting the DB on every HTTP request from the
# global_shutdown middleware. State changes are visible within 5 seconds.
_cache_lock = threading.Lock()
_state_cache: dict[str, tuple[str | None, float]] = {}  # {key: (value, expires_at)}
_CACHE_TTL = 5  # seconds


def get_state(key: str) -> str | None:
    """Return a global admin state value, cached for up to _CACHE_TTL seconds."""
    now = time.monotonic()
    with _cache_lock:
        cached = _state_cache.get(key)
        if cached is not None and cached[1] > now:
            return cached[0]

    with SessionLocal() as db:
        record = db.query(AdminState).filter(AdminState.key == key).first()
        value = record.value if record else None

    with _cache_lock:
        _state_cache[key] = (value, now + _CACHE_TTL)

    return value


def set_state(key: str, value: str) -> None:
    """Set a global admin state value and invalidate the local cache entry."""
    with SessionLocal() as db:
        record = db.query(AdminState).filter(AdminState.key == key).first()
        if record:
            record.value = value
        else:
            record = AdminState(key=key, value=value)
            db.add(record)
        db.commit()

    # Invalidate cache so callers see the new value within one TTL cycle
    with _cache_lock:
        _state_cache.pop(key, None)
