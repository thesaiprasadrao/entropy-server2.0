import secrets
import string

from sqlalchemy.orm import Session

from app.models.user_level_state import UserLevelState
from app.models.user import User
from app.models.level import Level


_SECRET_ALPHABET = string.ascii_letters + string.digits
_SECRET_LENGTH = 6


def _generate_random_secret() -> str:
    """Fallback: cryptographically random 6-character alphanumeric secret."""
    return "".join(secrets.choice(_SECRET_ALPHABET) for _ in range(_SECRET_LENGTH))


def _pick_flag(level: Level) -> str:
    """
    Pick a flag for this user from the level's flag_pool.
    Falls back to a random secret if the pool is empty or not configured.
    """
    if level.flag_pool:
        pool = [f.strip() for f in level.flag_pool.split(",") if f.strip()]
        if pool:
            return secrets.choice(pool)
    return _generate_random_secret()


def get_or_create_user(db: Session, ctfd_user_id: int, username: str) -> User:
    """Fetch an existing User or create a new one for the given ctfd_user_id."""
    user = db.query(User).filter(User.ctfd_user_id == ctfd_user_id).first()
    if user is None:
        user = User(ctfd_user_id=ctfd_user_id, username=username)
        db.add(user)
        db.flush()
    return user


def get_or_create_user_level_state(
    db: Session,
    ctfd_user_id: int,
    username: str,
    level_id: int,
) -> UserLevelState:
    """
    Return the existing UserLevelState for this (user, level) pair.
    If one does not exist, pick a flag from the level's pool and persist.

    Flag value = the picked flag (exact match required on submission).
    secret_key = same as flag_value for display purposes.
    """
    user = get_or_create_user(db, ctfd_user_id, username)

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
        flag = _pick_flag(level) if level else _generate_random_secret()
        state = UserLevelState(
            user_id=user.id,
            level_id=level_id,
            secret_key=flag,
            flag_value=flag,
        )
        db.add(state)

    db.commit()
    db.refresh(state)
    return state
