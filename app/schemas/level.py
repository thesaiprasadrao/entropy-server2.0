from pydantic import BaseModel


class OpenLevelRequest(BaseModel):
    ctfd_user_id: int
    username: str


class OpenLevelResponse(BaseModel):
    user_id: str
    level_id: int
    secret_key: str
    flag_value: str
    attempts: int
    solved: bool


class SubmitFlagRequest(BaseModel):
    ctfd_user_id: int
    submitted_flag: str


class SubmitFlagResponse(BaseModel):
    correct: bool
    attempts: int
    solved: bool
    message: str
