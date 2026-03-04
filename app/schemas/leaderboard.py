from pydantic import BaseModel
from datetime import datetime


class LeaderboardEntry(BaseModel):
    username: str
    solved_count: int
    last_solved_at: datetime | None
