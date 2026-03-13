import json
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.level import Level
from app.models.user import User
from app.models.user_level_state import UserLevelState
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.llm_client import send_prompt, _approx_token_count
from app.middleware.rate_limiter import check_rate_limit
from app.services.admin_state import get_state

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
    check_rate_limit(body.username)

    if get_state("pause_ai") == "true":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI temporarily paused"
        )

    # 1. Level must exist
    level = db.query(Level).filter(Level.id == level_id).first()
    if level is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Level {level_id} not found",
        )

    # 2. User must exist (must have called /open first)
    user = db.query(User).filter(User.username == body.username).first()
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

    # 4. Per-level token limits
    min_input_tokens = level.min_input_tokens
    max_input_tokens = level.max_input_tokens
    max_output_tokens = level.max_output_tokens

    # 5. Build conversation history for hard levels (memory mode)
    memory_limit = level.memory_limit  # None = stateless (easy/intermediate)
    conversation_history = None
    memory_used = None

    if memory_limit is not None:
        # Load stored history (list of {role, content} dicts)
        stored_raw = state.chat_history
        history: list = json.loads(stored_raw) if stored_raw else []

        # Pass the existing history to the LLM (will be trimmed after response)
        conversation_history = list(history)
        memory_used = len(history) // 2  # number of complete exchange pairs

    # 6. Send to LLM (token guard + key rotation inside send_prompt)
    llm_response = send_prompt(
        user_message=body.message,
        level_system_prompt=level.system_prompt,
        flag_value=state.flag_value,
        model=level.model,
        conversation_history=conversation_history,
        min_input_tokens=min_input_tokens,
        max_input_tokens=max_input_tokens,
        max_output_tokens=max_output_tokens,
    )

    # 7. Persist updated history for hard levels
    memory_reset = False
    if memory_limit is not None:
        history.append({"role": "user", "content": body.message})
        history.append({"role": "assistant", "content": llm_response})

        max_messages = memory_limit * 2
        if len(history) >= max_messages:
            history = []
            memory_reset = True

        state.chat_history = json.dumps(history)
        db.commit()
        memory_used = len(history) // 2

    return ChatResponse(
        response=llm_response,
        level_id=level_id,
        input_tokens_approx=_approx_token_count(body.message),
        memory_used=memory_used,
        memory_limit=memory_limit,
        memory_reset=memory_reset,
    )
