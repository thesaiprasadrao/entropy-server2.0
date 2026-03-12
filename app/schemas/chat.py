from typing import Optional
from pydantic import BaseModel


class ChatRequest(BaseModel):
    username: str   # team name
    message: str


class ChatResponse(BaseModel):
    response: str
    level_id: int
    input_tokens_approx: int
    memory_used: Optional[int] = None    # number of complete exchange pairs in history
    memory_limit: Optional[int] = None  # max exchange pairs allowed (None = stateless)
