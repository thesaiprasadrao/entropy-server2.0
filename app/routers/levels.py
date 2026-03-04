from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.level import Level
from app.schemas.level import OpenLevelRequest, OpenLevelResponse
from app.services.secret_service import get_or_create_user_level_state

router = APIRouter(prefix="/levels", tags=["levels"])


@router.post(
    "/{level_id}/open",
    response_model=OpenLevelResponse,
    summary="Open a level for a user — generates a unique secret on first call",
)
def open_level(
    level_id: int,
    body: OpenLevelRequest,
    db: Session = Depends(get_db),
) -> OpenLevelResponse:
    # Verify the level exists
    level = db.query(Level).filter(Level.id == level_id).first()
    if level is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Level {level_id} not found",
        )

    state = get_or_create_user_level_state(
        db=db,
        ctfd_user_id=body.ctfd_user_id,
        username=body.username,
        level_id=level_id,
    )

    return OpenLevelResponse(
        user_id=str(state.user_id),
        level_id=state.level_id,
        secret_key=state.secret_key,
        flag_value=state.flag_value,
        attempts=state.attempts,
        solved=state.solved,
    )
