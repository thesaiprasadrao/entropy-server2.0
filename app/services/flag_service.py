import secrets
import string
import hashlib

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.user_level_state import UserLevelState
from app.models.user import User
from app.models.level import Level
from app.config import get_settings


_FLAG_ALPHABET = string.ascii_letters + string.digits


def _generate_random_flag() -> str:
    return "".join(secrets.choice(_FLAG_ALPHABET) for _ in range(6))


def _stable_id_from_name(username: str) -> int:
    """Derive a stable positive int from a team name, within Postgres INTEGER range."""
    h = hashlib.sha256(username.lower().strip().encode()).hexdigest()
    return int(h[:8], 16) % (2**31)  # clamp to signed 32-bit max


def get_or_create_user(db: Session, username: str) -> User:
    """
    Look up a user by username (team name).
    - If pre-seeded: return the existing row.
    - If not found and dev mode (ALLOW_UNKNOWN_TEAMS=true): auto-create.
    - If not found and event mode (ALLOW_UNKNOWN_TEAMS=false): raise 403.
    """
    user = db.query(User).filter(User.username == username).first()
    if user:
        return user

    # Not pre-seeded
    allow = getattr(get_settings(), "ALLOW_UNKNOWN_TEAMS", True)
    if not allow:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Team '{username}' is not registered. Contact the organiser.",
        )

    # Dev / open mode — auto-create with hash-based ID
    ctf_user_id = _stable_id_from_name(username)
    user = User(ctf_user_id=ctf_user_id, username=username)
    db.add(user)
    db.flush()
    return user


def _get_unique_flag(db: Session, level: Level | None, level_id: int) -> str:
    assigned_flags = {
        row[0]
        for row in db.query(UserLevelState.flag_value)
        .filter(UserLevelState.level_id == level_id)
        .all()
    }

    if level and level.flag_pool:
        pool = [f.strip() for f in level.flag_pool.split(",") if f.strip()]
        if pool:
            available_flags = list(set(pool) - assigned_flags)
            if available_flags:
                return secrets.choice(available_flags)
            # If available_flags is empty, it means the pool is exhausted.
            # We naturally fall through to random generation below.

    # Fallback to random generation ensuring uniqueness
    while True:
        flag = _generate_random_flag()
        if flag not in assigned_flags:
            return flag


def get_or_create_user_level_state(
    db: Session,
    username: str,
    level_id: int,
) -> UserLevelState:
    user = get_or_create_user(db, username)

    state = (
        db.query(UserLevelState)
        .filter(
            UserLevelState.user_id == user.id,
            UserLevelState.level_id == level_id,
        )
        .first()
    )

    if state is None:
        level = db.query(Level).filter(Level.id == level_id).first()
        flag = _get_unique_flag(db, level, level_id)

        state = UserLevelState(
            user_id=user.id,
            level_id=level_id,
            flag_value=flag,
            username=username,
        )
        db.add(state)

    db.commit()
    db.refresh(state)
    return state


def validate_flag(
    db: Session,
    username: str,
    level_id: int,
    submitted_flag: str,
) -> dict:
    """Validate a submitted flag for a given user and level."""
    import hmac

    user = db.query(User).filter(User.username == username).first()
    if user is None:
        return {
            "correct": False,
            "attempts": 0,
            "solved": False,
            "message": "User has not opened this level yet.",
        }

    state = (
        db.query(UserLevelState)
        .filter(
            UserLevelState.user_id == user.id,
            UserLevelState.level_id == level_id,
        )
        .first()
    )

    if state is None:
        return {
            "correct": False,
            "attempts": 0,
            "solved": False,
            "message": "User has not opened this level yet.",
        }

    # Increment attempts regardless of correctness
    state.attempts = (state.attempts or 0) + 1
    state.updated_at = func.now()

    correct = hmac.compare_digest(
        submitted_flag.strip().lower(), state.flag_value.strip().lower()
    )

    if correct and not state.solved:
        state.solved = True

    db.commit()
    db.refresh(state)

    return {
        "correct": correct,
        "attempts": state.attempts,
        "solved": state.solved,
        "message": "Flag accepted!" if correct else "Incorrect flag.",
    }
