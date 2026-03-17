import json
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.level import Level
from app.models.user import User
from app.models.user_level_state import UserLevelState
from app.schemas.chat import ChatRequest, ChatResponse, ChatHistoryResponse, ChatHistoryMessage
from app.services.llm_client import send_prompt, _approx_token_count
from app.middleware.rate_limiter import check_rate_limit
from app.middleware.auth import verify_ctfd_session
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
    request: Request,
    db: Session = Depends(get_db),
    auth_username: str = Depends(verify_ctfd_session),
) -> ChatResponse:
    # 0. Enforce authenticated identity — ignore body.username, use verified session
    username = auth_username

    # 0b. Rate limit by IP.
    # X-Real-IP is set by Nginx (proxy_set_header X-Real-IP $remote_addr) and
    # overwrites any client-supplied value, so it is safe to trust here.
    # Falls back to the direct TCP peer (only reachable inside Docker network).
    client_ip = request.headers.get("X-Real-IP") or (
        request.client.host if request.client else "unknown"
    )
    check_rate_limit(client_ip)

    if get_state("pause_ai") == "true":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI temporarily paused",
        )

    # 1. Level must exist
    level = db.query(Level).filter(Level.id == level_id).first()
    if level is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Level {level_id} not found",
        )

    # 2. User must exist (must have called /open first)
    user = db.query(User).filter(User.username == username).first()
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

        # Sanitize: only allow 'user' and 'assistant' roles to prevent a
        # stored 'system' role from injecting a second system prompt into the LLM.
        ALLOWED_ROLES = {"user", "assistant"}
        history = [
            msg
            for msg in history
            if isinstance(msg, dict)
            and msg.get("role") in ALLOWED_ROLES
            and isinstance(msg.get("content"), str)
        ]

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

@router.get(
    "/{level_id}/history",
    response_model=ChatHistoryResponse,
    summary="Get active chat history for a level",
)
def get_chat_history(
    level_id: int,
    request: Request,
    db: Session = Depends(get_db),
    auth_username: str = Depends(verify_ctfd_session),
) -> ChatHistoryResponse:
    user = db.query(User).filter(User.username == auth_username).first()
    if not user:
        return ChatHistoryResponse(messages=[])
        
    state = (
        db.query(UserLevelState)
        .filter(
            UserLevelState.user_id == user.id,
            UserLevelState.level_id == level_id,
        )
        .first()
    )
    
    if not state or not state.chat_history:
        return ChatHistoryResponse(messages=[])

    history = json.loads(state.chat_history)
    messages = []
    
    for msg in history:
        if isinstance(msg, dict) and msg.get("role") in {"user", "assistant"}:
            messages.append(ChatHistoryMessage(
                role=msg.get("role"),
                content=msg.get("content", "")
            ))
            
    return ChatHistoryResponse(messages=messages)
