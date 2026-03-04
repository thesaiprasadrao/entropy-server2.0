import secrets
import string

from sqlalchemy.orm import Session

from app.models.user_level_state import UserLevelState
from app.models.user import User


_SECRET_ALPHABET = string.ascii_letters + string.digits
_SECRET_LENGTH = 6


def generate_secret() -> str:
    """Return a cryptographically random 6-character alphanumeric secret."""
    return "".join(secrets.choice(_SECRET_ALPHABET) for _ in range(_SECRET_LENGTH))


def get_or_create_user(db: Session, ctfd_user_id: int, username: str) -> User:
    """Fetch an existing User or create a new one for the given ctfd_user_id."""
    user = db.query(User).filter(User.ctfd_user_id == ctfd_user_id).first()
    if user is None:
        user = User(ctfd_user_id=ctfd_user_id, username=username)
        db.add(user)
        db.flush()  # assign user.id without committing
    return user


def get_or_create_user_level_state(
    db: Session,
    ctfd_user_id: int,
    username: str,
    level_id: int,
) -> UserLevelState:
    """
    Return the existing UserLevelState for this (user, level) pair.
    If one does not exist, generate a unique secret, build the flag, and persist.

    Flag format: <secret_key>_<level_id>   e.g. kx92aL_1
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
        secret_key = generate_secret()
        flag_value = f"{secret_key}_{level_id}"
        state = UserLevelState(
            user_id=user.id,
            level_id=level_id,
            secret_key=secret_key,
            flag_value=flag_value,
        )
        db.add(state)

    db.commit()
    db.refresh(state)
    return state
