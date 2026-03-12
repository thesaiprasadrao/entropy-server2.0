import uuid
import json
from datetime import datetime
from typing import Optional, List

from sqlalchemy import Integer, String, Boolean, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class UserLevelState(Base):
    __tablename__ = "user_level_state"

    __table_args__ = (
        UniqueConstraint("user_id", "level_id", name="uq_user_level"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    level_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("levels.id", ondelete="CASCADE"),
        nullable=False,
    )
    secret_key: Mapped[str] = mapped_column(String(64), nullable=False)
    flag_value: Mapped[str] = mapped_column(String(128), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    solved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    chat_history: Mapped[Optional[str]] = mapped_column(Text, nullable=True, default=None)  # JSON: list of {role, content}
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )
