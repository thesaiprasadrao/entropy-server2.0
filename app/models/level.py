from datetime import datetime
from typing import Optional

from sqlalchemy import Integer, String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Level(Base):
    __tablename__ = "levels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    level_number: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False, default="llama-3.3-70b-versatile", server_default="llama-3.3-70b-versatile")
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    flag_pool: Mapped[str] = mapped_column(Text, nullable=True)  # comma-separated flags
    ctfd_challenge_id: Mapped[int] = mapped_column(Integer, nullable=True)  # CTFd challenge mapping
    hint_policy: Mapped[str] = mapped_column(String(50), nullable=True, default=None)  # 'ai' = AI hints enabled
    difficulty: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, default=None)  # easy/intermediate/hard
    memory_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=None)  # max exchange pairs for hard levels
    min_input_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=None)  # min tokens per prompt
    max_input_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=None)  # max tokens per prompt
    max_output_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=None)  # max tokens per LLM output
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )
