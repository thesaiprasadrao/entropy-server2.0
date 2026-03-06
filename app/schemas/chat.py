from pydantic import BaseModel


class ChatRequest(BaseModel):
    username: str   # team name
    message: str


class ChatResponse(BaseModel):
    response: str
    level_id: int
    input_tokens_approx: int
