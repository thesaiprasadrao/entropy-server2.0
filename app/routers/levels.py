from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.models.level import Level
from app.schemas.level import (
    OpenLevelRequest,
    OpenLevelResponse,
    SubmitFlagRequest,
    SubmitFlagResponse,
)
from app.services.flag_service import get_or_create_user_level_state, validate_flag

router = APIRouter(prefix="/levels", tags=["levels"])


class LevelInfo(BaseModel):
    id: int
    name: str
    description: str
    ctfd_challenge_id: int | None = None
    difficulty: str | None = None
    memory_limit: int | None = None
    token_limit: int | None = None


@router.get("/list", response_model=list[LevelInfo], summary="List all available levels")
def list_levels(db: Session = Depends(get_db)) -> list[LevelInfo]:
    levels = db.query(Level).order_by(Level.id).all()
    return [
        LevelInfo(
            id=l.id,
            name=l.name,
            description=l.description or "",
            ctfd_challenge_id=l.ctfd_challenge_id,
            difficulty=l.difficulty,
            memory_limit=l.memory_limit,
            token_limit=l.token_limit,
        )
        for l in levels
    ]



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
        username=body.username,
        level_id=level_id,
    )

    return OpenLevelResponse(
        user_id=str(state.user_id),
        level_id=state.level_id,
        flag_value=state.flag_value,
        attempts=state.attempts,
        solved=state.solved,
    )


@router.post(
    "/{level_id}/submit",
    response_model=SubmitFlagResponse,
    summary="Submit a flag for validation — increments attempts, marks solved on correct flag",
)
def submit_flag(
    level_id: int,
    body: SubmitFlagRequest,
    db: Session = Depends(get_db),
) -> SubmitFlagResponse:
    # Verify the level exists
    level = db.query(Level).filter(Level.id == level_id).first()
    if level is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Level {level_id} not found",
        )

    result = validate_flag(
        db=db,
        username=body.username,
        level_id=level_id,
        submitted_flag=body.submitted_flag,
    )

    return SubmitFlagResponse(**result)
