from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from sqlalchemy import func
from fastapi import Depends

from app.database import get_db
from app.models.user import User
from app.models.user_level_state import UserLevelState
from app.schemas.leaderboard import LeaderboardEntry
from app.middleware.auth import verify_ctfd_session

router = APIRouter(prefix="/leaderboard", tags=["leaderboard"])


@router.get(
    "",
    response_model=list[LeaderboardEntry],
    summary="Get leaderboard — sorted by solved count desc, last solve time asc",
)
def get_leaderboard(
    db: Session = Depends(get_db),
    _auth: str = Depends(verify_ctfd_session),
) -> list[LeaderboardEntry]:
    """
    Returns all users who have solved at least one level,
    sorted by: most solved first, then earliest last solve time.
    """
    rows = (
        db.query(
            User.username,
            func.count(UserLevelState.id).label("solved_count"),
            func.max(UserLevelState.updated_at).label("last_solved_at"),
        )
        .join(UserLevelState, UserLevelState.user_id == User.id)
        .filter(UserLevelState.solved == True)
        .group_by(User.id, User.username)
        .order_by(
            func.count(UserLevelState.id).desc(),
            func.max(UserLevelState.updated_at).asc(),
        )
        .all()
    )

    return [
        LeaderboardEntry(
            username=row.username,
            solved_count=row.solved_count,
            last_solved_at=row.last_solved_at,
        )
        for row in rows
    ]
