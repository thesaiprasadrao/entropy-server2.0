from pydantic import BaseModel


class ChatRequest(BaseModel):
    ctfd_user_id: int
    message: str


class ChatResponse(BaseModel):
    response: str
    level_id: int
    input_tokens_approx: int
