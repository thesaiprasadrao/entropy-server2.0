from pydantic import BaseModel


class OpenLevelRequest(BaseModel):
    username: str   # team name — looked up in users table


class OpenLevelResponse(BaseModel):
    user_id: str
    level_id: int
    flag_value: str
    attempts: int
    solved: bool


class SubmitFlagRequest(BaseModel):
    username: str   # team name
    submitted_flag: str


class SubmitFlagResponse(BaseModel):
    correct: bool
    attempts: int
    solved: bool
    message: str
