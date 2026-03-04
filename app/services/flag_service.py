from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.user_level_state import UserLevelState
from app.models.user import User


def validate_flag(
    db: Session,
    ctfd_user_id: int,
    level_id: int,
    submitted_flag: str,
) -> dict:
    """
    Validate a submitted flag for a given user and level.

    Flow:
    1. Fetch the user row
    2. Fetch the user_level_state for (user, level)
    3. Increment attempts unconditionally
    4. Compare submitted_flag to stored flag_value (constant-time via secrets.compare_digest)
    5. If correct, mark solved = True

    Returns a dict with: correct, attempts, solved, message
    """
    import hmac  # constant-time string comparison

    user = db.query(User).filter(User.ctfd_user_id == ctfd_user_id).first()
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

    correct = hmac.compare_digest(submitted_flag, state.flag_value)

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
