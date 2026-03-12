from datetime import datetime

from sqlalchemy import Integer, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserHint(Base):
    __tablename__ = "user_hints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    level_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    hint_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_hint_time: Mapped[datetime] = mapped_column(DateTime, nullable=True)
