"""
Hints router — AI-generated hints for hard levels only.

Rules:
- Only levels with hint_policy = 'ai' in levels.yaml can serve hints.
- Max 5 hints per user per level.
- 2-minute cooldown between hints for the same user/level.
"""

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.level import Level
from app.models.user import User
from app.models.user_hint import UserHint
from app.services.hint_generator import generate_hint
from app.middleware.auth import verify_ctfd_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hints", tags=["hints"])

MAX_HINTS_PER_LEVEL = 5
HINT_COOLDOWN_SECONDS = 120  # 2 minutes


class HintRequest(BaseModel):
    username: str
    level_id: int


class HintResponse(BaseModel):
    hint: str
    hints_remaining: int


@router.post("", response_model=HintResponse, summary="Get an AI hint for a hard level")
def get_hint(
    body: HintRequest,
    request: Request,
    db: Session = Depends(get_db),
    auth_username: str = Depends(verify_ctfd_session),
) -> HintResponse:
    # Enforce authenticated identity — ignore body.username, use verified session
    username = auth_username

    # 1. Level must exist
    level = db.query(Level).filter(Level.id == body.level_id).first()
    if level is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Level not found"
        )

    # 2. Only levels with hint_policy = 'ai' support hints
    hint_policy = getattr(level, "hint_policy", None)
    if hint_policy != "ai":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Hints are not available for this level.",
        )

    # 3. User must exist
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Open the level first via POST /levels/{level_id}/open",
        )

    # 4. Look up (or create) user hint record
    hint_record = (
        db.query(UserHint)
        .filter(UserHint.user_id == username, UserHint.level_id == body.level_id)
        .first()
    )
    if hint_record is None:
        hint_record = UserHint(
            user_id=username,
            level_id=body.level_id,
            hint_count=0,
            last_hint_time=None,
        )
        db.add(hint_record)
        db.flush()

    # 5. Enforce max hints
    if hint_record.hint_count >= MAX_HINTS_PER_LEVEL:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"You have used all {MAX_HINTS_PER_LEVEL} hints for this level.",
        )

    # 6. Enforce cooldown
    if hint_record.last_hint_time is not None:
        now = datetime.now(timezone.utc)
        last = hint_record.last_hint_time.replace(tzinfo=timezone.utc)
        elapsed = (now - last).total_seconds()
        if elapsed < HINT_COOLDOWN_SECONDS:
            retry_in = int(HINT_COOLDOWN_SECONDS - elapsed)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Hint cooldown active. Retry in {retry_in}s.",
                headers={"Retry-After": str(retry_in)},
            )

    # 7. Generate hint via AI (flag/secret is NOT passed)
    try:
        hint_text = generate_hint(
            level_name=level.name,
            level_description=level.description,
            difficulty="hard",
        )
    except Exception as exc:
        logger.error("Hint generation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not generate hint. Try again.",
        )

    # 8. Record the hint usage
    hint_record.hint_count += 1
    hint_record.last_hint_time = datetime.utcnow()
    db.commit()

    hints_remaining = MAX_HINTS_PER_LEVEL - hint_record.hint_count
    logger.info(
        "Hint generated: user=%s level=%s count=%s",
        username,
        body.level_id,
        hint_record.hint_count,
    )
    return HintResponse(hint=hint_text, hints_remaining=hints_remaining)
