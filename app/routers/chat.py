from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.level import Level
from app.models.user import User
from app.models.user_level_state import UserLevelState
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.llm_client import send_prompt, _approx_token_count
from app.middleware.rate_limiter import check_rate_limit

router = APIRouter(prefix="/levels", tags=["chat"])


@router.post(
    "/{level_id}/chat",
    response_model=ChatResponse,
    summary="Send a prompt to the LLM for this level — secret is injected into system prompt",
)
def chat(
    level_id: int,
    body: ChatRequest,
    db: Session = Depends(get_db),
) -> ChatResponse:
    # 0. Rate limit — must be first, before any DB work
    check_rate_limit(body.ctfd_user_id)

    # 1. Level must exist
    level = db.query(Level).filter(Level.id == level_id).first()
    if level is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Level {level_id} not found",
        )

    # 2. User must exist (must have called /open first)
    user = db.query(User).filter(User.ctfd_user_id == body.ctfd_user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Open the level first via POST /levels/{level_id}/open",
        )

    # 3. User must have a secret for this level
    state = (
        db.query(UserLevelState)
        .filter(
            UserLevelState.user_id == user.id,
            UserLevelState.level_id == level_id,
        )
        .first()
    )
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Open the level first via POST /levels/{level_id}/open",
        )

    # 4. Send to LLM (token guard + key rotation inside send_prompt)
    llm_response = send_prompt(
        user_message=body.message,
        level_system_prompt=level.system_prompt,
        secret_key=state.secret_key,
    )

    return ChatResponse(
        response=llm_response,
        level_id=level_id,
        input_tokens_approx=_approx_token_count(body.message),
    )
