"""add difficulty memory_limit token_limit to levels and chat_history to user_level_state

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-13 02:56:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # Add difficulty, memory_limit, token_limit to levels table
    conn.execute(text(
        "ALTER TABLE levels ADD COLUMN IF NOT EXISTS difficulty VARCHAR(20)"
    ))
    conn.execute(text(
        "ALTER TABLE levels ADD COLUMN IF NOT EXISTS memory_limit INTEGER"
    ))
    conn.execute(text(
        "ALTER TABLE levels ADD COLUMN IF NOT EXISTS token_limit INTEGER"
    ))

    # Add hint_policy if somehow missing (defensive — was added in a previous deployment)
    conn.execute(text(
        "ALTER TABLE levels ADD COLUMN IF NOT EXISTS hint_policy VARCHAR(50)"
    ))

    # Add chat_history to user_level_state (JSON stored as TEXT)
    conn.execute(text(
        "ALTER TABLE user_level_state ADD COLUMN IF NOT EXISTS chat_history TEXT"
    ))


def downgrade() -> None:
    op.drop_column('levels', 'difficulty')
    op.drop_column('levels', 'memory_limit')
    op.drop_column('levels', 'token_limit')
    op.drop_column('user_level_state', 'chat_history')
