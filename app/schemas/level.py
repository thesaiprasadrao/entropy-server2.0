from pydantic import BaseModel, Field


class OpenLevelRequest(BaseModel):
    username: str = Field(max_length=128)  # team name — looked up in users table


class OpenLevelResponse(BaseModel):
    user_id: str
    level_id: int
    attempts: int
    solved: bool
    memory_used: int | None = None


class SubmitFlagRequest(BaseModel):
    username: str = Field(max_length=128)  # team name
    submitted_flag: str = Field(max_length=256)


class SubmitFlagResponse(BaseModel):
    correct: bool
    attempts: int
    solved: bool
    message: str
