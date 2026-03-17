from typing import Optional
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    username: str = Field(max_length=128)  # team name
    message: str = Field(max_length=4096)


class ChatResponse(BaseModel):
    response: str
    level_id: int
    input_tokens_approx: int
    memory_used: Optional[int] = None  # number of complete exchange pairs in history
    memory_limit: Optional[int] = None  # max exchange pairs allowed (None = stateless)
    memory_reset: bool = False

class ChatHistoryMessage(BaseModel):
    role: str
    content: str
    
class ChatHistoryResponse(BaseModel):
    messages: list[ChatHistoryMessage]
